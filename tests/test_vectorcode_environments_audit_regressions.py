"""Regression tests for the environments audit completed on 2026-10-07."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sqlite3
import sys
import tarfile
import types
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = ROOT / "vectorcode" / "src" / "environments"


def _module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _load(monkeypatch, name: str, relative_path: str, stubs: dict[str, types.ModuleType]):
    for stub_name, module in stubs.items():
        monkeypatch.setitem(sys.modules, stub_name, module)
    spec = importlib.util.spec_from_file_location(name, ENV_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _base_stubs():
    class FakeConfig(BaseModel):
        model_config = {"extra": "allow"}

    class FakeEnv:
        pass

    return {
        "vectorcode.src.bootstrap": _module("vectorcode.src.bootstrap", ensure_paths=lambda: None),
        "atroposlib.envs.base": _module(
            "atroposlib.envs.base",
            EvalHandlingEnum=SimpleNamespace(STOP_TRAIN="stop"),
            ScoredDataGroup=dict,
            ScoredDataItem=dict,
        ),
        "atroposlib.envs.server_handling.server_manager": _module(
            "atroposlib.envs.server_handling.server_manager", APIServerConfig=object
        ),
        "atroposlib.type_definitions": _module("atroposlib.type_definitions", Item=dict),
        "environments.vector_base_env": _module(
            "environments.vector_base_env",
            VectorAgentBaseEnv=FakeEnv,
            VectorAgentEnvConfig=FakeConfig,
        ),
        "environments.agent_loop": _module(
            "environments.agent_loop", AgentResult=object, VectorAgentLoop=object
        ),
        "environments.tool_context": _module("environments.tool_context", ToolContext=object),
        "tools.terminal_tool": _module(
            "tools.terminal_tool",
            register_task_env_overrides=lambda *a, **k: None,
            clear_task_env_overrides=lambda *a, **k: None,
            cleanup_vm=lambda *a, **k: None,
        ),
    }


async def test_agent_loop_records_positive_exit_code_tool_errors(monkeypatch):
    tool_result = json.dumps({"error": "command failed", "exit_code": 1})
    stubs = {
        "model_tools": _module(
            "model_tools", handle_function_call=lambda *a, **k: tool_result
        ),
        "tools.terminal_tool": _module(
            "tools.terminal_tool", get_active_env=lambda task_id: None
        ),
        "tools.tool_result_storage": _module(
            "tools.tool_result_storage",
            maybe_persist_tool_result=lambda content, **kwargs: content,
            enforce_turn_budget=lambda *a, **k: None,
        ),
        "tools.budget_config": _module("tools.budget_config", DEFAULT_BUDGET=object()),
        "tools.todo_tool": _module(
            "tools.todo_tool", TodoStore=object, todo_tool=lambda **kwargs: "{}"
        ),
    }
    module = _load(monkeypatch, "audit_agent_loop", "agent_loop.py", stubs)

    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="terminal", arguments='{"command":"false"}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[tool_call], content="", reasoning_content=None,
        ))]
    )

    class Server:
        async def chat_completion(self, **kwargs):
            return response

    result = await module.VectorAgentLoop(
        Server(), [{"type": "function"}], {"terminal"}, max_turns=1
    ).run([{"role": "user", "content": "run it"}])
    assert len(result.tool_errors) == 1
    assert result.tool_errors[0].error == "command failed"


def test_terminalbench_archive_extraction_and_upload_failure_are_fail_closed(
    monkeypatch, tmp_path
):
    module = _load(
        monkeypatch,
        "audit_terminalbench",
        "benchmarks/terminalbench_2/terminalbench2_env.py",
        _base_stubs(),
    )

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        data = b"assert True\n"
        info = tarfile.TarInfo("test_ok.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    with tarfile.open(fileobj=io.BytesIO(payload.getvalue()), mode="r:gz") as archive:
        module._safe_extract_tar(archive, tmp_path / "out")
    assert (tmp_path / "out" / "test_ok.py").read_bytes() == b"assert True\n"

    class FailingContext:
        def terminal(self, *args, **kwargs):
            return {"exit_code": 0, "output": ""}

        def upload_dir(self, *args, **kwargs):
            return [{"exit_code": 1, "output": "upload failed"}]

    env = object.__new__(module.TerminalBench2EvalEnv)
    env.config = SimpleNamespace(test_timeout=10)
    encoded = __import__("base64").b64encode(payload.getvalue()).decode("ascii")
    assert env._run_tests(
        {"tests_tar": encoded, "test_sh": "exit 0"}, FailingContext(), "task"
    ) == 0.0


def test_yc_bench_only_counts_completed_horizon_as_survival(monkeypatch, tmp_path):
    module = _load(
        monkeypatch,
        "audit_yc_bench",
        "benchmarks/yc_bench/yc_bench_env.py",
        _base_stubs(),
    )
    db_path = tmp_path / "unfinished.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE companies (funds_cents INTEGER)")
    conn.execute("INSERT INTO companies VALUES (25000000)")
    conn.execute("CREATE TABLE sim_events (event_type TEXT, scheduled_at TEXT)")
    conn.commit()
    conn.close()

    score = module._read_final_score(str(db_path))
    assert score["terminal_reason"] == "unknown"
    assert score["survived"] is False


async def test_agentic_opd_overwrites_model_authored_tests_with_trusted_tests(monkeypatch):
    module = _load(
        monkeypatch,
        "audit_agentic_opd",
        "agentic_opd_env.py",
        _base_stubs(),
    )

    class Context:
        def __init__(self):
            self.written = None

        def write_file(self, path, content):
            self.written = (path, content)
            return {"exit_code": 0}

        def terminal(self, command, timeout):
            return {"exit_code": 1, "output": "AssertionError"}

    env = object.__new__(module.AgenticOPDEnv)
    env.config = SimpleNamespace(
        max_agent_turns=10,
        correctness_weight=0.7,
        efficiency_weight=0.15,
        tool_usage_weight=0.15,
    )
    env._reward_buffer = []
    env._correctness_buffer = []
    env._efficiency_buffer = []
    env._tool_usage_buffer = []
    context = Context()
    result = SimpleNamespace(turns_used=1, messages=[])

    await env.compute_reward(
        {"test_code": "from solution import answer\nassert answer() == 42"},
        result,
        context,
    )
    assert context.written == (
        "test_solution.py",
        "from solution import answer\nassert answer() == 42",
    )
    assert env._correctness_buffer == [0.2]


def test_agentic_opd_hint_selection_requires_a_real_majority(monkeypatch):
    module = _load(
        monkeypatch,
        "audit_agentic_opd_majority",
        "agentic_opd_env.py",
        _base_stubs(),
    )
    positive = {"score": 1, "hint": "Use the error message to fix the call."}
    negative = {"score": -1, "hint": ""}
    assert module._select_best_hint([positive, negative, negative]) is None
    assert module._select_best_hint([positive, positive, negative]) == positive


async def test_web_research_efficiency_counts_tool_calls_not_llm_turns(monkeypatch):
    module = _load(
        monkeypatch,
        "audit_web_research",
        "web_research_env.py",
        _base_stubs(),
    )
    env = object.__new__(module.WebResearchEnv)
    env.config = SimpleNamespace(
        correctness_weight=0.0,
        tool_usage_weight=0.0,
        efficiency_weight=1.0,
        diversity_bonus=0.0,
        efficient_max_calls=2,
        heavy_penalty_calls=5,
    )
    env._reward_buffer = []
    env._correctness_buffer = []
    env._tool_usage_buffer = []
    env._efficiency_buffer = []
    env._diversity_buffer = []

    async def judge(**kwargs):
        return 1.0

    env._llm_judge = judge
    tool_calls = [
        {"function": {"name": "web_search", "arguments": "{}"}}
        for _ in range(6)
    ]
    result = SimpleNamespace(
        turns_used=1,
        messages=[
            {"role": "assistant", "tool_calls": tool_calls},
            {"role": "assistant", "content": "answer"},
        ],
    )
    reward = await env.compute_reward(
        {"question": "q", "answer": "a"}, result, SimpleNamespace()
    )
    assert reward == 0.52


def test_web_research_domain_normalization_only_removes_www_prefix(monkeypatch):
    module = _load(
        monkeypatch,
        "audit_web_research_domains",
        "web_research_env.py",
        _base_stubs(),
    )
    assert module.WebResearchEnv._extract_domains(
        "https://www.example.com/a https://wow.com/b"
    ) == {"example.com", "wow.com"}


def test_vector_tool_parser_keeps_historical_registry_alias():
    src = (ENV_ROOT / "tool_call_parsers" / "vector_parser.py").read_text(
        encoding="utf-8"
    )
    assert '@register_parser("vector")' in src
    assert '@register_parser("vectorcode")' in src
