"""vectorcode's real agent loop (engine/agent_loop.py).

2026-09-24 findings: it imported a `ToolRouter` that did not exist, so `run_conversation` crashed before its
first model call and the REPL silently fell back to a plain chat with no tools (which then invented file
contents). Also `providers.ModelRouter` did not exist and its import sat outside the try, so even bare local
model names never reached the Ollama fallback; and the Ollama fallback dropped the system prompt and sent
tool calls in the wrong format.

Child process: vectorcode's bare imports need `vectorcode/src` on sys.path, whose `mcp/`, `tools/` and
`recipes/` packages would otherwise shadow installed packages for the whole test run.
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
work = sys.argv[2]; os.chdir(work)
import pathlib
from engine.agent_loop import VectorAgent
from tools.registry import ToolRouter

out = {}
router = ToolRouter(project_dir=work)
out["tools"] = router.tool_names()
out["unknown_refused"] = json.loads(router.execute("send_message", {"target": "x", "message": "y"}))
out["read"] = json.loads(router.execute("read_file", {"path": "notes.txt"}))

# scripted model: first turn asks for read_file, second turn answers from the tool result
seen = {"calls": 0, "second_turn_messages": None}
def scripted(self, messages, system_message, tool_schemas):
    seen["calls"] += 1
    if seen["calls"] == 1:
        return {"content": "", "tool_calls": [{"id": "t1", "name": "read_file", "arguments": json.dumps({"path": "other.txt"})}],
                "finish_reason": "tool_calls", "usage": {}}
    seen["second_turn_messages"] = [m.get("role") for m in messages]
    tool_msg = [m for m in messages if m.get("role") == "tool"][-1]["content"]
    return {"content": "the file says: " + ("hello" if "hello" in tool_msg else "NOTHING"), "tool_calls": [], "finish_reason": "stop", "usage": {}}
VectorAgent._call_model = scripted
events = []
agent = VectorAgent(model_id="vector-focus", project_dir=pathlib.Path(work), session_id="t", quiet_mode=True, save_trajectories=False,
                    tool_start_callback=lambda n, a: events.append(("start", n)), tool_complete_callback=lambda n, r, ms: events.append(("done", n)))
res = agent.run_conversation("read other.txt", system_message="use tools", conversation_history=[])
out["loop"] = {"response": res["response"], "iterations": res["iterations"], "events": events, "second_turn_roles": seen["second_turn_messages"]}

# message conversion for Ollama
conv = VectorAgent._to_ollama_messages([
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "read_file", "arguments": "{\"path\": \"a\"}"}]},
    {"role": "tool", "name": "read_file", "content": "X"},
], "SYS")
out["conv"] = conv
print("RESULT:" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    work = Path(tempfile.mkdtemp(prefix="vc_loop_"))
    (work / "notes.txt").write_bytes(b"hello\nline two\n")
    (work / "other.txt").write_bytes(b"hello again\n")  # read_file dedups a repeated read of the same file
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VECTOR_HOME")}  # model_tools exports VECTOR_HOME into the parent; never let a child inherit the real one
    env.update(HOME=str(work / "home"), USERPROFILE=str(work / "home"), VECTOR_DB_PATH=str(work / "vm.db"), VECTOR_TEST_DATA_DIR=str(work / "data"), VECTOR_DB_KEY="vc-loop-test")
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT), str(work)], capture_output=True, text=True,
                       timeout=240, env=env, cwd=str(work))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert lines, f"child produced no result:\n{r.stderr[-900:]}"
    return json.loads(lines[-1][len("RESULT:"):])


def test_tool_router_exists_and_exposes_only_coding_tools(result):
    names = set(result["tools"])
    assert {"read_file", "write_file", "patch", "terminal", "search_files"} <= names
    assert not names & {"send_message", "discord", "spotify_playback", "cronjob", "delegate_task", "browser_navigate"}


def test_tool_router_refuses_tools_outside_the_agents_toolsets(result):
    assert "not available" in result["unknown_refused"]["error"]


def test_tool_router_executes_real_tools(result):
    assert result["read"]["total_lines"] == 2 and "hello" in result["read"]["content"]


def test_agent_loop_runs_a_tool_and_answers_from_the_real_result(result):
    loop = result["loop"]
    assert loop["events"] == [["start", "read_file"], ["done", "read_file"]]
    assert loop["response"] == "the file says: hello"
    assert loop["iterations"] == 2
    assert "tool" in loop["second_turn_roles"]


def test_ollama_message_conversion_keeps_system_prompt_and_tool_format(result):
    conv = result["conv"]
    assert conv[0] == {"role": "system", "content": "SYS"}
    assistant = conv[2]
    assert assistant["tool_calls"] == [{"function": {"name": "read_file", "arguments": {"path": "a"}}}]
    assert conv[3] == {"role": "tool", "content": "X", "tool_name": "read_file"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
