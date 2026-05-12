"""
VectorCode CLI — entry point.
Usage: vector [mode] [task]
  vector              → Mode A (interactive REPL)
  vector auto "task"  → Mode B (autonomous, single task)
  vector hybrid       → Mode C (hybrid with checkpoint gates)
  vector mcp          → start MCP server (stdio)
  vector mcp --sse    → start MCP server (SSE on port 9000)
  vector status       → show session status
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

# Suppress INFO/DEBUG logs — only show WARNING+ in interactive CLI
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING", format="<yellow>[VECTOR]</yellow> {message}")


def _print_banner():
    print("""
  ██╗   ██╗███████╗ ██████╗████████╗ ██████╗ ██████╗
  ██║   ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
  ██║   ██║█████╗  ██║        ██║   ██║   ██║██████╔╝
  ╚██╗ ██╔╝██╔══╝  ██║        ██║   ██║   ██║██╔══██╗
   ╚████╔╝ ███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║
    ╚═══╝  ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
  Coding District  |  Ollama local  |  /help for commands
""")


def cmd_repl(_args):
    from agents.districts.coding.vectorcode.repl import VectorREPL
    _print_banner()
    VectorREPL().run()


def cmd_auto(args):
    task = " ".join(args.task) if args.task else ""
    if not task:
        print("Usage: vector auto \"your task here\"")
        sys.exit(1)
    from agents.districts.coding.vectorcode.autonomous import VectorAutonomous
    va = VectorAutonomous()
    task_id = va.submit(task)
    print(f"[VectorCode] Task queued: {task_id}")
    print(f"[VectorCode] Task: {task}")


def cmd_hybrid(_args):
    from agents.districts.coding.vectorcode.hybrid import VectorHybrid, CheckpointGate
    vh = VectorHybrid()
    _print_banner()
    print("Mode C — Hybrid (checkpoint gates active)")
    print("  PLAN_APPROVAL  : ON")
    print("  RED_ACTION     : ON")
    print("  DESTRUCTIVE_EDIT: ON")
    print("\nSwitch to REPL for interactive use:")
    from agents.districts.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    repl.session.set_mode("hybrid")
    repl.run()


def cmd_mcp(args):
    import subprocess
    mcp_script = Path(__file__).parent.parent.parent.parent.parent / "core" / "mcp_server.py"
    cmd = [sys.executable, str(mcp_script)]
    if getattr(args, "sse", False):
        cmd += ["--transport", "sse", "--port", "9000"]
    print(f"[VectorCode] Starting MCP server ({' '.join(cmd[2:] or ['stdio'])})")
    subprocess.run(cmd)


def cmd_status(_args):
    from agents.districts.coding.vectorcode.session import VectorCodeSession
    s = VectorCodeSession.get()
    print(f"Mode    : {s.mode}")
    print(f"Model   : {s.current_model}")
    print(f"Task    : {s.task_id or 'none'}")
    print(f"History : {len(s.history)} entries")
    print(f"Agents  : {len(s.active_agents)} active")


def main():
    parser = argparse.ArgumentParser(
        prog="vector",
        description="VectorCode — VECTOR's local coding agent",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("repl",   help="Mode A: interactive terminal REPL (default)")
    auto_p = sub.add_parser("auto", help="Mode B: autonomous single task")
    auto_p.add_argument("task", nargs="*", help="Task description")
    sub.add_parser("hybrid", help="Mode C: hybrid with checkpoint gates")
    mcp_p = sub.add_parser("mcp", help="Start MCP server")
    mcp_p.add_argument("--sse", action="store_true", help="Use SSE transport on port 9000")
    sub.add_parser("status", help="Show current session status")

    args = parser.parse_args()

    dispatch = {
        "repl":   cmd_repl,
        "auto":   cmd_auto,
        "hybrid": cmd_hybrid,
        "mcp":    cmd_mcp,
        "status": cmd_status,
        None:     cmd_repl,   # default: REPL
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
