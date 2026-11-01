"""Ebbinghaus forgetting-curve decay for VECTOR's bulk memory tables.

    R(t) = e^(-t / S)                              (Ebbinghaus, 1885)

  t = days elapsed since the memory was last *touched* (created, or
      genuinely recalled/reused since)
  S = "stability" — how slowly the memory decays. Grows each time the
      memory is actually reused (spaced-repetition style: retrieval
      strengthens retention, it doesn't just reset a clock).

A row becomes eligible for eviction once R(t) drops below EVICTION_THRESHOLD
(~5% of original strength) — replacing a fixed calendar-day cliff. An item
nobody ever revisits fades on schedule; an item that keeps getting recalled
can outlive any fixed cutoff, because each recall both resets t=0 *and*
increases S (see reinforce()).

Owner's framing (2026-07-29): "When decay = 0 we can evict that data — not
based on 90 days." This module is the single source of truth for that
formula so episodic.py / reasoning_memory.py / tiering.py all decay the
same way.
"""
from __future__ import annotations

import math

# R(t) below this is "decayed away" — eligible for eviction.
# At S constant, R=0.05 is reached at t ≈ 3*S (ln(1/0.05) ≈ 2.996).
EVICTION_THRESHOLD = 0.05

# Multiplicative stability boost applied on each genuine recall/reuse.
# 1.3 means ~3 reinforcements roughly double a memory's half-life-equivalent
# survival window — deliberately gentle so reinforcement rewards sustained
# reuse over many recalls rather than one lucky hit.
REINFORCE_FACTOR = 1.3

# Ceiling so a very hot memory can't grow an effectively-infinite stability
# and become unprunable forever from a burst of reuse.
MAX_STABILITY_DAYS = 365.0

# Fallback stability (days) for rows written before this migration existed,
# or any row that somehow has no stored stability_days. Matches the
# t≈3*S relationship: a legacy row with no bulk/ephemeral hint decays to
# threshold at roughly the old 90-day bulk cutoff.
DEFAULT_STABILITY_DAYS = 30.0


def retention(elapsed_days: float, stability_days: float) -> float:
    """R(t) = e^(-t/S). elapsed_days<=0 -> 1.0 (freshly touched).
    stability_days<=0 is treated as already fully decayed (0.0) rather than
    raising, so a bad/missing value fails toward "eligible for eviction",
    not toward "never forgotten"."""
    if stability_days <= 0:
        return 0.0
    if elapsed_days <= 0:
        return 1.0
    return math.exp(-elapsed_days / stability_days)


def should_evict(elapsed_days: float, stability_days: float, threshold: float = EVICTION_THRESHOLD) -> bool:
    return retention(elapsed_days, stability_days) < threshold


def reinforce(stability_days: float | None) -> float:
    """Bump stability on genuine reuse. Missing/invalid input starts from
    DEFAULT_STABILITY_DAYS rather than 0, so a single early recall of a
    just-created row doesn't degenerate its stability."""
    base = stability_days if (stability_days and stability_days > 0) else DEFAULT_STABILITY_DAYS
    return min(base * REINFORCE_FACTOR, MAX_STABILITY_DAYS)


def initial_stability_days(is_ephemeral: bool) -> float:
    """Starting S for a freshly-written row, before any reinforcement.
    Deliberately imported lazily by callers from core.memory.tiering to
    avoid a hard import-time dependency here."""
    from core.memory import tiering as _tiering
    return (
        _tiering.EPHEMERAL_STABILITY_DAYS if is_ephemeral
        else _tiering.BULK_STABILITY_DAYS
    )


if __name__ == "__main__":
    # real test, no mocks
    # A never-reinforced ephemeral row (S=5d) should be long gone by day 200.
    assert should_evict(200, 5.0) is True
    # A 2-day-old ephemeral row should easily survive.
    assert should_evict(2, 5.0) is False
    # Reinforcement should raise stability multiplicatively, capped.
    s = 5.0
    for _ in range(3):
        s = reinforce(s)
    assert abs(s - 5.0 * (REINFORCE_FACTOR ** 3)) < 1e-9
    assert reinforce(10_000.0) == MAX_STABILITY_DAYS
    # A heavily-reinforced row can legitimately outlive the old 90-day cliff.
    assert should_evict(150, 60.0) is False  # R(150,60) ≈ 0.082 > 0.05
    assert should_evict(200, 60.0) is True   # R(200,60) ≈ 0.036 < 0.05
    print("✅ decay.py OK — Ebbinghaus retention/reinforcement formulas verified")
