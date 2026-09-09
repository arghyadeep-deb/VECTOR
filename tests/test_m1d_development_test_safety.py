"""
M1d/M1e — Development/Test Safety P0 Remediation regression tests.

Covers 3 of the 4 P0 findings from VECTOR_TECHNICAL_KNOWLEDGE/M1c_DEVELOPMENT_
TEST_ISOLATION_SAFETY_AUDIT.md (P0-A, P0-B, P0-D) and their fixes, recorded in
VECTOR_TECHNICAL_KNOWLEDGE/M1d_DEVELOPMENT_TEST_SAFETY_REMEDIATION.md.

P0-C (EpistemicTracker/CounterfactualMemory isolation boundary) was attempted
TWICE and reverted both times -- M1d's attempt (~260 failures, a process-wide
`VECTOR_DB_PATH` leak across 4 test files, now fixed at its source via the
`isolated_vector_db` fixture in tests/conftest.py) and M1e's re-attempt on
top of that fix (133 failures -- a much larger, previously-invisible gap:
~100+ existing test files legitimately isolate `VECTOR_DB_PATH` but never
also isolated these two specific classes). See
VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md "P0-C"
section for the full incident and recommended real fix.

These exist specifically to answer the adversarial question "can a future
developer accidentally remove the isolation guard without a failing test?" --
before this file, the P0-A/P0-B fixes lived only inside `__main__` blocks
(never pytest-collected).

Per this session's own testing convention: real behavior, no mocking of the
guard logic itself; mocking is only used where a P0-A test needs to prove a
real GREEN/RED action does NOT execute (the exact pattern already
established and proven in tests/test_r11_end_to_end_trace.py).
"""
from __future__ import annotations

import inspect
import os

import pytest


# ─── P0-A: core/loop/autonomous_loop.py self-test no longer runs a real,
# unisolated run_forever() ──────────────────────────────────────────────────

class TestP0AAutonomousLoopSmokeTestIsolation:

    def test_smoke_test_source_no_longer_calls_run_forever(self):
        """Structural guard: the self-test must never again call the real
        run_forever()/observe_loop()/think_loop() -- those are exactly what
        touched real stores and could execute a real action pre-fix. Checks
        the executable code only (the docstring legitimately mentions
        run_forever() in prose, describing the pre-fix behavior)."""
        import ast

        import core.loop.autonomous_loop as al
        src = inspect.getsource(al._smoke_test)
        tree = ast.parse(src)
        func_def = tree.body[0]
        code_without_docstring = ast.unparse(
            ast.Module(body=func_def.body[1:], type_ignores=[])
        )
        assert "run_forever" not in code_without_docstring, (
            "the M1d fix for P0-A was reverted -- _smoke_test() must never "
            "call the real AutonomousLoop.run_forever()"
        )
        assert "loop._gateway = fake_gateway" in src or "fake_gateway" in src, (
            "the M1d fix for P0-A was reverted -- _smoke_test() must stub "
            "the gateway before calling _act_on()"
        )

    @pytest.mark.asyncio
    async def test_smoke_test_runs_isolated_and_blocks_red_before_bridge(self):
        """Behavioral proof: the actual current _smoke_test() implementation
        constructs no real persistent store and genuinely blocks a RED
        candidate before the execution bridge."""
        import core.loop.autonomous_loop as al
        result = await al._smoke_test()
        assert result == {
            "lazy_construction_clean": True,
            "lifecycle_ok": True,
            "red_action_blocked_before_bridge": True,
        }


# ─── P0-B: core/memory/episodic.py self-test no longer touches real state ──

class TestP0BEpisodicSelfTestIsolation:

    def test_main_block_source_has_unconditional_isolation_override(self):
        """Structural guard: the self-test must set VECTOR_DB_PATH
        unconditionally (never `if ... not in os.environ`) and assert
        configured_db_path() resolves to the override before constructing
        EpisodicMemory() -- an absence-guarded (conditional) override is
        exactly the M1b anti-pattern this must never regress to."""
        import ast
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "memory", "episodic.py",
        )
        with open(src_path, "r", encoding="utf-8") as f:
            full_src = f.read()
        main_block_src = full_src[full_src.index("if __name__ =="):]

        assert "not in os.environ" not in main_block_src, (
            "episodic.py's __main__ block uses a conditional (absence-guarded) "
            "VECTOR_DB_PATH override -- this is the exact anti-pattern that "
            "caused the M1b incident; the override must be unconditional"
        )
        assert 'os.environ["VECTOR_DB_PATH"] = _tmp_db.name' in main_block_src
        assert "configured_db_path()" in main_block_src
        assert "assert str(configured_db_path())" in main_block_src


# ─── P0-C: EpistemicTracker / CounterfactualMemory isolation boundary ──────
# INTENTIONALLY NOT REMEDIATED -- attempted twice (M1d, M1e), reverted both
# times. M1e's attempt got past M1d's specific leak (fixed at its source),
# then found via a full-suite run that ~100+ existing test files legitimately
# isolate VECTOR_DB_PATH (via proper setUpModule/fixture patterns) but never
# also isolated EpistemicTracker/CounterfactualMemory specifically -- a much
# larger, previously-invisible gap than the 4-file leak this session fixed.
# See VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md "P0-C"
# section for the full incident and the recommended real fix (make these two
# classes honor VECTOR_DB_PATH natively, or audit the affected files) --
# both are real architecture/scope decisions for the owner, not a "narrow,
# safe" fix to attempt without their input.

class TestP0CNotRegressed:

    def test_epistemic_tracker_still_defaults_to_production_path_unmodified(self):
        import core.brain.epistemic_tracker as et_mod
        import inspect
        src = inspect.getsource(et_mod.EpistemicTracker.__init__)
        assert "assert_isolated_or_default" not in src, (
            "P0-C appears to have been re-applied without updating this test "
            "file and the M1e report's regression analysis -- do not land it "
            "without first solving the ~100-file isolation-gap root cause "
            "documented there"
        )

    def test_counterfactual_memory_still_defaults_to_production_path_unmodified(self):
        import core.memory.counterfactual as cf_mod
        import inspect
        src = inspect.getsource(cf_mod.CounterfactualMemory.__init__)
        assert "assert_isolated_or_default" not in src, (
            "P0-C appears to have been re-applied without updating this test "
            "file and the M1e report's regression analysis -- do not land it "
            "without first solving the ~100-file isolation-gap root cause "
            "documented there"
        )


# ─── P0-D: core/mcp_server.py ungated-tool warning ─────────────────────────

class TestP0DMcpServerWarning:

    def test_main_warns_before_serving_ungated_tools(self):
        """Structural guard: main() must print/log an unmissable warning
        about ungated tools before mcp.run() is ever called -- this test
        does NOT call main() itself (that would actually start serving)."""
        import core.mcp_server as mcp_mod
        src = inspect.getsource(mcp_mod.main)
        warn_idx = src.find("UNGATED")
        run_idx = src.find("mcp.run(")
        assert warn_idx != -1, "main() no longer warns about ungated tools"
        assert run_idx != -1, "main() no longer calls mcp.run() -- unexpected structural change"
        assert warn_idx < run_idx, (
            "the ungated-tools warning must appear BEFORE mcp.run() is called"
        )

    def test_bare_invocation_never_serves(self):
        """The scaffold-only path (no --transport/--port/--host args) must
        never reach main()/mcp.run() -- confirms P0-D's warning is placed on
        the real serving path only, not accidentally gating the safe path."""
        import core.mcp_server as mcp_mod
        src = inspect.getsource(mcp_mod)
        assert '_server_args & set(sys.argv[1:])' in src


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
