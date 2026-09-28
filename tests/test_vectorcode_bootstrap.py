"""vectorcode's path bootstrap must not hide the installed MCP SDK.

2026-09-24 finding: ensure_paths() puts vectorcode/src on sys.path, and its own `mcp/` folder then shadowed the
installed `mcp` package -- `from mcp.server.fastmcp import FastMCP` failed for every other consumer unless the
SDK happened to be imported before the bootstrap ran. Runs in child processes: it manipulates sys.path/meta_path.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_PROBE = r"""
import sys
sys.path.insert(0, sys.argv[1])
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()
import importlib.util
mcp_spec = importlib.util.find_spec("mcp")
import tools
print("MCP_ORIGIN=" + str(mcp_spec.origin if mcp_spec else None))
print("TOOLS_ORIGIN=" + str(tools.__file__))
try:
    from mcp.server.fastmcp import FastMCP
    print("FASTMCP=ok")
except Exception as exc:
    print("FASTMCP=" + type(exc).__name__)
ensure_paths()  # idempotent: must not stack a second hook
print("HOOKS=" + str(sum(1 for f in sys.meta_path if getattr(f, "__name__", "") == "_PreferInstalledMcp")))
"""


@pytest.fixture(scope="module")
def probe():
    r = subprocess.run([sys.executable, "-c", _PROBE, str(ROOT)], capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    out = dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln and ln.split("=", 1)[0] in
               ("MCP_ORIGIN", "TOOLS_ORIGIN", "FASTMCP", "HOOKS"))
    assert out, r.stderr[-800:]
    return out


def test_installed_mcp_sdk_wins_over_vectorcodes_own_mcp_folder(probe):
    pytest.importorskip("mcp")
    assert "site-packages" in probe["MCP_ORIGIN"].replace("\\", "/")
    assert probe["FASTMCP"] == "ok"


def test_other_bare_imports_still_resolve_to_vectorcode(probe):
    assert "vectorcode" in probe["TOOLS_ORIGIN"].replace("\\", "/")


def test_guard_is_installed_once(probe):
    assert probe["HOOKS"] == "1"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
