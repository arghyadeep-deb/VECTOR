# VectorCode VC-7: MCP Tool Expansion (14 → 314)

**Goal:** Expand VECTOR's MCP server from 14 tools to 314 tools across 17 categories, wiring all VectorCode components as callable MCP tools for Claude Code sessions and VECTOR's own MCP client.
**Architecture:** All new tools added to `core/mcp_server.py` via FastMCP tool decorators. Each category delegates to the appropriate VectorCode component. Tools are grouped by prefix (agent_*, swarm_*, memory_*, hook_*, task_*, security_*, neural_*, file_*, git_*, test_*, doc_*, browser_*, graph_*, perf_*, worker_*, config_*). Existing 14 tools unchanged.
**Files:**
- Modify: `core/mcp_server.py` (add 300 new tools across 16 new categories)
- Create: `tests/test_vectorcode_vc7.py`

---

### Task 1: Agent + Swarm tools (17 tools)

- [ ] Write failing test
  ```python
  from core.mcp_server import create_mcp_app
  def test_agent_tools_registered():
      app = create_mcp_app()
      tool_names = [t.name for t in app.list_tools()]
      for name in ["agent_spawn", "agent_list", "agent_status", "agent_stop",
                   "agent_metrics", "agent_pool", "agent_health", "agent_logs",
                   "swarm_init", "swarm_submit", "swarm_assign",
                   "swarm_execute", "swarm_status", "swarm_shutdown",
                   "swarm_topology", "swarm_agents", "swarm_report"]:
          assert name in tool_names, f"Missing tool: {name}"
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "agent_swarm" -v` → expect FAIL
- [ ] Add agent_* and swarm_* tools to `core/mcp_server.py`
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "agent_swarm" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc7): MCP agent + swarm tools (17)"`

---

### Task 2: Memory + Hook + Task tools (37 tools)

- [ ] Write failing test
  ```python
  def test_memory_hook_task_tools_registered():
      from core.mcp_server import create_mcp_app
      app = create_mcp_app()
      tool_names = [t.name for t in app.list_tools()]
      memory_tools = ["memory_faiss_add", "memory_faiss_search", "memory_pattern_save",
                      "memory_pattern_recall", "memory_bridge_sync", "memory_export",
                      "memory_import", "memory_stats", "memory_clear",
                      "memory_semantic_search", "memory_recent", "memory_categories"]
      hook_tools = ["hook_register", "hook_fire", "hook_list",
                    "hook_pre_edit", "hook_post_edit", "hook_pre_task",
                    "hook_post_task", "hook_session_start", "hook_session_end",
                    "hook_route", "hook_explain", "hook_notify",
                    "hook_intelligence", "hook_task_complete",
                    "hook_session_restore", "hook_post_command", "hook_transfer"]
      task_tools = ["task_create", "task_assign", "task_complete",
                    "task_list", "task_update", "task_delete",
                    "task_status", "task_submit_bg"]
      for name in memory_tools + hook_tools + task_tools:
          assert name in tool_names, f"Missing: {name}"
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "memory_hook_task" -v` → expect FAIL
- [ ] Add memory_*, hook_*, task_* tools to `core/mcp_server.py`
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "memory_hook_task" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc7): MCP memory + hook + task tools (37)"`

---

### Task 3: Security + Neural + File + Git tools (52 tools)

- [ ] Write failing test
  ```python
  def test_security_neural_file_git_tools():
      from core.mcp_server import create_mcp_app
      app = create_mcp_app()
      tool_names = [t.name for t in app.list_tools()]
      security = ["security_scan", "security_audit", "security_validate",
                  "security_path_check", "security_cve_scan",
                  "security_threats", "security_report",
                  "security_input_validate", "security_executor_check", "security_allowlist"]
      neural = ["neural_pattern_save", "neural_pattern_recall", "neural_train",
                "neural_status", "neural_predict", "neural_optimize",
                "neural_reward", "neural_stats"]
      file_t = ["file_read", "file_write", "file_edit", "file_grep",
                "file_glob", "file_delete", "file_exists",
                "file_diff", "file_list_dir", "file_copy"]
      git_t = ["git_commit", "git_push", "git_pr_create", "git_diff",
               "git_blame", "git_log", "git_branch",
               "git_checkout", "git_status", "git_stash",
               "git_merge", "git_rebase"]
      for name in security + neural + file_t + git_t:
          assert name in tool_names, f"Missing: {name}"
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "security_neural" -v` → expect FAIL
- [ ] Add security_*, neural_*, file_*, git_* tools to `core/mcp_server.py`
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "security_neural" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc7): MCP security + neural + file + git tools (52)"`

---

### Task 4: Test + Doc + Browser + Graph + Perf + Worker + Config tools (194 tools)

- [ ] Write failing test
  ```python
  def test_remaining_tool_categories():
      from core.mcp_server import create_mcp_app
      app = create_mcp_app()
      tool_names = [t.name for t in app.list_tools()]
      # spot-check each category has at least 4 tools
      categories = ["test_", "doc_", "browser_", "graph_", "perf_", "worker_", "config_"]
      for prefix in categories:
          matching = [n for n in tool_names if n.startswith(prefix)]
          assert len(matching) >= 4, f"Category {prefix} has only {len(matching)} tools"
  def test_total_tool_count():
      from core.mcp_server import create_mcp_app
      app = create_mcp_app()
      tools = app.list_tools()
      assert len(tools) >= 300, f"Expected 300+ tools, got {len(tools)}"
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "remaining" -v` → expect FAIL
- [ ] Add test_*, doc_*, browser_*, graph_*, perf_*, worker_*, config_* tools to `core/mcp_server.py`
- [ ] Run: `pytest tests/test_vectorcode_vc7.py -k "remaining" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc7): MCP test/doc/browser/graph/perf/worker/config tools"`

---

### Task 5: Full VC-7 smoke — 314 tools registered

- [ ] Run: `pytest tests/test_vectorcode_vc7.py -v` → all pass
- [ ] Run: `python -c "from core.mcp_server import create_mcp_app; app=create_mcp_app(); print(f'Tools: {len(app.list_tools())}')"` → prints `Tools: 314` (or higher)
- [ ] Commit: `git commit -m "feat(vc7): MCP expansion complete — 14→314 tools"`
