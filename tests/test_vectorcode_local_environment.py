"""vectorcode's local shell backend on Windows.

2026-09-24 findings: `terminal`, `read_file`, `patch` and `search_files` all returned an EMPTY result with a
success status. Root causes: (1) the output drain used select() on a pipe (sockets only on Windows), so the
drain thread exited immediately and every command's output was dropped; (2) stdin was written through a
text-mode wrapper that turned LF into CRLF, so `write_file` changed line endings and `patch` then failed its
own verification; (3) the POSIX /tmp cwd file was unreadable from Windows Python.

The checks run in a child process: vectorcode's bare imports need `vectorcode/src` on sys.path, whose
`mcp/`, `tools/` and `recipes/` packages would otherwise shadow installed packages for the whole test run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash on PATH")

_CHILD = r"""
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "vectorcode", "src"))
sys.path.insert(0, sys.argv[1])
from loguru import logger; logger.remove()
work = sys.argv[2]; os.chdir(work)
from tools.environments.local import LocalEnvironment, _msys_to_windows
from tools import registry as R
import model_tools
reg = R.registry
out = {}
env = LocalEnvironment(cwd=work)
r = env.execute("echo hi-from-bash && cat notes.txt")
out["execute"] = r
out["cwd_after"] = env.cwd
out["msys"] = [_msys_to_windows("/c/Users/x"), _msys_to_windows("/c"), _msys_to_windows("C:\\Users\\x"), _msys_to_windows("/tmp")]
out["read"] = json.loads(reg.dispatch("read_file", {"path": "notes.txt"}))
out["terminal"] = json.loads(reg.dispatch("terminal", {"command": "echo tool-terminal-ok"}))
out["write"] = json.loads(reg.dispatch("write_file", {"path": "out.txt", "content": "written by tool\n"}))
out["patch"] = json.loads(reg.dispatch("patch", {"mode": "replace", "path": "out.txt", "old_string": "written", "new_string": "patched"}))
out["bytes"] = open("out.txt", "rb").read().decode()
out["search"] = json.loads(reg.dispatch("search_files", {"pattern": "line two", "path": "."}))
print("RESULT:" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    work = Path(tempfile.mkdtemp(prefix="vc_env_"))
    (work / "notes.txt").write_bytes(b"hello\nline two\n")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(work / "home"), USERPROFILE=str(work / "home"), VECTOR_DB_PATH=str(work / "vm.db"), VECTOR_TEST_DATA_DIR=str(work / "data"), VECTOR_DB_KEY="vc-env-test")
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT), str(work)], capture_output=True, text=True,
                       timeout=240, env=env, cwd=str(work))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result:\n{r.stderr[-800:]}"
    return json.loads(lines[-1][len("RESULT:"):])


def test_execute_returns_the_command_output(result):
    assert "hi-from-bash" in result["execute"]["output"]
    assert "hello" in result["execute"]["output"] and "line two" in result["execute"]["output"]
    assert result["execute"]["returncode"] == 0


def test_cwd_marker_is_stripped_from_output(result):
    assert "__VECTOR_CWD_" not in result["execute"]["output"]


def test_cwd_is_reported_as_a_native_path(result):
    if os.name == "nt":
        assert result["cwd_after"][1:3] == ":\\"


def test_msys_paths_convert_to_windows_paths(result):
    assert result["msys"] == ["C:\\Users\\x", "C:\\", "C:\\Users\\x", "/tmp"]


def test_read_file_returns_the_real_content(result):
    assert result["read"]["total_lines"] == 2 and "line two" in result["read"]["content"]


def test_terminal_tool_returns_output(result):
    assert result["terminal"]["output"] == "tool-terminal-ok" and result["terminal"]["exit_code"] == 0


def test_write_file_keeps_lf_line_endings(result):
    assert result["write"]["bytes_written"] == len("written by tool\n")


def test_patch_persists_and_verifies(result):
    assert result["patch"]["success"] is True
    assert result["bytes"] == "patched by tool\n"


def test_search_files_finds_the_match(result):
    assert result["search"]["total_count"] == 1 and result["search"]["matches"][0]["line"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
