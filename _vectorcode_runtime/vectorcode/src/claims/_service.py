"""
vectorcode/src/claims/_service.py
Core claiming lifecycle — claim, release, handoff, progress, auto-assign.
"""
from __future__ import annotations

from vectorcode.src.claims._types import (  # noqa: F401
    ClaimStatus, IssuePriority, IssueComplexity, AgentType,
    Claimant, Issue, IssueClaim, WorkStealingConfig, DEFAULT_CONFIG,
    _VALID_TRANSITIONS, _ACTIVE_STATUSES,
)
from vectorcode.src.claims._persistence import ClaimRepository  # noqa: F401

import time
import uuid
from typing import Optional
from loguru import logger


class ClaimService:
    """Core VECTOR task claiming lifecycle."""

    def __init__(self, repo: Optional[ClaimRepository] = None) -> None:
        self.repo = repo or ClaimRepository()

    def claim(
        self,
        issue_id: str,
        claimant: Claimant,
        issue_title: str = "",
        labels: Optional[list[str]] = None,
        priority: IssuePriority = IssuePriority.medium,
        complexity: IssueComplexity = IssueComplexity.moderate,
        required_capabilities: Optional[list[str]] = None,
    ) -> Optional[IssueClaim]:
        existing = self.repo.find_by_issue_id(issue_id)
        # find_by_issue_id() returns the latest claim not in a terminal
        # status (completed/released/expired) -- so "already claimed" must
        # mean any non-terminal status, not just literally "active".
        # Checking only `== ClaimStatus.active` let a second claim() call
        # slip through while the existing claim was paused/blocked/
        # in_review/pending_handoff/stealable, creating two live claims for
        # the same issue_id and defeating the mutual-exclusion this system
        # exists to provide (real caller: swarm.py's start_task()).
        if existing and existing.status in _ACTIVE_STATUSES:
            logger.warning(f"[VECTOR][claims] issue {issue_id} already claimed by {existing.claimant.name} (status={existing.status.value})")
            return None
        active_count = self.repo.count_by_agent(claimant.id)
        if active_count >= claimant.max_concurrent_claims:
            logger.warning(f"[VECTOR][claims] {claimant.name} at capacity ({active_count}/{claimant.max_concurrent_claims})")
            return None
        required = required_capabilities or []
        if required:
            missing = [c for c in required if c not in claimant.capabilities]
            if missing:
                logger.warning(f"[VECTOR][claims] {claimant.name} missing capabilities: {missing}")
                return None
        now = time.time()
        claim = IssueClaim(
            id=f"claim-{uuid.uuid4().hex}", issue_id=issue_id, claimant=claimant,
            status=ClaimStatus.active, claimed_at=now, last_activity_at=now,
        )
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ClaimCreated", {
            "claimant_id": claimant.id, "issue_title": issue_title,
            "priority": priority.value if hasattr(priority, "value") else str(priority),
        })
        logger.info(f"[VECTOR][claims] {claimant.name} claimed issue {issue_id}")
        return claim

    def release(self, issue_id: str, claimant_id: str) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            return False
        if claim.claimant.id != claimant_id:
            return False
        if any(h.status == "pending" for h in claim.handoff_chain):
            return False
        claim.status = ClaimStatus.released
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ClaimReleased", {"claimant_id": claimant_id})
        logger.info(f"[VECTOR][claims] {claimant_id} released issue {issue_id}")
        return True

    def update_progress(self, issue_id: str, claimant_id: str, progress: int) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim or claim.claimant.id != claimant_id:
            return False
        claim.progress = max(0, min(100, progress))
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ProgressUpdated", {"progress": claim.progress})
        return True

    def update_status(self, issue_id: str, new_status: ClaimStatus, note: Optional[str] = None) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            return False
        allowed = _VALID_TRANSITIONS.get(claim.status, set())
        if new_status not in allowed:
            logger.warning(f"[VECTOR][claims] invalid transition {claim.status} -> {new_status}")
            return False
        old = claim.status
        claim.status = new_status
        claim.last_activity_at = time.time()
        if note:
            claim.notes.append(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {note}")
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "StatusChanged", {"from": old.value, "to": new_status.value})
        return True

    def get_claimed_by(self, agent_id: str) -> list[IssueClaim]:
        return [c for c in self.repo.find_by_agent_id(agent_id) if c.status in _ACTIVE_STATUSES]

    def expire_stale(self, max_age_minutes: int = 120) -> list[IssueClaim]:
        cutoff = time.time() - max_age_minutes * 60
        stale = self.repo.find_stale(cutoff)
        expired = []
        for claim in stale:
            if claim.status != ClaimStatus.active:
                continue
            claim.status = ClaimStatus.expired
            self.repo.save(claim)
            self.repo.append_event(claim.id, claim.issue_id, "ClaimExpired", {"max_age_minutes": max_age_minutes})
            expired.append(claim)
        return expired

    def register_claimant(self, agent_id: str, agent_type: str, capacity: int = 1) -> None:
        """Register an agent as a claimant (no-op if already known; used by work-stealing)."""
        logger.debug(f"[VECTOR][claims] registered claimant {agent_id} type={agent_type} capacity={capacity}")
