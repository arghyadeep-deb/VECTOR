"""Regression tests for the agents/providers/speech depth audit."""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).parent.parent
VECTORCODE_SRC = REPO_ROOT / "vectorcode" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(VECTORCODE_SRC))


class _ApprovingWorkflowGateway:
    async def evaluate_external(self, action_type, params, source):
        return SimpleNamespace(approved=True, level="RED", reason="Owner confirmed")


async def test_workflow_nonzero_command_is_not_reported_as_success():
    from agents.workflow_engine import WorkflowEngine

    command = [sys.executable, "-c", "raise SystemExit(7)"]
    result = await WorkflowEngine(permission_gateway=_ApprovingWorkflowGateway()).execute(
        {"id": "nonzero", "steps": [{"action": "bash", "command": command}]}
    )

    assert result["status"] == "failed"
    assert "status 7" in result["results"][0]["error"]


@pytest.mark.parametrize("action", ["llm", "made-up-action"])
async def test_workflow_placeholder_actions_do_not_claim_completion(action):
    from agents.workflow_engine import WorkflowEngine

    result = await WorkflowEngine().execute(
        {"id": action, "steps": [{"action": action, "prompt": "hello"}]}
    )

    assert result["status"] == "failed"


def test_legacy_provider_adapters_import_with_their_declared_base_types():
    from providers.base import (
        BaseProvider,
        CompletionResult,
        ModelCapabilities,
        TokenUsage,
    )
    from providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider("http://localhost:1234/v1")
    assert isinstance(provider, BaseProvider)
    assert isinstance(provider.probe_capabilities("gpt-4o"), ModelCapabilities)
    assert isinstance(provider._make_result("ok", "model", TokenUsage()), CompletionResult)


def test_capability_probe_records_new_probe_result():
    from providers.base import ModelCapabilities
    from providers.capability_probe import CapabilityProbe

    class Registry:
        def __init__(self):
            self.data = {}

        def get(self, model_id):
            return self.data.get(model_id)

        def set(self, model_id, caps):
            self.data[model_id] = caps

    class Provider:
        def probe_capabilities(self, model):
            return ModelCapabilities(context_window=8192, tool_use=True)

    probe = CapabilityProbe()
    probe._registry = Registry()
    caps = probe.get_or_probe("custom/model", Provider())

    assert caps.tool_use is True
    assert probe._registry.data["custom/model"]["tool_use"] is True


def test_provider_replacement_retires_removed_aliases(monkeypatch):
    import providers
    from providers.base import ProviderProfile

    monkeypatch.setattr(providers, "_discovered", True)
    monkeypatch.setattr(providers, "_REGISTRY", {})
    monkeypatch.setattr(providers, "_ALIASES", {})
    providers.register_provider(ProviderProfile(name="demo", aliases=("old",)))
    providers.register_provider(ProviderProfile(name="demo", aliases=("new",)))

    assert providers.get_provider_profile("old") is None
    assert providers.get_provider_profile("new").name == "demo"


@pytest.mark.parametrize(
    "module_name", ["providers.rate_limit", "providers.rate_limit_tracker"]
)
def test_rate_limit_reset_parser_accepts_provider_duration_units(module_name):
    module = __import__(module_name, fromlist=["parse_rate_limit_headers"])
    state = module.parse_rate_limit_headers(
        {
            "x-ratelimit-limit-requests": "100",
            "x-ratelimit-remaining-requests": "99",
            "x-ratelimit-reset-requests": "1500ms",
        }
    )

    assert state is not None
    assert state.requests_min.reset_seconds == pytest.approx(1.5)


def test_speech_auto_discovery_skips_unhealthy_backend(monkeypatch):
    from vectorcode.src.speech import _discovery

    unhealthy = SimpleNamespace(health=lambda: False)
    healthy = SimpleNamespace(health=lambda: True)
    backends = {"faster-whisper": unhealthy, "openai": healthy}
    monkeypatch.setattr(
        _discovery, "_create_backend", lambda key, config: backends.get(key)
    )
    config = SimpleNamespace(speech=SimpleNamespace(backend="auto"))

    assert _discovery.get_speech_backend(config) is healthy


def test_explicit_speech_backend_does_not_return_unhealthy_instance(monkeypatch):
    from vectorcode.src.speech import _discovery

    unhealthy = SimpleNamespace(health=lambda: False)
    monkeypatch.setattr(
        _discovery, "_create_backend", lambda key, config: unhealthy
    )
    config = SimpleNamespace(speech=SimpleNamespace(backend="deepgram"))

    assert _discovery.get_speech_backend(config) is None


def test_tts_result_save_replaces_existing_file(tmp_path):
    from vectorcode.src.speech.tts import TTSResult

    output = tmp_path / "speech.wav"
    output.write_bytes(b"old")

    assert TTSResult(audio=b"new audio").save(output) == output
    assert output.read_bytes() == b"new audio"


def test_public_deep_research_module_exports_canonical_agent():
    from vectorcode.src.agents.deep_research import DeepResearchAgent as PublicAgent
    from vectorcode.src.vc_agents.deep_research import DeepResearchAgent as CanonicalAgent

    assert PublicAgent is CanonicalAgent


async def test_coordinator_rejects_duplicate_ids_and_clears_tasks_on_shutdown():
    from agents.coordinator import SwarmCoordinator

    coordinator = SwarmCoordinator()
    coordinator.spawn_agent("worker")
    await coordinator.assign_task({"id": "same", "type": "general"})

    with pytest.raises(ValueError, match="task id already exists"):
        await coordinator.assign_task({"id": "same", "type": "general"})

    await coordinator.shutdown()
    assert coordinator.get_status()["tasks"] == 0
