# VectorCode VC-6: Code Graph + Browser Tools

**Goal:** Build AST-based code graph with blast-radius analysis (ported from code-review-graph) and Playwright browser automation tools.
**Architecture:** CodeGraph builds an incremental AST index using Python's ast module + SQLite, tracks function/class dependencies, computes blast radius for any changed symbol. BrowserTools wraps Playwright async API with permission-gated actions (navigate/screenshot/click/extract are YELLOW; form-submit is RED).
**Files:**
- Create: `agents/districts/coding/vectorcode/tools/code_graph.py`
- Create: `agents/districts/coding/vectorcode/tools/browser_tools.py`
- Create: `tests/test_vectorcode_vc6.py`

---

### Task 1: CodeGraph — AST index + blast-radius

- [ ] Write failing test
  ```python
  import textwrap
  from agents.districts.coding.vectorcode.tools.code_graph import CodeGraph
  def test_code_graph_indexes_file(tmp_path):
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
      assert "foo" in symbols
      assert "bar" in symbols
  def test_code_graph_blast_radius(tmp_path):
      src = tmp_path / "module.py"
      src.write_text("def foo():\n    return bar()\ndef bar():\n    return 42\n")
      cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
      cg.index_file("module.py")
      radius = cg.blast_radius("bar")
      assert "foo" in radius
  def test_code_graph_incremental_update(tmp_path):
      src = tmp_path / "module.py"
      src.write_text("def foo():\n    pass\n")
      cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
      cg.index_file("module.py")
      src.write_text("def foo():\n    pass\ndef baz():\n    pass\n")
      cg.index_file("module.py")
      symbols = cg.list_symbols("module.py")
      assert "baz" in symbols
  def test_code_graph_repo_scan(tmp_path):
      (tmp_path / "a.py").write_text("def f(): pass\n")
      (tmp_path / "b.py").write_text("def g(): pass\n")
      cg = CodeGraph(repo_root=str(tmp_path), db_path=str(tmp_path / "graph.db"))
      cg.index_repo()
      assert len(cg.list_all_symbols()) >= 2
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc6.py -k "code_graph" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/tools/code_graph.py`
- [ ] Run: `pytest tests/test_vectorcode_vc6.py -k "code_graph" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc6): CodeGraph AST index + blast-radius analysis"`

---

### Task 2: BrowserTools — Playwright automation

- [ ] Write failing test
  ```python
  from unittest.mock import patch, AsyncMock, MagicMock
  from agents.districts.coding.vectorcode.tools.browser_tools import BrowserTools
  def test_browser_tools_permission_levels():
      bt = BrowserTools.__new__(BrowserTools)
      assert bt.NAVIGATE_PERMISSION == "yellow"
      assert bt.SCREENSHOT_PERMISSION == "yellow"
      assert bt.SUBMIT_FORM_PERMISSION == "red"
  def test_browser_tools_navigate_goes_through_gateway():
      with patch("agents.districts.coding.vectorcode.tools.browser_tools.PermissionGateway") as MockGW:
          mock_gw = MagicMock()
          mock_gw.check.return_value = True
          MockGW.return_value = mock_gw
          bt = BrowserTools.__new__(BrowserTools)
          bt._gateway = mock_gw
          bt._page = MagicMock()
          bt._page.goto = AsyncMock()
          import asyncio
          asyncio.run(bt._navigate_with_gate("http://localhost:8000"))
          mock_gw.check.assert_called()
  def test_browser_tools_screenshot_returns_bytes():
      bt = BrowserTools.__new__(BrowserTools)
      bt._page = MagicMock()
      bt._page.screenshot = AsyncMock(return_value=b"fake_png_data")
      import asyncio
      result = asyncio.run(bt._take_screenshot())
      assert isinstance(result, bytes)
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc6.py -k "browser" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/tools/browser_tools.py`
- [ ] Run: `pytest tests/test_vectorcode_vc6.py -k "browser" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc6): BrowserTools Playwright navigate/screenshot/click"`

---

### Task 3: Full VC-6 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc6.py -v` → all pass
- [ ] Commit: `git commit -m "feat(vc6): code-graph + browser tools complete"`
