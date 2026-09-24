"""vectorcode skill library visibility + home helper.

2026-09-24 findings: `skills_list` returned nothing although 4,000+ SKILL.md files ship under vectorcode/skills
(the tool only scanned ~/.vector/skills plus hand-configured external dirs), and tui_gateway imported a
`get_vectorcode_home` that did not exist. Child process: bare imports need vectorcode/src on sys.path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CHILD = r"""
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "vectorcode", "src"))
sys.path.insert(0, sys.argv[1])
from loguru import logger; logger.remove()
from agent.skill_utils import get_external_skills_dirs
from vector_constants import get_vectorcode_home, get_vector_home
dirs = get_external_skills_dirs()
out = {"dirs": [str(d) for d in dirs], "home_alias": get_vectorcode_home() == get_vector_home()}
from tools.registry import registry
import model_tools
r = json.loads(registry.dispatch("skills_list", {}))
out["success"] = r.get("success"); out["count"] = len(r.get("skills", []))
import importlib
for mod in ("tui_gateway.server", "tui_gateway.entry", "tui_gateway.ws"):
    try:
        importlib.import_module(mod); out[mod] = "ok"
    except BaseException as e:
        out[mod] = type(e).__name__ + ": " + str(e)[:160]
from pathlib import Path
from tools.registry import ToolRouter
rt = ToolRouter(Path.cwd())
out["todo"] = json.loads(rt.execute("todo", {"todos": [{"id": "1", "content": "write it", "status": "pending"}]}))
out["todo_read"] = json.loads(rt.execute("todo", {}))
out["memory"] = json.loads(rt.execute("memory", {"action": "add", "target": "memory", "content": "vector test fact"}))
out["session_search"] = json.loads(rt.execute("session_search", {"query": ""}))
out["descriptions"] = [x["description"] for x in r.get("skills", [])[:20]]
import transports
out["transports"] = sorted(transports.list_transports())
print("RESULT:" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    work = Path(tempfile.mkdtemp(prefix="vc_skills_"))
    (work / "home").mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(work / "home"), USERPROFILE=str(work / "home"), VECTOR_DB_PATH=str(work / "vm.db"),
               VECTOR_TEST_DATA_DIR=str(work / "data"), VECTOR_DB_KEY="vc-skills-test")
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT)], capture_output=True, text=True, timeout=280,
                       env=env, cwd=str(work))
    # tui_gateway.entry re-points stdout at stderr (stdout is its JSON-RPC pipe), so look in both
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result:\n{r.stderr[-900:]}"
    return json.loads(lines[-1][len("RESULT:"):])


def test_shipped_skill_library_is_a_default_skills_dir(result):
    assert any(d.replace("\\", "/").endswith("vectorcode/skills") for d in result["dirs"])


def test_skills_list_returns_the_shipped_skills(result):
    assert result["success"] and result["count"] > 1000


def test_get_vectorcode_home_alias_exists(result):
    assert result["home_alias"] is True


def test_skill_descriptions_are_parsed_past_the_ingest_comment(result):
    assert not any(d.startswith("<!--") for d in result["descriptions"])
    assert all(d.strip() for d in result["descriptions"])


def test_todo_tool_works_inside_the_router(result):
    """model_tools answered 'must be handled by the agent loop' for todo/memory/session_search."""
    assert result["todo"]["summary"]["total"] == 1 and result["todo_read"]["summary"]["pending"] == 1


def test_memory_tool_works_inside_the_router(result):
    assert "error" not in result["memory"] and result["memory"].get("success") is not False, result["memory"]


def test_session_search_reaches_the_session_db(result):
    assert "must be handled" not in json.dumps(result["session_search"]), result["session_search"]


@pytest.mark.parametrize("mod", ["tui_gateway.server", "tui_gateway.entry", "tui_gateway.ws"])
def test_tui_gateway_modules_import(result, mod):
    """They imported a missing get_vectorcode_home / load_vectorcode_dotenv, a shim that hides _CRASH_LOG, and
    Unix-only SIGPIPE/SIGHUP."""
    assert result[mod] == "ok", result[mod]


def test_transports_register_without_a_phantom_ollama_module(result):
    assert result["transports"] == ["anthropic_messages", "chat_completions"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
