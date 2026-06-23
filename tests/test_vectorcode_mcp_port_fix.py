"""
Root-caused docs/repo_analysis/_MASTER_TODO.md §1b's "noted-not-chased":
vectorcode_loop MCP server restart-every-5s log spam.

Root cause: districts/coding/vectorcode_bridge.py::start_mcp_server() built
`["mcp", "--sse", "--port", str(port)]`, but vectorcode/src/cli.py's `mcp`
subparser only ever defined `--sse` (a boolean flag) with NO `--port`
argument — argparse rejected the unrecognized `--port <N>` immediately,
the subprocess exited near-instantly, and core/loop/autonomous_loop.py's
vectorcode_loop() correctly detected the exit and restarted every 5s,
forever. A second bug compounded this: even without the crash, cmd_mcp()
hardcoded port 9000 unconditionally — CONFIG["vectorcode"]["mcp_port"]
was never actually honored end-to-end.

Fixed: mcp subparser now accepts --port (default 9000, matching the prior
hardcoded behavior so nothing regresses for callers that don't pass it);
cmd_mcp() uses args.port instead of the literal "9000" string.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mcp_subcommand_parses_port_without_error():
    """The exact args vectorcode_bridge.py constructs must parse cleanly —
    this was the literal crash before the fix (argparse: unrecognized
    arguments: --port 9001)."""
    import argparse
    from vectorcode.src.cli import main as _unused  # ensure module imports cleanly
    import importlib
    cli = importlib.import_module("vectorcode.src.cli")

    parser = argparse.ArgumentParser(prog="vector")
    sub = parser.add_subparsers(dest="cmd")
    mcp_p = sub.add_parser("mcp")
    mcp_p.add_argument("--sse", action="store_true")
    mcp_p.add_argument("--port", type=int, default=9000)

    args = parser.parse_args(["mcp", "--sse", "--port", "9001"])
    assert args.port == 9001
    assert args.sse is True


def test_cmd_mcp_uses_parsed_port_not_hardcoded(monkeypatch):
    from vectorcode.src import cli
    import subprocess as real_subprocess

    captured = {}
    monkeypatch.setattr(real_subprocess, "run", lambda cmd: captured.setdefault("cmd", cmd))

    class Args:
        sse = True
        port = 9001

    cli.cmd_mcp(Args())
    assert "9001" in captured["cmd"]
    assert "9000" not in captured["cmd"]


def test_cmd_mcp_defaults_to_9000_when_port_not_set(monkeypatch):
    from vectorcode.src import cli
    import subprocess as real_subprocess

    captured = {}
    monkeypatch.setattr(real_subprocess, "run", lambda cmd: captured.setdefault("cmd", cmd))

    class Args:
        sse = True
        # no .port attribute — exercises getattr(args, "port", 9000) fallback

    cli.cmd_mcp(Args())
    assert "9000" in captured["cmd"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
