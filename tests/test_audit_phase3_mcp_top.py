"""Phase 3 audit: top-level core/mcp_tools/* regression tests.

Every test drives the real tool function through a tiny fake MCP registry and fakes
only the downstream collaborator (subprocess, ObsidianSync, claims, ...), asserting
the concrete behaviour. No network, no real subprocess, no real DB or repo writes.
"""
import asyncio
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.mcp_tools import builtins as builtins_mod


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, fn=None, **_):
        def deco(f):
            self.tools[f.__name__] = f
            return f
        return deco(fn) if fn is not None else deco

    def resource(self, *_a, **_k):
        return lambda f: f


def _call(fn, *a, **k):
    out = fn(*a, **k)
    if asyncio.iscoroutine(out):
        out = asyncio.run(out)
    return out


def _tools(adder):
    m = FakeMCP()
    adder(m)
    return m.tools


def _install(monkeypatch, dotted, **attrs):
    """Install a fake module (and parents) into sys.modules."""
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        name = ".".join(parts[:i])
        if name not in sys.modules or i == len(parts):
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    mod = sys.modules[dotted]
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# --- marketing_cli: subprocess failure must not look like success -------------

def test_marketing_cli_nonzero_exit_is_reported_as_error(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(returncode=2, stdout="", stderr="boom: bad token")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = tools["marketing_cli"]("activecampaign", '{"a": 1}')
    assert out.startswith("CLI error for 'activecampaign'")
    assert "exit code 2" in out and "boom: bad token" in out
    argv, kw = calls[0]
    assert argv[0] == "node" and argv[1].endswith("activecampaign.js")
    assert kw["input"] == '{"a": 1}' and "shell" not in kw


def test_marketing_cli_success_returns_stdout(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kw: SimpleNamespace(returncode=0, stdout="fine\n", stderr=""))
    tools = _tools(builtins_mod.add_builtin_tools)
    assert tools["marketing_cli"]("activecampaign") == "fine"


def test_marketing_cli_rejects_traversal_name(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    tools = _tools(builtins_mod.add_builtin_tools)
    assert "Invalid tool name" in tools["marketing_cli"]("../../etc/x")


# --- review_code: prefix-confusion + await-on-sync ----------------------------

def test_review_code_rejects_sibling_dir_with_shared_prefix(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    evil = tmp_path / "repo_evil"
    root.mkdir()
    evil.mkdir()
    secret = evil / "x.py"
    secret.write_text("x = 1\n")
    monkeypatch.setattr(builtins_mod, "_ROOT", root)
    reviewed = []
    _install(monkeypatch, "districts.coding.code_reviewer",
             CodeReviewer=lambda: SimpleNamespace(review_file=lambda p: reviewed.append(p) or {}))
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["review_code"], str(secret))
    assert out.startswith("Access denied")
    assert reviewed == []


def test_review_code_runs_sync_reviewer_and_returns_result(monkeypatch, tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    monkeypatch.setattr(builtins_mod, "_ROOT", tmp_path)
    _install(monkeypatch, "districts.coding.code_reviewer",
             CodeReviewer=lambda: SimpleNamespace(review_file=lambda p: {"file": p, "score": 97}))
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["review_code"], str(f))
    assert "'score': 97" in out and not out.startswith("Code review failed")


def test_review_code_refuses_non_python_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("KEY=secret\n")
    monkeypatch.setattr(builtins_mod, "_ROOT", tmp_path)
    tools = _tools(builtins_mod.add_builtin_tools)
    assert _call(tools["review_code"], str(env)).startswith("Access denied")


# --- write_note: title traversal ----------------------------------------------

@pytest.mark.parametrize("title", ["../../evil", "a/b", "..\\x", "x..y", " "])
def test_write_note_rejects_path_in_title(monkeypatch, title):
    writes = []

    class FakeSync:
        def write_note(self, **kw):
            writes.append(kw)

    _install(monkeypatch, "core.memory.obsidian_sync", ObsidianSync=FakeSync)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["write_note"], title, "body", "Research", "")
    assert out.startswith("Note write failed")
    assert writes == []


def test_write_note_valid_title_still_writes(monkeypatch):
    writes = []

    class FakeSync:
        def write_note(self, **kw):
            writes.append(kw)

    _install(monkeypatch, "core.memory.obsidian_sync", ObsidianSync=FakeSync)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["write_note"], "My Note", "body", "Research", "a, b")
    assert "written" in out
    assert writes == [{"title": "My Note", "content": "body", "folder": "Research", "tags": ["a", "b"]}]


# --- search_vault: ObsidianSync.query is async and has no top_k ---------------

def test_search_vault_awaits_async_query(monkeypatch):
    class FakeSync:
        async def query(self, text, mode="hybrid"):
            return f"hit:{text}:{mode}"

    _install(monkeypatch, "core.memory.obsidian_sync", ObsidianSync=FakeSync)
    tools = _tools(builtins_mod.add_builtin_tools)
    assert _call(tools["search_vault"], "alpha", 3) == "hit:alpha:hybrid"


# --- mine_reddit ---------------------------------------------------------------

def test_mine_reddit_uses_real_miner_method(monkeypatch):
    seen = []

    class FakeMiner:
        async def fetch_hot(self, sub, limit=10):
            seen.append((sub, limit))
            return [{"title": "t"}]

    _install(monkeypatch, "districts.research.reddit_miner", RedditMiner=FakeMiner)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["mine_reddit"], "LocalLLaMA", 4)
    assert json.loads(out) == [{"title": "t"}] and seen == [("LocalLLaMA", 4)]


def test_mine_reddit_rejects_bad_subreddit_and_empty_result(monkeypatch):
    class FakeMiner:
        async def fetch_hot(self, sub, limit=10):
            return []

    _install(monkeypatch, "districts.research.reddit_miner", RedditMiner=FakeMiner)
    tools = _tools(builtins_mod.add_builtin_tools)
    assert "invalid subreddit" in _call(tools["mine_reddit"], "../admin")
    assert _call(tools["mine_reddit"], "empty").startswith("Reddit mining failed")


# --- read_paper: SSRF + nonexistent .read() ------------------------------------

def test_read_paper_blocks_internal_url(monkeypatch):
    used = []
    _install(monkeypatch, "districts.research.paper_reader",
             PaperReader=lambda: used.append(1) or SimpleNamespace())
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["read_paper"], "http://169.254.169.254/latest/meta-data")
    assert "blocked" in out and used == []


def test_read_paper_arxiv_url_searches_by_id(monkeypatch):
    seen = []

    class FakeReader:
        async def search_papers(self, q, max_results=5):
            seen.append((q, max_results))
            return [{"title": "Attention"}]

    _install(monkeypatch, "districts.research.paper_reader", PaperReader=FakeReader)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["read_paper"], "https://arxiv.org/abs/1706.03762")
    assert seen == [("1706.03762", 1)] and "Attention" in out


# --- git_status / ask_user_question ---------------------------------------------

def test_git_status_empty_result_is_failure(monkeypatch):
    _install(monkeypatch, "districts.coding.git_bot",
             GitBot=lambda: SimpleNamespace(get_status=lambda: {}))
    tools = _tools(builtins_mod.add_builtin_tools)
    assert _call(tools["git_status"]).startswith("Git status failed")


def test_ask_user_question_pushes_sync_and_reports_success(monkeypatch):
    pushed = []

    class FakeNudge:
        def push(self, text, source="proactive", need="", priority=0.8):
            pushed.append((text, priority))
            return {"text": text}

    _install(monkeypatch, "core.loop.nudge_engine", NudgeEngine=FakeNudge)
    tools = _tools(builtins_mod.add_builtin_tools)
    out = _call(tools["ask_user_question"], "Deploy?", ["yes", "no"])
    assert out == "Question sent to owner: Deploy?"
    assert pushed and pushed[0][1] <= 1.0 and "1. yes" in pushed[0][0]


# --- claims tools: wrappers are async and must be awaited -----------------------

def test_claims_tools_await_async_wrappers(monkeypatch):
    from core.mcp_tools.coordination import add_claims_tools

    async def mk(**_):
        return {"success": True}

    async def claim(issue_id, agent_id, agent_name, capabilities=None, title="", priority="medium"):
        return {"success": True, "issue_id": issue_id}

    async def stats():
        return {"total": 0}

    async def stealable():
        return {"total": 0, "stealable": []}

    async def rebalance(ids):
        return {"total_moves": 0, "ids": ids}

    async def lst(agent_id=None):
        return {"total": 0, "claims": []}

    async def rel(i, a):
        return {"success": True}

    async def steal(i, s, n):
        return {"success": False}

    import vectorcode.src.claims as claims_mod
    for name, fn in [("mcp_claim_task", claim), ("mcp_release_task", rel), ("mcp_list_claims", lst),
                     ("mcp_steal_task", steal), ("mcp_get_stealable", stealable),
                     ("mcp_rebalance_load", rebalance), ("mcp_claim_stats", stats)]:
        monkeypatch.setattr(claims_mod, name, fn)
    tools = _tools(add_claims_tools)
    assert json.loads(_call(tools["claim_task"], "I-1", "a1", "Agent")) == {"success": True, "issue_id": "I-1"}
    assert json.loads(_call(tools["claim_stats"])) == {"total": 0}
    assert json.loads(_call(tools["rebalance_agent_load"], "a, b")) == {"total_moves": 0, "ids": ["a", "b"]}
    assert json.loads(_call(tools["release_task"], "I-1", "a1")) == {"success": True}
    assert json.loads(_call(tools["list_claims"])) == {"total": 0, "claims": []}
    assert json.loads(_call(tools["steal_task"], "I-1", "a2", "B")) == {"success": False}
    assert json.loads(_call(tools["get_stealable_tasks"])) == {"total": 0, "stealable": []}


# --- knowledge_scan_domain default root -----------------------------------------

def test_knowledge_scan_default_root_is_repo_root(monkeypatch):
    from core.mcp_tools.knowledge import add_knowledge_tools
    import core.knowledge.domain_extractor as de

    seen = {}

    class Ctx:
        def to_dict(self):
            return {"fileCount": 1}

    def fake_scan(self, root, output_path=None):
        seen["root"] = Path(root)
        return Ctx()

    monkeypatch.setattr(de.DomainExtractor, "scan", fake_scan)
    tools = _tools(add_knowledge_tools)
    json.loads(_call(tools["knowledge_scan_domain"]))
    repo_root = Path(__file__).resolve().parents[1]
    assert seen["root"] == repo_root


# --- speak_as: empty text is not "spoken" ---------------------------------------

def test_speak_as_empty_text_is_error(monkeypatch):
    from core.mcp_tools.voice import add_voice_profile_tools

    import core.voice.voice_profiles  # noqa: F401  (real package must be loaded first)

    spoke = []
    _install(monkeypatch, "core.voice.tts",
             VoiceTTS=lambda: SimpleNamespace(speak=lambda *a, **k: spoke.append(a)))
    tools = _tools(add_voice_profile_tools)
    out = json.loads(_call(tools["speak_as"], "default", "   "))
    assert "error" in out and "status" not in out and spoke == []


# --- email_status from a worker thread (no current event loop) -------------------

def test_email_status_works_without_current_event_loop(monkeypatch):
    from core.mcp_tools.communications import add_email_tools

    class FakeAgent:
        async def run(self, task):
            return {"status": "ok", "unread": 3, "task": task}

    _install(monkeypatch, "districts.communications.email_agent", EmailAgent=FakeAgent)
    tools = _tools(add_email_tools)

    async def from_worker_thread():
        return await asyncio.to_thread(tools["email_status"])

    out = json.loads(asyncio.run(from_worker_thread()))
    assert out.get("unread") == 3 and "error" not in out


# --- code_graph_build: repo_path confined to the repo ---------------------------

def test_code_graph_build_confined_to_repo(monkeypatch, tmp_path):
    from core.mcp_tools.code_graph import add_code_graph_tools

    built = []
    _install(monkeypatch, "districts.coding.code_review_graph",
             build_graph=lambda p: built.append(p) or {"status": "ok"})
    tools = _tools(add_code_graph_tools)
    out = _call(tools["code_graph_build"], str(tmp_path))
    assert out.startswith("Error") and built == []
    out = _call(tools["code_graph_build"], "../..")
    assert out.startswith("Error") and built == []
    assert "ok" in _call(tools["code_graph_build"], ".")
    assert built == [str(Path(__file__).resolve().parents[1])]
