"""
vectorcode/src/claims/__init__.py
VECTOR Task Claiming System — package entry point.

All public symbols are re-exported here so existing code that does:
    from vectorcode.src.claims import ClaimService, ClaimRepository, ...
continues to work unchanged.
"""
from ._types import (
    ClaimStatus,
    IssuePriority,
    IssueComplexity,
    AgentType,
    StealableReason,
    Claimant,
    Issue,
    HandoffRecord,
    StealableInfo,
    ContestInfo,
    IssueClaim,
    WorkStealingConfig,
    DEFAULT_CONFIG,
    DEFAULT_DB_PATH,
    _VALID_TRANSITIONS,
    _ACTIVE_STATUSES,
)
from ._persistence import ClaimRepository
from ._service import ClaimService
from ._stealing import (
    WorkStealingService,
    LoadBalancer,
    mcp_claim_task,
    mcp_release_task,
    mcp_list_claims,
    mcp_steal_task,
    mcp_get_stealable,
    mcp_rebalance_load,
    mcp_claim_stats,
)

__all__ = [
    "ClaimStatus", "IssuePriority", "IssueComplexity", "AgentType", "StealableReason",
    "Claimant", "Issue", "HandoffRecord", "StealableInfo", "ContestInfo", "IssueClaim",
    "WorkStealingConfig", "DEFAULT_CONFIG", "DEFAULT_DB_PATH",
    "ClaimRepository", "ClaimService", "WorkStealingService", "LoadBalancer",
    "mcp_claim_task", "mcp_release_task", "mcp_list_claims", "mcp_steal_task",
    "mcp_get_stealable", "mcp_rebalance_load", "mcp_claim_stats",
]
