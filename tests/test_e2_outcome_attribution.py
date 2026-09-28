"""
E2 — Outcome Attribution.

Question: does VECTOR know what happened AFTER a decision, and does that
knowledge attribute correctly?

AUDIT SUMMARY (full detail: VECTOR_TECHNICAL_KNOWLEDGE/E2_OUTCOME_ATTRIBUTION_REPORT.md):

Reward writers found in core/loop/autonomous_loop.py's _act_on() family:
  1. Main path (~line 1313): reward = uf*0.40 + goal_progress*0.25 +
     not_overridden*0.15 + not_corrected*0.15 + completed*0.05 -- REAL
     computed signal (user_feedback if present, else a completion-based
     estimate; district-reported goal_progress if present, else a
     documented 0.5 default; real override/correction flags).
  2. VectorCode path (~line 1092): reward = 0.8 if status=="ok" else 0.3 --
     a HARDCODED binary proxy for success/failure, not a computed signal.
  3. Plan-step path (_act_on_plan_step, ~line 1596): reward = 0.7 if
     status=="completed" else 0.3 -- same HARDCODED binary pattern.

THE BUG FOUND AND FIXED (this stage): the plan-step writer computed its own
situation_hash via `hashlib.sha256(f"plan_step:{action_type}:{json.dumps(
params, sort_keys=True)}")` instead of calling PolicyMemory's own canonical
`make_situation_hash()` -- a SEPARATE identity namespace from every other
reward writer/reader in this codebase. A reward learned from executing a
plan step could never be read back by DecisionEngine scoring the identical
(action_type, params) as a regular candidate, and vice versa -- the reward
was recorded, but effectively unattributable to future decisions about the
same real situation. This exact writer was already identified as a 4th
non-canonical caller during Task 89 (D2) and explicitly deferred as an
"identity-merge design question" rather than silently left broken -- E2's
explicit authorization to perform minimal reader/writer reconnection closes
it now, using the identical reasoning as R9's core/runtime/plans.py fix.

Nothing here creates a new Experience table, fabricates a production
outcome, or changes what reward VALUE is computed for either path -- only
which situation_hash key the plan-step reward is filed under.
"""
import inspect

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

from core.loop.decision_engine import DecisionEngine
from core.memory.policy import PolicyMemory


@pytest.mark.unit
class TestPlanStepIdentityFix:

    def test_plan_step_writer_no_longer_uses_separate_hash_scheme(self):
        """The pre-fix bug, proven directly from source: the old ad-hoc
        sha256(f"plan_step:...") construction is gone from the actual
        _act_on_plan_step method body (a historical mention of the removed
        pattern in an explanatory comment is expected and fine -- only the
        real code construct matters here)."""
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert 'sk = f"plan_step:' not in src
        assert "hashlib.sha256(sk.encode())" not in src

    def test_plan_step_writer_now_uses_canonical_make_situation_hash(self):
        """Direct proof the fixed writer calls the SAME canonical identity
        function decision_engine.py's reader (_score_candidate ->
        get_score()) uses -- reusing the existing identity, not introducing
        a second one."""
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert "pm.make_situation_hash(winner.action_type, winner.params)" in src

    def test_plan_step_reward_now_lands_in_the_same_bucket_decision_engine_reads(self):
        """Behavioral proof: a reward recorded the way _act_on_plan_step now
        does is genuinely readable by decision_engine's own scoring path for
        the identical (action_type, params) situation -- the exact causal
        connection that was broken before this fix."""
        import uuid
        pm = PolicyMemory()
        action_type = f"e2_plan_step_probe_action_{uuid.uuid4().hex[:8]}"
        params = {"goal_id": "g_e2_probe"}

        # Simulate the FIXED plan-step writer exactly as autonomous_loop.py
        # now does it.
        h_plan_step_writer = pm.make_situation_hash(action_type, params)
        pm.update_from_outcome(action_type, h_plan_step_writer, 0.7)

        # decision_engine._score_candidate()'s reader path, independently
        # reconstructed the same way it always computes it.
        e = DecisionEngine()
        from core.loop.decision_engine import Candidate
        candidate = Candidate(action_type=action_type, params=params)
        h_reader = e._make_situation_hash(candidate)

        assert h_plan_step_writer == h_reader
        score = pm.get_score(action_type, h_reader)
        assert score == pytest.approx(0.7, abs=0.01), (
            "a reward recorded via the fixed plan-step writer must be readable "
            "by decision_engine's own scoring path for the same real situation"
        )


@pytest.mark.unit
class TestRewardWriterHonesty:
    """Documents, with a direct behavioral/source assertion (not just prose),
    which reward writers use a real computed signal vs. a hardcoded proxy --
    E2's own required audit output, made testable so it cannot silently
    drift out of sync with the report."""

    def test_main_reward_path_uses_a_real_weighted_formula(self):
        # RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR2_MEANINGFUL_UTILITY_REPORT.md):
        # this test used to pin the exact bug RR-2 fixes -- E2's own audit
        # documented `result.get("goal_progress", 0.5)` as "the one
        # HARDCODED sub-component of an otherwise real, computed reward"
        # and asserted its continued presence so it "does not hide that it
        # exists". RG-D/RR-0 later proved this exact fallback fabricated a
        # "half advanced my goal" credit for every action with NO attached
        # goal (e.g. repeated read_code), inflating its reward to ~0.755.
        # RR-2 removed the fallback: unknown goal_progress now contributes
        # 0 (not a fabricated 0.5) to the weighted sum, verified via
        # explicit key-presence checking rather than a `.get(..., default)`.
        # This test now pins the FIX instead of the bug it replaced.
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on)
        assert "uf * 0.40" in src
        assert "goal_progress * 0.25" in src
        # The literal old-bug string still appears in this function's own
        # RR-2 explanatory comment (quoting what the bug used to look like)
        # -- so the "gone" check must look only at executable statements,
        # not prose, the same way r16's own AST-based attack test does.
        import ast
        import textwrap
        tree = ast.parse(textwrap.dedent(src))
        func_body = tree.body[0].body
        if func_body and isinstance(func_body[0], ast.Expr) and isinstance(func_body[0].value, ast.Constant):
            func_body = func_body[1:]
        code_only = ast.unparse(ast.Module(body=func_body, type_ignores=[]))
        assert 'result.get(\'goal_progress\', 0.5)' not in code_only, (
            "the old goal_progress default-to-0.5 fallback (RG-D/RR-0's "
            "proven fabricated-positive-reward bug) must be gone from the "
            "real executable code (comments may still discuss it)"
        )
        assert '_goal_progress_known' in code_only, (
            "goal_progress must now be read via explicit key-presence "
            "checking, not a silently-defaulting .get(..., 0.5) fallback"
        )

    def test_vectorcode_reward_is_a_documented_hardcoded_binary(self):
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on)
        assert "reward = 0.8 if vc_result.get" in src

    def test_plan_step_reward_is_a_documented_hardcoded_binary(self):
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert "reward = 0.7 if completed else 0.3" in src

    def test_policy_memory_reward_writer_signature_unchanged(self):
        """E2 changed WHICH hash a caller passes in, never the reward-writing
        contract itself."""
        sig = inspect.signature(PolicyMemory.update_from_outcome)
        assert list(sig.parameters) == ["self", "action_type", "situation_hash", "reward"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
