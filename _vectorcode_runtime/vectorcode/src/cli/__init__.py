"""
vectorcode/src/cli/__init__.py
VECTOR CLI package — drop-in replacement for cli.py monolith.
"""
from ._commands import (
    cmd_repl, cmd_auto, cmd_hybrid, cmd_mcp, cmd_run, cmd_status,
    cmd_sessions, cmd_models, cmd_agents, cmd_skills, cmd_completion,
    cmd_usage, cmd_gateway, cmd_auth, cmd_profile, cmd_doctor,
    cmd_vector_cli_dispatch, cmd_self_update, cmd_version, cmd_cron,
    cmd_acp, cmd_plugins, cmd_tools,
)
from ._runner import main, _run_ipc, _print_hud_banner, _strip_ansi

__all__ = [
    "main", "cmd_repl", "cmd_auto", "cmd_hybrid", "cmd_mcp", "cmd_run",
    "cmd_status", "cmd_sessions", "cmd_models", "cmd_agents", "cmd_skills",
    "cmd_completion", "cmd_usage", "cmd_gateway", "cmd_auth", "cmd_profile",
    "cmd_doctor", "cmd_vector_cli_dispatch", "cmd_self_update", "cmd_version",
    "cmd_cron", "cmd_acp", "cmd_plugins", "cmd_tools",
]
