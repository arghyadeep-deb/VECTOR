"""Wave 1 tool tests — file ops, bash, delegate, memory, web, mcp, vision, cron, todo."""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "python"))


# ── File tools ────────────────────────────────────────────────────────────────

def test_read_file_basic():
    from vectorcode.tools.file_tools import read_file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        tmp = f.name
    try:
        result = read_file(tmp)
        assert "hello world" in result
    finally:
        os.unlink(tmp)


def test_read_file_not_found():
    from vectorcode.tools.file_tools import read_file
    result = json.loads(read_file("/nonexistent/path/file.txt"))
    assert "error" in result


def test_write_file_creates_file():
    from vectorcode.tools.file_tools import write_file
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.txt")
        result = json.loads(write_file(path, "content here"))
        assert result["success"] is True
        assert open(path).read() == "content here"


def test_patch_replaces_string():
    from vectorcode.tools.file_tools import write_file, patch
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        tmp = f.name
    try:
        result = json.loads(patch(tmp, "world", "python"))
        assert result["success"] is True
        assert open(tmp).read() == "hello python"
    finally:
        os.unlink(tmp)


def test_patch_not_found():
    from vectorcode.tools.file_tools import write_file, patch
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        tmp = f.name
    try:
        result = json.loads(patch(tmp, "nonexistent", "replacement"))
        assert "error" in result
    finally:
        os.unlink(tmp)


def test_search_files_by_name():
    from vectorcode.tools.file_tools import search_files
    result = json.loads(search_files(path=".", file_pattern="*.py", max_results=5))
    assert "files" in result or "matches" in result


def test_search_files_by_content():
    from vectorcode.tools.file_tools import search_files
    result = json.loads(search_files(path="vectorcode/python/vectorcode/tools", pattern="def read_file"))
    assert "matches" in result
    assert result["count"] >= 1


# ── Terminal ──────────────────────────────────────────────────────────────────

def test_bash_echo():
    from vectorcode.tools.terminal import bash
    result = json.loads(bash("echo hello"))
    assert "hello" in result["stdout"]
    assert result["returncode"] == 0


def test_bash_cd_updates_cwd():
    from vectorcode.tools.terminal import bash, _get_cwd
    original = _get_cwd()
    result = json.loads(bash(f"cd {original}"))
    assert result["returncode"] == 0


def test_bash_timeout():
    from vectorcode.tools.terminal import bash
    result = json.loads(bash("python -c \"import time; time.sleep(10)\"", timeout=1))
    assert "error" in result or result.get("returncode", 0) != 0


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_has_tools():
    from vectorcode.tools.registry import ToolRegistry
    reg = ToolRegistry.global_instance()
    names = reg.get_all_tool_names()
    assert "read_file" in names
    assert "write_file" in names
    assert "bash" in names


def test_registry_dispatch_unknown():
    from vectorcode.tools.registry import ToolRegistry
    reg = ToolRegistry.global_instance()
    result = reg.handle_function_call("nonexistent_tool_xyz", {})
    assert "not registered" in result


def test_registry_get_tool_definitions():
    from vectorcode.tools.registry import ToolRegistry
    reg = ToolRegistry.global_instance()
    defs = reg.get_tool_definitions("coding")
    assert len(defs) > 0
    assert all("function" in d for d in defs)


# ── Todo ──────────────────────────────────────────────────────────────────────

def test_todo_lifecycle():
    from vectorcode.tools.todo_tool import todo_add, todo_list_all, todo_complete, todo_remove
    # Add
    r = json.loads(todo_add("test task"))
    assert r["success"] is True
    tid = r["id"]
    # List
    todos = json.loads(todo_list_all())["todos"]
    assert any(t["id"] == tid for t in todos)
    # Complete
    r2 = json.loads(todo_complete(tid))
    assert r2["success"] is True
    # Remove
    r3 = json.loads(todo_remove(tid))
    assert r3["success"] is True


# ── Cron ──────────────────────────────────────────────────────────────────────

def test_cron_add_list_remove():
    from vectorcode.tools.cron_tools import cron_add, cron_list, cron_remove
    r = json.loads(cron_add("0 9 * * *", "daily summary"))
    assert r["success"] is True
    job_id = r["id"]
    jobs = json.loads(cron_list())["jobs"]
    assert any(j["id"] == job_id for j in jobs)
    r2 = json.loads(cron_remove(job_id))
    assert r2["success"] is True


# ── Binary extensions ─────────────────────────────────────────────────────────

def test_binary_extensions():
    from vectorcode.tools.binary_extensions import has_binary_extension
    assert has_binary_extension("image.png") is True
    assert has_binary_extension("script.py") is False
    assert has_binary_extension("archive.zip") is True
    assert has_binary_extension("README.md") is False


# ── Path security ─────────────────────────────────────────────────────────────

def test_path_security():
    from vectorcode.tools.path_security import validate_within_dir, has_traversal_component
    root = Path("/tmp/safe")
    assert validate_within_dir(Path("/tmp/safe/file.txt"), root) is None
    assert validate_within_dir(Path("/etc/passwd"), root) is not None
    assert has_traversal_component("../etc/passwd") is True
    assert has_traversal_component("src/main.py") is False
