"""
VC-1 Core Foundation Tests
All tests exactly as specified in plan-vc1-core-foundation.md
"""

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Task 1: VectorCodeSession — shared state singleton
# ─────────────────────────────────────────────────────────────────────────────

from vectorcode.src.session import VectorCodeSession


def test_session_singleton():
    a = VectorCodeSession.get()
    b = VectorCodeSession.get()
    assert a is b


def test_session_fields():
    s = VectorCodeSession.get()
    assert hasattr(s, "mode")           # "repl" | "auto" | "hybrid"
    assert hasattr(s, "task_id")
    assert hasattr(s, "repo_path")
    assert hasattr(s, "history")        # list of {role, content}
    assert hasattr(s, "active_agents")
    assert hasattr(s, "current_model")


def test_session_set_mode_valid():
    s = VectorCodeSession.get()
    s.set_mode("auto")
    assert s.mode == "auto"
    s.set_mode("repl")
    assert s.mode == "repl"


def test_session_set_mode_invalid():
    s = VectorCodeSession.get()
    with pytest.raises(ValueError):
        s.set_mode("invalid_mode")


def test_session_reset():
    s = VectorCodeSession.get()
    s.history.append({"role": "user", "content": "hello"})
    s.active_agents.append("vector-coder")
    s.reset()
    assert s.history == []
    assert s.active_agents == []


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: SemanticRouter — model routing
# ─────────────────────────────────────────────────────────────────────────────

from vectorcode.src.router import SemanticRouter


def test_router_routes_code():
    r = SemanticRouter()
    assert r.route("write a function") == "vector-coder"


def test_router_routes_review():
    r = SemanticRouter()
    assert r.route("review this code") == "vector-dev"


def test_router_routes_plan():
    r = SemanticRouter()
    assert r.route("plan how to refactor") == "vector-reasoning"


def test_router_routes_quick():
    r = SemanticRouter()
    assert r.route("what is the status") == "vector-fast"


def test_router_switch_minimised():
    r = SemanticRouter()
    models = [r.route(t) for t in ["plan the task", "write the code", "review it"]]
    switches = sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])
    assert switches <= 3


def test_router_routes_deep():
    r = SemanticRouter()
    assert r.route("deep analysis of the codebase") == "vector-deep"


def test_router_routes_council():
    r = SemanticRouter()
    assert r.route("council vote on this critical decision") == "vector-chairman"


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: FileTools — read/write/edit/grep/glob
# ─────────────────────────────────────────────────────────────────────────────

from vectorcode.src.tools.file_tools import FileTools


def test_file_read_write(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("hello.py", "print('hello')")
    assert ft.read("hello.py") == "print('hello')"


def test_file_grep(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("code.py", "def foo():\n    pass\ndef bar():\n    pass")
    results = ft.grep("def ", "*.py")
    assert len(results) == 2


def test_file_glob(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("a.py", "x")
    ft.write("b.py", "y")
    assert len(ft.glob("*.py")) == 2


def test_file_edit(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("edit.py", "old_text")
    ft.edit("edit.py", "old_text", "new_text")
    assert ft.read("edit.py") == "new_text"


def test_file_blocks_traversal(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    with pytest.raises(PermissionError):
        ft.read("../../etc/passwd")


def test_file_exists(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("exists.py", "x")
    assert ft.exists("exists.py") is True
    assert ft.exists("nonexistent.py") is False


def test_file_diff(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    diff = ft.diff("foo.py", "old line\n", "new line\n")
    assert "-old line" in diff
    assert "+new line" in diff


def test_file_edit_raises_if_old_not_found(tmp_path):
    ft = FileTools(repo_root=str(tmp_path))
    ft.write("f.py", "hello")
    with pytest.raises(ValueError):
        ft.edit("f.py", "not_present", "replacement")


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: BashTools — safe command execution
# ─────────────────────────────────────────────────────────────────────────────

from vectorcode.src.tools.bash_tools import BashTools


def test_bash_allowed_command():
    bt = BashTools()
    result = bt.run(["python", "--version"])
    assert result.returncode == 0
    assert "Python" in (result.stdout + result.stderr)


def test_bash_blocks_rm_rf():
    bt = BashTools()
    with pytest.raises(PermissionError):
        bt.run(["rm", "-rf", "/"])


def test_bash_blocks_shell_true():
    bt = BashTools()
    with pytest.raises(PermissionError):
        bt.run(["bash", "-c", "whoami"])


def test_bash_timeout():
    import time
    bt = BashTools()
    start = time.time()
    with pytest.raises(TimeoutError):
        bt.run(["python", "-c", "import time; time.sleep(30)"], timeout=1)
    assert time.time() - start < 5


def test_bash_is_allowed_git():
    bt = BashTools()
    assert bt.is_allowed(["git", "status"]) is True


def test_bash_is_allowed_pytest():
    bt = BashTools()
    assert bt.is_allowed(["pytest", "tests/"]) is True


def test_bash_blocks_unknown_command():
    bt = BashTools()
    with pytest.raises(PermissionError):
        bt.run(["curl", "http://example.com"])


# ─────────────────────────────────────────────────────────────────────────────
# Task 5: InputValidator + PathValidator
# ─────────────────────────────────────────────────────────────────────────────

from vectorcode.src.security.validator import InputValidator, PathValidator


def test_path_validator_blocks_traversal(tmp_path):
    pv = PathValidator(repo_root=str(tmp_path))
    with pytest.raises(PermissionError):
        pv.validate("../secret")


def test_path_validator_allows_valid(tmp_path):
    pv = PathValidator(repo_root=str(tmp_path))
    result = pv.validate("src/main.py")
    assert result.endswith("src/main.py")


def test_input_validator_tool_call():
    iv = InputValidator()
    result = iv.validate_tool_call("read_file", {"path": "src/main.py"})
    assert result["path"] == "src/main.py"


def test_input_validator_rejects_empty_path():
    iv = InputValidator()
    with pytest.raises(ValueError):
        iv.validate_tool_call("read_file", {"path": ""})


def test_input_validator_rejects_unknown_tool():
    iv = InputValidator()
    with pytest.raises(ValueError):
        iv.validate_tool_call("unknown_tool", {"path": "x"})


def test_input_validator_write_file():
    iv = InputValidator()
    result = iv.validate_tool_call("write_file", {"path": "out.py", "content": "x = 1"})
    assert result["path"] == "out.py"
    assert result["content"] == "x = 1"


