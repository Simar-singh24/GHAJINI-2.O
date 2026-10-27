"""
Memory Integrity Engine — deterministic rule-based service.

All logic here is pure Python (no network, no LLM, no embeddings).
It can be unit-tested fully offline.

Decision outcomes:
  ANSWER          – verified, sourced, fresh, non-conflicting evidence exists.
  WARN            – evidence exists but is expired or due for review.
  REVIEW_REQUIRED – source recorded but not yet verified by a caregiver.
  CONFLICT        – incompatible claims exist for same subject+property.
  ABSTAIN         – no sufficient supporting information exists.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import MemoryClaim, MemoryConflict, MemoryClaimHistory

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Decision data classes (plain dicts to avoid Pydantic dependency here)
# ─────────────────────────────────────────────

DECISION_ANSWER = "ANSWER"
DECISION_WARN = "WARN"
DECISION_REVIEW_REQUIRED = "REVIEW_REQUIRED"
DECISION_CONFLICT = "CONFLICT"
DECISION_ABSTAIN = "ABSTAIN"


def _now() -> datetime:
    return datetime.utcnow()


# ─────────────────────────────────────────────
# Core integrity evaluation
# ─────────────────────────────────────────────

def evaluate_claim(claim: MemoryClaim) -> dict:
    """
    Evaluate a single MemoryClaim and return a decision dict.
    Does NOT touch the database (read-only input).
    """
    now = _now()

    # Expired?
    if claim.expiry_date and claim.expiry_date < now:
        return _decision(
            DECISION_WARN,
            reason_codes=["EXPIRED"],
            warning=f"This memory expired on {claim.expiry_date.date()}. It must not be relied on as current truth.",
            supporting=[claim.id],
        )

    # Due for review?
    if claim.review_due_date and claim.review_due_date < now and claim.integrity_status != "expired":
        return _decision(
            DECISION_WARN,
            reason_codes=["REVIEW_DUE"],
            warning=f"This memory was due for review by {claim.review_due_date.date()}.",
            supporting=[claim.id],
        )

    # Rejected?
    if claim.integrity_status == "rejected":
        return _decision(
            DECISION_ABSTAIN,
            reason_codes=["REJECTED"],
            warning="This claim was explicitly rejected by a caregiver.",
        )

    # Not verified?
    if claim.integrity_status in ("unverified", "needs_review"):
        return _decision(
            DECISION_REVIEW_REQUIRED,
            reason_codes=["NOT_VERIFIED"],
            supporting=[claim.id],
            warning="This claim has not been verified by an authorised caregiver.",
        )

    # Conflicting status (set externally when a MemoryConflict exists)?
    if claim.integrity_status == "conflicting":
        return _decision(
            DECISION_CONFLICT,
            reason_codes=["HAS_OPEN_CONFLICT"],
            supporting=[claim.id],
            warning="A conflicting claim exists for this subject and property.",
        )

    # All checks passed — verified, fresh
    if claim.integrity_status == "verified":
        return _decision(
            DECISION_ANSWER,
            reason_codes=["VERIFIED", "SOURCED", "FRESH"],
            supporting=[claim.id],
        )

    return _decision(DECISION_ABSTAIN, reason_codes=["UNKNOWN_STATUS"])


def evaluate_question(
    question: str,
    claims: List[MemoryClaim],
    open_conflicts: List[MemoryConflict],
) -> dict:
    """
    Given a list of candidate MemoryClaims (already retrieved by the caller)
    and any open conflicts, return an aggregate decision.

    Conflict detection is by subject + property_key — not global string match.
    Limitation: candidate retrieval is semantic (similarity-based) so this
    function may not see ALL relevant claims if the retrieval missed them.
    """
    if not claims:
        return _decision(DECISION_ABSTAIN, reason_codes=["NO_MATCHING_CLAIMS"])

    # Check if any open conflict involves a retrieved claim
    retrieved_ids = {c.id for c in claims}
    relevant_conflicts = [
        cnf for cnf in open_conflicts
        if cnf.claim_a_id in retrieved_ids or cnf.claim_b_id in retrieved_ids
    ]
    if relevant_conflicts:
        conflict_claim_ids = []
        for cnf in relevant_conflicts:
            conflict_claim_ids += [cnf.claim_a_id, cnf.claim_b_id]
        return _decision(
            DECISION_CONFLICT,
            reason_codes=["CONFLICTING_CLAIMS"],
            supporting=list(retrieved_ids),
            conflicting=list(set(conflict_claim_ids)),
            warning="Incompatible claims exist for this information. A caregiver must resolve the disagreement first.",
            next_action="Open Caregiver Review to compare and resolve conflicting claims.",
        )

    # Evaluate each claim individually and pick the strongest
    decisions = [evaluate_claim(c) for c in claims]

    # Priority: ANSWER > WARN > REVIEW_REQUIRED > ABSTAIN
    for d in decisions:
        if d["decision"] == DECISION_ANSWER:
            return d
    for d in decisions:
        if d["decision"] == DECISION_WARN:
            return d
    for d in decisions:
        if d["decision"] == DECISION_REVIEW_REQUIRED:
            return d
    return _decision(DECISION_ABSTAIN, reason_codes=["NO_SAFE_CLAIM"])


def _decision(
    decision: str,
    reason_codes: Optional[List[str]] = None,
    supporting: Optional[List[int]] = None,
    conflicting: Optional[List[int]] = None,
    warning: Optional[str] = None,
    next_action: Optional[str] = None,
) -> dict:
    return {
        "decision": decision,
        "reason_codes": reason_codes or [],
        "supporting_claim_ids": supporting or [],
        "conflicting_claim_ids": conflicting or [],
        "warning": warning,
        "next_action": next_action,
    }


# ─────────────────────────────────────────────
# Conflict detection helper (called after every new MemoryClaim insert)
# ─────────────────────────────────────────────

def detect_and_register_conflicts(claim: MemoryClaim, db: Session) -> List[MemoryConflict]:
    """
    Find existing verified/unverified claims with same (patient_id, subject,
    property_key) and incompatible property_value.  Register new MemoryConflict
    records and mark both claims as 'conflicting'.

    Returns newly created conflict records.
    """
    if not claim.subject or not claim.property_key:
        return []

    # Find siblings with same subject + property_key, different value, not rejected
    siblings = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.patient_id == claim.patient_id,
            MemoryClaim.subject == claim.subject,
            MemoryClaim.property_key == claim.property_key,
            MemoryClaim.id != claim.id,
            MemoryClaim.integrity_status != "rejected",
        )
        .all()
    )

    new_conflicts: List[MemoryConflict] = []

    for sibling in siblings:
        # Values must differ (case-insensitive strip)
        if (sibling.property_value or "").strip().lower() == (claim.property_value or "").strip().lower():
            continue

        # Check if conflict already exists
        existing = (
            db.query(MemoryConflict)
            .filter(
                MemoryConflict.claim_a_id.in_([claim.id, sibling.id]),
                MemoryConflict.claim_b_id.in_([claim.id, sibling.id]),
                MemoryConflict.resolution_status == "open",
            )
            .first()
        )
        if existing:
            continue

        conflict = MemoryConflict(
            patient_id=claim.patient_id,
            claim_a_id=sibling.id,
            claim_b_id=claim.id,
            subject=claim.subject,
            property_key=claim.property_key,
            resolution_status="open",
        )
        db.add(conflict)

        # Mark both claims as conflicting
        for affected in [claim, sibling]:
            if affected.integrity_status not in ("rejected", "expired"):
                affected.integrity_status = "conflicting"
                _append_history(affected, actor="system", action="flagged_conflict",
                                previous_status=affected.integrity_status, new_status="conflicting",
                                note=f"Auto-flagged: conflict detected with claim #{claim.id if affected is sibling else sibling.id}",
                                db=db)

        new_conflicts.append(conflict)

    if new_conflicts:
        db.commit()
        for cf in new_conflicts:
            db.refresh(cf)

    return new_conflicts


# ─────────────────────────────────────────────
# Audit helpers
# ─────────────────────────────────────────────

def _append_history(
    claim: MemoryClaim,
    actor: str,
    action: str,
    previous_status: Optional[str],
    new_status: Optional[str],
    note: Optional[str],
    db: Session,
) -> MemoryClaimHistory:
    entry = MemoryClaimHistory(
        claim_id=claim.id,
        actor=actor,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        note=note,
        recorded_at=_now(),
    )
    db.add(entry)
    return entry


def verify_claim(
    claim: MemoryClaim,
    actor: str,
    note: Optional[str],
    db: Session,
) -> MemoryClaim:
    """Mark claim as verified; add audit entry."""
    prev = claim.integrity_status
    claim.integrity_status = "verified"
    claim.verified_by = actor
    claim.verified_at = _now()
    claim.updated_at = _now()
    _append_history(claim, actor=actor, action="verified", previous_status=prev,
                    new_status="verified", note=note, db=db)
    db.commit()
    db.refresh(claim)
    return claim


def reject_claim(
    claim: MemoryClaim,
    actor: str,
    note: Optional[str],
    db: Session,
) -> MemoryClaim:
    """Mark claim as rejected; add audit entry."""
    prev = claim.integrity_status
    claim.integrity_status = "rejected"
    claim.updated_at = _now()
    _append_history(claim, actor=actor, action="rejected", previous_status=prev,
                    new_status="rejected", note=note, db=db)
    db.commit()
    db.refresh(claim)
    return claim


def resolve_conflict(
    conflict: MemoryConflict,
    winning_claim_id: int,
    actor: str,
    note: Optional[str],
    db: Session,
) -> MemoryConflict:
    """
    Resolve a conflict: mark winning claim verified, losing claim rejected.
    Both original claims are retained (no deletion).
    Adds audit entries to both claims and updates the conflict record.
    """
    if conflict.resolution_status != "open":
        raise ValueError("Conflict is already resolved.")

    if winning_claim_id == conflict.claim_a_id:
        winner_id, loser_id = conflict.claim_a_id, conflict.claim_b_id
        conflict.resolution_status = "resolved_a"
    elif winning_claim_id == conflict.claim_b_id:
        winner_id, loser_id = conflict.claim_b_id, conflict.claim_a_id
        conflict.resolution_status = "resolved_b"
    else:
        raise ValueError("winning_claim_id must be one of the two conflicting claims.")

    winner = db.get(MemoryClaim, winner_id)
    loser = db.get(MemoryClaim, loser_id)

    if winner:
        verify_claim(winner, actor=actor, note=f"Resolved conflict #{conflict.id}: chosen as authoritative. {note or ''}", db=db)
    if loser:
        reject_claim(loser, actor=actor, note=f"Resolved conflict #{conflict.id}: superseded by claim #{winner_id}. {note or ''}", db=db)

    conflict.resolved_by = actor
    conflict.resolved_at = _now()
    conflict.resolution_note = note

    db.commit()
    db.refresh(conflict)
    return conflict


def correct_claim(
    old_claim: MemoryClaim,
    new_statement: str,
    new_property_value: Optional[str],
    actor: str,
    note: Optional[str],
    db: Session,
    **kwargs,
) -> MemoryClaim:
    """
    Create a new corrected MemoryClaim that supersedes the old one.
    Old claim is marked 'rejected' (preserved in DB).
    """
    prev_status = old_claim.integrity_status
    old_claim.integrity_status = "rejected"
    old_claim.updated_at = _now()
    _append_history(old_claim, actor=actor, action="corrected",
                    previous_status=prev_status, new_status="rejected",
                    note=f"Superseded by correction. {note or ''}", db=db)

    new_claim = MemoryClaim(
        patient_id=old_claim.patient_id,
        statement=new_statement,
        category=old_claim.category,
        subject=kwargs.get("subject", old_claim.subject),
        property_key=kwargs.get("property_key", old_claim.property_key),
        property_value=new_property_value if new_property_value is not None else old_claim.property_value,
        source_type=kwargs.get("source_type", old_claim.source_type),
        source_description=kwargs.get("source_description", old_claim.source_description),
        author=actor,
        integrity_status="unverified",
        supersedes_id=old_claim.id,
        review_due_date=kwargs.get("review_due_date"),
        expiry_date=kwargs.get("expiry_date"),
    )
    db.add(new_claim)
    db.commit()
    db.refresh(new_claim)

    _append_history(new_claim, actor=actor, action="created",
                    previous_status=None, new_status="unverified",
                    note=f"Correction of claim #{old_claim.id}. {note or ''}", db=db)
    db.commit()

    # Detect new conflicts for the replacement claim
    detect_and_register_conflicts(new_claim, db)

    return new_claim
