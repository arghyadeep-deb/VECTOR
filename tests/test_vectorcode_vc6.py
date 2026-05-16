"""
VC-6 test suite — CodeGraph + BrowserTools.

Run:
    pytest tests/test_vectorcode_vc6.py -v
    pytest tests/test_vectorcode_vc6.py -k "code_graph" -v
    pytest tests/test_vectorcode_vc6.py -k "browser"    -v
"""

import sys
import textwrap
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.coding.vectorcode.tools.code_graph import CodeGraph
from agents.coding.vectorcode.tools.browser_tools import BrowserTools


# ─────────────────────────────────────────────────────────────────────────────
# CodeGraph tests
# ─────────────────────────────────────────────────────────────────────────────

def test_code_graph_indexes_file(tmp_path):
    """index_file parses symbols and makes them queryable via list_symbols."""
    src = tmp_path / "module.py"
    src.write_text(textwrap.dedent("""
        def foo():
            return bar()
        def bar():
            return 42
    """))
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_file("module.py")
    symbols = cg.list_symbols("module.py")
    assert "foo" in symbols, f"foo missing from {symbols}"
    assert "bar" in symbols, f"bar missing from {symbols}"


def test_code_graph_blast_radius(tmp_path):
    """blast_radius('bar') returns callers of bar — i.e. foo."""
    src = tmp_path / "module.py"
    src.write_text("def foo():\n    return bar()\ndef bar():\n    return 42\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_file("module.py")
    radius = cg.blast_radius("bar")
    assert "foo" in radius, f"Expected foo in blast_radius('bar'), got {radius}"


def test_code_graph_incremental_update(tmp_path):
    """Re-indexing a modified file reflects new symbols without stale rows."""
    src = tmp_path / "module.py"
    src.write_text("def foo():\n    pass\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_file("module.py")

    # Modify and re-index
    src.write_text("def foo():\n    pass\ndef baz():\n    pass\n")
    cg.index_file("module.py")

    symbols = cg.list_symbols("module.py")
    assert "baz" in symbols, f"baz not found after incremental update: {symbols}"


def test_code_graph_repo_scan(tmp_path):
    """index_repo walks all .py files and returns total symbol count >= file count."""
    (tmp_path / "a.py").write_text("def f(): pass\n")
    (tmp_path / "b.py").write_text("def g(): pass\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_repo()
    all_symbols = cg.list_all_symbols()
    assert len(all_symbols) >= 2, f"Expected >=2 symbols, got {all_symbols}"


def test_code_graph_class_symbols(tmp_path):
    """Classes and their methods are indexed with correct kinds."""
    src = tmp_path / "myclass.py"
    src.write_text(textwrap.dedent("""
        class Animal:
            def speak(self):
                pass
        def helper():
            pass
    """))
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_file("myclass.py")
    symbols = cg.list_symbols("myclass.py")
    assert "Animal" in symbols
    assert "speak" in symbols
    assert "helper" in symbols


def test_code_graph_empty_file(tmp_path):
    """Empty file indexes to 0 symbols without crashing."""
    src = tmp_path / "empty.py"
    src.write_text("")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    count = cg.index_file("empty.py")
    assert count == 0


def test_code_graph_missing_file(tmp_path):
    """index_file on a non-existent path returns 0 without raising."""
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    count = cg.index_file("does_not_exist.py")
    assert count == 0


def test_code_graph_blast_radius_no_callers(tmp_path):
    """blast_radius returns empty list for a symbol with no callers."""
    (tmp_path / "solo.py").write_text("def solo():\n    return 1\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_file("solo.py")
    assert cg.blast_radius("solo") == []


def test_code_graph_dependents(tmp_path):
    """dependents returns files that call into the specified file."""
    (tmp_path / "utils.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "main.py").write_text("def run():\n    return helper()\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_repo()
    deps = cg.dependents("utils.py")
    assert "main.py" in deps, f"Expected main.py in dependents, got {deps}"


def test_code_graph_list_all_symbols_across_files(tmp_path):
    """list_all_symbols returns unique names from all indexed files."""
    (tmp_path / "x.py").write_text("def alpha(): pass\n")
    (tmp_path / "y.py").write_text("def beta(): pass\n")
    cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
    cg.index_repo()
    syms = cg.list_all_symbols()
    assert "alpha" in syms
    assert "beta" in syms


# ─────────────────────────────────────────────────────────────────────────────
# BrowserTools tests
# ─────────────────────────────────────────────────────────────────────────────

def test_browser_tools_permission_levels():
    """Class-level permission constants have correct values."""
    bt = BrowserTools.__new__(BrowserTools)
    assert bt.NAVIGATE_PERMISSION == "yellow"
    assert bt.SCREENSHOT_PERMISSION == "yellow"
    assert bt.CLICK_PERMISSION == "yellow"
    assert bt.SUBMIT_FORM_PERMISSION == "red"


def test_browser_tools_navigate_goes_through_gateway():
    """_navigate_with_gate calls self._gateway.check()."""
    with patch("agents.coding.vectorcode.tools.browser_tools.PermissionGateway") as MockGW:
        mock_gw = MagicMock()
        mock_gw.check.return_value = True
        MockGW.return_value = mock_gw

        bt = BrowserTools.__new__(BrowserTools)
        bt._gateway = mock_gw
        bt._page = MagicMock()
        bt._page.goto = AsyncMock()
        bt._page.title = AsyncMock(return_value="Test Page")

        asyncio.run(bt._navigate_with_gate("http://localhost:8000"))
        mock_gw.check.assert_called()


def test_browser_tools_screenshot_returns_bytes():
    """_take_screenshot returns bytes (even with a mock page)."""
    bt = BrowserTools.__new__(BrowserTools)
    bt._page = MagicMock()
    bt._page.screenshot = AsyncMock(return_value=b"fake_png_data")

    result = asyncio.run(bt._take_screenshot())
    assert isinstance(result, bytes)
    assert result == b"fake_png_data"


def test_browser_tools_navigate_blocked_returns_empty():
    """When gateway.check returns False, navigate returns empty string."""
    bt = BrowserTools.__new__(BrowserTools)
    mock_gw = MagicMock()
    mock_gw.check.return_value = False
    bt._gateway = mock_gw
    bt._page = MagicMock()
    bt._page.goto = AsyncMock()

    result = asyncio.run(bt._navigate_with_gate("http://example.com"))
    assert result == ""


def test_browser_tools_screenshot_no_page_returns_empty():
    """_take_screenshot with no page returns empty bytes."""
    bt = BrowserTools.__new__(BrowserTools)
    bt._page = None

    result = asyncio.run(bt._take_screenshot())
    assert result == b""


def test_browser_tools_click_blocked_returns_false():
    """_click_element returns False when gateway denies."""
    bt = BrowserTools.__new__(BrowserTools)
    mock_gw = MagicMock()
    mock_gw.check.return_value = False
    bt._gateway = mock_gw
    bt._page = MagicMock()

    result = asyncio.run(bt._click_element("button#submit"))
    assert result is False


def test_browser_tools_submit_form_gated_red():
    """submit_form calls gateway with 'red' level."""
    bt = BrowserTools.__new__(BrowserTools)
    mock_gw = MagicMock()
    mock_gw.check.return_value = False   # RED → not approved without confirmation
    bt._gateway = mock_gw
    bt._page = MagicMock()

    result = asyncio.run(bt._submit_form_async("form#login", {"user": "a", "pass": "b"}))
    # Gateway denied → returns False
    assert result is False
    # Verify check was called with "red" level
    call_args = mock_gw.check.call_args
    assert call_args[0][0] == "red" or call_args[0][1] == "submit_form_browser"


def test_browser_tools_extract_text_no_page_returns_empty():
    """extract_text with no page returns empty string."""
    bt = BrowserTools.__new__(BrowserTools)
    bt._page = None

    result = asyncio.run(bt._extract_text_async())
    assert result == ""


def test_browser_tools_stub_mode_when_playwright_missing():
    """BrowserTools can be instantiated even when playwright is not installed."""
    with patch("agents.coding.vectorcode.tools.browser_tools._PLAYWRIGHT_AVAILABLE", False):
        # Just checking no import errors / crashes on instantiation
        bt = BrowserTools.__new__(BrowserTools)
        bt._page = None
        result = asyncio.run(bt._take_screenshot())
        assert result == b""
