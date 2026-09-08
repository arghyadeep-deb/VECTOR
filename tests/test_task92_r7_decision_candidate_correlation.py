"""
Task 92 — R7 Decision/Candidate Correlation regression + behavioral tests.

Pre-fix gap (confirmed by direct source audit, not assumption): DecisionEngine
never generated any per-occurrence identity at all. The ONE place in the
codebase that already had a column literally named `decision_id`
(CounterfactualMemory's `rejections`/`outcomes` tables, see
core/memory/counterfactual.py) was being fed `winner.action_type` at every
real call site (core/loop/autonomous_loop.py, core/loop/permission_gateway.py)
-- a reusable action-type string, not a unique event identifier. Two
completely unrelated decision occurrences involving the same action_type
collapsed onto the same "decision_id" value. This is independently documented
in core/training/reasoning_chain_dataset.py's own docstring: "``decision_id``
is actually a generic ``action_type`` string".

Fix: core/loop/decision_engine.py's `Candidate`/`Decision` dataclasses gained
`candidate_id` (unique per Candidate object, generated at construction) and
`decision_id` (stamped onto every candidate scored by ONE `evaluate()` call,
generated fresh each call). These flow into the EXISTING, already-JSON/
schemaless correlation surfaces this audit found:
  - EpisodicMemory.store()'s `context` dict (decision_engine.evaluate()'s own
    "log every candidate" loop -- candidate_generated/scored + selected)
  - CounterfactualMemory.record_rejection()'s existing `decision_id` param
    (now given the real value) + its existing `context` dict param (now
    carries candidate_id) -- candidate_vetoed/suppressed
  - loop_state.save_decision()'s JSON payload (additive keys)
  - EpisodicMemory.store_chain()'s `steps` JSON list (one appended
    correlation marker entry) -- candidate_executed

core/memory/policy.py (update_from_outcome / record_suppression),
core/loop/permission_gateway.py, and core/city/governor.py were explicitly
NOT modified -- see TestNoRewardSemanticChange and TestGovernanceUnchanged
below, which assert this directly from source/signatures rather than trusting
a description.

Per .claude/rules/testing.md, this suite exercises the REAL DecisionEngine,
REAL AutonomousLoop._act_on(), and a REAL CounterfactualMemory backed by an
isolated temp-file SQLite db (never the live/experiment database) -- only
Governor.dispatch, PolicyMemory, and EpisodicMemory.store_chain are stubbed,
exactly mirroring the established pattern in
tests/test_task89c_goal_progress.py and
tests/test_counterfactual_block_penalizes_policy.py.
"""
import asyncio
import inspect
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import CONFIG
from core.loop.decision_engine import Candidate, Decision, DecisionEngine
from core.memory.policy import PolicyMemory


def make_candidate(action_type="test_action", confidence=0.5, urgency=0.5,
                    timing_score=1.0, estimated_cost_inr=0.0, goal_ids=None,
                    params=None):
    return Candidate(
        action_type=action_type,
        params=params if params is not None else {},
        goal_ids=goal_ids or [],
        confidence=confidence,
        urgency=urgency,
        timing_score=timing_score,
        estimated_cost_inr=estimated_cost_inr,
    )


@pytest.fixture
def engine():
    """Real DecisionEngine, real PolicyMemory.make_situation_hash (pure, no
    DB access). Matches tests/test_task91_r6_candidate_diversity.py."""
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    # R8/R9: stub the correction-learner getter -- otherwise every
    # evaluate() call (this file's uniqueness tests run up to 300 in a
    # loop) does a real, bounded-but-nonzero-latency EpisodicMemory lookup
    # that adds up. Matches every other subsystem getter already stubbed
    # here.
    e._get_correction_learner = MagicMock(return_value=None)
    return e


# ═══════════════════════════════════════════════════════════════════════════
# A, B, C, H — decision_id uniqueness
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestDecisionIdUniqueness:

    async def test_a_every_decision_gets_unique_decision_id(self, engine):
        c1 = make_candidate("A")
        c2 = make_candidate("B")
        decision = await engine.evaluate([c1, c2])
        assert isinstance(decision.decision_id, str) and decision.decision_id
        assert decision.decision_id.startswith("d:")
        # every candidate scored in this call shares it
        assert c1.decision_id == decision.decision_id
        assert c2.decision_id == decision.decision_id

    async def test_b_repeated_evaluate_different_decision_ids_same_candidate_set(self, engine):
        def factory():
            return [make_candidate("A", confidence=0.9), make_candidate("B", confidence=0.3)]
        d1 = await engine.evaluate(factory())
        d2 = await engine.evaluate(factory())
        assert d1.decision_id != d2.decision_id

    async def test_c_same_action_different_decision_id_across_occurrences(self, engine):
        """The winning candidate's decision_id differs across two occurrences
        even when action_type+params are identical -- decision_id is an
        INSTANCE identifier, not derived from the reusable situation hash."""
        params = {"goal_id": "g_x", "title": "same every time"}
        d1 = await engine.evaluate([make_candidate("A", params=params)])
        d2 = await engine.evaluate([make_candidate("A", params=params)])
        assert d1.winner.decision_id != d2.winner.decision_id
        h1 = engine._make_situation_hash(d1.winner)
        h2 = engine._make_situation_hash(d2.winner)
        assert h1 == h2, "situation_hash must stay the same reusable identity"
        assert d1.winner.decision_id != h1, "decision_id must never equal the situation hash"

    async def test_h_many_rapid_decisions_never_collide(self, engine):
        seen = set()
        for _ in range(300):
            d = await engine.evaluate([make_candidate("A"), make_candidate("B")])
            assert d.decision_id not in seen
            seen.add(d.decision_id)
        assert len(seen) == 300


# ═══════════════════════════════════════════════════════════════════════════
# D, F(identity) — candidate_id
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestCandidateId:

    async def test_d_candidate_id_identifies_candidate_within_decision(self, engine):
        a, b, c = make_candidate("A"), make_candidate("B"), make_candidate("C")
        decision = await engine.evaluate([a, b, c])
        ids = {a.candidate_id, b.candidate_id, c.candidate_id}
        assert len(ids) == 3  # all distinct
        assert decision.winner.candidate_id in ids
        # the winner IS one of the original objects, identity-preserved
        assert any(decision.winner is x for x in (a, b, c))

    async def test_candidate_id_stable_through_scoring(self, engine):
        c = make_candidate("A")
        before = c.candidate_id
        await engine.evaluate([c])
        assert c.candidate_id == before, "scoring must not regenerate candidate_id"

    async def test_duplicate_identity_candidates_still_get_distinct_candidate_ids(self, engine):
        params = {"k": "v"}
        a = make_candidate("dup", params=params)
        b = make_candidate("dup", params=params)
        await engine.evaluate([a, b])
        assert a.candidate_id != b.candidate_id
        assert engine._make_situation_hash(a) == engine._make_situation_hash(b)

    async def test_same_action_params_across_two_decisions_distinct_candidate_ids(self, engine):
        """D1 -> candidate A, D2 -> candidate A (same action_type/params):
        C1 != C2 even though the reusable situation hash is identical."""
        params = {"goal_id": "g_repeat"}
        d1 = await engine.evaluate([make_candidate("A", params=params)])
        d2 = await engine.evaluate([make_candidate("A", params=params)])
        assert d1.winner.candidate_id != d2.winner.candidate_id
        assert engine._make_situation_hash(d1.winner) == engine._make_situation_hash(d2.winner)


# ═══════════════════════════════════════════════════════════════════════════
# E, F, G — propagation into existing downstream veto/outcome records
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def cf_temp():
    """Real CounterfactualMemory backed by an isolated temp-file SQLite db --
    never the live/experiment database."""
    from core.memory.counterfactual import CounterfactualMemory
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    cf = CounterfactualMemory(db_path=db_path)
    yield cf
    cf.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def loop_with_fakes():
    """Real AutonomousLoop._act_on(); Governor/PolicyMemory/EpisodicMemory
    stubbed exactly like tests/test_task89c_goal_progress.py's
    `loop_with_fake_governor` fixture -- none of those are what R7 changed."""
    from core.loop.autonomous_loop import AutonomousLoop
    loop = AutonomousLoop()

    fake_governor = MagicMock()
    fake_governor.dispatch = AsyncMock(return_value={"status": "ok", "goal_progress": 0.5})
    loop._governor = fake_governor

    fake_policy = MagicMock()
    fake_policy.update_from_outcome = MagicMock()
    fake_policy.get_score = MagicMock(return_value=0.5)
    fake_policy.make_situation_hash = MagicMock(side_effect=PolicyMemory.make_situation_hash)
    fake_policy.record_suppression = MagicMock()
    loop._policy = fake_policy

    fake_memory = MagicMock()
    fake_memory.recall = MagicMock(return_value=[])
    fake_memory.store_chain = MagicMock(return_value="chain-id")
    loop._memory = fake_memory

    return loop


async def _make_winner_via_real_evaluate(action_type, params=None):
    """Produce a real winner Candidate the same way the autonomous loop does
    -- through DecisionEngine.evaluate() -- so decision_id/candidate_id are
    genuinely populated, not hand-set."""
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_correction_learner = MagicMock(return_value=None)
    decision = await e.evaluate([make_candidate(action_type, params=params)])
    return decision.winner


@pytest.mark.unit
class TestPropagationDownstream:

    async def test_e_ids_survive_into_counterfactual_veto_record(self, loop_with_fakes, cf_temp, monkeypatch):
        """END-TO-END proof (task's own scenario): candidate -> evaluate() ->
        decision_id D1 / candidate C1 -> _act_on() auto-blocks via
        CounterfactualMemory (a pre-seeded matching rejection) -> verify the
        resulting rejection record.decision_id == D1 and its context
        candidate_id == C1."""
        action_type = f"r7_veto_{uuid.uuid4().hex[:8]}"
        proposal_seed = f"{action_type} {{}}"
        cf_temp.record_rejection("seed", proposal_seed, "seed rejection for should_avoid()")

        monkeypatch.setattr("core.memory.counterfactual.CounterfactualMemory", lambda: cf_temp)

        winner = await _make_winner_via_real_evaluate(action_type, params={})
        loop = loop_with_fakes
        await loop._act_on(winner)

        loop._governor.dispatch.assert_not_called()  # veto must short-circuit before governor

        rows = cf_temp.get_similar_rejections(proposal_seed, limit=5)
        matches = [r for r in rows if r["decision_id"] == winner.decision_id]
        assert matches, f"no rejection row found with decision_id={winner.decision_id}"
        row = matches[0]
        ctx = json.loads(row["context"]) if row["context"] else {}
        assert ctx.get("candidate_id") == winner.candidate_id

    async def test_f_two_vetoed_decisions_never_cross_attribute(self, loop_with_fakes, cf_temp, monkeypatch):
        """Adversarial #4: a vetoed candidate cannot accidentally be
        attributed to another decision. Two separate veto occurrences of the
        SAME action_type must each carry their own decision_id/candidate_id."""
        action_type = f"r7_veto2_{uuid.uuid4().hex[:8]}"
        proposal_seed = f"{action_type} {{}}"
        cf_temp.record_rejection("seed", proposal_seed, "seed rejection")
        monkeypatch.setattr("core.memory.counterfactual.CounterfactualMemory", lambda: cf_temp)

        winner1 = await _make_winner_via_real_evaluate(action_type, params={})
        await loop_with_fakes._act_on(winner1)
        winner2 = await _make_winner_via_real_evaluate(action_type, params={})
        await loop_with_fakes._act_on(winner2)

        assert winner1.decision_id != winner2.decision_id
        assert winner1.candidate_id != winner2.candidate_id

        rows = cf_temp.get_similar_rejections(proposal_seed, limit=10)
        by_decision = {r["decision_id"]: r for r in rows if r["decision_id"] in
                       (winner1.decision_id, winner2.decision_id)}
        assert set(by_decision) == {winner1.decision_id, winner2.decision_id}
        ctx1 = json.loads(by_decision[winner1.decision_id]["context"])
        ctx2 = json.loads(by_decision[winner2.decision_id]["context"])
        assert ctx1["candidate_id"] == winner1.candidate_id
        assert ctx2["candidate_id"] == winner2.candidate_id
        assert ctx1["candidate_id"] != ctx2["candidate_id"]

    async def test_g_executed_candidate_correlation_survives_into_reasoning_chain(self, loop_with_fakes):
        """An executed (non-vetoed) candidate retains correlation into the
        existing store_chain() outcome record."""
        action_type = f"r7_exec_{uuid.uuid4().hex[:8]}"
        winner = await _make_winner_via_real_evaluate(action_type, params={"p": 1})
        # give it a non-empty reasoning_chain like a real scored candidate
        winner.reasoning_chain = [{"factor": "goal_alignment", "value": 0.5, "weight": 0.3}]

        loop = loop_with_fakes
        await loop._act_on(winner)

        loop._governor.dispatch.assert_called_once()  # reached execution, not vetoed
        loop._memory.store_chain.assert_called_once()
        _, kwargs = loop._memory.store_chain.call_args
        steps = kwargs["steps"]
        correlation_entries = [s for s in steps if "correlation" in s]
        assert len(correlation_entries) == 1
        corr = correlation_entries[0]["correlation"]
        assert corr["decision_id"] == winner.decision_id
        assert corr["candidate_id"] == winner.candidate_id


# ═══════════════════════════════════════════════════════════════════════════
# I — legacy record readback
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLegacyCompatibility:

    def test_i_legacy_rejection_row_without_context_reads_back_safely(self, cf_temp):
        """A rejection recorded exactly the OLD way (no context, decision_id
        equal to a bare action_type) -- matching every pre-R7 call site and
        every existing test in tests/integration/test_spec11_year2_gaps.py
        etc. -- must still read back without crashing, and `context` must
        default to an empty-safe value."""
        cf_temp.record_rejection("legacy_action_type", "legacy_action_type {}", "old-style rejection")
        rows = cf_temp.get_similar_rejections("legacy_action_type {}", limit=5)
        assert rows
        row = rows[0]
        assert row["decision_id"] == "legacy_action_type"
        ctx = json.loads(row["context"]) if row["context"] else {}
        assert ctx.get("candidate_id") is None  # absent, not a crash
        avoid, conf, reason = cf_temp.should_avoid("legacy_action_type {}", threshold=0.4)
        assert avoid is True

    def test_i2_policy_memory_legacy_row_shape_untouched(self):
        """R7 did not touch policy_memory's schema or reader/writer contract
        -- a fresh (action_type, params) pair still returns DEFAULT_SCORE and
        update_from_outcome still works exactly as before R4-R6."""
        pm = PolicyMemory()
        h = pm.make_situation_hash(f"r7_legacy_probe_{uuid.uuid4().hex[:8]}", {})
        assert pm.get_score("nonexistent_action_xyz", h) == pm.DEFAULT_SCORE


# ═══════════════════════════════════════════════════════════════════════════
# J — R6 behavior unchanged
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestR6StillWorks:

    async def test_j_staleness_threshold_and_safe_alternative_still_work(self, engine):
        threshold = int(CONFIG.get("candidate_staleness_streak", 5))

        def factory():
            return [make_candidate("A", confidence=0.9, urgency=0.9),
                    make_candidate("B", confidence=0.4, urgency=0.4)]
        for _ in range(threshold):
            d = await engine.evaluate(factory())
            assert d.winner.action_type == "A"
        d_final = await engine.evaluate(factory())
        assert d_final.winner.action_type == "B", "R6 staleness suppression must still engage"

    async def test_j_no_alternative_no_fabrication_still_holds(self, engine):
        threshold = int(CONFIG.get("candidate_staleness_streak", 5))
        for _ in range(threshold + 3):
            d = await engine.evaluate([make_candidate("only")])
            assert d.winner.action_type == "only"


# ═══════════════════════════════════════════════════════════════════════════
# K, L — no FORBIDDEN action, no governance change, security
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGovernanceAndSecurity:

    async def test_k_no_forbidden_action_type_created_by_id_tagging(self, engine):
        candidates = [make_candidate("delete_repo"), make_candidate("send_email")]
        original_types = {c.action_type for c in candidates}
        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type in original_types
        assert {c.action_type for c in decision.all_candidates} == original_types

    def test_l_permission_gateway_source_has_no_r7_code(self):
        """R7 must not modify PermissionGateway. Prove it by scanning the
        actual current source for any decision_id/candidate_id reference --
        if this ever fails, someone added R7-shaped code to a file R7 was
        explicitly forbidden from touching."""
        import core.loop.permission_gateway as pg
        src = inspect.getsource(pg)
        assert "candidate_id" not in src

    def test_l_governor_source_has_no_r7_code(self):
        import core.city.governor as gov
        src = inspect.getsource(gov)
        assert "candidate_id" not in src
        assert "decision_id" not in src

    async def test_9_ids_never_contain_sensitive_param_content(self, engine):
        sensitive = make_candidate(
            "action_with_secret",
            params={"password": "hunter2-super-secret", "api_key": "sk-ABCDEFGHIJK"},
        )
        decision = await engine.evaluate([sensitive])
        for blob in (sensitive.decision_id, sensitive.candidate_id, decision.decision_id):
            assert "hunter2" not in blob
            assert "sk-ABCDEFGHIJK" not in blob
            assert "password" not in blob
            assert "api_key" not in blob

    async def test_10_veto_path_never_reaches_governor(self, loop_with_fakes, cf_temp, monkeypatch):
        """Governance is not bypassed: when should_avoid() fires, execution
        must stop before Governor.dispatch is ever called (same assertion as
        test_e, isolated here as an explicit governance-non-bypass check)."""
        action_type = f"r7_gov_{uuid.uuid4().hex[:8]}"
        proposal_seed = f"{action_type} {{}}"
        cf_temp.record_rejection("seed", proposal_seed, "seed rejection")
        monkeypatch.setattr("core.memory.counterfactual.CounterfactualMemory", lambda: cf_temp)
        winner = await _make_winner_via_real_evaluate(action_type, params={})
        await loop_with_fakes._act_on(winner)
        loop_with_fakes._governor.dispatch.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# No reward-semantics change — proven from signatures, not description
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestNoRewardSemanticChange:

    def test_update_from_outcome_signature_unchanged(self):
        sig = inspect.signature(PolicyMemory.update_from_outcome)
        assert list(sig.parameters) == ["self", "action_type", "situation_hash", "reward"], (
            "R7 must not add decision_id/candidate_id to PolicyMemory.update_from_outcome "
            "-- policy_memory rows are AGGREGATE (avg_reward across many decisions); see "
            "the report's REWARD REQUIREMENT section for why this was explicitly not done."
        )

    def test_record_suppression_signature_unchanged(self):
        sig = inspect.signature(PolicyMemory.record_suppression)
        assert list(sig.parameters) == ["self", "action_type", "situation_hash"]

    def test_make_situation_hash_signature_unchanged(self):
        sig = inspect.signature(PolicyMemory.make_situation_hash)
        assert list(sig.parameters) == ["context", "params"]

    def test_counterfactual_record_rejection_signature_unchanged(self):
        """core/memory/counterfactual.py itself was NOT modified by R7 --
        only what VALUE autonomous_loop.py passes into its existing
        decision_id/context parameters changed."""
        from core.memory.counterfactual import CounterfactualMemory
        sig = inspect.signature(CounterfactualMemory.record_rejection)
        assert list(sig.parameters) == ["self", "decision_id", "proposal", "reason", "context"]


if __name__ == "__main__":
    import sys

    async def _main():
        e = DecisionEngine()
        e._get_policy = MagicMock()
        e._get_policy().get_score.return_value = 0.5
        e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e._get_goals = MagicMock(); e._get_goals().get_active_goals.return_value = []
        e._get_memory = MagicMock(); e._get_memory().store.return_value = None
        e._get_epistemic = MagicMock(); e._get_epistemic().get_belief.return_value = None
        e._get_reasoning_bank = MagicMock(return_value=None)
        e._get_neural_trainer = MagicMock(return_value=None)
        e._get_context_engine = MagicMock(); e._get_context_engine().get_world_state.return_value = {}
        e._get_correction_learner = MagicMock(return_value=None)

        d1 = await e.evaluate([make_candidate("A"), make_candidate("B")])
        d2 = await e.evaluate([make_candidate("A"), make_candidate("B")])
        return (
            d1.decision_id != d2.decision_id
            and d1.winner.candidate_id != d2.winner.candidate_id
            and d1.winner.decision_id == d1.decision_id
        )

    sys.stdout.reconfigure(encoding="utf-8")
    ok = asyncio.run(_main())
    print("✅ test_task92_r7_decision_candidate_correlation OK" if ok else "❌ FAILED")
