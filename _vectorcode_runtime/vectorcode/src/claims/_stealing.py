"""
vectorcode/src/claims/_stealing.py
Work stealing, load balancing, and MCP tool wrappers.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

from loguru import logger

from ._types import (
    AgentType, ClaimStatus, Claimant, IssueClaim, IssuePriority,
    StealableInfo, StealableReason, ContestInfo, WorkStealingConfig,
    DEFAULT_CONFIG, _ACTIVE_STATUSES,
)
from ._persistence import ClaimRepository
from ._service import ClaimService


class WorkStealingService:
    """Redistributes stale/blocked/overloaded work to idle agents."""

    def __init__(
        self,
        repo: Optional[ClaimRepository] = None,
        config: Optional[WorkStealingConfig] = None,
    ) -> None:
        self.repo = repo or ClaimRepository()
        self.config = config or WorkStealingConfig()

    def _get_agent_type(self, claimant: Claimant) -> AgentType:
        for t in AgentType:
            if t.value in claimant.specializations or t.value in claimant.capabilities or t.value in claimant.name.lower():
                return t
        return AgentType.coder

    def _in_grace_period(self, claim: IssueClaim) -> bool:
        return (time.time() - claim.claimed_at) < self.config.grace_period_minutes * 60

    def _protected_by_progress(self, claim: IssueClaim) -> bool:
        return claim.progress >= self.config.min_progress_to_protect

    def _allowed_stealer_types(self, claimant: Claimant) -> Optional[list[AgentType]]:
        if not self.config.allow_cross_type_steal:
            return None
        owner_type = self._get_agent_type(claimant)
        allowed = {owner_type}
        for t1, t2 in self.config.cross_type_steal_rules:
            if owner_type == t1:
                allowed.add(t2)
            if owner_type == t2:
                allowed.add(t1)
        return list(allowed)

    def mark_stealable(self, issue_id: str, reason: StealableReason, original_progress: int = 0) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim or claim.steal_info is not None:
            return claim is not None
        if self._in_grace_period(claim) or self._protected_by_progress(claim):
            return False
        claim.steal_info = StealableInfo(
            reason=reason, marked_at=time.time(),
            original_progress=original_progress or claim.progress,
            allowed_stealer_types=self._allowed_stealer_types(claim.claimant),
        )
        claim.status = ClaimStatus.stealable
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "IssueMarkedStealable", {"reason": reason.value})
        logger.info(f"[VECTOR][claims] {issue_id} marked stealable ({reason.value})")
        return True

    def steal(self, issue_id: str, stealer: Claimant) -> Optional[IssueClaim]:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim or claim.steal_info is None or claim.status != ClaimStatus.stealable:
            return None
        if self._in_grace_period(claim) or self._protected_by_progress(claim):
            return None
        stealer_count = self.repo.count_by_agent(stealer.id)
        if stealer_count >= self.config.overload_threshold:
            return None
        now = time.time()
        prev = claim.claimant
        prev_steal = claim.steal_info
        claim.contest_info = ContestInfo(
            contested_at=now, contested_by=prev, stolen_by=stealer,
            reason="", window_ends_at=now + self.config.contest_window_minutes * 60,
        )
        claim.claimant = stealer
        claim.steal_info = None
        claim.status = ClaimStatus.active
        claim.last_activity_at = now
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "IssueStolen", {
            "previous_claimant_id": prev.id, "new_claimant_id": stealer.id,
            "steal_reason": prev_steal.reason.value,
        })
        logger.info(f"[VECTOR][claims] {stealer.name} stole {issue_id} from {prev.name}")
        return claim

    def get_stealable(self, agent_type: Optional[AgentType] = None) -> list[IssueClaim]:
        return [
            c for c in self.repo.find_stealable(agent_type)
            if not self._in_grace_period(c) and not self._protected_by_progress(c)
        ]

    def auto_mark_stealable(self, config: Optional[WorkStealingConfig] = None) -> int:
        cfg = config or self.config
        all_claims = self.repo.find_all_active()
        now = time.time()
        marked = 0
        for claim in all_claims:
            if claim.steal_info is not None:
                continue
            if (now - claim.claimed_at) < cfg.grace_period_minutes * 60:
                continue
            if claim.progress >= cfg.min_progress_to_protect:
                continue
            if (now - claim.last_activity_at) > cfg.stale_threshold_minutes * 60:
                if self.mark_stealable(claim.issue_id, StealableReason.stale, claim.progress):
                    marked += 1
            elif (claim.status == ClaimStatus.blocked and claim.blocked_at and
                  (now - claim.blocked_at) > cfg.blocked_threshold_minutes * 60):
                if self.mark_stealable(claim.issue_id, StealableReason.blocked, claim.progress):
                    marked += 1
        logger.info(f"[VECTOR][claims] auto-marked {marked} claims as stealable")
        return marked


class LoadBalancer:
    """Swarm-level utilisation tracking and rebalance recommendations."""

    _DEFAULT_MAX_CLAIMS = 5

    def __init__(self, repo: Optional[ClaimRepository] = None) -> None:
        self.repo = repo or ClaimRepository()
        self._background_task: Optional[asyncio.Task] = None

    def get_agent_load(self, agent_ids: list[str]) -> dict[str, float]:
        result = {}
        for aid in agent_ids:
            claims = [c for c in self.repo.find_by_agent_id(aid) if c.status in _ACTIVE_STATUSES]
            pct = min(100.0, (len(claims) / self._DEFAULT_MAX_CLAIMS) * 100)
            result[aid] = round(pct, 1)
        return result

    def find_overloaded(self, agents: list[Claimant], threshold: float = 90.0) -> list[str]:
        load = self.get_agent_load([a.id for a in agents])
        return [aid for aid, pct in load.items() if pct >= threshold]

    def find_underloaded(self, agents: list[Claimant], threshold: float = 30.0) -> list[str]:
        load = self.get_agent_load([a.id for a in agents])
        return [aid for aid, pct in load.items() if pct <= threshold]

    def rebalance(
        self, agents: list[Claimant], config: Optional[WorkStealingConfig] = None,
        overload_threshold_pct: float = 90.0, underload_threshold_pct: float = 30.0,
        max_moves: int = 10,
    ) -> list[tuple[str, str, str]]:
        overloaded = self.find_overloaded(agents, overload_threshold_pct)
        underloaded = self.find_underloaded(agents, underload_threshold_pct)
        if not overloaded or not underloaded:
            return []
        moves: list[tuple[str, str, str]] = []
        for over_id in overloaded:
            if len(moves) >= max_moves or not underloaded:
                break
            claims = sorted(
                [c for c in self.repo.find_by_agent_id(over_id) if c.status == ClaimStatus.active and c.progress < 25],
                key=lambda c: c.progress,
            )
            for claim in claims:
                if len(moves) >= max_moves or not underloaded:
                    break
                moves.append((claim.id, over_id, underloaded[0]))
                underloaded.pop(0)
        return moves


# ---------------------------------------------------------------------------
# Singleton helpers + MCP wrappers
# ---------------------------------------------------------------------------

_repo: Optional[ClaimRepository] = None
_claim_svc: Optional[ClaimService] = None
_steal_svc: Optional[WorkStealingService] = None
_lb: Optional[LoadBalancer] = None


def _get_repo() -> ClaimRepository:
    global _repo
    if _repo is None:
        _repo = ClaimRepository()
    return _repo


def _get_claim_svc() -> ClaimService:
    global _claim_svc
    if _claim_svc is None:
        _claim_svc = ClaimService(_get_repo())
    return _claim_svc


def _get_steal_svc() -> WorkStealingService:
    global _steal_svc
    if _steal_svc is None:
        _steal_svc = WorkStealingService(_get_repo())
    return _steal_svc


def _get_lb() -> LoadBalancer:
    global _lb
    if _lb is None:
        _lb = LoadBalancer(_get_repo())
    return _lb


async def mcp_claim_task(
    issue_id: str, agent_id: str, agent_name: str,
    capabilities: Optional[list[str]] = None, title: str = "", priority: str = "medium",
) -> dict[str, Any]:
    svc = _get_claim_svc()
    claimant = Claimant(id=agent_id, type="agent", name=agent_name, capabilities=capabilities or [])
    claim = svc.claim(
        issue_id=issue_id, claimant=claimant, issue_title=title,
        priority=IssuePriority(priority) if priority in IssuePriority._value2member_map_ else IssuePriority.medium,
    )
    if claim is None:
        return {"success": False, "error": "Claim failed"}
    return {"success": True, "claim_id": claim.id, "issue_id": claim.issue_id,
            "claimant": claim.claimant.name, "status": claim.status.value}


async def mcp_release_task(issue_id: str, agent_id: str) -> dict[str, Any]:
    return {"success": _get_claim_svc().release(issue_id, agent_id), "issue_id": issue_id}


async def mcp_list_claims(agent_id: Optional[str] = None) -> dict[str, Any]:
    repo = _get_repo()
    claims = (
        [c for c in repo.find_by_agent_id(agent_id) if c.status in _ACTIVE_STATUSES]
        if agent_id else repo.find_all_active()
    )
    return {"total": len(claims), "claims": [
        {"claim_id": c.id, "issue_id": c.issue_id, "claimant": c.claimant.name,
         "status": c.status.value, "progress": c.progress}
        for c in claims
    ]}


async def mcp_steal_task(issue_id: str, stealer_id: str, stealer_name: str) -> dict[str, Any]:
    stealer = Claimant(id=stealer_id, type="agent", name=stealer_name)
    claim = _get_steal_svc().steal(issue_id, stealer)
    if claim is None:
        return {"success": False, "error": "Steal failed"}
    return {"success": True, "claim_id": claim.id, "new_claimant": stealer_name}


async def mcp_get_stealable(agent_type: Optional[str] = None) -> dict[str, Any]:
    at = AgentType(agent_type) if agent_type and agent_type in AgentType._value2member_map_ else None
    claims = _get_steal_svc().get_stealable(at)
    return {"total": len(claims), "claims": [
        {"claim_id": c.id, "issue_id": c.issue_id, "reason": c.steal_info.reason.value if c.steal_info else "unknown"}
        for c in claims
    ]}


async def mcp_rebalance_load(agent_ids: list[str]) -> dict[str, Any]:
    agents = [Claimant(id=aid, type="agent", name=aid) for aid in agent_ids]
    moves = _get_lb().rebalance(agents)
    return {"moves": [{"claim_id": m[0], "from": m[1], "to": m[2]} for m in moves]}


async def mcp_claim_stats() -> dict[str, Any]:
    repo = _get_repo()
    all_claims = repo.find_all()
    by_status: dict[str, int] = {}
    for c in all_claims:
        by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
    return {"total": len(all_claims), "by_status": by_status}
