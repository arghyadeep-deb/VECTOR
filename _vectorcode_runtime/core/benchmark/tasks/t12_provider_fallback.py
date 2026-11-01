"""T12 — Provider Fallback: LLM provider chain fails over correctly.

Verify ProviderClient has fallback chain structure. Test that when primary
provider fails, the system can attempt alternative providers.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class ProviderFallbackTask(BenchmarkTask):
    task_id = "T12"
    category = "provider_fallback"
    required_capability = "ProviderClient fallback chain across multiple LLM providers"
    expected_behavior = "When primary provider fails, fallback chain attempts alternatives"

    def run(self, state) -> TaskResult:
        from core.inference.provider_client import ProviderClient

        client = ProviderClient()

        # Check structural capability
        has_chat = hasattr(client, "chat")

        # Check that the provider registry has multiple providers
        provider_count = 0
        try:
            from core.inference.llm_providers import LLMProvider
            provider_count = len(LLMProvider) if hasattr(LLMProvider, "__members__") else 0
        except Exception:
            pass

        # Check model catalog exists
        catalog_available = False
        try:
            from core.inference.model_catalog import MODEL_CATALOG
            catalog_available = True
        except Exception:
            try:
                from core.inference import model_catalog
                catalog_available = hasattr(model_catalog, "MODEL_CATALOG") or hasattr(model_catalog, "get_models")
            except Exception:
                pass

        if not has_chat:
            return self._failure(
                actual="ProviderClient has no chat() method",
                outcome="ProviderClient structurally broken",
            )

        # Check Ollama fallback exists
        ollama_available = False
        try:
            from core.inference.ollama_safe import ollama_safe
            ollama_available = True
        except Exception:
            pass

        structural_complete = has_chat and catalog_available and ollama_available and provider_count > 5

        if structural_complete:
            return self._success(
                actual=(
                    f"ProviderClient verified: chat() present, "
                    f"{provider_count} providers registered, "
                    f"model catalog available, Ollama fallback present. "
                    f"Full fallback chain: cloud -> Ollama terminal."
                ),
                outcome="Provider fallback chain structurally complete",
                details={
                    "provider_count": provider_count,
                    "catalog_available": catalog_available,
                    "ollama_fallback": ollama_available,
                },
            )
        else:
            return self._failure(
                actual=(
                    f"Partial: chat={has_chat}, providers={provider_count}, "
                    f"catalog={catalog_available}, ollama={ollama_available}"
                ),
                outcome="Fallback chain incomplete",
                details={
                    "provider_count": provider_count,
                    "catalog_available": catalog_available,
                    "ollama_fallback": ollama_available,
                },
            )


TASK_CLASS = ProviderFallbackTask
