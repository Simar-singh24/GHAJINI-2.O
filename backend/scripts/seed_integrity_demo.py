"""
Demo Data Seeder — Ghajini 2.0 Memory Integrity Engine
=======================================================
Seeds ALL FICTIONAL demo data for the jury walkthrough.
Includes:
  - 3 people: Priya (daughter), Arun (son), Dr. Sharma (family doctor)
  - Verified facts with provenance
  - 2 conflicting Priya location claims (different fictional caregivers)
  - A stale/review-due appointment memory
  - An appointment linked to a reminder
  - A corrected claim with previous-version history
  - A rejected claim
  - A missing fact (no claim seeded for it)
  - Dignity preferences
  - Legacy Memory records remain unverified (migration test)

Usage:
  cd backend
  python scripts/seed_integrity_demo.py         # seeds if empty
  python scripts/seed_integrity_demo.py --reset  # wipes integrity tables, re-seeds
                                                  # (does NOT touch legacy Memory table)

WARNING: --reset deletes integrity demo data. Never run on a user's database without explicit consent.
All data is FICTIONAL for demonstration purposes only.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.db.models import (
    Appointment, DignityPreferences, MemoryClaim, MemoryClaimHistory,
    MemoryConflict, Patient, Person, PersonFace, Reminder, ReminderLog,
)
from app.modules.integrity.engine import (
    detect_and_register_conflicts, verify_claim, reject_claim, correct_claim,
    _append_history,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_integrity_demo")

FICTIONAL_LABEL = "[FICTIONAL DEMO DATA]"


def reset_integrity_tables(db):
    """Wipe only integrity-related tables. Legacy Memory table is untouched."""
    logger.warning("Resetting integrity tables (MemoryClaims, conflicts, history, appointments, dignity_preferences)...")
    db.query(MemoryClaimHistory).delete()
    db.query(MemoryConflict).delete()
    db.query(MemoryClaim).delete()
    # Remove linked appointment data from reminders but keep the reminders
    db.execute(Reminder.__table__.update().values(appointment_id=None, stale_flag=False))
    db.query(Appointment).delete()
    db.query(DignityPreferences).delete()
    db.commit()
    logger.info("Integrity tables reset.")


def seed(db, patient_id: int = 1):
    now = datetime.utcnow()

    # ── Dignity Preferences ──────────────────────────────────────
    if not db.query(DignityPreferences).filter_by(patient_id=patient_id).first():
        prefs = DignityPreferences(
            patient_id=patient_id,
            plain_language=True,
            large_text=True,
            discreet_reminders=True,
            spoken_answers=True,
            notification_privacy=True,
        )
        db.add(prefs)
        db.commit()
        logger.info("Seeded dignity preferences.")

    def make_claim(
        statement: str,
        category: str,
        subject: str,
        property_key: str,
        property_value: str,
        source_type: str,
        source_description: str,
        author: str,
        status: str = "unverified",
        verified_by: str = None,
        review_due: datetime = None,
        expiry: datetime = None,
        supersedes_id: int = None,
    ) -> MemoryClaim:
        c = MemoryClaim(
            patient_id=patient_id,
            statement=f"{FICTIONAL_LABEL} {statement}",
            category=category,
            subject=subject,
            property_key=property_key,
            property_value=property_value,
            source_type=source_type,
            source_description=source_description,
            author=author,
            recorded_at=now,
            integrity_status=status,
            verified_by=verified_by,
            verified_at=now if status == "verified" else None,
            review_due_date=review_due,
            expiry_date=expiry,
            supersedes_id=supersedes_id,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        _append_history(c, actor=author or "system", action="created",
                        previous_status=None, new_status=status,
                        note=f"Seeded by demo script. {FICTIONAL_LABEL}", db=db)
        db.commit()
        return c

    # ── Verified facts ────────────────────────────────────────────
    c_arun_phone = make_claim(
        statement="Arun's phone number is +91-98765-43210.",
        category="contact",
        subject="Arun",
        property_key="phone",
        property_value="+91-98765-43210",
        source_type="family_member",
        source_description="Provided by Arun directly during caregiver onboarding",
        author="Caregiver Nisha",
        status="verified",
        verified_by="Caregiver Nisha",
    )
    logger.info(f"Seeded verified claim: Arun phone (id={c_arun_phone.id})")

    c_sharma_role = make_claim(
        statement="Dr. Sharma is the family doctor who monitors blood pressure.",
        category="medical",
        subject="Dr. Sharma",
        property_key="role",
        property_value="family doctor - blood pressure monitor",
        source_type="medical_record",
        source_description="Hospital discharge summary 2024-01-15",
        author="Caregiver Nisha",
        status="verified",
        verified_by="Caregiver Nisha",
    )
    logger.info(f"Seeded verified claim: Dr. Sharma role (id={c_sharma_role.id})")

    c_priya_rel = make_claim(
        statement="Priya is the patient's daughter and visits every Sunday.",
        category="family",
        subject="Priya",
        property_key="relationship",
        property_value="daughter",
        source_type="family_member",
        source_description="Confirmed by Priya in initial caregiver intake form",
        author="Caregiver Nisha",
        status="verified",
        verified_by="Caregiver Nisha",
    )
    logger.info(f"Seeded verified claim: Priya relationship (id={c_priya_rel.id})")

    # ── CONFLICTING Priya location claims ─────────────────────────
    # Claim A: by Caregiver Nisha
    c_priya_loc_a = make_claim(
        statement="Priya lives in Bangalore (Indiranagar area).",
        category="location",
        subject="Priya",
        property_key="location",
        property_value="Bangalore, Indiranagar",
        source_type="caregiver_input",
        source_description="Recorded by Caregiver Nisha on 2024-09-01",
        author="Caregiver Nisha",
        status="unverified",
    )
    logger.info(f"Seeded conflict claim A: Priya location Bangalore (id={c_priya_loc_a.id})")

    # Claim B: by Caregiver Ravi (different author, different city)
    c_priya_loc_b = make_claim(
        statement="Priya lives in Chennai (Adyar area) as of 2024-11.",
        category="location",
        subject="Priya",
        property_key="location",
        property_value="Chennai, Adyar",
        source_type="caregiver_input",
        source_description="Recorded by Caregiver Ravi on 2024-11-01 after Priya mentioned relocation",
        author="Caregiver Ravi",
        status="unverified",
    )
    logger.info(f"Seeded conflict claim B: Priya location Chennai (id={c_priya_loc_b.id})")

    # Auto-detect and register conflict
    detect_and_register_conflicts(c_priya_loc_b, db)
    db.refresh(c_priya_loc_a)
    db.refresh(c_priya_loc_b)
    logger.info("Conflict registered for Priya location claims.")

    # ── Stale / review-due appointment memory ─────────────────────
    past_review = now - timedelta(days=30)
    c_appt_stale = make_claim(
        statement="Dr. Sharma appointment scheduled for 09:00 on 2024-10-15 at City Clinic.",
        category="appointment",
        subject="Dr. Sharma",
        property_key="appointment_time",
        property_value="09:00 2024-10-15",
        source_type="caregiver_input",
        source_description="Caregiver Nisha entered this 40 days ago",
        author="Caregiver Nisha",
        status="needs_review",
        review_due=past_review,
    )
    logger.info(f"Seeded stale appointment claim (id={c_appt_stale.id})")

    # ── Corrected claim with version history ─────────────────────
    # Old claim (will be superseded)
    c_arun_loc_old = make_claim(
        statement="Arun lives in Mumbai.",
        category="location",
        subject="Arun",
        property_key="location",
        property_value="Mumbai",
        source_type="caregiver_input",
        source_description="Early record from 2023",
        author="Caregiver Nisha",
        status="unverified",
    )
    # New corrected claim supersedes it
    c_arun_loc_new = correct_claim(
        old_claim=c_arun_loc_old,
        new_statement="Arun lives in Indiranagar, Bangalore (moved 2024-08).",
        new_property_value="Indiranagar, Bangalore",
        actor="Caregiver Nisha",
        note="Arun confirmed the move during his September visit.",
        db=db,
        subject="Arun",
        property_key="location",
        source_description="Confirmed by Arun directly in Sept 2024",
    )
    logger.info(f"Seeded correction: old claim id={c_arun_loc_old.id}, new claim id={c_arun_loc_new.id}")

    # ── Rejected claim ────────────────────────────────────────────
    c_rejected = make_claim(
        statement="The patient's home is at 42 MG Road, Pune.",
        category="location",
        subject="Patient",
        property_key="home_address",
        property_value="42 MG Road, Pune",
        source_type="caregiver_input",
        source_description="Entered in error — address belongs to a different patient",
        author="Caregiver Ravi",
        status="unverified",
    )
    reject_claim(c_rejected, actor="Caregiver Nisha", note="Wrong patient — rejected.", db=db)
    logger.info(f"Seeded rejected claim (id={c_rejected.id})")

    # ── No claim for "best friend's phone number" (missing fact test) ──
    logger.info("No claim seeded for 'best friend phone' — missing fact abstention test.")

    # ── Appointment linked to a Reminder ─────────────────────────
    appt = Appointment(
        patient_id=patient_id,
        title="Blood Pressure Check with Dr. Sharma",
        appointment_time="10:00",
        location="City Clinic, MG Road",
        with_person="Dr. Sharma",
        notes=f"{FICTIONAL_LABEL} Routine monthly BP check.",
        status="active",
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    logger.info(f"Seeded appointment (id={appt.id})")

    # Link reminder to appointment
    linked_reminder = Reminder(
        patient_id=patient_id,
        title="Remind: BP check with Dr. Sharma at 10:00",
        scheduled_time="10:00",
        frequency="monthly",
        status="pending",
        appointment_id=appt.id,
        stale_flag=False,
    )
    db.add(linked_reminder)
    db.commit()
    db.refresh(linked_reminder)
    logger.info(f"Seeded linked reminder (id={linked_reminder.id}) for appointment (id={appt.id})")

    logger.info("=== Demo data seeding complete. ===")
    logger.info("REMINDER: All seeded data is FICTIONAL and for demonstration purposes only.")


def main():
    parser = argparse.ArgumentParser(description="Seed Ghajini 2.0 Integrity Demo Data")
    parser.add_argument("--reset", action="store_true", help="Wipe and re-seed integrity tables (NOT legacy Memory table)")
    args = parser.parse_args()

    settings.init_directories()
    init_db()

    db = SessionLocal()
    try:
        pid = settings.DEFAULT_PATIENT_ID
        patient = db.query(Patient).filter(Patient.id == pid).first()
        if not patient:
            patient = Patient(id=pid, name="Primary Patient (Demo)")
            db.add(patient)
            db.commit()
            logger.info(f"Created patient id={pid}")

        if args.reset:
            reset_integrity_tables(db)

        # Only seed if no claims exist
        existing = db.query(MemoryClaim).filter_by(patient_id=pid).count()
        if existing > 0 and not args.reset:
            logger.info(f"Found {existing} existing claims. Skipping seed (use --reset to re-seed).")
        else:
            seed(db, pid)
    finally:
        db.close()


if __name__ == "__main__":
    main()
