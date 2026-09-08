"""
E3 — Persistence.

Question: does legitimate learning survive a process boundary / database
close-reopen / restart, WITHOUT relying on any global, cache, process-local
counter, or singleton in-memory state that could silently mask a real
persistence defect?

AUDIT SUMMARY (full detail: VECTOR_TECHNICAL_KNOWLEDGE/E3_LEARNING_PERSISTENCE_REPORT.md):

1. `PolicyMemory` (core/memory/policy.py) has NO in-memory cache at all --
   `get_score()`/`update_from_outcome()` issue a real SQL SELECT/UPSERT on
   every single call. There is no code path by which a cached value could
   diverge from what is actually on disk. E1 (this session) already proved
   PolicyMemory's persistence end-to-end (real restart, real winner flip,
   duplicate/old-update controls) using fresh instances across a real
   connection close -- that proof stands, referenced here rather than
   duplicated.

2. `EpistemicTracker` (core/brain/epistemic_tracker.py) DOES keep an
   in-memory `self._beliefs` dict, populated from the DB at __init__ and
   updated BEFORE the SQL write in `update_belief()`/`_persist_belief()`.
   This is architecturally the exact risk E3 warns about: if `_persist_belief()`
   silently fails (it is wrapped in a broad `except Exception: logger.debug(...)`),
   `get_belief()` on the SAME instance would still report the new value as if
   it were durable, because it reads the in-memory dict, not the database.
   R9 (this session) already used FRESH instances (not the same object) to
   test restart behavior, which is the correct methodology and would have
   caught a genuine defect -- but nothing had explicitly proven WHAT HAPPENS
   if a write genuinely fails: does a real restart correctly reveal the loss
   (honest), or does something else paper over it? THIS is what E3 tests
   directly, closing that specific verification gap.

3. `EpisodicMemory`'s CircuitBreakerOpenError fallback path buffers writes
   in `_memory_buffer` when the circuit is open, logging a WARNING when it
   does -- an intentional, honestly-logged degradation, not a silent success
   claim. Not a "hidden cache masking failure" in the sense E3 warns about;
   noted, not further tested here (unrelated to policy/epistemic learning).

RESULT: no persistence defect was found. EpistemicTracker's in-memory cache
does NOT mask a real persistence failure across an actual restart -- a
failed write is correctly absent after reopening with a fresh instance,
exactly as it should be. No production code was changed in this stage.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.brain.epistemic_tracker import EpistemicTracker
from core.memory.policy import PolicyMemory


@pytest.mark.unit
class TestPolicyMemoryHasNoCache:

    def test_no_in_memory_cache_attribute_exists(self):
        pm = PolicyMemory()
        # PolicyMemory is a thin stateless wrapper -- every call hits SQL
        # directly. Confirm there is no dict/cache attribute that could
        # diverge from disk state.
        cache_like = [a for a in vars(pm) if "cache" in a.lower() or a.startswith("_beliefs")]
        assert cache_like == [], f"unexpected cache-like attribute(s) on PolicyMemory: {cache_like}"


@pytest.mark.unit
class TestEpistemicTrackerCacheDoesNotMaskFailure:

    def test_in_memory_value_visible_before_persistence_completes(self):
        """Documents the real intermediate state honestly: within the SAME
        instance, a just-written belief IS visible via the in-memory cache
        even before (or if) the SQL write completes. This is expected
        behavior, not a bug -- the risk is only whether this cache
        incorrectly implies DURABILITY across a restart, tested next."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            et = EpistemicTracker(db_path=db_path)
            with patch.object(et, "_persist_belief", side_effect=RuntimeError("simulated disk failure")):
                et.update_belief("e3_probe_key", "value", 0.9, "test")
                # Same-instance read still sees it -- this is the cache, not
                # yet proven durable.
                assert et.get_belief("e3_probe_key")["confidence"] == 0.9
            et.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_a_failed_persist_is_honestly_absent_after_a_real_restart(self):
        """THE core E3 proof: if the SQL write genuinely fails, a real
        restart (fresh EpistemicTracker instance, same db file) must NOT
        see the value -- the cache must never manufacture false durability.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            et1 = EpistemicTracker(db_path=db_path)
            with patch.object(et1, "_persist_belief", side_effect=RuntimeError("simulated disk failure")):
                et1.update_belief("e3_failure_key", "should not survive", 0.9, "test")
            et1.close()

            # Real restart: fresh instance, same file, no shared Python state.
            et2 = EpistemicTracker(db_path=db_path)
            belief = et2.get_belief("e3_failure_key")
            assert belief is None, (
                "a belief whose persistence genuinely failed must be honestly "
                "absent after a real restart -- the in-memory cache must never "
                "manufacture false durability"
            )
            et2.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_a_successful_persist_survives_a_real_restart(self):
        """Positive control for the test above: a genuinely successful write
        DOES survive, so the negative result above is meaningful (not just
        an artifact of a broken test)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            et1 = EpistemicTracker(db_path=db_path)
            et1.update_belief("e3_success_key", "should survive", 0.9, "test")  # real write, no patch
            et1.close()

            et2 = EpistemicTracker(db_path=db_path)
            belief = et2.get_belief("e3_success_key")
            assert belief is not None
            assert belief["confidence"] == 0.9
            et2.close()
        finally:
            Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
