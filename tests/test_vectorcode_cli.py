"""vectorcode's CLI, launched the way the owner launches it (vector.bat -> `python vectorcode/vector.py`, no
PYTHONPATH tweaks).

2026-09-24 findings: `status`, `sessions`, `models`, `skills`, `completion`, `plugins`, `auth` and `run` crashed
(bare imports needing vectorcode/src on sys.path; a `config/` package shadowing `config.py`; a `ModelRouter` and
`cmd_auth_*` functions that never existed), and `run` made one tool-less chat call that invented file contents.
Everything runs in child processes with a throwaway HOME/DB so nothing touches the owner's state.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = str(ROOT / "vectorcode" / "vector.py")


@pytest.fixture(scope="module")
def sandbox():
    home = Path(tempfile.mkdtemp(prefix="vc_cli_"))
    (home / "data").mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(home), USERPROFILE=str(home), VECTOR_HOME=str(home / "vhome"), VECTOR_DB_PATH=str(home / "vm.db"),
               VECTOR_TEST_DATA_DIR=str(home / "data"), VECTOR_DB_KEY="vc-cli-test", PYTHONIOENCODING="utf-8")
    return env, home


def _run(sandbox, *args, timeout=120):
    env, home = sandbox
    return subprocess.run([sys.executable, LAUNCHER, *args], capture_output=True, text=True, timeout=timeout,
                          env=env, cwd=str(home), encoding="utf-8", errors="replace")


@pytest.mark.parametrize("cmd", [
    ["status"], ["sessions"], ["models"], ["skills"], ["completion"], ["plugins"], ["auth", "list"],
    ["agents"], ["providers"], ["version"], ["doctor"],
])
def test_subcommand_runs_without_crashing(sandbox, cmd):
    r = _run(sandbox, *cmd)
    assert "Traceback" not in r.stdout + r.stderr, (r.stdout + r.stderr)[-800:]
    assert r.returncode == 0, (r.stdout + r.stderr)[-800:]


def test_models_lists_the_configured_models(sandbox):
    r = _run(sandbox, "models")
    assert "Configured models" in r.stdout and "ollama" in r.stdout


def test_run_without_a_task_prints_usage_instead_of_crashing(sandbox):
    r = _run(sandbox, "run", "--dir", str(sandbox[1]))
    assert "Traceback" not in r.stdout + r.stderr
    assert "Usage" in r.stdout


def test_run_refuses_honestly_when_the_agent_cannot_run(sandbox):
    """No model reachable under that name -> a clear error and a non-zero exit, never an invented answer."""
    env, home = sandbox
    (home / "notes.txt").write_text("hello\n", encoding="utf-8")
    r = _run(sandbox, "run", "--dir", str(home), "--model", "ollama/definitely-not-a-real-model-xyz",
             "Read notes.txt and tell me its contents", timeout=180)
    assert r.returncode == 1, (r.stdout + r.stderr)[-600:]
    assert "could not run" in r.stderr
    assert "hello" not in r.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
