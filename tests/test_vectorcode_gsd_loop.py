"""vectorcode's plan -> execute -> verify loop (`vector auto`).

2026-09-24 finding: `GSDLoop.run()` returned a trace of phase NAMES ("discuss, plan, execute, verify") without
running anything, and `vector auto` queued that on a daemon thread and exited -- a task that never ran was
reported as accepted. It must now run a real cycle through an executor, or say plainly that nothing ran.

Child process: vectorcode's bare imports need `vectorcode/src` on sys.path (its `mcp/`, `tools/`, `recipes/`
packages would otherwise shadow installed packages for the whole test run).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CHILD = r"""
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "vectorcode", "src"))
sys.path.insert(0, sys.argv[1])
from loguru import logger; logger.remove()
from gsd_loop import GSDLoop

def scripted(verdicts):
    calls = []
    it = iter(verdicts)
    def ex(prompt):
        calls.append(prompt.split("\n")[0][:14])
        if prompt.startswith("VERIFY"):
            return next(it)
        return "did the work"
    return ex, calls

out = {}
out["no_executor"] = GSDLoop(mode="auto").run("t")
ex, calls = scripted(["PASS all good"])
out["pass"] = GSDLoop(mode="auto", executor=ex).run("t"); out["pass_calls"] = calls
ex, calls = scripted(["FAIL missing file", "PASS now fine"])
out["retry"] = GSDLoop(mode="auto", executor=ex).run("t")
ex, calls = scripted(["FAIL a", "FAIL b", "FAIL c"])
out["always_fail"] = GSDLoop(mode="auto", executor=ex).run("t")
def boom(prompt): raise RuntimeError("model unreachable")
out["error"] = GSDLoop(mode="auto", executor=boom).run("t")
print("RESULT:" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    work = Path(tempfile.mkdtemp(prefix="vc_gsd_"))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(work / "home"), USERPROFILE=str(work / "home"), VECTOR_DB_PATH=str(work / "vm.db"), VECTOR_TEST_DATA_DIR=str(work / "data"), VECTOR_DB_KEY="vc-gsd-test")
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT)], capture_output=True, text=True, timeout=200,
                       env=env, cwd=str(work))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result:\n{r.stderr[-900:]}"
    return json.loads(lines[-1][len("RESULT:"):])


def test_without_an_executor_it_says_nothing_ran(result):
    r = result["no_executor"]
    assert r["status"] == "not_executed" and r["trace"] == [] and "nothing was run" in r["reason"]


def test_a_passing_task_runs_plan_execute_verify(result):
    r = result["pass"]
    assert r["status"] == "passed" and r["trace"] == ["plan", "execute", "verify"]
    assert r["output"] == "did the work" and r["verification"].startswith("PASS")


def test_a_failed_verification_triggers_another_attempt(result):
    r = result["retry"]
    assert r["status"] == "passed" and r["trace"] == ["plan", "execute", "verify", "execute", "verify"]


def test_gives_up_after_the_retry_limit_and_reports_failure(result):
    r = result["always_fail"]
    assert r["status"] == "failed" and r["trace"].count("execute") == 3


def test_an_executor_error_is_reported_not_swallowed(result):
    r = result["error"]
    assert r["status"] == "error" and "model unreachable" in r["reason"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
