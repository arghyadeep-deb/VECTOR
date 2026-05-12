# VectorCode VC-1: Core Foundation

**Goal:** Build the shared session state, semantic model router, file/bash tools, and security layer that all other VectorCode phases depend on.
**Architecture:** All files live under `agents/districts/coding/vectorcode/`. Session is a singleton dataclass. Router maps task types to Ollama model names respecting RULE 4. FileTools and BashTools wrap all I/O through the security layer before touching disk or shell. No subprocess.shell=True anywhere — all commands run via subprocess.run with list args only.
**Files:**
- Create: `agents/districts/coding/vectorcode/__init__.py`
- Create: `agents/districts/coding/vectorcode/session.py`
- Create: `agents/districts/coding/vectorcode/router.py`
- Create: `agents/districts/coding/vectorcode/tools/__init__.py`
- Create: `agents/districts/coding/vectorcode/tools/file_tools.py`
- Create: `agents/districts/coding/vectorcode/tools/bash_tools.py`
- Create: `agents/districts/coding/vectorcode/security/__init__.py`
- Create: `agents/districts/coding/vectorcode/security/validator.py`
- Create: `agents/districts/coding/vectorcode/security/safe_executor.py`
- Create: `tests/test_vectorcode_vc1.py`

---

### Task 1: VectorCodeSession — shared state singleton

- [ ] Write failing test
  ```python
  # tests/test_vectorcode_vc1.py
  from agents.districts.coding.vectorcode.session import VectorCodeSession
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
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py::test_session_singleton tests/test_vectorcode_vc1.py::test_session_fields -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/session.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py::test_session_singleton tests/test_vectorcode_vc1.py::test_session_fields -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): VectorCodeSession singleton"`

---

### Task 2: SemanticRouter — model routing

- [ ] Write failing test
  ```python
  from agents.districts.coding.vectorcode.router import SemanticRouter
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
      switches = sum(1 for i in range(1, len(models)) if models[i] != models[i-1])
      assert switches <= 3
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "router" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/router.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "router" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): SemanticRouter Ollama model routing"`

---

### Task 3: FileTools — read/write/edit/grep/glob

- [ ] Write failing test
  ```python
  import pytest
  from agents.districts.coding.vectorcode.tools.file_tools import FileTools
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
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "file" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/tools/file_tools.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "file" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): FileTools read/write/edit/grep/glob"`

---

### Task 4: BashTools — safe command execution (subprocess list-args only, shell=False always)

- [ ] Write failing test
  ```python
  import pytest
  from agents.districts.coding.vectorcode.tools.bash_tools import BashTools
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
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "bash" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/tools/bash_tools.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "bash" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): BashTools safe command execution"`

---

### Task 5: InputValidator + PathValidator

- [ ] Write failing test
  ```python
  import pytest
  from agents.districts.coding.vectorcode.security.validator import InputValidator, PathValidator
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
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "validator" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/security/validator.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "validator" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): InputValidator + PathValidator"`

---

### Task 6: SafeExecutor — allowlist + injection protection

- [ ] Write failing test
  ```python
  import pytest
  from agents.districts.coding.vectorcode.security.safe_executor import SafeExecutor
  def test_safe_executor_allowlist_git():
      se = SafeExecutor()
      assert se.is_allowed(["git", "status"]) is True
  def test_safe_executor_allowlist_pytest():
      se = SafeExecutor()
      assert se.is_allowed(["pytest", "tests/"]) is True
  def test_safe_executor_blocks_rm():
      se = SafeExecutor()
      assert se.is_allowed(["rm", "-rf", "/"]) is False
  def test_safe_executor_blocks_shell_injection():
      se = SafeExecutor()
      assert se.is_allowed(["python", "-c", "import subprocess; subprocess.run(['rm','-rf','/'])"]) is False
  def test_safe_executor_execute_ok():
      se = SafeExecutor()
      result = se.execute(["python", "--version"])
      assert result["ok"] is True
      assert "Python" in result["stdout"] or "Python" in result["stderr"]
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "executor" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/security/safe_executor.py`
- [ ] Run: `pytest tests/test_vectorcode_vc1.py -k "executor" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc1): SafeExecutor allowlist + injection protection"`

---

### Task 7: Full VC-1 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc1.py -v` → all pass, 0 failures
- [ ] Commit: `git commit -m "feat(vc1): core foundation complete — session/router/tools/security"`
