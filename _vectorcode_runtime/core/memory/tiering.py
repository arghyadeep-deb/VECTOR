"""Data tiering policy for VECTOR's multi-DB mesh.

The owner wants the laptop to hold only "extremely important and mandatory" data
while the cloud mesh (Supabase + Turso + D1) holds everything. This module is the
single source of truth for that split:

  critical → kept on local SQLite (encrypted, offline-available) AND mirrored to
             cloud; never auto-forgotten by the decay/forgetting pass.
  bulk     → mirrored to cloud as the durable source of truth; locally it is a
             cache that the forgetting pass may prune after it has synced.

Both the mesh (multi_db_manager) and the forgetting pass (episodic.prune_old_episodes)
read this policy so the definition lives in exactly one place.
"""
from __future__ import annotations

# Whole tables that are always critical (low-volume, high-value provenance).
CRITICAL_TABLES = frozenset({
    "semantic_memory",    # learned facts/preferences
    "agent_history",      # ghost memory — irreplaceable
    "policy_memory",      # RL reward history
    "skill_memory",       # skill mastery
})

# Within high-volume tables, these event types are still critical and must not
# be forgotten locally. (episodic_memory + reasoning_chains are bulk otherwise.)
CRITICAL_EVENT_TYPES = frozenset({
    "council", "ghost", "death", "consolidation", "security",
})

# High-frequency, low-value operational telemetry + test pollution. In 24/7
# operation these flood episodic_memory (a single observe-loop or a leaked test
# can write hundreds of thousands of rows) yet carry no long-term value — the
# durable signal already lives in policy_memory / reasoning_chains / semantic.
# The forgetting pass applies EPHEMERAL_RETENTION_DAYS to these instead of the
# default 90d, so growth is bounded without losing anything meaningful.
EPHEMERAL_EVENT_TYPES = frozenset({
    "concurrent",            # test-pollution sentinel (concurrency stress tests)
    "test", "unit",          # leaked test rows
    "api_health_check",      # health-probe telemetry
    "context_budget_handle", # internal token-budget bookkeeping
    "governor_dispatch",     # routing telemetry (the decision is in reasoning_chains)
    "observe", "observation",# raw sensor ticks
})

# 2026-07-29: forgetting switched from a fixed calendar-day cliff to
# Ebbinghaus decay (R = e^(-t/S), see core.memory.decay) — "when decay ≈ 0
# we can evict that data, not based on a fixed N days" (owner's framing).
# These are the *starting* stability (S, in days) for freshly-written rows;
# genuine reuse reinforces S upward per-row from there (decay.reinforce()),
# so a row that keeps getting recalled can legitimately outlive these
# defaults. Chosen so an unreinforced row decays below
# decay.EVICTION_THRESHOLD (0.05) at roughly the same point the old fixed
# cutoffs did (t ≈ 3*S at R=0.05): EPHEMERAL_STABILITY_DAYS=5 -> ~15d
# (was 14d fixed); BULK_STABILITY_DAYS=30 -> ~90d (was 90d fixed).
EPHEMERAL_STABILITY_DAYS = 5.0
BULK_STABILITY_DAYS = 30.0

# Backward-compat alias — nothing else in this codebase reads this anymore
# (episodic.py's prune_old_episodes was rewritten to use decay.py directly),
# kept only so an external/vendored script importing the old name doesn't
# hard-crash; prefer EPHEMERAL_STABILITY_DAYS in new code.
EPHEMERAL_RETENTION_DAYS = 15

TIER_CRITICAL = "critical"
TIER_BULK = "bulk"


def classify(table: str, record: dict | None = None) -> str:
    """Return TIER_CRITICAL or TIER_BULK for a record."""
    if table in CRITICAL_TABLES:
        return TIER_CRITICAL
    if table == "episodic_memory" and record:
        if record.get("event_type") in CRITICAL_EVENT_TYPES:
            return TIER_CRITICAL
    return TIER_BULK


def is_critical(table: str, record: dict | None = None) -> bool:
    return classify(table, record) == TIER_CRITICAL


def protected_event_types() -> frozenset:
    """Episodic event types the forgetting pass must never prune."""
    return CRITICAL_EVENT_TYPES


def ephemeral_event_types() -> frozenset:
    """High-frequency telemetry/test event types the forgetting pass prunes
    after EPHEMERAL_RETENTION_DAYS instead of the default 90d."""
    return EPHEMERAL_EVENT_TYPES
