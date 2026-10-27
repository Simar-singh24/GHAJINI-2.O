"""
Integrity API router — extends (not replaces) the existing memory/chat routes.
Mounts at /v1/integrity

Endpoints:
  POST   /claims                  — create a memory claim with provenance
  GET    /claims                  — list claims (with optional filters)
  GET    /claims/{id}             — single claim detail + history
  POST   /claims/{id}/verify      — caregiver verifies a claim   [caregiver role]
  POST   /claims/{id}/reject      — caregiver rejects a claim    [caregiver role]
  POST   /claims/{id}/correct     — caregiver corrects (versioned update)
  GET    /conflicts               — list open conflicts
  POST   /conflicts/{id}/resolve  — resolve conflict (choose winner) [caregiver role]
  POST   /ask                     — integrity-gated question answering
  GET    /appointments            — list appointments
  POST   /appointments            — create appointment
  POST   /appointments/{id}/update — update appointment, flag stale reminders
  GET    /audit                   — full audit history for a patient
  GET    /preferences             — get dignity preferences
  PUT    /preferences             — update dignity preferences
"""

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Appointment, DignityPreferences, MemoryClaim, MemoryClaimHistory,
    MemoryConflict, Reminder, ReminderLog,
)
from app.db.session import get_db
from app.modules.integrity.engine import (
    DECISION_ANSWER, DECISION_ABSTAIN, DECISION_CONFLICT, DECISION_WARN,
    correct_claim, detect_and_register_conflicts, evaluate_question,
    reject_claim, resolve_conflict, verify_claim,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────
# Demo Role Auth (NOT production; clearly labelled)
# ─────────────────────────────────────────────

DEMO_CAREGIVER_TOKEN = "demo-caregiver-2024"


def require_caregiver(x_demo_role: str = Header(default="")) -> str:
    """
    DEMO-ONLY authorization header check.
    Pass header: X-Demo-Role: demo-caregiver-2024
    This is NOT production authentication/authorization.
    """
    if x_demo_role != DEMO_CAREGIVER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Caregiver authorization required. "
                "Pass header X-Demo-Role: demo-caregiver-2024. "
                "NOTE: This is a demo-only role check, not production security."
            ),
        )
    return x_demo_role


# ─────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────

class ClaimCreate(BaseModel):
    statement: str
    category: Optional[str] = "general"
    subject: Optional[str] = None
    property_key: Optional[str] = None
    property_value: Optional[str] = None
    source_type: Optional[str] = "caregiver_input"
    source_description: Optional[str] = None
    author: Optional[str] = None
    review_due_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    patient_id: Optional[int] = None


class ClaimResponse(BaseModel):
    id: int
    patient_id: int
    statement: str
    category: Optional[str]
    subject: Optional[str]
    property_key: Optional[str]
    property_value: Optional[str]
    source_type: str
    source_description: Optional[str]
    author: Optional[str]
    integrity_status: str
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    review_due_date: Optional[datetime]
    expiry_date: Optional[datetime]
    supersedes_id: Optional[int]
    recorded_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClaimHistoryItem(BaseModel):
    id: int
    actor: str
    action: str
    previous_status: Optional[str]
    new_status: Optional[str]
    note: Optional[str]
    recorded_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClaimDetail(ClaimResponse):
    history: List[ClaimHistoryItem] = []


class VerifyRequest(BaseModel):
    actor: str
    note: Optional[str] = None


class RejectRequest(BaseModel):
    actor: str
    note: Optional[str] = None


class CorrectRequest(BaseModel):
    new_statement: str
    new_property_value: Optional[str] = None
    actor: str
    note: Optional[str] = None
    subject: Optional[str] = None
    property_key: Optional[str] = None
    source_description: Optional[str] = None
    review_due_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None


class ConflictResponse(BaseModel):
    id: int
    patient_id: int
    claim_a_id: int
    claim_b_id: int
    subject: Optional[str]
    property_key: Optional[str]
    resolution_status: str
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    resolution_note: Optional[str]
    created_at: datetime
    claim_a: Optional[ClaimResponse] = None
    claim_b: Optional[ClaimResponse] = None
    model_config = ConfigDict(from_attributes=True)


class ResolveRequest(BaseModel):
    winning_claim_id: int
    actor: str
    note: Optional[str] = None


class IntegrityAskRequest(BaseModel):
    question: str
    patient_id: Optional[int] = None
    subject_hint: Optional[str] = None


class IntegrityAskResponse(BaseModel):
    decision: str
    answer: Optional[str] = None
    supporting_claims: List[ClaimResponse] = []
    conflicting_claims: List[ClaimResponse] = []
    warning: Optional[str] = None
    next_action: Optional[str] = None
    reason_codes: List[str] = []


class AppointmentCreate(BaseModel):
    title: str
    appointment_time: str
    location: Optional[str] = None
    with_person: Optional[str] = None
    notes: Optional[str] = None
    patient_id: Optional[int] = None


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    title: str
    appointment_time: str
    location: Optional[str]
    with_person: Optional[str]
    notes: Optional[str]
    status: str
    supersedes_id: Optional[int]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AppointmentUpdateRequest(BaseModel):
    new_appointment_time: str
    actor: str
    note: Optional[str] = None


class AppointmentImpactResponse(BaseModel):
    old_appointment: AppointmentResponse
    new_appointment: AppointmentResponse
    stale_reminders: List[dict]
    message: str


class PreferencesResponse(BaseModel):
    patient_id: int
    plain_language: bool
    large_text: bool
    discreet_reminders: bool
    spoken_answers: bool
    notification_privacy: bool
    model_config = ConfigDict(from_attributes=True)


class PreferencesUpdate(BaseModel):
    plain_language: Optional[bool] = None
    large_text: Optional[bool] = None
    discreet_reminders: Optional[bool] = None
    spoken_answers: Optional[bool] = None
    notification_privacy: Optional[bool] = None


# ─────────────────────────────────────────────
# Memory Claims
# ─────────────────────────────────────────────

@router.post("/claims", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(payload: ClaimCreate, db: Session = Depends(get_db)):
    pid = payload.patient_id or settings.DEFAULT_PATIENT_ID
    claim = MemoryClaim(
        patient_id=pid,
        statement=payload.statement.strip(),
        category=payload.category,
        subject=payload.subject,
        property_key=payload.property_key,
        property_value=payload.property_value,
        source_type=payload.source_type or "caregiver_input",
        source_description=payload.source_description,
        author=payload.author,
        review_due_date=payload.review_due_date,
        expiry_date=payload.expiry_date,
        integrity_status="unverified",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    # Append creation history
    from app.modules.integrity.engine import _append_history
    _append_history(claim, actor=payload.author or "system", action="created",
                    previous_status=None, new_status="unverified",
                    note="Claim created", db=db)
    db.commit()

    # Detect conflicts
    detect_and_register_conflicts(claim, db)
    db.refresh(claim)
    return claim


@router.get("/claims", response_model=List[ClaimResponse])
def list_claims(
    patient_id: int = Query(default=1),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    subject: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
    db: Session = Depends(get_db),
):
    q = db.query(MemoryClaim).filter(MemoryClaim.patient_id == patient_id)
    if status_filter:
        q = q.filter(MemoryClaim.integrity_status == status_filter)
    if subject:
        q = q.filter(MemoryClaim.subject == subject)
    return q.order_by(MemoryClaim.created_at.desc()).limit(limit).all()


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(MemoryClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    resp = ClaimDetail.model_validate(claim)
    resp.history = [ClaimHistoryItem.model_validate(h) for h in claim.history]
    return resp


@router.post("/claims/{claim_id}/verify", response_model=ClaimResponse)
def verify_claim_endpoint(
    claim_id: int,
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_caregiver),
):
    claim = db.get(MemoryClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.integrity_status == "rejected":
        raise HTTPException(status_code=400, detail="Cannot verify a rejected claim.")
    return verify_claim(claim, actor=payload.actor, note=payload.note, db=db)


@router.post("/claims/{claim_id}/reject", response_model=ClaimResponse)
def reject_claim_endpoint(
    claim_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_caregiver),
):
    claim = db.get(MemoryClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return reject_claim(claim, actor=payload.actor, note=payload.note, db=db)


@router.post("/claims/{claim_id}/correct", response_model=ClaimResponse)
def correct_claim_endpoint(
    claim_id: int,
    payload: CorrectRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_caregiver),
):
    old_claim = db.get(MemoryClaim, claim_id)
    if not old_claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    new_claim = correct_claim(
        old_claim=old_claim,
        new_statement=payload.new_statement,
        new_property_value=payload.new_property_value,
        actor=payload.actor,
        note=payload.note,
        db=db,
        subject=payload.subject,
        property_key=payload.property_key,
        source_description=payload.source_description,
        review_due_date=payload.review_due_date,
        expiry_date=payload.expiry_date,
    )
    return new_claim


# ─────────────────────────────────────────────
# Conflicts
# ─────────────────────────────────────────────

@router.get("/conflicts", response_model=List[ConflictResponse])
def list_conflicts(
    patient_id: int = Query(default=1),
    resolution_status: Optional[str] = Query(default="open"),
    db: Session = Depends(get_db),
):
    q = db.query(MemoryConflict).filter(MemoryConflict.patient_id == patient_id)
    if resolution_status:
        q = q.filter(MemoryConflict.resolution_status == resolution_status)
    conflicts = q.order_by(MemoryConflict.created_at.desc()).all()
    result = []
    for cnf in conflicts:
        cr = ConflictResponse.model_validate(cnf)
        if cnf.claim_a:
            cr.claim_a = ClaimResponse.model_validate(cnf.claim_a)
        if cnf.claim_b:
            cr.claim_b = ClaimResponse.model_validate(cnf.claim_b)
        result.append(cr)
    return result


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictResponse)
def resolve_conflict_endpoint(
    conflict_id: int,
    payload: ResolveRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_caregiver),
):
    conflict = db.get(MemoryConflict, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    try:
        resolved = resolve_conflict(conflict, payload.winning_claim_id, payload.actor, payload.note, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cr = ConflictResponse.model_validate(resolved)
    if resolved.claim_a:
        cr.claim_a = ClaimResponse.model_validate(resolved.claim_a)
    if resolved.claim_b:
        cr.claim_b = ClaimResponse.model_validate(resolved.claim_b)
    return cr


# ─────────────────────────────────────────────
# Integrity-gated Ask
# ─────────────────────────────────────────────

@router.post("/ask", response_model=IntegrityAskResponse)
def integrity_ask(payload: IntegrityAskRequest, db: Session = Depends(get_db)):
    pid = payload.patient_id or settings.DEFAULT_PATIENT_ID
    q_lower = payload.question.lower()

    import re
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', q_lower)
    STOP_WORDS = {"what", "who", "when", "where", "how", "is", "are", "the", "a", "an", "this", "that", "patient", "patients", "tell", "does", "with", "from", "your", "my", "our", "about", "have"}
    words = [w for w in cleaned.split() if len(w) >= 3 and w not in STOP_WORDS]
    all_claims = db.query(MemoryClaim).filter(
        MemoryClaim.patient_id == pid,
        MemoryClaim.integrity_status != "rejected",
    ).all()

    # Score by keyword overlap across statement, subject, property key/value
    def relevance(c: MemoryClaim) -> int:
        if not words:
            return 0
        fields = " ".join(filter(None, [c.statement, c.subject, c.property_key, c.property_value])).lower()
        return sum(1 for w in words if w in fields)

    scored = sorted(all_claims, key=relevance, reverse=True)
    candidates = [c for c in scored if relevance(c) > 0][:5]

    # Collect open conflicts for candidates
    cand_ids = {c.id for c in candidates}
    open_conflicts = (
        db.query(MemoryConflict)
        .filter(
            MemoryConflict.patient_id == pid,
            MemoryConflict.resolution_status == "open",
        )
        .filter(
            (MemoryConflict.claim_a_id.in_(cand_ids)) |
            (MemoryConflict.claim_b_id.in_(cand_ids))
        )
        .all()
    )

    decision = evaluate_question(payload.question, candidates, open_conflicts)

    # Build answer text only for ANSWER or WARN
    answer_text: Optional[str] = None
    supporting_claims: List[MemoryClaim] = []
    conflicting_claims_list: List[MemoryClaim] = []

    if decision["decision"] in (DECISION_ANSWER, DECISION_WARN):
        sup_ids = set(decision["supporting_claim_ids"])
        supporting_claims = [c for c in candidates if c.id in sup_ids]
        if supporting_claims:
            # Return verbatim statement (LLM not used for personal facts)
            answer_text = supporting_claims[0].statement

    if decision["decision"] == DECISION_CONFLICT:
        all_ids = set(decision["supporting_claim_ids"]) | set(decision["conflicting_claim_ids"])
        all_rel = db.query(MemoryClaim).filter(MemoryClaim.id.in_(all_ids)).all()
        for c in all_rel:
            if c.id in set(decision["conflicting_claim_ids"]):
                conflicting_claims_list.append(c)
            else:
                supporting_claims.append(c)

    return IntegrityAskResponse(
        decision=decision["decision"],
        answer=answer_text,
        supporting_claims=[ClaimResponse.model_validate(c) for c in supporting_claims],
        conflicting_claims=[ClaimResponse.model_validate(c) for c in conflicting_claims_list],
        warning=decision.get("warning"),
        next_action=decision.get("next_action"),
        reason_codes=decision.get("reason_codes", []),
    )


# ─────────────────────────────────────────────
# Appointments
# ─────────────────────────────────────────────

@router.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    pid = payload.patient_id or settings.DEFAULT_PATIENT_ID
    appt = Appointment(
        patient_id=pid,
        title=payload.title.strip(),
        appointment_time=payload.appointment_time.strip(),
        location=payload.location,
        with_person=payload.with_person,
        notes=payload.notes,
        status="active",
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


@router.get("/appointments", response_model=List[AppointmentResponse])
def list_appointments(patient_id: int = Query(default=1), db: Session = Depends(get_db)):
    return (
        db.query(Appointment)
        .filter(Appointment.patient_id == patient_id, Appointment.status == "active")
        .order_by(Appointment.created_at.desc())
        .all()
    )


@router.post("/appointments/{appointment_id}/update", response_model=AppointmentImpactResponse)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_caregiver),
):
    old = db.get(Appointment, appointment_id)
    if not old:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Archive old version
    old.status = "superseded"

    # Create new version
    new_appt = Appointment(
        patient_id=old.patient_id,
        title=old.title,
        appointment_time=payload.new_appointment_time,
        location=old.location,
        with_person=old.with_person,
        notes=payload.note or old.notes,
        status="active",
        supersedes_id=old.id,
    )
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)

    # Find linked reminders that still use the old time
    stale = (
        db.query(Reminder)
        .filter(
            Reminder.appointment_id == old.id,
            Reminder.scheduled_time == old.appointment_time,
            Reminder.stale_flag == False,
        )
        .all()
    )
    stale_info = []
    for r in stale:
        r.stale_flag = True
        r.appointment_id = new_appt.id
        log = ReminderLog(
            patient_id=r.patient_id,
            reminder_id=r.id,
            action="stale_flagged",
            details=(
                f"Appointment '{old.title}' time changed from '{old.appointment_time}' "
                f"to '{payload.new_appointment_time}' by {payload.actor}. Reminder requires review."
            ),
        )
        db.add(log)
        stale_info.append({
            "reminder_id": r.id,
            "title": r.title,
            "old_scheduled_time": old.appointment_time,
            "new_appointment_time": payload.new_appointment_time,
        })

    db.commit()

    return AppointmentImpactResponse(
        old_appointment=AppointmentResponse.model_validate(old),
        new_appointment=AppointmentResponse.model_validate(new_appt),
        stale_reminders=stale_info,
        message=(
            f"Appointment updated. {len(stale_info)} linked reminder(s) flagged as stale "
            f"because they still reference the old time '{old.appointment_time}'."
        ),
    )


# ─────────────────────────────────────────────
# Audit History
# ─────────────────────────────────────────────

@router.get("/audit", response_model=List[ClaimHistoryItem])
def get_audit(
    patient_id: int = Query(default=1),
    limit: int = Query(default=100),
    db: Session = Depends(get_db),
):
    claim_ids = [
        c.id for c in db.query(MemoryClaim.id).filter(MemoryClaim.patient_id == patient_id).all()
    ]
    if not claim_ids:
        return []
    history = (
        db.query(MemoryClaimHistory)
        .filter(MemoryClaimHistory.claim_id.in_(claim_ids))
        .order_by(MemoryClaimHistory.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return [ClaimHistoryItem.model_validate(h) for h in history]


# ─────────────────────────────────────────────
# Dignity Preferences
# ─────────────────────────────────────────────

def _get_or_create_prefs(patient_id: int, db: Session) -> DignityPreferences:
    prefs = db.query(DignityPreferences).filter(DignityPreferences.patient_id == patient_id).first()
    if not prefs:
        prefs = DignityPreferences(patient_id=patient_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(patient_id: int = Query(default=1), db: Session = Depends(get_db)):
    return _get_or_create_prefs(patient_id, db)


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    payload: PreferencesUpdate,
    patient_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    prefs = _get_or_create_prefs(patient_id, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(prefs, field, value)
    prefs.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prefs)
    return prefs
