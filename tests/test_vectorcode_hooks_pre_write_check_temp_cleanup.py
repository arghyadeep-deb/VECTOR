"""Regression for vectorcode/hooks/pre_write_check.py:

os.unlink(tmp_path) only ran on the success path (right after
py_compile.compile() returned without raising) -- never inside the
`except py_compile.PyCompileError` branch (the common, expected case: the
hook is specifically designed to catch and block syntax errors) nor the
generic `except Exception` branch. Every blocked write therefore leaked a
temp .py file in the system temp directory forever, since this hook fires
on every single Edit/Write tool call.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).parent.parent / "vectorcode" / "hooks" / "pre_write_check.py"


def _run_hook(content: str) -> subprocess.CompletedProcess:
    import json

    payload = json.dumps({"file_path": "example.py", "content": content})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
    )


def _stray_tmp_py_files() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("tmp*.py")}


def test_blocked_syntax_error_does_not_leak_temp_file():
    before = _stray_tmp_py_files()
    result = _run_hook("def broken(:\n    pass\n")
    after = _stray_tmp_py_files()

    assert result.returncode == 2
    assert after - before == set(), (
        f"pre_write_check.py leaked temp file(s): {after - before}"
    )


def test_valid_syntax_allows_write_and_does_not_leak_temp_file():
    before = _stray_tmp_py_files()
    result = _run_hook("def ok():\n    return 1\n")
    after = _stray_tmp_py_files()

    assert result.returncode == 0
    assert after - before == set()
