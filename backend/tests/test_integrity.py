"""
Ghajini 2.0 — Memory Integrity Engine Reliability Test Suite
=============================================================
12 tests covering the full integrity policy spec.
All tests are deterministic (no LLM, no network, no FAISS required).
Uses an in-memory SQLite database isolated per test session.
Run from backend/ directory:
  pytest tests/test_integrity.py -v
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.db.models import Patient, MemoryClaim, MemoryConflict, MemoryClaimHistory, Appointment, Reminder
from app.main import app
from app.modules.integrity.engine import (
    evaluate_claim, evaluate_question, detect_and_register_conflicts,
    verify_claim, reject_claim, correct_claim, resolve_conflict,
    DECISION_ANSWER, DECISION_ABSTAIN, DECISION_CONFLICT,
    DECISION_REVIEW_REQUIRED, DECISION_WARN,
)

from sqlalchemy.pool import StaticPool

# ──────────────────────────────────────────────────────────────
# Test DB setup (in-memory, isolated from production data)
# ──────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def test_db(test_engine):
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    # Ensure test patient exists
    patient = db.query(Patient).filter(Patient.id == 1).first()
    if not patient:
        db.add(Patient(id=1, name="Test Patient"))
        db.commit()
    yield db
    db.close()


@pytest.fixture(scope="module")
def api_client(test_engine):
    """FastAPI test client wired to the in-memory test database."""
    TestSession = sessionmaker(bind=test_engine)
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


CAREGIVER_HEADERS = {"X-Demo-Role": "demo-caregiver-2024"}


def make_claim(db, **kwargs) -> MemoryClaim:
    defaults = dict(
        patient_id=1,
        statement="Test claim",
        category="general",
        subject=None,
        property_key=None,
        property_value=None,
        source_type="caregiver_input",
        source_description="Test source",
        author="Test Caregiver",
        integrity_status="unverified",
    )
    defaults.update(kwargs)
    c = MemoryClaim(**defaults)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ──────────────────────────────────────────────────────────────
# Test 1: Verified sourced fact → ANSWER with source
# ──────────────────────────────────────────────────────────────

def test_01_verified_fact_returns_answer(test_db):
    """Verified sourced fact → ANSWER decision."""
    c = make_claim(test_db,
        statement="Priya's phone is 9876543210",
        subject="Priya", property_key="phone", property_value="9876543210",
        integrity_status="verified", verified_by="Caregiver Nisha",
    )
    decision = evaluate_claim(c)
    assert decision["decision"] == DECISION_ANSWER, f"Expected ANSWER, got {decision}"
    assert "VERIFIED" in decision["reason_codes"]
    assert c.id in decision["supporting_claim_ids"]


# ──────────────────────────────────────────────────────────────
# Test 2: Missing fact → ABSTAIN without inventing
# ──────────────────────────────────────────────────────────────

def test_02_missing_fact_abstains(test_db):
    """No matching claims → ABSTAIN."""
    decision = evaluate_question("What is the best friend's secret code?", claims=[], open_conflicts=[])
    assert decision["decision"] == DECISION_ABSTAIN, f"Expected ABSTAIN, got {decision}"
    assert "NO_MATCHING_CLAIMS" in decision["reason_codes"]


# ──────────────────────────────────────────────────────────────
# Test 3: Conflicting claims → CONFLICT, no automatic winner
# ──────────────────────────────────────────────────────────────

def test_03_conflicting_claims_returns_conflict(test_db):
    """Two incompatible claims for same property → CONFLICT."""
    c_a = make_claim(test_db,
        statement="Priya lives in Bangalore",
        subject="Priya", property_key="location", property_value="Bangalore",
        integrity_status="unverified",
    )
    c_b = make_claim(test_db,
        statement="Priya lives in Chennai",
        subject="Priya", property_key="location", property_value="Chennai",
        integrity_status="unverified",
    )
    detect_and_register_conflicts(c_b, test_db)
    test_db.refresh(c_a)
    test_db.refresh(c_b)

    conflict = test_db.query(MemoryConflict).filter(
        MemoryConflict.claim_a_id.in_([c_a.id, c_b.id]) |
        MemoryConflict.claim_b_id.in_([c_a.id, c_b.id])
    ).first()
    assert conflict is not None, "Conflict should have been registered"

    decision = evaluate_question("Where does Priya live?", [c_a, c_b], [conflict])
    assert decision["decision"] == DECISION_CONFLICT, f"Expected CONFLICT, got {decision}"
    assert "CONFLICTING_CLAIMS" in decision["reason_codes"]
    # No automatic winner selected
    assert decision.get("answer") is None


# ──────────────────────────────────────────────────────────────
# Test 4: Expired/review-due fact → WARN, blocked reliance
# ──────────────────────────────────────────────────────────────

def test_04_expired_fact_warns(test_db):
    """Expired claim → WARN, not ANSWER."""
    past = datetime.utcnow() - timedelta(days=10)
    c = make_claim(test_db,
        statement="Dr. Sharma appointment at 09:00",
        subject="Dr. Sharma", property_key="appointment_time", property_value="09:00",
        integrity_status="verified",
        expiry_date=past,
    )
    decision = evaluate_claim(c)
    assert decision["decision"] == DECISION_WARN, f"Expected WARN, got {decision}"
    assert "EXPIRED" in decision["reason_codes"]


def test_04b_review_due_fact_warns(test_db):
    """Past review_due_date claim → WARN."""
    past = datetime.utcnow() - timedelta(days=5)
    c = make_claim(test_db,
        statement="Address is 42 Palm Avenue",
        subject="Patient", property_key="address", property_value="42 Palm Avenue",
        integrity_status="verified",
        review_due_date=past,
    )
    decision = evaluate_claim(c)
    assert decision["decision"] == DECISION_WARN, f"Expected WARN for review-due, got {decision}"
    assert "REVIEW_DUE" in decision["reason_codes"]


# ──────────────────────────────────────────────────────────────
# Test 5: Caregiver correction → new version, old retained
# ──────────────────────────────────────────────────────────────

def test_05_correction_retains_old_version(test_db):
    """Correcting a claim creates new claim; old is marked rejected, not deleted."""
    old = make_claim(test_db,
        statement="Arun lives in Mumbai",
        subject="Arun", property_key="location", property_value="Mumbai",
    )
    old_id = old.id
    new_claim = correct_claim(old, "Arun lives in Bangalore", "Bangalore",
                              "Caregiver Nisha", "Moved in Aug 2024", test_db)
    test_db.refresh(old)
    # Old preserved and rejected
    old_in_db = test_db.get(MemoryClaim, old_id)
    assert old_in_db is not None, "Old claim must not be deleted"
    assert old_in_db.integrity_status == "rejected"
    assert new_claim.supersedes_id == old_id
    assert new_claim.integrity_status == "unverified"
    # Audit history on both
    old_history_actions = [h.action for h in old_in_db.history]
    assert "corrected" in old_history_actions


# ──────────────────────────────────────────────────────────────
# Test 6: Two caregivers disagree → both claims retained, conflict open
# ──────────────────────────────────────────────────────────────

def test_06_caregiver_disagreement_preserved(test_db):
    """Two different caregivers enter conflicting claims → both kept, conflict open."""
    c1 = make_claim(test_db,
        statement="Priya works at Hospital A",
        subject="Priya", property_key="workplace", property_value="Hospital A",
        author="Caregiver Nisha",
    )
    c2 = make_claim(test_db,
        statement="Priya works at Clinic B",
        subject="Priya", property_key="workplace", property_value="Clinic B",
        author="Caregiver Ravi",
    )
    detect_and_register_conflicts(c2, test_db)
    test_db.refresh(c1)
    test_db.refresh(c2)
    conflict = test_db.query(MemoryConflict).filter(
        ((MemoryConflict.claim_a_id == c1.id) & (MemoryConflict.claim_b_id == c2.id)) |
        ((MemoryConflict.claim_a_id == c2.id) & (MemoryConflict.claim_b_id == c1.id))
    ).first()
    assert conflict is not None
    assert conflict.resolution_status == "open"
    # Both claims still in DB
    assert test_db.get(MemoryClaim, c1.id) is not None
    assert test_db.get(MemoryClaim, c2.id) is not None


# ──────────────────────────────────────────────────────────────
# Test 7: Appointment update → stale reminders identified
# ──────────────────────────────────────────────────────────────

def test_07_appointment_update_flags_stale_reminder(api_client, test_db):
    """Update appointment → linked reminder flagged stale; unlinked reminder unchanged."""
    # Create appointment via API
    appt_resp = api_client.post("/v1/integrity/appointments", json={
        "title": "Test Appointment",
        "appointment_time": "09:00",
        "with_person": "Dr. Test",
        "patient_id": 1,
    })
    assert appt_resp.status_code == 201, appt_resp.text
    appt_id = appt_resp.json()["id"]

    # Create linked reminder in test_db
    linked_rem = Reminder(
        patient_id=1, title="Test reminder linked",
        scheduled_time="09:00", frequency="daily", status="pending",
        appointment_id=appt_id, stale_flag=False,
    )
    unlinked_rem = Reminder(
        patient_id=1, title="Unrelated reminder",
        scheduled_time="11:00", frequency="daily", status="pending",
        stale_flag=False,
    )
    test_db.add(linked_rem)
    test_db.add(unlinked_rem)
    test_db.commit()
    linked_id = linked_rem.id
    unlinked_id = unlinked_rem.id

    # Update appointment
    update_resp = api_client.post(
        f"/v1/integrity/appointments/{appt_id}/update",
        json={"new_appointment_time": "11:30", "actor": "Caregiver Nisha"},
        headers=CAREGIVER_HEADERS,
    )
    assert update_resp.status_code == 200, update_resp.text
    data = update_resp.json()
    stale_ids = [r["reminder_id"] for r in data["stale_reminders"]]
    assert linked_id in stale_ids, "Linked reminder should be stale"
    assert unlinked_id not in stale_ids, "Unrelated reminder must NOT be flagged"


# ──────────────────────────────────────────────────────────────
# Test 8: Audit trail — actor and timestamp recorded
# ──────────────────────────────────────────────────────────────

def test_08_audit_trail_recorded(test_db):
    """Verify/reject actions produce audit entries with actor and timestamp."""
    c = make_claim(test_db, statement="Audit test claim")
    verify_claim(c, actor="Caregiver Nisha", note="Audit test", db=test_db)
    test_db.refresh(c)
    history = test_db.query(MemoryClaimHistory).filter_by(claim_id=c.id).all()
    actors = [h.actor for h in history]
    actions = [h.action for h in history]
    assert "Caregiver Nisha" in actors
    assert "verified" in actions
    for h in history:
        assert h.recorded_at is not None


# ──────────────────────────────────────────────────────────────
# Test 9: Authorization — unauthorized caller blocked
# ──────────────────────────────────────────────────────────────

def test_09_unauthorized_caregiver_blocked(api_client, test_db):
    """Caregiver endpoints reject missing/wrong demo role header."""
    c = make_claim(test_db, statement="Authz test claim")
    # No header
    resp_no_auth = api_client.post(f"/v1/integrity/claims/{c.id}/verify",
                                    json={"actor": "Hacker"})
    assert resp_no_auth.status_code == 403

    # Wrong token
    resp_bad_auth = api_client.post(f"/v1/integrity/claims/{c.id}/verify",
                                     json={"actor": "Hacker"},
                                     headers={"X-Demo-Role": "wrong-token"})
    assert resp_bad_auth.status_code == 403


# ──────────────────────────────────────────────────────────────
# Test 10: Dignity preferences — retrievable and updatable
# ──────────────────────────────────────────────────────────────

def test_10_dignity_preferences_settable(api_client):
    """Dignity preferences can be retrieved and updated."""
    get_resp = api_client.get("/v1/integrity/preferences?patient_id=1")
    assert get_resp.status_code == 200
    prefs = get_resp.json()
    assert "plain_language" in prefs

    put_resp = api_client.put("/v1/integrity/preferences?patient_id=1",
                               json={"plain_language": False, "discreet_reminders": True})
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["plain_language"] is False
    assert updated["discreet_reminders"] is True


# ──────────────────────────────────────────────────────────────
# Test 11: LLM cannot introduce absent personal fact
# ──────────────────────────────────────────────────────────────

def test_11_integrity_ask_abstains_without_claims(api_client):
    """Ask a question with no matching claims → ABSTAIN, no invented answer."""
    resp = api_client.post("/v1/integrity/ask", json={
        "question": "What is the patient's best friend's credit card number?",
        "patient_id": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == DECISION_ABSTAIN, f"Expected ABSTAIN, got {data}"
    assert data["answer"] is None, "Should NOT fabricate an answer"


# ──────────────────────────────────────────────────────────────
# Test 12: Regression — unrelated new claim doesn't break existing verified answer
# ──────────────────────────────────────────────────────────────

def test_12_regression_unrelated_claim_safe(test_db):
    """Adding an unrelated new claim must not affect an existing verified answer."""
    # Existing verified claim
    c_existing = make_claim(test_db,
        statement="Patient's home address is 42 Palm Avenue, Bangalore",
        subject="Patient", property_key="home_address", property_value="42 Palm Avenue, Bangalore",
        integrity_status="verified", verified_by="Caregiver Nisha",
    )
    decision_before = evaluate_claim(c_existing)
    assert decision_before["decision"] == DECISION_ANSWER

    # Unrelated new claim with same patient but different subject+property
    c_unrelated = make_claim(test_db,
        statement="Arun's favourite food is idli",
        subject="Arun", property_key="favourite_food", property_value="idli",
        integrity_status="unverified",
    )
    detect_and_register_conflicts(c_unrelated, test_db)

    # Existing claim still returns ANSWER
    test_db.refresh(c_existing)
    decision_after = evaluate_claim(c_existing)
    assert decision_after["decision"] == DECISION_ANSWER, \
        f"Regression: existing verified answer broken by unrelated claim. Got: {decision_after}"
