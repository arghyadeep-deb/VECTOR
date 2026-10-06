"""Regression tests for the 2026-10-07 engine/mining audit."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vectorcode.src.engine import _discovery as compatibility_discovery
from vectorcode.src.engine.agent_loop import VectorAgent
from vectorcode.src.engine.conversation import _build_system_prompt
from vectorcode.src.engine.safety import _SafeWriter
from vectorcode.src.engine.tool_exec import _paths_overlap
from vectorcode.src.engine.tool_exec import execute_tool_calls_sequential
from vectorcode.src.mining._abc import Sidecar
from vectorcode.src.mining._constants import PEARL_IMAGE_TAG, PEARL_PINNED_REF
from vectorcode.src.mining._collector import MiningTelemetryCollector
from vectorcode.src.mining._metrics import parse_gateway_metrics
from vectorcode.src.mining._discovery import check_pearld_reachable
from vectorcode.src.vc_engine import _discovery as canonical_discovery


def test_engine_discovery_shim_delegates_to_canonical_implementation() -> None:
    assert compatibility_discovery.get_engine is canonical_discovery.get_engine
    assert compatibility_discovery.discover_engines is canonical_discovery.discover_engines
    assert compatibility_discovery.discover_models is canonical_discovery.discover_models
    assert compatibility_discovery._make_engine is canonical_discovery._make_engine


def test_conversation_system_prompt_contains_real_session_hydration() -> None:
    prompt = _build_system_prompt(
        SimpleNamespace(
            session_id="engine-audit",
            model="test-model",
            ephemeral_system_prompt="PURPOSE-BUILT TEST PROMPT",
        )
    )

    assert "[SESSION CONTEXT" in prompt
    assert prompt.endswith("PURPOSE-BUILT TEST PROMPT")


def test_parallel_path_overlap_is_case_insensitive_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(
        "vectorcode.src.engine.tool_exec.os.path.normcase",
        lambda value: value.casefold(),
    )

    assert _paths_overlap(Path("C:/Work/Project"), Path("c:/work/project/file.py"))


def test_approval_callback_exception_fails_closed() -> None:
    agent = object.__new__(VectorAgent)
    agent._approval_cb = lambda *_args: (_ for _ in ()).throw(RuntimeError("gate down"))
    agent._tool_start_cb = None
    agent._tool_complete_cb = None

    result = agent._execute_one_tool(
        {"id": "call-1", "name": "write_file", "arguments": '{"path": "x"}'}
    )

    assert result["content"] == "[BLOCKED: approval check failed for write_file]"


def test_safe_writer_flush_suppresses_closed_stream_without_recursive_logging() -> None:
    class ClosedStream:
        def flush(self) -> None:
            raise ValueError("closed")

    assert _SafeWriter(ClosedStream()).flush() is None


def test_invalid_tool_json_is_not_dispatched() -> None:
    called = False

    def dispatch(*_args):
        nonlocal called
        called = True

    [result] = execute_tool_calls_sequential(
        [{"id": "bad", "name": "write_file", "arguments": "{"}],
        dispatch,
        object(),
    )

    assert called is False
    assert "invalid tool arguments" in result["result"]["error"]


def test_pearld_json_rpc_error_is_not_reported_as_success(monkeypatch) -> None:
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"result": None, "error": {"code": -28, "message": "warming up"}}

    monkeypatch.setattr("vectorcode.src.mining._discovery.httpx.post", lambda *_a, **_kw: Response())

    ok, detail = check_pearld_reachable("http://127.0.0.1:9999", "user", "secret")

    assert ok is False
    assert "JSON-RPC error" in detail


def test_sidecar_round_trip_and_malformed_file_are_distinguishable(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "mining.json"
    payload = {"provider": "vllm-pearl", "pid": 123}

    assert Sidecar.read(path) is None
    Sidecar.write(path, payload)
    assert Sidecar.read(path) == payload
    assert not list(path.parent.glob(".mining-*"))

    path.write_text("{not-json", encoding="utf-8")
    assert Sidecar.read(path) is None


def test_gateway_metrics_constructs_complete_stats() -> None:
    stats = parse_gateway_metrics(
        "\n".join(
            [
                "pearl_gateway_shares_submitted_total 5",
                "pearl_gateway_shares_accepted_total 4",
                "pearl_gateway_blocks_found_total 1",
                "pearl_gateway_last_share_timestamp 123.5",
                "pearl_gateway_errors_total 2",
            ]
        ),
        provider_id="vllm-pearl",
    )

    assert stats.shares_submitted == 5
    assert stats.shares_accepted == 4
    assert stats.blocks_found == 1
    assert stats.hashrate == 0.0
    assert stats.last_share_at == 123.5
    assert stats.last_error == "2 gateway errors observed"


async def test_collector_missing_sidecar_reports_error_state(tmp_path: Path) -> None:
    collector = MiningTelemetryCollector(tmp_path / "missing.json", telemetry_store=object())

    stats = await collector.collect_once()

    assert stats.provider_id == "unknown"
    assert stats.last_error == "mining sidecar unavailable"


def test_pearl_git_ref_is_not_the_docker_image_tag() -> None:
    assert PEARL_PINNED_REF == "master"
    assert PEARL_PINNED_REF != PEARL_IMAGE_TAG


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
