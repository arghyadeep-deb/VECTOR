"""Capability probing for VectorCode providers.

Probes a model by sending a minimal test request and observing the response.
Results cached in ModelRegistry (~/.config/vector/model-registry.json).
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.providers.base import ModelCapabilities
from agents.districts.coding.vectorcode.config import ModelRegistry


_PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "probe_echo",
        "description": "Echo the input back",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}]


class CapabilityProbe:
    """Probe a model once; cache the result; re-use on subsequent calls."""

    def __init__(self) -> None:
        self._registry = ModelRegistry()

    def get_or_probe(self, model_id: str, provider) -> ModelCapabilities:
        """
        Return cached capabilities or probe the model if not yet cached.
        model_id format: "provider/model-name"
        """
        cached = self._registry.get(model_id)
        if cached:
            return ModelCapabilities(**cached)

        logger.info(f"[VECTOR][probe] probing capabilities for {model_id}...")
        caps = self._probe(model_id, provider)
        self._registry.set(model_id, {
            "context_window":     caps.context_window,
            "tool_use":           caps.tool_use,
            "vision":             caps.vision,
            "structured_output":  caps.structured_output,
            "supports_streaming": caps.supports_streaming,
        })
        return caps

    def _probe(self, model_id: str, provider) -> ModelCapabilities:
        # Delegate to provider's own probe_capabilities — it knows the model best
        short_name = model_id.split("/", 1)[-1] if "/" in model_id else model_id
        try:
            return provider.probe_capabilities(short_name)
        except Exception as e:
            logger.warning(f"[VECTOR][probe] probe_capabilities failed for {model_id}: {e}")
            return ModelCapabilities()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from agents.districts.coding.vectorcode.providers.ollama import OllamaProvider
    prober = CapabilityProbe()
    p = OllamaProvider()
    caps = prober.get_or_probe("ollama/vector-focus", p)
    assert isinstance(caps.context_window, int) and caps.context_window > 0
    print(f"capability_probe.py OK — context_window={caps.context_window}")
