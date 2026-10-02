"""Regression: FastAPIReviewer/PythonReviewer/SecurityReviewer's run()
filename-read branch read any caller-supplied path with zero confinement --
same bug class fixed in code_reviewer.py/architect_bot.py/bug_hunter.py/
code_explorer.py/minimal_change_engineer.py this cycle. Governor-dispatchable
via {"type": "review_fastapi"/"review_python"/"review_security", "params":
{"filename": ...}}. Ironic for security_reviewer.py specifically: this is the
exact "path traversal" vulnerability class the agent itself exists to
detect in other code.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.fastapi_reviewer import FastAPIReviewer
from districts.coding.python_reviewer import PythonReviewer
from districts.coding.security_reviewer import SecurityReviewer


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_fastapi_reviewer_rejects_path_outside_repo(tmp_path):
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'real-secret'\n")
    result = _run(FastAPIReviewer().run({"type": "review_fastapi", "params": {"filename": str(outside)}}))
    assert "error" in result
    assert "outside repo" in result["error"].lower() or "not a .py file" in result["error"].lower()


def test_python_reviewer_rejects_path_outside_repo(tmp_path):
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'real-secret'\n")
    result = _run(PythonReviewer().run({"type": "review", "params": {"filename": str(outside)}}))
    assert "error" in result
    assert "outside repo" in result["error"].lower() or "not a .py file" in result["error"].lower()


def test_security_reviewer_rejects_path_outside_repo(tmp_path):
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'real-secret'\n")
    result = _run(SecurityReviewer().run({"type": "review_security", "params": {"filename": str(outside)}}))
    assert "error" in result
    assert "outside repo" in result["error"].lower() or "not a .py file" in result["error"].lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
