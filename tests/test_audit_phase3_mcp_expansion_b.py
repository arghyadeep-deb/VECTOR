"""Audit phase 3 -- MCP expansion modules (browser/docs/tests/performance/memory/graph).

Tool parameters are attacker-influenceable (prompt injection). No real browser,
network, pytest subprocess or the real main DB is used: subprocess.run, httpx,
socket.getaddrinfo, the stealth-browser client and the episodic DB are faked or
pointed at tmp_path.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import json
import sqlite3
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.mcp_tools.expansion_modules import browser as browser_mod
from core.mcp_tools.expansion_modules import docs as docs_mod
from core.mcp_tools.expansion_modules import graph as graph_mod
from core.mcp_tools.expansion_modules import memory as memory_mod
from core.mcp_tools.expansion_modules import performance as perf_mod
from core.mcp_tools.expansion_modules import tests as tests_mod


# --------------------------------------------------------------------------- helpers
class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, fn=None, **_meta):
        def deco(f):
            self.tools[f.__name__] = f
            return f

        return deco(fn) if fn is not None else deco


def _call(tools, tool_name, /, **kwargs):
    out = tools[tool_name](**kwargs)
    if inspect.isawaitable(out):
        out = asyncio.run(out)
    return json.loads(out)


class _Runner:
    """Records every subprocess.run argv; returns a canned result."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def __call__(self, argv, *a, **kw):
        self.calls.append(list(argv))
        return self.result


@pytest.fixture
def approved_dir(tmp_path, monkeypatch):
    d = tmp_path / "approved_exports"
    d.mkdir()
    monkeypatch.setattr("core.mcp_tools.memory_safety.memory_export_dir", lambda: d.resolve())
    return d.resolve()


# =========================================================================== browser
class _FakeBrowserClient:
    instances = []

    def __init__(self, *a, **kw):
        self.calls = []
        self._base = "http://127.0.0.1:9377"
        _FakeBrowserClient.instances.append(self)

    def _rec(self, name, *args, **kw):
        async def _r():
            # recorded only when the coroutine is actually awaited/run
            self.calls.append((name, args, kw))
            return self._ret(name)

        return _r()

    def _ret(self, name):
        if name == "screenshot":
            return b"\x89PNG-bytes"
        if name == "snapshot":
            return "- page: ok"
        if name == "create_tab":
            return {"tabId": "t1"}
        return {"ok": True, "op": name}

    def create_tab(self, *a, **k):
        return self._rec("create_tab", *a, **k)

    def navigate(self, *a, **k):
        return self._rec("navigate", *a, **k)

    def screenshot(self, *a, **k):
        return self._rec("screenshot", *a, **k)

    def type_text(self, *a, **k):
        return self._rec("type_text", *a, **k)

    def click(self, *a, **k):
        return self._rec("click", *a, **k)

    def snapshot(self, *a, **k):
        return self._rec("snapshot", *a, **k)


@pytest.fixture
def browser_tools(monkeypatch):
    _FakeBrowserClient.instances.clear()
    monkeypatch.setattr("core.stealth_browser.client.StealthBrowserClient", _FakeBrowserClient)
    # public IP for any hostname -> DNS never touches the network
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", port))],
    )
    mcp = _FakeMCP()
    browser_mod.add_browser_tools(mcp)
    return mcp.tools


def _client():
    # the tool creates the client lazily; blocked calls never create one
    return _FakeBrowserClient.instances[-1] if _FakeBrowserClient.instances else SimpleNamespace(calls=[])


def test_browser_navigate_awaits_client_and_returns_result(browser_tools):
    out = _call(browser_tools, "browser_navigate", url="https://example.com/a", tab_id="t1")
    assert out == {"ok": True, "op": "navigate"}
    assert _client().calls == [("navigate", ("t1", "https://example.com/a"), {})]


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "http://127.0.0.1:9377/",
        "javascript:alert(1)",
        "http://localhost/admin",
    ],
)
def test_browser_navigate_blocks_ssrf_and_non_http(browser_tools, url):
    out = _call(browser_tools, "browser_navigate", url=url)
    assert "SSRF" in out["error"]
    assert not any(c[0] == "navigate" for c in _client().calls)


def test_browser_navigate_blocks_hostname_resolving_to_private_ip(browser_tools, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("10.0.0.5", port))],
    )
    out = _call(browser_tools, "browser_navigate", url="http://intranet.example.test/")
    assert "SSRF" in out["error"]
    assert not any(c[0] == "navigate" for c in _client().calls)


def test_browser_navigate_allows_search_macro(browser_tools):
    out = _call(browser_tools, "browser_navigate", url="@google_search:ai news")
    assert out["ok"] is True
    assert _client().calls[-1] == ("navigate", ("default", "@google_search:ai news"), {})


def test_browser_screenshot_returns_base64_not_coroutine_repr(browser_tools):
    out = _call(browser_tools, "browser_screenshot", tab_id="t1")
    assert out["ok"] is True
    assert base64.b64decode(out["base64"]) == b"\x89PNG-bytes"
    assert out["size_bytes"] == len(b"\x89PNG-bytes")


def test_browser_form_actually_types_each_field(browser_tools):
    out = _call(browser_tools, "browser_form", selector="#f", values='{"a": "1", "b": "2"}', tab_id="t1")
    assert out["ok"] is True
    typed = [(c[1], c[2]) for c in _client().calls if c[0] == "type_text"]
    assert typed == [(("t1", "1"), {"ref": "#f [name=a]"}), (("t1", "2"), {"ref": "#f [name=b]"})]


def test_browser_click_ref_vs_css_selector(browser_tools):
    _call(browser_tools, "browser_click", selector="e12", tab_id="t1")
    _call(browser_tools, "browser_click", selector="#go", tab_id="t1")
    clicks = [(c[1], c[2]) for c in _client().calls if c[0] == "click"]
    assert clicks == [(("t1",), {"ref": "e12"}), (("t1",), {"selector": "#go"})]


def test_browser_open_reports_tab_id(browser_tools):
    out = _call(browser_tools, "browser_open")
    assert out["ok"] is True and out["tab_id"] == "t1"


def test_browser_download_blocks_ssrf_url(browser_tools, monkeypatch):
    posts = []

    class _FakeHttpx:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            posts.append((url, kw))
            return SimpleNamespace(status_code=500, content=b"")

    monkeypatch.setattr("httpx.AsyncClient", _FakeHttpx)
    out = _call(browser_tools, "browser_download", url="http://169.254.169.254/latest/user-data", tab_id="t1")
    assert "SSRF" in out["error"]
    assert posts == []


# =========================================================================== tests.py
@pytest.fixture
def test_tools(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "tests" / "unit").mkdir(parents=True)
    monkeypatch.setattr(tests_mod, "_ROOT", root)
    mcp = _FakeMCP()
    tests_mod.add_test_tools(mcp)
    return SimpleNamespace(tools=mcp.tools, root=root)


def test_test_run_exact_argv_with_double_dash(test_tools, monkeypatch):
    runner = _Runner(returncode=0, stdout="1 passed")
    monkeypatch.setattr(subprocess, "run", runner)
    out = _call(test_tools.tools, "test_run", path="tests/unit")
    assert runner.calls == [["pytest", "-v", "--tb=short", "--", "tests/unit"]]
    assert out["passed"] is True and out["returncode"] == 0


@pytest.mark.parametrize("bad", ["-pevil_plugin", "--rootdir=/tmp", "-c/tmp/evil.ini", "--co"])
@pytest.mark.parametrize("tool", ["test_run", "test_debug", "test_profile", "test_validate", "test_coverage", "test_fix", "test_snapshot"])
def test_pytest_tools_reject_option_looking_path(test_tools, monkeypatch, tool, bad):
    runner = _Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    out = _call(test_tools.tools, tool, path=bad)
    assert "error" in out
    assert runner.calls == []


@pytest.mark.parametrize("bad", ["../outside_dir", "/etc", "tests/../../outside"])
def test_test_run_rejects_path_outside_repo(test_tools, monkeypatch, bad):
    runner = _Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    out = _call(test_tools.tools, "test_run", path=bad)
    assert "error" in out and runner.calls == []


def test_test_run_nonzero_exit_never_reported_as_passed(test_tools, monkeypatch):
    # exit 5 = "no tests collected", exit 2 = collection error
    for rc in (1, 2, 5):
        monkeypatch.setattr(subprocess, "run", _Runner(returncode=rc, stdout="no tests ran"))
        out = _call(test_tools.tools, "test_run", path="tests/unit")
        assert out["passed"] is False and out["returncode"] == rc


def test_test_filter_keyword_cannot_inject_option(test_tools, monkeypatch):
    runner = _Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    _call(test_tools.tools, "test_filter", keyword="-p evil")
    # a single attached argv element: "-k" + value, never a separate "-p"
    assert runner.calls == [["pytest", "-k-p evil", "-v", "--tb=short"]]
    assert _call(test_tools.tools, "test_filter", keyword="  ")["error"]


def test_test_discover_reports_collection_failure(test_tools, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _Runner(returncode=2, stdout="", stderr="ImportError: boom"))
    out = _call(test_tools.tools, "test_discover")
    assert "error" in out and "exit 2" in out["error"]


def test_test_create_rejects_docstring_breakout_and_traversal(test_tools):
    evil = 'x"""\nimport os; os.system("id")\n"""'
    assert "error" in _call(test_tools.tools, "test_create", name=evil)
    assert "error" in _call(test_tools.tools, "test_create", name="ok", target="../../escape")
    assert not list(test_tools.root.parent.rglob("test_x*"))
    assert not (test_tools.root.parent / "escape").exists()


def test_test_create_writes_inside_repo(test_tools):
    out = _call(test_tools.tools, "test_create", name="my-mod", target="tests/unit")
    assert out["ok"] is True
    p = Path(out["path"])
    assert p == (test_tools.root / "tests" / "unit" / "test_my_mod.py").resolve()
    assert p.is_file()


def test_test_generate_does_not_read_outside_repo(test_tools, tmp_path, monkeypatch):
    outside = tmp_path / "secret_outside.py"
    outside.write_text("API_KEY = 'hunter2'\n")
    sent = []
    fake_llm = types.ModuleType("core.inference.vectorcode_llm")
    fake_llm.chat = lambda prompt, *a, **k: sent.append(prompt) or "generated"
    monkeypatch.setitem(sys.modules, "core.inference.vectorcode_llm", fake_llm)
    out = _call(test_tools.tools, "test_generate", module=str(outside))
    assert "error" in out
    assert sent == []  # file content never reached the (cloud-routed) LLM


def test_test_mock_does_not_execute_module(test_tools, monkeypatch):
    mod = test_tools.root / "sidefx_mod.py"
    marker = test_tools.root / "ran.marker"
    mod.write_text(
        "import pathlib\n"
        "pathlib.Path(__file__).with_name('ran.marker').write_text('x')\n"
        "class Foo: pass\n"
        "def bar(): pass\n"
    )
    monkeypatch.syspath_prepend(str(test_tools.root))
    sys.modules.pop("sidefx_mod", None)
    out = _call(test_tools.tools, "test_mock", module="sidefx_mod")
    assert out["classes"] == ["Foo"] and out["functions"] == ["bar"]
    assert not marker.exists()


def test_test_mock_rejects_invalid_names(test_tools):
    assert "error" in _call(test_tools.tools, "test_mock", module="os; import evil")
    # a stdlib module is not a repo module: it must not be imported/inspected
    assert "error" in _call(test_tools.tools, "test_mock", module="os")


def test_test_data_blocks_traversal(test_tools, tmp_path):
    (test_tools.root / "tests" / "fixtures").mkdir(parents=True)
    secret = test_tools.root / "secret.txt"
    secret.write_text("TOP-SECRET")
    out = _call(test_tools.tools, "test_data", name="../../secret.txt")
    assert "error" in out and "TOP-SECRET" not in json.dumps(out)
    (test_tools.root / "tests" / "fixtures" / "ok.json").write_text("{}")
    assert _call(test_tools.tools, "test_data", name="ok.json")["content"] == "{}"


def test_test_watch_rejects_path_outside_repo(test_tools, tmp_path, monkeypatch):
    def _no_sleep(_):
        raise RuntimeError("entered watch loop on an outside path")

    monkeypatch.setattr("time.sleep", _no_sleep)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "a.py").write_text("x = 1\n")
    out = _call(test_tools.tools, "test_watch", path=str(outside))
    assert "error" in out


# =========================================================================== docs.py
@pytest.fixture
def doc_tools(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "core").mkdir()
    monkeypatch.setattr(docs_mod, "_ROOT", root)
    gen_calls = []

    class _FakeGen:
        def generate_weekly_summary(self):
            return "weekly"

        def generate_changelog(self):
            return "changelog"

        def write_document(self, content, doc_type):
            gen_calls.append((content, doc_type))
            return True

    monkeypatch.setattr("districts.qa.doc_generator.DocGenerator", _FakeGen)
    tw_calls = []

    class _FakeWriter:
        def scan_module(self, p):
            tw_calls.append(("scan", p))
            return {"file": p}

        def generate_module_docs(self, p):
            tw_calls.append(("gen", p))
            return "# docs"

    monkeypatch.setattr("districts.qa.technical_writer.TechnicalWriter", _FakeWriter)
    mcp = _FakeMCP()
    docs_mod.add_doc_tools(mcp)
    return SimpleNamespace(tools=mcp.tools, root=root, gen_calls=gen_calls, tw_calls=tw_calls)


def test_doc_delete_sibling_prefix_dir_is_not_inside_root(doc_tools):
    # str.startswith("/tmp/x/repo") is True for "/tmp/x/repo_evil/..." -- is_relative_to is not
    evil_dir = doc_tools.root.parent / (doc_tools.root.name + "_evil")
    evil_dir.mkdir()
    victim = evil_dir / "victim.md"
    victim.write_text("keep me")
    out = _call(doc_tools.tools, "doc_delete", doc_path=f"../{evil_dir.name}/victim.md")
    assert "error" in out
    assert victim.exists()


def test_doc_delete_refuses_source_and_secret_files(doc_tools):
    code = doc_tools.root / "core" / "policy.py"
    code.write_text("x = 1\n")
    env = doc_tools.root / ".env"
    env.write_text("KEY=1\n")
    assert "error" in _call(doc_tools.tools, "doc_delete", doc_path="core/policy.py")
    assert "error" in _call(doc_tools.tools, "doc_delete", doc_path=".env")
    assert code.exists() and env.exists()


def test_doc_delete_deletes_a_doc(doc_tools):
    d = doc_tools.root / "docs" / "old.md"
    d.write_text("x")
    assert _call(doc_tools.tools, "doc_delete", doc_path="docs/old.md")["ok"] is True
    assert not d.exists()


def test_doc_copy_cannot_write_python_into_source_tree(doc_tools):
    src = doc_tools.root / "docs" / "payload.md"
    src.write_text("import os; os.system('id')\n")
    out = _call(doc_tools.tools, "doc_copy", src="docs/payload.md", dst="core/evil.py")
    assert "error" in out
    assert not (doc_tools.root / "core" / "evil.py").exists()


def test_doc_move_and_publish_reject_traversal(doc_tools):
    outside = doc_tools.root.parent / "outside.md"
    outside.write_text("secret")
    assert "error" in _call(doc_tools.tools, "doc_publish", doc_path="../outside.md")
    assert "error" in _call(doc_tools.tools, "doc_move", src="../outside.md", dst="docs/o.md")
    assert not (doc_tools.root / "docs" / "outside.md").exists()
    assert outside.exists()


def test_doc_compare_argv_has_double_dash_and_resolved_paths(doc_tools, monkeypatch):
    a = doc_tools.root / "docs" / "a.md"
    b = doc_tools.root / "docs" / "b.md"
    a.write_text("1")
    b.write_text("2")
    runner = _Runner(returncode=1, stdout="--- a\n+++ b\n")
    monkeypatch.setattr(subprocess, "run", runner)
    out = _call(doc_tools.tools, "doc_compare", v1_path="docs/a.md", v2_path="docs/b.md")
    assert runner.calls == [["diff", "-u", "--", str(a.resolve()), str(b.resolve())]]
    assert out["diff"].startswith("---")


def test_doc_compare_rejects_options_and_outside_files(doc_tools, monkeypatch):
    runner = _Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    assert "error" in _call(doc_tools.tools, "doc_compare", v1_path="-r", v2_path="docs/a.md")
    assert "error" in _call(doc_tools.tools, "doc_compare", v1_path="/etc/passwd", v2_path="docs/a.md")
    assert runner.calls == []


def test_doc_compare_diff_failure_is_not_reported_as_no_differences(doc_tools, monkeypatch):
    (doc_tools.root / "docs" / "a.md").write_text("1")
    monkeypatch.setattr(subprocess, "run", _Runner(returncode=2, stdout="", stderr="diff: b.md: No such file"))
    out = _call(doc_tools.tools, "doc_compare", v1_path="docs/a.md", v2_path="docs/missing.md")
    assert "error" in out and "diff" not in out


def test_doc_generate_unknown_type_is_an_error_not_generated(doc_tools):
    assert "error" in _call(doc_tools.tools, "doc_generate", doc_type="nonsense")
    assert _call(doc_tools.tools, "doc_generate", doc_type="changelog") == "changelog"


def test_doc_draft_calls_write_document_with_sanitised_slug(doc_tools):
    out = _call(doc_tools.tools, "doc_draft", title="../../etc/My Title!", content="body")
    assert out["ok"] is True
    assert doc_tools.gen_calls == [("body", "draft_etc_My_Title")]
    assert Path(out["path"]).parent == doc_tools.root / "docs"


@pytest.mark.parametrize("tool", ["doc_update", "doc_extract", "doc_validate", "doc_lint", "doc_review"])
def test_doc_module_tools_only_scan_python_files_inside_repo(doc_tools, tmp_path, tool):
    outside = tmp_path / "outside_mod.py"
    outside.write_text("x = 1\n")
    assert "error" in _call(doc_tools.tools, tool, module=str(outside))
    assert "error" in _call(doc_tools.tools, tool, module="../outside_mod.py")
    assert doc_tools.tw_calls == []
    inside = doc_tools.root / "core" / "m.py"
    inside.write_text("x = 1\n")
    _call(doc_tools.tools, tool, module="core/m.py")
    assert doc_tools.tw_calls and doc_tools.tw_calls[-1][1] == str(inside.resolve())


def test_doc_search_without_backend_is_an_error_not_empty_results(doc_tools, monkeypatch):
    class _NoSearch:
        pass

    monkeypatch.setattr("core.memory.obsidian_sync.ObsidianSync", _NoSearch)
    out = _call(doc_tools.tools, "doc_search", query="anything")
    assert "error" in out and "results" not in out


def test_doc_import_only_accepts_doc_file_types(doc_tools, tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_text("PRIVATE")
    note = tmp_path / "note.md"
    note.write_text("hello")
    assert "error" in _call(doc_tools.tools, "doc_import", path=str(secret))
    assert not (doc_tools.root / "docs" / "id_rsa").exists()
    assert _call(doc_tools.tools, "doc_import", path=str(note))["ok"] is True


# =========================================================================== memory.py
@pytest.fixture
def mem_tools(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE TABLE episodic_memory (id TEXT, event_type TEXT, content TEXT, timestamp TEXT)")
    conn.execute("CREATE TABLE episodic_memory_fts (id TEXT, content TEXT)")
    conn.execute("CREATE TABLE semantic_memory (key TEXT, value TEXT, category TEXT)")
    conn.executemany(
        "INSERT INTO episodic_memory VALUES (?,?,?,?)",
        [("1", "t", "old", "2026-01-01"), ("2", "t", "new", "2026-02-01")],
    )
    conn.executemany("INSERT INTO episodic_memory_fts VALUES (?,?)", [("1", "old"), ("2", "new")])
    conn.executemany("INSERT INTO semantic_memory VALUES (?,?,?)", [("k1", "v", "alpha"), ("k2", "v", "beta"), ("k3", "v", "alpha")])
    conn.commit()

    @contextlib.contextmanager
    def _cursor():
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()

    class _FakeEpi:
        stats = {"episodic_memory": 2}

        def get_stats(self):
            return type(self).stats

    chain_calls = []

    class _FakeRM:
        def store_chain(self, **kw):
            chain_calls.append(kw)
            return "chain-123"

        def inject_past_reasoning(self, situation, limit=3):
            return f"past:{situation}:{limit}"

    monkeypatch.setattr("core.memory.episodic.get_temp_cursor", _cursor)
    monkeypatch.setattr("core.memory.episodic.EpisodicMemory", _FakeEpi)
    monkeypatch.setattr("core.memory.reasoning_memory.ReasoningMemory", _FakeRM)
    async def approve(*_args, **_kwargs):
        return SimpleNamespace(approved=True, level="RED", reason="approved")

    monkeypatch.setattr(memory_mod, "evaluate_destructive_action", approve)
    mcp = _FakeMCP()
    memory_mod.add_memory_tools(mcp)
    return SimpleNamespace(tools=mcp.tools, conn=conn, chain_calls=chain_calls, epi=_FakeEpi)


def test_memory_recent_returns_rows_newest_first(mem_tools):
    out = _call(mem_tools.tools, "memory_recent", limit=1)
    assert out["count"] == 1 and out["entries"][0]["content"] == "new"
    # LIMIT -1 would dump the whole table: limit is clamped
    assert _call(mem_tools.tools, "memory_recent", limit=-1)["count"] == 1


def test_memory_categories_lists_real_categories(mem_tools):
    assert sorted(_call(mem_tools.tools, "memory_categories")["categories"]) == ["alpha", "beta"]


def test_memory_clear_also_clears_fts_index(mem_tools):
    assert "error" in _call(mem_tools.tools, "memory_clear")  # confirm required
    assert mem_tools.conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0] == 2
    out = _call(mem_tools.tools, "memory_clear", confirm="CONFIRM_CLEAR_MEMORY")
    assert out["cleared"] is True
    assert mem_tools.conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0] == 0
    assert mem_tools.conn.execute("SELECT COUNT(*) FROM episodic_memory_fts").fetchone()[0] == 0


def test_memory_pattern_save_uses_real_store_chain_signature(mem_tools):
    out = _call(mem_tools.tools, "memory_pattern_save", task="t", plan="p", outcome="o", reward=0.9)
    assert out == {"ok": True, "chain_id": "chain-123"}
    assert mem_tools.chain_calls == [
        {"situation": "t", "goal_ids": [], "steps": ["p"], "action": "p", "outcome": "o", "reward": 0.9}
    ]


def test_memory_pattern_recall_returns_patterns(mem_tools):
    assert _call(mem_tools.tools, "memory_pattern_recall", task="x", limit=2)["patterns"] == "past:x:2"


def test_memory_stats_empty_dict_is_an_error(mem_tools):
    mem_tools.epi.stats = {}
    assert "error" in _call(mem_tools.tools, "memory_stats")


# =========================================================================== performance.py
@pytest.fixture
def perf_tools(tmp_path, monkeypatch, approved_dir):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(perf_mod, "_ROOT", root)
    mcp = _FakeMCP()
    perf_mod.add_perf_tools(mcp)
    return SimpleNamespace(tools=mcp.tools, root=root, approved=approved_dir)


def test_perf_profile_runs_resolved_script_with_sys_executable(perf_tools, monkeypatch):
    script = perf_tools.root / "bench.py"
    script.write_text("print(1)\n")
    runner = _Runner(returncode=0)
    monkeypatch.setattr(subprocess, "run", runner)
    out = _call(perf_tools.tools, "perf_profile", file_path="bench.py")
    assert runner.calls == [[sys.executable, str(script.resolve())]]
    assert out["ok"] is True and out["returncode"] == 0


@pytest.mark.parametrize("bad", ["-cimport os;os.system('id')", "--version", "../escape.py", "/etc/passwd", "notes.txt", "missing.py"])
def test_perf_profile_rejects_option_outside_and_non_py(perf_tools, monkeypatch, tmp_path, bad):
    (perf_tools.root / "notes.txt").write_text("x")
    (tmp_path / "escape.py").write_text("x=1\n")
    runner = _Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    assert "error" in _call(perf_tools.tools, "perf_profile", file_path=bad)
    assert runner.calls == []


def test_perf_profile_failing_script_is_not_ok(perf_tools, monkeypatch):
    (perf_tools.root / "boom.py").write_text("raise SystemExit(3)\n")
    monkeypatch.setattr(subprocess, "run", _Runner(returncode=3, stderr="Traceback"))
    out = _call(perf_tools.tools, "perf_profile", file_path="boom.py")
    assert out["ok"] is False and out["returncode"] == 3 and "Traceback" in out["stderr"]


@pytest.mark.parametrize("tool", ["perf_hotspots", "perf_flame_graph"])
def test_perf_hotspots_failing_script_is_error_not_profile(perf_tools, monkeypatch, tool):
    (perf_tools.root / "boom.py").write_text("raise SystemExit(1)\n")
    monkeypatch.setattr(subprocess, "run", _Runner(returncode=1, stderr="Traceback"))
    out = _call(perf_tools.tools, tool, file_path="boom.py")
    assert "error" in out and "exited with code 1" in out["error"]
    assert "-c" not in json.dumps(_call(perf_tools.tools, tool, file_path="-cprint(1)"))  # option rejected, not run


def test_perf_export_path_is_confined_to_approved_dir(perf_tools, tmp_path):
    outside = tmp_path / "clobbered.json"
    outside.write_text("ORIGINAL")
    assert "error" in _call(perf_tools.tools, "perf_export", path=str(outside))
    assert outside.read_text() == "ORIGINAL"
    ok = _call(perf_tools.tools, "perf_export", path="snap.json")
    assert Path(ok["path"]) == perf_tools.approved / "snap.json"
    assert (perf_tools.approved / "snap.json").is_file()


def test_perf_import_path_is_confined_to_approved_dir(perf_tools, tmp_path):
    outside = tmp_path / "other.json"
    outside.write_text('{"a": 1}')
    assert "error" in _call(perf_tools.tools, "perf_import", path=str(outside))


def test_perf_import_store_failure_is_reported(perf_tools, monkeypatch):
    (perf_tools.approved / "b.json").write_text('{"cpu": 1}')

    class _BrokenEpi:
        def store(self, *a, **k):
            raise RuntimeError("db down")

    monkeypatch.setattr("core.memory.episodic.EpisodicMemory", _BrokenEpi)
    out = _call(perf_tools.tools, "perf_import", path=str(perf_tools.approved / "b.json"))
    assert "error" in out and "ok" not in out  # was: swallowed -> {"ok": True}


def test_perf_baseline_stores_with_real_episodic_signature(perf_tools, monkeypatch):
    stored = []

    class _Epi:
        def store(self, event_type, content, tags=None, **kw):
            stored.append((event_type, json.loads(content), tags))

    monkeypatch.setattr("core.memory.episodic.EpisodicMemory", _Epi)
    out = _call(perf_tools.tools, "perf_baseline", name="nightly")
    assert out["ok"] is True
    assert stored[0][0] == "perf_baseline" and stored[0][1]["name"] == "nightly"
    assert stored[0][2] == ["performance", "baseline"]


def test_perf_stress_worker_count_is_clamped(perf_tools, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _Runner())
    out = _call(perf_tools.tools, "perf_stress", workers=500, duration_sec=1)
    assert out["workers"] == 32 and len(out["results"]) == 32


def test_perf_latency_samples_clamped_and_zero_ok(perf_tools):
    out = _call(perf_tools.tools, "perf_latency", samples=0)
    assert out["samples"] == 1 and "p99" in out


# =========================================================================== graph.py
class _FakeKG:
    def __init__(self):
        self.entities = []
        self.relations = []

    def add_entity(self, name, entity_type="concept", properties=None):
        self.entities.append((name, entity_type, properties))

    def add_relation(self, *a, **k):
        self.relations.append((a, k))

    def all_entities(self, entity_type=None):
        return [SimpleNamespace(name="old", entity_type="symbol", created_at=0.0)]

    def entity_count(self):
        return 1


@pytest.fixture
def graph_tools(tmp_path, monkeypatch, approved_dir):
    root = tmp_path / "repo"
    root.mkdir()
    kg = _FakeKG()
    monkeypatch.setattr(graph_mod, "_ROOT", root)
    monkeypatch.setattr("core.memory.knowledge_graph.get_knowledge_graph", lambda *a, **k: kg)
    scans = []

    class _FakeWriter:
        def scan_module(self, p):
            scans.append(p)
            return {"file": p}

    monkeypatch.setattr("districts.qa.technical_writer.TechnicalWriter", _FakeWriter)
    mcp = _FakeMCP()
    graph_mod.add_graph_tools(mcp)
    return SimpleNamespace(tools=mcp.tools, root=root, kg=kg, approved=approved_dir, scans=scans)


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd), capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_graph_diff_is_read_only_and_counts_real_symbols(graph_tools):
    root = graph_tools.root
    _git(root, "init", "-q")
    (root / "a.py").write_text("def f():\n    pass\n")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "one")
    (root / "a.py").write_text("def f():\n    pass\n\nclass C:\n    def m(self):\n        pass\n")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "two")
    head_before = _git(root, "rev-parse", "HEAD")
    branch_before = _git(root, "rev-parse", "--abbrev-ref", "HEAD")

    out = _call(graph_tools.tools, "graph_diff", branch_a="HEAD~1", branch_b="HEAD")

    assert (out["entity_count_a"], out["entity_count_b"], out["diff"]) == (1, 3, 2)
    assert _git(root, "rev-parse", "HEAD") == head_before
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == branch_before  # not detached by a checkout
    assert (root / "a.py").read_text().count("def ") == 2  # working tree untouched


def test_graph_diff_never_runs_checkout_and_rejects_option_refs(graph_tools, monkeypatch):
    runner = _Runner(returncode=0, stdout="abc123\n")
    monkeypatch.setattr(subprocess, "run", runner)
    for ref in ("--orphan=pwn", "-f", "x y", ""):
        assert "error" in _call(graph_tools.tools, "graph_diff", branch_a=ref, branch_b="HEAD")
    _call(graph_tools.tools, "graph_diff", branch_a="HEAD~1", branch_b="HEAD")
    assert runner.calls  # valid refs do reach git ...
    assert all("checkout" not in argv for argv in runner.calls)  # ... but never a checkout
    assert all(not a.startswith("-") or a in {"--verify", "--end-of-options", "--name-only", "-z", "--"} for argv in runner.calls for a in argv[1:] if a.startswith("-"))


def test_graph_diff_unknown_ref_is_error(graph_tools):
    _git(graph_tools.root, "init", "-q")
    out = _call(graph_tools.tools, "graph_diff", branch_a="nope", branch_b="HEAD")
    assert "error" in out and "unknown git ref" in out["error"]


def test_graph_export_and_import_confined_to_approved_dir(graph_tools, tmp_path):
    outside = tmp_path / "pwn.json"
    assert "error" in _call(graph_tools.tools, "graph_export", path=str(outside))
    assert not outside.exists()
    ok = _call(graph_tools.tools, "graph_export", path="g.json")
    assert Path(ok["path"]) == graph_tools.approved / "g.json"

    leak = tmp_path / "leak.json"
    leak.write_text(json.dumps({"entities": [{"name": "from-outside", "type": "x"}]}))
    assert "error" in _call(graph_tools.tools, "graph_import", path=str(leak))
    assert graph_tools.kg.entities == []

    (graph_tools.approved / "in.json").write_text(json.dumps({"entities": [{"name": "n1", "type": "t"}, {"type": "no-name"}, "junk"]}))
    assert _call(graph_tools.tools, "graph_import", path="in.json") == {"ok": True, "imported": 1}


def test_graph_merge_and_compare_confined(graph_tools, tmp_path):
    leak = tmp_path / "leak.json"
    leak.write_text(json.dumps({"entities": [{"name": "x"}], "relations": []}))
    assert "error" in _call(graph_tools.tools, "graph_merge", other_path=str(leak))
    assert "error" in _call(graph_tools.tools, "graph_compare", other_path=str(leak))
    assert graph_tools.kg.entities == []


def test_graph_rebuild_stays_inside_repo(graph_tools, tmp_path):
    scan_outside = tmp_path / "elsewhere"
    scan_outside.mkdir()
    (scan_outside / "x.py").write_text("def g():\n    pass\n")
    assert "error" in _call(graph_tools.tools, "graph_rebuild", scan_path=str(scan_outside))
    assert "error" in _call(graph_tools.tools, "graph_rebuild", scan_path="../elsewhere")
    (graph_tools.root / "core").mkdir()
    (graph_tools.root / "core" / "a.py").write_text("def f():\n    pass\n\nclass K:\n    pass\n")
    out = _call(graph_tools.tools, "graph_rebuild", scan_path="core/")
    assert out["entities_added"] == 2
    assert {e[0] for e in graph_tools.kg.entities} == {"core/a.py::f", "core/a.py::K"}


def test_graph_clean_does_not_claim_removal(graph_tools):
    out = _call(graph_tools.tools, "graph_clean", older_than_days=1)
    assert out["removed_count"] == 0 and out["stale_count"] == 1


def test_graph_symbols_only_scans_py_inside_repo(graph_tools, tmp_path):
    outside = tmp_path / "o.py"
    outside.write_text("x=1\n")
    assert "error" in _call(graph_tools.tools, "graph_symbols", file_path=str(outside))
    assert graph_tools.scans == []
    inside = graph_tools.root / "m.py"
    inside.write_text("x=1\n")
    _call(graph_tools.tools, "graph_symbols", file_path="m.py")
    assert graph_tools.scans == [str(inside.resolve())]
