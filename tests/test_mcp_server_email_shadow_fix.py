"""
Root-caused a real, structural bug found while debugging a recurring
"MCP server exited — restarting in 5s" loop spam during a live soak run
(2026-06-24), after confirming the vectorcode/src/cli.py path bug (a
separate, already-fixed issue -- see test_vectorcode_mcp_port_fix.py) was
not the only cause.

Root cause: core/mcp_server.py has no sys.path setup of its own. When
launched as a direct script (`python core/mcp_server.py ...` -- exactly
what districts/coding/vectorcode_bridge.py::start_mcp_server() does via
subprocess.Popen), Python auto-prepends the SCRIPT'S OWN DIRECTORY
(core/) to sys.path[0]. Since core/ contains a real subpackage named
core/email/ (VECTOR's own email handling), every module inside core/
becomes importable by its bare name -- so the first time anything deep in
the import chain does a plain `import email` (pydantic's plugin loader
does exactly this via importlib.metadata), Python resolves it to VECTOR's
core/email/ instead of the stdlib email package, which then crashes on an
unrelated circular-ish import (core.email -> core.memory -> core.config)
with a confusing "cannot import name 'CONFIG' from 'core.config'" error
that has nothing to do with the real problem.

This reproduces identically regardless of invocation cwd -- confirmed by
running `python core/mcp_server.py` directly from the repo root.
core/mcp_server.py's own docstring says "Run: python core/mcp_server.py",
i.e. direct-script invocation is the documented, intended usage, not an
edge case.

Fixed: core/mcp_server.py now removes its own auto-added directory from
sys.path and ensures the real repo root is present instead, before any
other import runs.
"""
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_MCP_SERVER = _REPO_ROOT / "core" / "mcp_server.py"


def test_mcp_server_module_source_strips_its_own_directory_from_sys_path():
    """Static check that the fix is actually present: core/mcp_server.py
    must remove its own auto-prepended directory from sys.path before any
    import that could trigger the stdlib `email` shadowing (pydantic's
    plugin loader does this transitively), and that fix-up must come
    before the first `from core.` import in the file."""
    source = _MCP_SERVER.read_text(encoding="utf-8")
    fixup_idx = source.find("sys.path[:] = [p for p in sys.path if p !=")
    first_core_import_idx = source.find("from core.")
    assert fixup_idx != -1, (
        "core/mcp_server.py must strip its own auto-prepended script "
        "directory from sys.path before any import that could trigger "
        "the core/email/ vs stdlib email shadowing bug"
    )
    assert fixup_idx < first_core_import_idx, (
        "the sys.path fix-up must run before the first 'from core.' import"
    )


def test_mcp_server_script_does_not_crash_on_startup_import_chain():
    """Real, non-mocked reproduction of the actual failure: launch
    core/mcp_server.py exactly as vectorcode_bridge.py does (direct script,
    stdio transport so it doesn't need a free port), and confirm it gets
    past the import chain that previously crashed with "cannot import name
    'CONFIG' from 'core.config'". The process is killed after a short grace
    period since stdio-mode mcp_server.py blocks waiting for input -- the
    test only cares that it didn't crash during import/startup."""
    proc = subprocess.Popen(
        [sys.executable, str(_MCP_SERVER)],
        cwd=str(_REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        proc.wait(timeout=3)
        # If it exited within 3s, it must not be because of the import crash.
        _, stderr = proc.communicate()
        assert "cannot import name 'CONFIG'" not in stderr
        assert "core/email" not in stderr.replace("\\", "/")
    except subprocess.TimeoutExpired:
        # Still running after 3s with no crash -- the good outcome for a
        # stdio server waiting on input. Clean up.
        proc.kill()
        proc.wait(timeout=5)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
