"""VectorCode CLI commands — consolidated from VectorCode 52+ CLI files."""
from loguru import logger

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


def cmd_version(args):
    print(f"VectorCode v{VERSION}")


def cmd_status(args):
    """Show status of all components."""
    print(f"VectorCode v{VERSION}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  CWD: {Path.cwd()}")
    print(f"  Comms platforms: telegram, discord, slack, signal, whatsapp, matrix, email, webhook")
    try:
        from providers.model_metadata import MODELS
        print(f"  Models configured: {len(MODELS)}")
    except Exception as _sve:
        logger.debug("[VECTOR][cli_commands] suppressed Exception: %s", _sve)


def cmd_doctor(args):
    """Check configuration and dependencies."""
    checks = []
    checks.append(("Python 3.11+", sys.version_info >= (3, 11)))
    try: import ollama; checks.append(("Ollama SDK", True))
    except Exception: checks.append(("Ollama SDK", False))
    try: import httpx; checks.append(("httpx", True))
    except Exception: checks.append(("httpx", False))
    try: import aiohttp; checks.append(("aiohttp", True))
    except Exception: checks.append(("aiohttp", False))
    try: import loguru; checks.append(("loguru", True))
    except Exception: checks.append(("loguru", False))
    for name, ok in checks:
        print(f"  {'✓' if ok else '✗'} {name}")


def cmd_setup(args):
    """Interactive setup wizard."""
    print("VectorCode Setup Wizard")
    print("=======================")
    ans = input("Configure Ollama? [Y/n]: ") or "y"
    if ans.lower() == "y":
        print("  Make sure Ollama is running: ollama serve")
        print("  VectorCode will auto-detect models on startup.")
    ans = input("Enter default API key for Anthropic (optional): ")
    if ans.strip():
        os.environ["ANTHROPIC_API_KEY"] = ans.strip()
        print("  ANTHROPIC_API_KEY set for this session.")
    ans = input("Enter default API key for OpenAI (optional): ")
    if ans.strip():
        os.environ["OPENAI_API_KEY"] = ans.strip()
        print("  OPENAI_API_KEY set for this session.")
    print("Setup complete. Run 'vector' to start.")


def cmd_logs(args):
    """Show recent logs."""
    log_dir = Path.home() / ".vector" / "logs"
    if not log_dir.exists():
        print("No logs found.")
        return
    logs = sorted(log_dir.glob("*.log"), reverse=True)
    if args.get("tail") and logs:
        lines = logs[0].read_text().splitlines()[-20:]
        for line in lines:
            print(line)
    elif logs:
        for log_file in logs[:5]:
            print(f"  {log_file.name} ({log_file.stat().st_size} bytes)")
    else:
        print("No logs found.")


def cmd_backup(args):
    """Backup configuration and data."""
    backup_dir = Path.home() / ".vector" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    dst = backup_dir / f"vector_backup_{ts}"
    dst.mkdir(parents=True, exist_ok=True)
    src = Path.home() / ".vector"
    if src.exists():
        for item in src.iterdir():
            if item.name not in ("backups", "logs", "cache"):
                if item.is_file(): shutil.copy2(item, dst)
        print(f"Backup saved to {dst}")
    else:
        print("Nothing to backup.")


def cmd_completion(args):
    """Generate shell completion script."""
    shell = args.get("shell", "bash")
    if shell == "bash":
        print('''_vector_completions() {
    local cur opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    opts="repl run auto status doctor setup logs backup version help"
    COMPREPLY=($(compgen -W "${opts}" -- ${cur}))
}
complete -F _vector_completions vector''')
    elif shell == "zsh":
        print('''#compdef vector
_arguments \\
    "repl:Start interactive REPL" \\
    "run:One-shot task" \\
    "status:Show status" \\
    "doctor:Check dependencies" \\
    "setup:Setup wizard" \\
    "logs:View logs" \\
    "backup:Backup config" \\
    "version:Show version"''')
    else:
        print(f"Unknown shell: {shell}")


def cmd_update(args):
    """Update VectorCode to latest version."""
    print("Update not yet implemented. Pull latest from repository.")


CMD_TABLE: dict[str, dict] = {
    "version": {"fn": cmd_version, "help": "Show version"},
    "status": {"fn": cmd_status, "help": "Show system status"},
    "doctor": {"fn": cmd_doctor, "help": "Check dependencies and configuration"},
    "setup": {"fn": cmd_setup, "help": "Interactive setup wizard"},
    "logs": {"fn": cmd_logs, "help": "View logs"},
    "backup": {"fn": cmd_backup, "help": "Backup configuration"},
    "completion": {"fn": cmd_completion, "help": "Generate shell completion"},
    "update": {"fn": cmd_update, "help": "Update VectorCode"},
}


def run_cli_command(cmd_name: str, args: Optional[dict] = None):
    cmd = CMD_TABLE.get(cmd_name)
    if cmd:
        cmd["fn"](args or {})
    else:
        print(f"Unknown command: {cmd_name}. Try: {', '.join(CMD_TABLE.keys())}")
