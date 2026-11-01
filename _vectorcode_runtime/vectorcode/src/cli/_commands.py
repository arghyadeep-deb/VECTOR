"""vectorcode/src/cli/_commands.py — CLI commands from the canonical cli.py monolith."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

_KEY = "_vector_cli_monolith"
if _KEY not in sys.modules:
    _path = Path(__file__).parent.parent / "cli.py"
    _spec = importlib.util.spec_from_file_location(_KEY, str(_path))
    assert _spec is not None
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_KEY] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_mod = sys.modules[_KEY]

cmd_repl = _mod.cmd_repl
cmd_auto = _mod.cmd_auto
cmd_hybrid = _mod.cmd_hybrid
cmd_mcp = _mod.cmd_mcp
cmd_run = _mod.cmd_run
cmd_status = _mod.cmd_status
cmd_sessions = _mod.cmd_sessions
cmd_models = _mod.cmd_models
cmd_agents = _mod.cmd_agents
cmd_skills = _mod.cmd_skills
cmd_completion = _mod.cmd_completion
cmd_usage = _mod.cmd_usage
cmd_gateway = _mod.cmd_gateway
cmd_auth = _mod.cmd_auth
cmd_profile = _mod.cmd_profile
cmd_doctor = _mod.cmd_doctor
cmd_vector_cli_dispatch = _mod.cmd_vector_cli_dispatch
cmd_self_update = _mod.cmd_self_update
cmd_version = _mod.cmd_version
cmd_cron = _mod.cmd_cron
cmd_acp = _mod.cmd_acp
cmd_plugins = _mod.cmd_plugins
cmd_tools = _mod.cmd_tools
main = _mod.main
_run_ipc = _mod._run_ipc
_print_hud_banner = _mod._print_hud_banner
_strip_ansi = _mod._strip_ansi
