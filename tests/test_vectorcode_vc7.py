"""VC-7 tests: MCP tool expansion 14 → 300+ tools."""
import asyncio
import pytest


def _get_tool_names():
    from core.mcp_server import create_mcp_app
    app = create_mcp_app()
    tools = asyncio.run(app.list_tools())
    return [t.name for t in tools]


def test_agent_tools_registered():
    tool_names = _get_tool_names()
    for name in [
        "agent_spawn", "agent_list", "agent_status", "agent_stop",
        "agent_metrics", "agent_pool", "agent_health", "agent_logs",
        "swarm_init", "swarm_submit", "swarm_assign",
        "swarm_execute", "swarm_status", "swarm_shutdown",
        "swarm_topology", "swarm_agents", "swarm_report",
    ]:
        assert name in tool_names, f"Missing tool: {name}"


def test_memory_hook_task_tools_registered():
    tool_names = _get_tool_names()
    memory_tools = [
        "memory_faiss_add", "memory_faiss_search", "memory_pattern_save",
        "memory_pattern_recall", "memory_bridge_sync", "memory_export",
        "memory_import", "memory_stats", "memory_clear",
        "memory_semantic_search", "memory_recent", "memory_categories",
    ]
    hook_tools = [
        "hook_register", "hook_fire", "hook_list",
        "hook_pre_edit", "hook_post_edit", "hook_pre_task",
        "hook_post_task", "hook_session_start", "hook_session_end",
        "hook_route", "hook_explain", "hook_notify",
        "hook_intelligence", "hook_task_complete",
        "hook_session_restore", "hook_post_command", "hook_transfer",
    ]
    task_tools = [
        "task_create", "task_assign", "task_complete",
        "task_list", "task_update", "task_delete",
        "task_status", "task_submit_bg",
    ]
    for name in memory_tools + hook_tools + task_tools:
        assert name in tool_names, f"Missing: {name}"


def test_security_neural_file_git_tools():
    tool_names = _get_tool_names()
    security = [
        "security_scan", "security_audit", "security_validate",
        "security_path_check", "security_cve_scan",
        "security_threats", "security_report",
        "security_input_validate", "security_executor_check", "security_allowlist",
    ]
    neural = [
        "neural_pattern_save", "neural_pattern_recall", "neural_train",
        "neural_status", "neural_predict", "neural_optimize",
        "neural_reward", "neural_stats",
    ]
    file_t = [
        "file_read", "file_write", "file_edit", "file_grep",
        "file_glob", "file_delete", "file_exists",
        "file_diff", "file_list_dir", "file_copy",
    ]
    git_t = [
        "git_commit", "git_push", "git_pr_create", "git_diff",
        "git_blame", "git_log", "git_branch",
        "git_checkout", "git_stash",
        "git_merge", "git_rebase",
    ]
    for name in security + neural + file_t + git_t:
        assert name in tool_names, f"Missing: {name}"


def test_remaining_tool_categories():
    tool_names = _get_tool_names()
    categories = ["test_", "doc_", "browser_", "graph_", "perf_", "worker_", "config_"]
    for prefix in categories:
        matching = [n for n in tool_names if n.startswith(prefix)]
        assert len(matching) >= 4, f"Category {prefix} has only {len(matching)} tools"


def test_total_tool_count():
    tool_names = _get_tool_names()
    assert len(tool_names) >= 300, f"Expected 300+ tools, got {len(tool_names)}"
