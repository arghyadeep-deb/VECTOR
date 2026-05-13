"""
VectorCode Tool Registry — all tools wired here for agent/REPL access.

Tool categories:
  filesystem    — read, write, edit, grep, glob, list, move, create, delete, diff
  bash          — bash, background_bash
  git           — git_status, git_diff, git_log, git_commit, git_create_branch, git_push, git_blame
  web           — web_search, web_fetch
  opencli       — search, hn_top, reddit_hot, github_trending, twitter_trending
  code_graph    — find_symbol, get_references (LSP-style codebase graph)
  browser       — browse, screenshot (playwright)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger


# ── Tool registry ─────────────────────────────────────────────────────────────

_REGISTRY: dict = {}


def _lazy(name: str, factory):
    """Register a lazily-instantiated tool."""
    _REGISTRY[name] = {"factory": factory, "instance": None}


def get_tool(name: str):
    """Return a tool instance by name (instantiated lazily on first use)."""
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Unknown tool: '{name}'. Available: {list(_REGISTRY.keys())}")
    if entry["instance"] is None:
        try:
            entry["instance"] = entry["factory"]()
            logger.debug(f"[VECTOR][tools] instantiated tool: {name}")
        except Exception as e:
            logger.warning(f"[VECTOR][tools] tool '{name}' unavailable: {e}")
            return None
    return entry["instance"]


def list_tools() -> list[str]:
    return sorted(_REGISTRY.keys())


# ── Register all tools ─────────────────────────────────────────────────────────

# Filesystem
_lazy("file",       lambda: __import__("tools.file_tools",  fromlist=["FileTools"]).FileTools(str(Path.cwd())))
_lazy("git",        lambda: __import__("tools.git_tools",   fromlist=["GitTools"]).GitTools(repo_root=str(Path.cwd())))
_lazy("web",        lambda: __import__("tools.web_tools",   fromlist=["WebTools"]).WebTools())
_lazy("opencli",    lambda: __import__("tools.opencli_tool",fromlist=["OpenCLITool"]).OpenCLITool())
_lazy("bash",       lambda: __import__("tools.bash_tools",  fromlist=["BashTools"]).BashTools())
_lazy("browser",    lambda: __import__("tools.browser_tools",fromlist=["BrowserTools"]).BrowserTools())
_lazy("code_graph", lambda: __import__("tools.code_graph",  fromlist=["CodeGraph"]).CodeGraph(str(Path.cwd())))


# ── Convenience helpers used by the REPL ──────────────────────────────────────

def make_file_tools(repo_root: str = ""):
    from tools.file_tools import FileTools
    return FileTools(repo_root or str(Path.cwd()))


def make_git_tools(repo_root: str = ""):
    from tools.git_tools import GitTools
    return GitTools(repo_root=repo_root or str(Path.cwd()))


def make_web_tools():
    from tools.web_tools import WebTools
    return WebTools()


def make_opencli_tool():
    from tools.opencli_tool import OpenCLITool
    return OpenCLITool()


if __name__ == "__main__":
    print("Registered tools:", list_tools())
    try:
        wt = make_web_tools()
        assert wt is not None
        print("  web_tools OK")
    except Exception as e:
        print(f"  web_tools WARN: {e}")
    try:
        oc = make_opencli_tool()
        assert oc is not None
        health = oc.check_health()
        print(f"  opencli_tool OK — available={health['available']}")
    except Exception as e:
        print(f"  opencli_tool WARN: {e}")
    print("tools/__init__.py OK")
