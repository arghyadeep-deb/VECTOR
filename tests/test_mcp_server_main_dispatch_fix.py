"""
Root-caused the REAL, final cause of the "MCP server exited — restarting
in 5s" loop spam (2026-06-24 live soak run) -- found after fixing two other
real bugs in the same call chain (vectorcode/src/cli.py's path bug, and
core/mcp_server.py's stdlib-email-shadowing bug) that turned out not to be
the whole story.

Root cause: core/mcp_server.py's `if __name__ == "__main__":` block NEVER
calls main() -- the function that actually parses --transport/--port and
calls `mcp.run(transport="sse", ...)` to serve requests. The __main__ block
instead always runs its OWN, separate, hardcoded scaffold-verification
logic (prints a tool list banner, matching this codebase's own
"# real test, no mocks" self-test convention from code_style.md) and then
the script falls off the end and exits with returncode 0 -- regardless of
what CLI args were passed.

This was invisible in every manual interactive test during debugging:
`python core/mcp_server.py --transport sse --port N` prints
"mcp_server.py OK -- VECTOR server built" (the scaffold banner, easily
mistaken for "server started successfully") and then exits almost
instantly with rc=0 -- not a crash, just silent non-dispatch. Confirmed via
direct subprocess.Popen + proc.poll(): returncode 0 within ~4 seconds,
every single time, regardless of args.

Fixed: __main__ now checks whether real server args were passed
(--transport/--port/--host present in sys.argv) and dispatches to main()
in that case; falls back to the original scaffold self-test only when
invoked bare, preserving the existing convention for the common
"is this file importable and buildable" smoke-test case.
"""
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_MCP_SERVER = _REPO_ROOT / "core" / "mcp_server.py"


def test_mcp_server_main_function_exists_and_is_callable():
    """Sanity: main() must still exist as a real, callable dispatch
    function (it was never deleted, just never invoked)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", _MCP_SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.main)


def test_mcp_server_with_sse_args_actually_blocks_serving_not_exits_immediately():
    """The exact real-world reproduction: invoke exactly as
    districts/coding/vectorcode_bridge.py::start_mcp_server() does, and
    confirm the process is STILL RUNNING after a few seconds -- the old
    bug exited with returncode 0 almost immediately, every time."""
    proc = subprocess.Popen(
        [sys.executable, str(_MCP_SERVER), "--transport", "sse", "--port", "9199"],
        cwd=str(_REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4)
        assert proc.poll() is None, (
            "mcp_server.py exited on its own (returncode "
            f"{proc.returncode}) instead of blocking to serve SSE requests "
            "-- the __main__ block is not dispatching to main()"
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_mcp_server_with_no_args_still_runs_the_scaffold_self_test():
    """The existing, established convention must still work for the bare
    invocation case (no CLI args) -- this is the codebase's own
    "# real test, no mocks" pattern from code_style.md, not something to
    break while fixing the dispatch bug."""
    result = subprocess.run(
        [sys.executable, str(_MCP_SERVER)],
        cwd=str(_REPO_ROOT),
        # A cold Windows import can approach 20 seconds when the wider suite
        # is busy (notably while torch probes CUDA). Keep a finite hang guard
        # without making normal startup a timing race.
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
