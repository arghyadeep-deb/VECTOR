"""Audit phase 3 (MCP expansion modules A): argument injection, path confinement,
secret redaction and failure-reported-as-success. tmp_path only, never the real repo."""
from __future__ import annotations

import json
import asyncio
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mcp_tools.expansion_modules import config as m_config
from core.mcp_tools.expansion_modules import files as m_files
from core.mcp_tools.expansion_modules import git as m_git
from core.mcp_tools.expansion_modules import hooks as m_hooks
from core.mcp_tools.expansion_modules import security as m_security
from core.mcp_tools.expansion_modules import swarm as m_swarm
from core.mcp_tools.expansion_modules import tasks as m_tasks
from core.mcp_tools.expansion_modules import workers as m_workers


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, fn=None, **kw):
        def deco(f):
            self.tools[f.__name__] = f
            return f
        return deco(fn) if fn else deco


def load(module, adder, root: Path | None = None, monkeypatch=None):
    if root is not None:
        monkeypatch.setattr(module, "_ROOT", root, raising=False)
    mcp = FakeMCP()
    adder(mcp)
    return mcp.tools


def call(fn, *a, **k):
    result = fn(*a, **k)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return json.loads(result)


@pytest.fixture(autouse=True)
def approve_destructive_tool_gates(monkeypatch):
    async def approve(*_args, **_kwargs):
        return SimpleNamespace(approved=True, level="RED", reason="approved")

    for module in (m_config, m_files, m_tasks, m_workers):
        monkeypatch.setattr(module, "evaluate_destructive_action", approve)


# ---------------------------------------------------------------- git
@pytest.fixture
def git_tools(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return load(m_git, m_git.add_git_tools, tmp_path, monkeypatch), calls


@pytest.mark.parametrize("tool,arg", [
    ("git_checkout", "--orphan"), ("git_checkout", "-f"), ("git_merge", "--upload-pack=x"),
    ("git_rebase", "--exec=touch pwned"), ("git_branch", "-D"), ("git_checkout", "a..b"),
    ("git_merge", "x y"),
])
def test_git_refs_starting_with_dash_rejected(git_tools, tool, arg):
    tools, calls = git_tools
    out = call(tools[tool], arg)
    assert out["ok"] is False and "invalid" in out["error"]
    assert calls == []


def test_git_checkout_valid_ref_uses_double_dash(git_tools):
    tools, calls = git_tools
    assert call(tools["git_checkout"], "feature/x")["ok"] is True
    assert calls == [["git", "checkout", "feature/x", "--"]]


def test_git_push_rejects_transport_remote_and_option_branch(git_tools):
    tools, calls = git_tools
    assert call(tools["git_push"], "ext::sh -c id", "main")["ok"] is False
    assert call(tools["git_push"], "--receive-pack=x", "main")["ok"] is False
    assert call(tools["git_push"], "origin", "--force")["ok"] is False
    assert call(tools["git_push"], "origin", "main")["ok"] is True
    assert calls == [["git", "push", "origin", "main"]]


def test_git_commit_add_uses_double_dash_and_blocks_secrets(git_tools):
    tools, calls = git_tools
    out = call(tools["git_commit"], "msg", ".env")
    assert out["ok"] is False and calls == []
    out = call(tools["git_commit"], "msg", "-f,a.py")
    assert calls[0] == ["git", "add", "--", "-f"]  # '-f' is a path, never the force option
    assert out["ok"] is True


def test_git_commit_add_failure_not_reported_as_success(tmp_path, monkeypatch):
    def fake_run(cmd, **kw):
        if cmd[:2] == ["git", "add"]:
            return SimpleNamespace(returncode=128, stdout="", stderr="fatal: pathspec")
        return SimpleNamespace(returncode=0, stdout="committed", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    tools = load(m_git, m_git.add_git_tools, tmp_path, monkeypatch)
    out = call(tools["git_commit"], "msg", "nope.py")
    assert out["ok"] is False and "pathspec" in out["error"]


def test_git_stash_unknown_action_does_not_stash(git_tools):
    tools, calls = git_tools
    assert call(tools["git_stash"], "list")["ok"] is False
    assert calls == []


def test_git_log_clamps_n_and_reports_failure(tmp_path, monkeypatch):
    seen = []
    def fake_run(cmd, **kw):
        seen.append(cmd)
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")
    monkeypatch.setattr(subprocess, "run", fake_run)
    tools = load(m_git, m_git.add_git_tools, tmp_path, monkeypatch)
    out = call(tools["git_log"], 10**9)
    assert seen[0] == ["git", "log", "-200", "--oneline"]
    assert out["ok"] is False and "not a git repository" in out["error"]


def test_git_blame_double_dash_and_secret_path(git_tools):
    tools, calls = git_tools
    assert call(tools["git_blame"], ".env")["ok"] is False
    call(tools["git_blame"], "a.py")
    assert calls == [["git", "blame", "-n", "--", "a.py"]]


def test_git_real_repo_checkout_dash_ref_does_not_run(tmp_path, monkeypatch):
    # real git in a throwaway repo: '--orphan' must not create an orphan branch
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tools = load(m_git, m_git.add_git_tools, tmp_path, monkeypatch)
    out = call(tools["git_checkout"], "--orphan")
    assert out["ok"] is False
    head = (tmp_path / ".git" / "HEAD").read_text()
    assert "--orphan" not in head


# ---------------------------------------------------------------- files
@pytest.fixture
def file_tools(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("hello\n")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / "core" / "loop").mkdir(parents=True)
    (tmp_path / "core" / "config.py").write_text("x=1\n")
    return load(m_files, m_files.add_file_tools, tmp_path, monkeypatch)


def test_file_read_blocks_sibling_prefix_dir(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    evil = tmp_path / "repo-evil"
    evil.mkdir()
    (evil / "x.txt").write_text("stolen")
    tools = load(m_files, m_files.add_file_tools, root, monkeypatch)
    out = call(tools["file_read"], "../repo-evil/x.txt")  # str.startswith would accept this
    assert out["error"] == "Path traversal denied"


def test_file_read_denies_env_and_ok_reads_file(file_tools):
    assert "denied" in call(file_tools["file_read"], ".env")["error"]
    assert call(file_tools["file_read"], "a.txt")["content"]["content"] == "hello"


def test_file_read_missing_surfaces_error(file_tools):
    out = call(file_tools["file_read"], "nope.txt")
    assert out["ok"] is False and "not found" in out["error"].lower()


def test_file_symlink_escape_denied(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("s")
    (root / "lnk").symlink_to(outside)
    tools = load(m_files, m_files.add_file_tools, root, monkeypatch)
    assert call(tools["file_read"], "lnk")["error"] == "Path traversal denied"


def test_file_write_protected_path_denied(file_tools):
    assert "Protected" in call(file_tools["file_write"], "core/config.py", "x")["error"]
    assert "Protected" in call(file_tools["file_edit"], ".claude/settings.json", "a", "b")["error"]


def test_file_delete_and_copy_require_coding_grant(file_tools, tmp_path):
    out = call(file_tools["file_delete"], "a.txt")
    assert out["ok"] is False and "grant" in out["error"]
    assert (tmp_path / "a.txt").exists()
    out = call(file_tools["file_copy"], "a.txt", "b.txt")
    assert out["ok"] is False and not (tmp_path / "b.txt").exists()


def test_file_delete_and_copy_with_grant_still_protect_files(file_tools, tmp_path, monkeypatch):
    import core.loop.permission_gateway as pg
    monkeypatch.setattr(pg, "is_coding_grant_active", lambda: True)
    assert "Protected" in call(file_tools["file_delete"], "core/config.py")["error"]
    assert "denied" in call(file_tools["file_copy"], ".env", "leak.txt")["error"]
    assert "Protected" in call(file_tools["file_copy"], "a.txt", "core/config.py")["error"]
    assert call(file_tools["file_copy"], "a.txt", "b.txt")["ok"] is True
    assert call(file_tools["file_delete"], "b.txt")["ok"] is True


def test_file_grep_rejects_option_pattern(file_tools, monkeypatch):
    import districts.coding.coding_tools as ct
    seen = []
    monkeypatch.setattr(ct, "grep_code", lambda *a, **k: seen.append(a) or {"matches": []})
    out = call(file_tools["file_grep"], "--pre=/bin/sh", ".")
    assert "must not start" in out["error"] and seen == []


def test_file_grep_returns_matches_from_dict_result(file_tools, monkeypatch, tmp_path):
    import districts.coding.coding_tools as ct
    monkeypatch.setattr(ct, "grep_code", lambda p, path, **k: {"matches": [{"file": "a.txt", "line": 1, "text": "hello"}], "count": 1})
    # tools were bound at load time to the original grep_code, so reload
    tools = load(m_files, m_files.add_file_tools, tmp_path, monkeypatch)
    out = call(tools["file_grep"], "hello", ".")
    assert out["results"][0]["text"] == "hello"


def test_file_grep_path_outside_root_denied(file_tools):
    assert call(file_tools["file_grep"], "x", "/etc")["error"] == "Path traversal denied"


def test_file_glob_and_exists_confined(file_tools):
    assert "denied" in call(file_tools["file_glob"], "../*")["error"]
    assert "denied" in call(file_tools["file_glob"], "/etc/*")["error"]
    assert ".env" not in call(file_tools["file_glob"], "*")["matches"]
    assert call(file_tools["file_exists"], "../../etc/passwd")["error"] == "Path traversal denied"
    assert call(file_tools["file_list_dir"], "..")["error"] == "Path traversal denied"


def test_file_diff_failure_not_reported_as_no_changes(file_tools, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository"))
    out = call(file_tools["file_diff"], "a.txt")
    assert out["ok"] is False and "No changes" not in json.dumps(out)


# ---------------------------------------------------------------- config
@pytest.fixture
def cfg_tools(tmp_path, monkeypatch):
    return load(m_config, m_config.add_config_tools, tmp_path, monkeypatch)


def test_config_get_does_not_echo_secrets(cfg_tools):
    from core.config import CONFIG
    CONFIG["db_key"] = "SUPER-SECRET-DB-KEY"
    CONFIG.setdefault("coding", {})["github_token"] = "ghp_leak"
    try:
        assert "SUPER-SECRET" not in cfg_tools["config_get"]("db_key")
        assert "ghp_leak" not in cfg_tools["config_get"]("coding")
        assert "ghp_leak" not in cfg_tools["config_list"]()
        assert "SUPER-SECRET" not in cfg_tools["config_diff"]()
        assert "ghp_leak" not in cfg_tools["config_export"]()
    finally:
        CONFIG.pop("db_key", None)


def test_config_env_redacts_secret_env(cfg_tools, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("VECTOR_DB_KEY", "dbk-leak")
    out = cfg_tools["config_env"]()
    assert "sk-leak" not in out and "dbk-leak" not in out


def test_config_set_apply_cannot_touch_permission_or_shell(cfg_tools):
    from core.config import CONFIG
    before = json.dumps(CONFIG.get("permission"), default=str)
    out = call(cfg_tools["config_set"], "permission", "{}")
    assert out["ok"] is False
    out = call(cfg_tools["config_apply"], json.dumps({"permission": {}, "allow_shell_exec": True}))
    assert out["ok"] is False and set(out["denied"]) == {"permission", "allow_shell_exec"}
    assert json.dumps(CONFIG.get("permission"), default=str) == before


def test_config_restore_and_import_confined(cfg_tools, tmp_path):
    (tmp_path / "evil.txt").write_text("PWNED=1")
    assert call(cfg_tools["config_restore"], "evil.txt")["ok"] is False
    assert not (tmp_path / ".env").exists()
    assert call(cfg_tools["config_restore"], "../../etc/passwd")["ok"] is False
    assert "traversal" in call(cfg_tools["config_import"], "/etc/passwd")["error"].lower()


# ---------------------------------------------------------------- hooks
def test_hook_name_traversal_rejected(tmp_path, monkeypatch):
    import core.brain_hooks as bh
    ran = []
    monkeypatch.setattr(bh, "run_hook", lambda n, d="": ran.append(n) or ("", 0))
    tools = load(m_hooks, m_hooks.add_hook_tools, tmp_path, monkeypatch)
    out = call(tools["hook_fire"], "../../evil", "{}")
    assert out["result"]["ok"] is False and ran == []


def test_hook_nonzero_exit_reported(tmp_path, monkeypatch):
    import core.brain_hooks as bh
    monkeypatch.setattr(bh, "run_hook", lambda n, d="": ("boom", 1))
    tools = load(m_hooks, m_hooks.add_hook_tools, tmp_path, monkeypatch)
    out = call(tools["hook_fire"], "session-start", "{}")
    assert out["result"]["ok"] is False and out["result"]["exit_code"] == 1


def test_hook_register_does_not_claim_registered(tmp_path, monkeypatch):
    tools = load(m_hooks, m_hooks.add_hook_tools, tmp_path, monkeypatch)
    out = call(tools["hook_register"], "pre_edit", "rm -rf /")
    assert out["ok"] is False and out["status"] != "registered"


# ---------------------------------------------------------------- workers / tasks
class FakeTQ:
    def __init__(self):
        self.submitted = []
    def cancel(self, tid):
        return False
    def submit(self, work, name, **kw):
        self.submitted.append(name)
        return "tid1"
    def summary(self):
        return {"n": 1}


@pytest.fixture
def worker_tools(tmp_path, monkeypatch):
    import core.loop.task_queue as tqm
    tq = FakeTQ()
    monkeypatch.setattr(tqm, "get_task_queue", lambda: tq)
    return load(m_workers, m_workers.add_worker_tools, tmp_path, monkeypatch)


def test_worker_cancel_false_not_reported_ok(worker_tools):
    assert call(worker_tools["worker_cancel"], "missing")["ok"] is False


def test_task_delete_false_not_reported_ok(tmp_path, monkeypatch):
    import core.loop.task_queue as tqm
    monkeypatch.setattr(tqm, "get_task_queue", lambda: FakeTQ())
    tools = load(m_tasks, m_tasks.add_task_tools, tmp_path, monkeypatch)
    assert call(tools["task_delete"], "missing")["ok"] is False


def test_worker_export_confined_and_json_only(worker_tools, tmp_path):
    victim = tmp_path / "core" / "config.py"
    victim.parent.mkdir(parents=True)
    victim.write_text("keep")
    assert call(worker_tools["worker_export"], "core/config.py")["ok"] is False
    assert victim.read_text() == "keep"
    assert call(worker_tools["worker_export"], "../escape.json")["ok"] is False
    assert not (tmp_path.parent / "escape.json").exists()
    assert call(worker_tools["worker_export"], "out.json")["ok"] is True
    assert (tmp_path / "out.json").exists()


def test_worker_import_confined(worker_tools):
    assert "traversal" in call(worker_tools["worker_import"], "/etc/passwd")["error"].lower()


def test_worker_scale_bounded(worker_tools):
    from core.config import CONFIG
    prev = dict(CONFIG.get("task_queue", {}))
    try:
        assert call(worker_tools["worker_scale"], 10**9)["ok"] is False
        assert call(worker_tools["worker_scale"], 0)["ok"] is False
        assert CONFIG.get("task_queue", {}).get("max_concurrent") == prev.get("max_concurrent")
    finally:
        CONFIG["task_queue"] = prev


def test_worker_timeout_noop_not_reported_ok(worker_tools):
    assert call(worker_tools["worker_timeout"], "t1", 5)["ok"] is False


# ---------------------------------------------------------------- security / swarm
def test_security_path_check_sibling_prefix(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "repo-evil").mkdir()
    tools = load(m_security, m_security.add_security_tools, root, monkeypatch)
    assert call(tools["security_path_check"], "../repo-evil/x")["safe"] is False
    assert call(tools["security_path_check"], "src/x.py")["safe"] is True
    assert call(tools["security_path_check"], "/etc/passwd")["safe"] is False


def test_security_cve_scan_failure_not_reported_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="boom"))
    tools = load(m_security, m_security.add_security_tools, tmp_path, monkeypatch)
    out = call(tools["security_cve_scan"], ".")
    assert out["ok"] is False and "clean" not in json.dumps(out).lower()


def test_security_cve_scan_uses_real_pip_audit_binary(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: seen.append(cmd) or SimpleNamespace(returncode=0, stdout="{}", stderr=""))
    tools = load(m_security, m_security.add_security_tools, tmp_path, monkeypatch)
    out = call(tools["security_cve_scan"], ".")
    assert seen[0][0] == "pip-audit" and out["ok"] is True and out["vulnerable"] is False


def test_security_scan_async_scanner_not_reported_as_result(tmp_path, monkeypatch):
    import districts.security.threat_scout as ts

    class Scout:
        async def scan_file(self, p):
            return {"clean": True}

    monkeypatch.setattr(ts, "ThreatScout", Scout)
    tools = load(m_security, m_security.add_security_tools, tmp_path, monkeypatch)
    out = call(tools["security_scan"], "a.py")
    assert out["ok"] is False and "NOT scanned" in out["error"]


def test_swarm_submit_without_dispatch_not_reported_dispatched(tmp_path, monkeypatch):
    import core.swarm.orchestrator as orch
    monkeypatch.setattr(orch, "get_orchestrator", lambda: SimpleNamespace())
    tools = load(m_swarm, m_swarm.add_swarm_tools, tmp_path, monkeypatch)
    out = call(tools["swarm_submit"], "x", "{}")
    assert out["ok"] is False and out.get("status") != "dispatched"


def test_swarm_execute_unawaited_coroutine_not_a_result(tmp_path, monkeypatch):
    import core.swarm.orchestrator as orch

    class O:
        async def parallel_dispatch(self, t):
            return [{"ok": True}]

    monkeypatch.setattr(orch, "get_orchestrator", lambda: O())
    tools = load(m_swarm, m_swarm.add_swarm_tools, tmp_path, monkeypatch)
    out = call(tools["swarm_execute"], "[]")
    assert out["ok"] is False and "NOT executed" in out["error"]
