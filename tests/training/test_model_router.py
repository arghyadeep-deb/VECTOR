"""Tests for TaskClassifier and ModelRouter: domain detection, routing, hot-swap, and adapter listing."""

import tempfile
from pathlib import Path

from core.inference.model_router import TaskClassifier, ModelRouter


def _make_dummy_adapter(base_dir: Path, name: str):
    d = base_dir / name
    d.mkdir(parents=True, exist_ok=True)
    manifest = d / "manifest.json"
    manifest.write_text(
        '{"name": "' + name + '", "base_model": "vector-test", '
        '"training_result": {"final_loss": 0.1}}',
        encoding="utf-8",
    )


class TestTaskClassifier:
    def setup_method(self):
        self.cls = TaskClassifier(llm_fallback=False)

    def test_classify_coding(self):
        result = self.cls.classify("Write a Python function to sort a list")
        assert result.domain == "coding"
        assert result.confidence > 0.0

    def test_classify_research(self):
        result = self.cls.classify("Summarize the latest paper on transformers")
        assert result.domain == "research"

    def test_classify_voice(self):
        result = self.cls.classify("Say hello and set a timer for 5 minutes")
        assert result.domain == "voice"

    def test_classify_personality(self):
        result = self.cls.classify("Tell me a joke sir")
        assert result.domain == "personality"

    def test_classify_general(self):
        result = self.cls.classify("What is the weather like?")
        assert result.domain == "general"

    def test_classify_empty(self):
        result = self.cls.classify("")
        assert result.domain == "general"
        assert result.confidence == 0.0


class TestModelRouter:
    def test_route_returns_routing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            result = router.route("Write a binary search function")
            assert result.domain == "coding"
            assert result.confidence >= 0.0
            assert result.model_name == "vector-test"

    def test_route_personality(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            result = router.route("What is your personality? Who are you?")
            assert result.domain == "personality"

    def test_list_adapters_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            adapters = router.list_adapters()
            assert isinstance(adapters, list)

    def test_list_adapters_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_dummy_adapter(Path(tmp), "test_lora_v1")
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            adapters = router.list_adapters()
            names = [a.get("name", "") for a in adapters]
            assert "test_lora_v1" in names

    def test_get_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            router.route("fix this bug")
            router.route("explain quantum computing")
            stats = router.get_stats()
            assert stats["total_routes"] >= 2
            assert "domain_counts" in stats
            assert "coding" in stats["domain_counts"]

    def test_get_domain_for_task(self):
        router = ModelRouter(adapter_dir=tempfile.mktemp(), base_model="vector-test")
        domain = router.get_domain_for_task("Say hello and greet")
        assert domain == "voice"

    def test_hot_swap_no_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            result = router.hot_swap("nonexistent")
            assert result is False

    def test_register_adapter_for_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ModelRouter(adapter_dir=tmp, base_model="vector-test")
            router.register_adapter_for_domain("coding", "coding_v1")
            result = router.route("debug this function")
            assert result.adapter_name == "coding_v1"
