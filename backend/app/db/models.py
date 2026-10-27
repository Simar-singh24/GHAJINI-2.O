"""
Database models for Ghajini 2.0 - Memory Integrity Engine.
Extends the original schema with MemoryClaim, MemoryClaimHistory,
MemoryConflict, Appointment, and DignityPreferences.
Original tables preserved intact. All new tables use create_all (idempotent).
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import relationship as orm_relationship

from app.db.session import Base


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), default="Default Patient", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    people = orm_relationship("Person", back_populates="patient", cascade="all, delete-orphan")
    memories = orm_relationship("Memory", back_populates="patient", cascade="all, delete-orphan")
    reminders = orm_relationship("Reminder", back_populates="patient", cascade="all, delete-orphan")
    consents = orm_relationship("Consent", back_populates="patient", cascade="all, delete-orphan")
    alerts = orm_relationship("Alert", back_populates="patient", cascade="all, delete-orphan")
    audit_logs = orm_relationship("AuditLog", back_populates="patient", cascade="all, delete-orphan")
    places = orm_relationship("Place", back_populates="patient", cascade="all, delete-orphan")
    claims = orm_relationship("MemoryClaim", back_populates="patient", cascade="all, delete-orphan")
    appointments = orm_relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    dignity_preferences = orm_relationship("DignityPreferences", back_populates="patient", uselist=False, cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    name = Column(String(120), nullable=False)
    relationship = Column(String(80), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="people")
    faces = orm_relationship("PersonFace", back_populates="person", cascade="all, delete-orphan")


class PersonFace(Base):
    __tablename__ = "person_faces"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(255), nullable=False)
    embedding_json = Column(Text, nullable=True)
    quality_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    person = orm_relationship("Person", back_populates="faces")


class Memory(Base):
    """Legacy unstructured memory - kept for backward compat. New code uses MemoryClaim."""
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    text = Column(Text, nullable=False)
    category = Column(String(50), nullable=True, default="general")
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="memories")


class Appointment(Base):
    """Structured appointment with version history. Changing appointment_time creates a new record."""
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    title = Column(String(200), nullable=False)
    appointment_time = Column(String(50), nullable=False)
    location = Column(String(200), nullable=True)
    with_person = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="active")
    supersedes_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="appointments")
    reminders = orm_relationship("Reminder", back_populates="appointment")
    supersedes = orm_relationship("Appointment", remote_side="Appointment.id", foreign_keys="Appointment.supersedes_id")


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    title = Column(String(200), nullable=False)
<<<<<<< Updated upstream
    message = Column(Text, nullable=True)
    scheduled_time = Column(String(20), nullable=False)  # e.g., "09:00"
    frequency = Column(String(50), default="daily", nullable=False)
    rrule = Column(String(200), nullable=True)  # iCal RRULE e.g. "FREQ=DAILY" or "FREQ=WEEKLY;BYDAY=MO,WE,FR"
    is_critical = Column(Boolean, default=False, nullable=False)
    escalate_after_min = Column(Integer, default=10, nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, triggered, acknowledged, snoozed, distressed, escalated
    retry_count = Column(Integer, default=0, nullable=False)
    last_triggered_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
=======
    scheduled_time = Column(String(20), nullable=False)
    frequency = Column(String(50), default="daily", nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_triggered_at = Column(DateTime, nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    stale_flag = Column(Boolean, default=False, nullable=False)
>>>>>>> Stashed changes
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="reminders")
    logs = orm_relationship("ReminderLog", back_populates="reminder", cascade="all, delete-orphan")
    appointment = orm_relationship("Appointment", back_populates="reminders")


class ReminderLog(Base):
    __tablename__ = "reminder_logs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False, index=True)
<<<<<<< Updated upstream
    action = Column(String(50), nullable=False)  # triggered, repeated, acknowledged, snoozed, distressed, escalated
    outcome = Column(String(50), default="ignored", nullable=False)  # ignored, repeated, acknowledged, snoozed, distressed, escalated
=======
    action = Column(String(50), nullable=False)
>>>>>>> Stashed changes
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    reminder = orm_relationship("Reminder", back_populates="logs")


class Consent(Base):
    __tablename__ = "consents"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=True)
    consent_given = Column(Boolean, nullable=False, default=True)
    consent_type = Column(String(100), default="face_recognition_and_data_storage", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="consents")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_type = Column(String(50), nullable=False)  # "sos_button", "emergency_phrase", "reminder_escalated", "distress_response"
    message = Column(Text, nullable=False)
    status = Column(String(50), default="sent", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = orm_relationship("Patient", back_populates="alerts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    action = Column(String(50), nullable=False)  # "create_person", "delete_person", "export_data", "wipe_all_data", "alert_created", "recognition"
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = orm_relationship("Patient", back_populates="audit_logs")


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    name = Column(String(120), nullable=False)
    address = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = orm_relationship("Place", back_populates="places") if False else orm_relationship("Patient", back_populates="places")


class MemoryClaim(Base):
    """
    Enriched, provenance-aware memory with integrity metadata.
    Status values: unverified | verified | needs_review | conflicting | expired | rejected
    """
    __tablename__ = "memory_claims"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    statement = Column(Text, nullable=False)
    category = Column(String(80), nullable=True, default="general")
    subject = Column(String(120), nullable=True)
    property_key = Column(String(80), nullable=True)
    property_value = Column(Text, nullable=True)
    source_type = Column(String(50), nullable=False, default="caregiver_input")
    source_description = Column(Text, nullable=True)
    author = Column(String(120), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    integrity_status = Column(String(30), nullable=False, default="unverified", index=True)
    verified_by = Column(String(120), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    review_due_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    supersedes_id = Column(Integer, ForeignKey("memory_claims.id", ondelete="SET NULL"), nullable=True)
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="claims")
    history = orm_relationship(
        "MemoryClaimHistory", back_populates="claim",
        cascade="all, delete-orphan",
        order_by="MemoryClaimHistory.recorded_at",
    )
    supersedes = orm_relationship(
        "MemoryClaim", remote_side="MemoryClaim.id",
        foreign_keys="MemoryClaim.supersedes_id",
    )
    conflicts_as_a = orm_relationship(
        "MemoryConflict", foreign_keys="MemoryConflict.claim_a_id",
        back_populates="claim_a", cascade="all, delete-orphan",
    )
    conflicts_as_b = orm_relationship(
        "MemoryConflict", foreign_keys="MemoryConflict.claim_b_id",
        back_populates="claim_b", cascade="all, delete-orphan",
    )


class MemoryClaimHistory(Base):
    """Append-only audit log of every edit/verification decision on a MemoryClaim."""
    __tablename__ = "memory_claim_history"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("memory_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    actor = Column(String(120), nullable=False)
    action = Column(String(50), nullable=False)
    previous_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    note = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claim = orm_relationship("MemoryClaim", back_populates="history")


class MemoryConflict(Base):
    """Tracks unresolved disagreements between two MemoryClaims on the same subject+property."""
    __tablename__ = "memory_conflicts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    claim_a_id = Column(Integer, ForeignKey("memory_claims.id", ondelete="CASCADE"), nullable=False)
    claim_b_id = Column(Integer, ForeignKey("memory_claims.id", ondelete="CASCADE"), nullable=False)
    subject = Column(String(120), nullable=True)
    property_key = Column(String(80), nullable=True)
    resolution_status = Column(String(30), nullable=False, default="open", index=True)
    resolved_by = Column(String(120), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claim_a = orm_relationship("MemoryClaim", foreign_keys=[claim_a_id], back_populates="conflicts_as_a")
    claim_b = orm_relationship("MemoryClaim", foreign_keys=[claim_b_id], back_populates="conflicts_as_b")


class DignityPreferences(Base):
    """Per-patient dignity/display preferences. One row per patient."""
    __tablename__ = "dignity_preferences"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plain_language = Column(Boolean, default=True, nullable=False)
    large_text = Column(Boolean, default=True, nullable=False)
    discreet_reminders = Column(Boolean, default=False, nullable=False)
    spoken_answers = Column(Boolean, default=True, nullable=False)
    notification_privacy = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    patient = orm_relationship("Patient", back_populates="dignity_preferences")
