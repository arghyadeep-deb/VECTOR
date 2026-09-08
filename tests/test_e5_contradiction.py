"""
E5 — Contradiction.

Question: how does VECTOR handle belief A vs. belief NOT-A, or conflicting
correction lessons? Does it detect contradiction, silently overwrite, use
confidence/provenance/recency, or become unstable?

AUDIT SUMMARY (full detail: VECTOR_TECHNICAL_KNOWLEDGE/E5_CONTRADICTION_REPORT.md):

1. `EpistemicTracker`: already proven deterministic in R9 (same-key UPSERT =
   last-write-wins; `merge_belief()` = fixed 0.7/0.3 blend). Not re-tested.

2. `CorrectionLearner._consolidate()` already has a confidence-gated
   supersession branch (`if new.correction != existing.correction and
   new.confidence > existing.confidence: <supersede, recording provenance>`).
   This IS a real, existing, deterministic contradiction-resolution policy.

3. TWO real bugs were found and FIXED in the mechanics around it (neither
   changes the confidence-gate policy itself):
   a. `_find_duplicate()` returned the FIRST matching stored row
      (`mem.recall()`'s own order), not the most current one -- since
      `_consolidate()` never updates a row in place (every call re-stores a
      fresh one), this could hand consolidation a STALE base state. Fixed:
      now scans all matches and picks the highest-(confidence, timestamp)
      one.
   b. `retrieve_applicable_lessons()` had the same staleness exposure on the
      READ side -- an old, already-superseded/reinforced snapshot of the
      exact same lesson (same situation_hash) could be returned alongside
      its own replacement as if they were two independent lessons. Fixed:
      dedup by situation_hash before sorting/limiting, keeping the same
      highest-(confidence, timestamp) winner.

4. ONE genuine limitation was found, INVESTIGATED, and left UNFIXED,
   honestly reported: `_find_duplicate()`/`_consolidate()` can only ever
   compare corrections that already produce the SAME situation_hash, and
   that hash includes the correction's own text -- so two corrections with
   DIFFERENT wording about what is actually the exact same real-world fact
   (e.g. "the deadline is Friday" vs "the deadline is Monday") are NEVER
   recognized as related, and the confidence-gated supersession branch
   never engages for them. A same-domain+situation-only hash WAS tried and
   reverted after a direct regression test proved it also incorrectly
   collapses genuinely independent, non-contradictory corrections that
   merely share a broad situation (confirmed against the pre-existing
   `test_multiple_corrections_same_domain`, which correctly expects 3
   simultaneously-valid, unrelated coding tips to remain independently
   retrievable). Distinguishing "a different answer to the same question"
   from "an additional, compatible tip for the same context" needs semantic
   judgment this codebase's existing non-LLM mechanisms (exact hash, keyword
   tags, Jaccard word-overlap) cannot reliably provide -- "Friday" and
   "Monday" share no lexical overlap either, so no similarity-based
   heuristic tried here could tell the two cases apart. This is reported as
   an open architectural question, per E5's own explicit "only implement a
   minimal policy IF supported by existing architecture" instruction -- it
   is not, so nothing was forced.
"""
import pytest

from core.memory.correction_learner import CorrectionLearner


class _FakeCorrectionStore:
    """Minimal, functionally-real in-memory stand-in for EpisodicMemory's
    (store, recall) contract -- matches tests/test_r8_correction_learning.py's
    own fixture, reimplemented here to keep this file self-contained."""

    def __init__(self):
        self.rows: list[dict] = []

    def store(self, event_type, content, tags=None, context=None, source="vector"):
        self.rows.append({"event_type": event_type, "content": content, "tags": tags or []})
        return f"row-{len(self.rows)}"

    def recall(self, query, limit=5, event_type=None):
        rows = [r for r in self.rows if event_type is None or r["event_type"] == event_type]
        return [{"content": r["content"]} for r in rows[-limit:]]


def make_learner(shared_store=None):
    learner = CorrectionLearner()
    learner._memory = shared_store if shared_store is not None else _FakeCorrectionStore()
    return learner


@pytest.mark.unit
class TestExactDuplicateReinforcement:
    """The real, reachable contradiction/consolidation path: repeated
    identical corrections reinforce confidence deterministically and never
    duplicate the stored lesson."""

    def test_a_alone_stored(self):
        learner = make_learner()
        lesson_a = learner.process_owner_message(
            "no, use httpx instead of requests",
            context={"situation": "e5_probe_situation"},
        )
        assert lesson_a is not None
        retrieved = learner.retrieve_applicable_lessons(limit=5)
        assert len(retrieved) == 1

    def test_a_plus_identical_resubmission_reinforces_not_duplicates(self):
        learner = make_learner()
        first = learner.process_owner_message(
            "no, use httpx instead of requests",
            context={"situation": "e5_probe_situation"},
        )
        second = learner.process_owner_message(
            "no, use httpx instead of requests",  # identical text -> same situation_hash
            context={"situation": "e5_probe_situation"},
        )
        assert second.confidence >= first.confidence, "repeated confirmation must reinforce, not reset"
        assert second.times_applied >= 1

        retrieved = learner.retrieve_applicable_lessons(limit=5)
        assert len(retrieved) == 1, (
            "an identical resubmission must consolidate into ONE lesson, never silently "
            "accumulate as a second independent row"
        )

    def test_find_duplicate_uses_the_most_current_snapshot_not_the_first(self):
        """Direct proof of fix (a): after several reinforcements,
        _find_duplicate() must hand consolidation the CURRENT (highest
        confidence) state, not the original first-ever-stored row."""
        learner = make_learner()
        text = "hmm, use httpx"  # implicit pattern, starts below the 0.95 ceiling so reinforcement is visible
        ctx = {"situation": "e5_staleness_probe"}
        first = learner.process_owner_message(text, context=ctx)
        assert first.confidence < 0.95, "test setup: must start below the ceiling for this proof to be meaningful"
        for _ in range(3):
            learner.process_owner_message(text, context=ctx)

        found = learner._find_duplicate(first)
        assert found is not None
        assert found.confidence > first.confidence, (
            "_find_duplicate() must return the reinforced (current), not the "
            "original (stale), snapshot"
        )
        assert found.times_applied >= first.times_applied

    def test_retrieval_never_returns_stale_and_current_snapshots_together(self):
        """Direct proof of fix (b): retrieve_applicable_lessons() must never
        surface an old snapshot of a lesson alongside its own more-current
        replacement as if they were two separate lessons."""
        learner = make_learner()
        text = "no, use httpx instead of requests"
        ctx = {"situation": "e5_retrieval_probe"}
        for _ in range(4):
            learner.process_owner_message(text, context=ctx)

        retrieved = learner.retrieve_applicable_lessons(limit=10)
        assert len(retrieved) == 1, (
            f"expected exactly 1 deduplicated lesson, got {len(retrieved)}: "
            f"{[(r.id, r.confidence) for r in retrieved]}"
        )

    def test_restart_preserves_the_reinforced_state(self):
        shared_store = _FakeCorrectionStore()
        text = "no, use httpx instead of requests"
        ctx = {"situation": "e5_restart_probe"}
        learner1 = make_learner(shared_store)
        for _ in range(3):
            learner1.process_owner_message(text, context=ctx)
        before_restart = learner1.retrieve_applicable_lessons(limit=5)[0]

        learner2 = make_learner(shared_store)  # "restart": fresh instance, same durable store
        after_restart = learner2.retrieve_applicable_lessons(limit=5)
        assert len(after_restart) == 1
        assert after_restart[0].confidence == pytest.approx(before_restart.confidence, abs=0.001)
        assert after_restart[0].times_applied == before_restart.times_applied


@pytest.mark.unit
class TestIndependentCoLocatedCorrectionsStayIndependent:
    """Confirms the reverted decision was correct: genuinely independent,
    non-contradictory corrections about a shared broad situation remain
    separately retrievable -- this is the exact pre-existing behavior E5's
    investigation confirmed must NOT be broken."""

    def test_three_unrelated_tips_for_one_situation_all_remain_retrievable(self):
        learner = make_learner()
        ctx = {"situation": "e5_independent_tips_situation"}
        for utterance in [
            "no, use httpx instead of requests",
            "wrong, always use type hints",
            "actually, prefer async over sync",
        ]:
            lesson = learner.process_owner_message(utterance, context=ctx)
            assert lesson is not None

        retrieved = learner.retrieve_applicable_lessons(limit=10)
        assert len(retrieved) == 3, (
            "three genuinely independent tips for the same broad situation must "
            "all remain retrievable -- they must NOT be collapsed as if they "
            "contradicted each other"
        )


@pytest.mark.unit
class TestContradictionCannotEscalateAuthority:

    def test_correction_confidence_never_exceeds_the_documented_ceiling(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "no, wrong, that's incorrect, absolutely definitely use httpx",
            context={"situation": "e5_ceiling_probe"},
        )
        assert lesson.confidence <= 0.95

    def test_consolidation_does_not_touch_governance(self):
        import inspect
        src = inspect.getsource(CorrectionLearner._consolidate)
        assert "Governor" not in src
        assert "PermissionGateway" not in src

    def test_find_duplicate_does_not_touch_governance(self):
        import inspect
        src = inspect.getsource(CorrectionLearner._find_duplicate)
        assert "Governor" not in src
        assert "PermissionGateway" not in src


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
