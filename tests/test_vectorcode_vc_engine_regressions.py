"""Regression tests for vc_engine provider error and option handling."""

from __future__ import annotations

import sys
import types
import importlib
from types import SimpleNamespace

import pytest

from vectorcode.src.vc_core.types import Message, Role
from vectorcode.src.vc_engine._openai_compat import _OpenAICompatibleEngine
from vectorcode.src.vc_engine.cloud import CloudEngine


class _Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"model": "test-model", "choices": []}


class _HttpClient:
    def post(self, *_args, **_kwargs) -> _Response:
        return _Response()


def test_openai_compat_rejects_success_response_without_choices() -> None:
    engine = object.__new__(_OpenAICompatibleEngine)
    engine.engine_id = "test"
    engine._host = "http://test.invalid"
    engine._client = _HttpClient()

    with pytest.raises(RuntimeError, match="without choices"):
        engine.generate(
            [Message(role=Role.USER, content="hello")],
            model="test-model",
        )


@pytest.mark.parametrize(
    ("model", "client_attr"),
    [
        ("openrouter/vendor/model", "_openrouter_client"),
        ("MiniMax-M2.7", "_minimax_client"),
    ],
)
def test_cloud_openai_compatible_providers_forward_tools(
    model: str,
    client_attr: str,
) -> None:
    captured: dict = {}

    returned_tool_calls = None
    if model.startswith("openrouter/"):
        returned_tool_calls = [
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="lookup", arguments='{"q":"x"}'),
            )
        ]

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="ok", tool_calls=returned_tool_calls
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
            model=model,
        )

    engine = object.__new__(CloudEngine)
    setattr(
        engine,
        client_attr,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    tools = [{"type": "function", "function": {"name": "lookup"}}]

    result = engine.generate(
        [Message(role=Role.USER, content="hello")],
        model=model,
        tools=tools,
    )

    assert captured["tools"] == tools
    if returned_tool_calls:
        assert result["tool_calls"] == [
            {"id": "call-1", "name": "lookup", "arguments": '{"q":"x"}'}
        ]


def test_missing_mining_constants_degrades_gracefully(monkeypatch) -> None:
    import vectorcode.src.vc_engine._discovery as discovery

    mining = types.ModuleType("vector.mining")
    mining.Sidecar = SimpleNamespace(read=lambda _path: None)
    monkeypatch.setitem(sys.modules, "vector.mining", mining)
    monkeypatch.delitem(sys.modules, "vector.mining._constants", raising=False)

    discovery._maybe_register_mining_sidecar_engine()


def test_all_telemetry_compatibility_modules_import() -> None:
    modules = (
        "aggregator", "batch", "efficiency", "energy_amd", "energy_apple",
        "energy_monitor", "energy_nvidia", "energy_rapl", "flops",
        "gpu_monitor", "instrumented_engine", "itl", "phase_metrics",
        "session", "steady_state", "store", "vllm_metrics", "wrapper",
    )

    imported = [
        importlib.import_module(f"vectorcode.src.telemetry.{name}")
        for name in modules
    ]

    assert all(hasattr(module, "__all__") for module in imported)


def test_apple_models_endpoint_is_unhealthy_without_platform_support(
    monkeypatch,
) -> None:
    import vectorcode.src.vc_engine.apple_fm_shim as shim

    monkeypatch.setattr(shim, "apple_fm", None)

    assert shim.list_models().status_code == 503


def test_nexa_models_endpoint_is_unhealthy_without_sdk(monkeypatch) -> None:
    import vectorcode.src.vc_engine.nexa_shim as shim

    monkeypatch.setattr(shim, "nexaai", None)
    monkeypatch.setattr(shim, "_llm", None)

    assert shim.list_models().status_code == 503
