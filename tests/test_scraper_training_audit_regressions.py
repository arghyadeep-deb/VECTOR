"""Regression coverage for the scraper/training deep audit (2026-10-07)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError


def test_training_package_keeps_all_public_exports() -> None:
    import core.training as training

    assert "LoRATrainer" in training.__all__
    assert "build_dpo_pairs" in training.__all__


@pytest.mark.parametrize("name", ["../escape", "/absolute", r"C:\\escape", ".", ".."])
def test_adapter_name_cannot_escape_adapter_root(name: str) -> None:
    from core.training.training_config import AdapterConfig

    with pytest.raises(ValidationError):
        AdapterConfig(name=name, base_model="test", target_modules=["q_proj"])


def test_training_deduplicate_removes_near_duplicates() -> None:
    from core.training.data_collector import DataCollector

    first = "VECTOR should preserve this long training example with several distinct words for robust learning."
    second = first + " Extra"
    rows = [{"text": first}, {"text": second}]

    assert DataCollector().deduplicate(rows) == [rows[0]]


def test_default_spider_error_hook_does_not_raise() -> None:
    from core.scraper.spiders.request import Request
    from core.scraper.spiders.spider import Spider

    class MinimalSpider(Spider):
        name = "default_error_hook"

        async def parse(self, response):
            if False:
                yield response

    spider = MinimalSpider()
    asyncio.run(spider.on_error(Request("https://example.com"), ConnectionError("down")))


def test_safe_redirect_mode_does_not_delegate_redirects_to_curl() -> None:
    from core.scraper.engines.static import FetcherClient

    session = FetcherClient()
    args = session._merge_request_args(url="https://example.com", follow_redirects="safe")
    assert args["allow_redirects"] is False


def test_openmythos_tokenization_texts_are_built_from_column_batches() -> None:
    from core.training.openmythos.trainer import _format_tokenization_texts

    batch = {
        "instruction": ["inst-a", "inst-b"],
        "input": ["input-a", "input-b"],
        "output": ["out-a", "out-b"],
    }
    assert _format_tokenization_texts(batch) == [
        "inst-a\ninput-a\nout-a",
        "inst-b\ninput-b\nout-b",
    ]


@pytest.mark.parametrize("name", ["../outside", "/tmp/outside", r"C:\\outside"])
def test_ollama_registry_model_names_are_confined(tmp_path: Path, name: str) -> None:
    from core.training.openmythos.export_to_ollama import OllamaExporter

    exporter = OllamaExporter.__new__(OllamaExporter)
    exporter.registry_path = tmp_path / "registry"
    exporter.registry_path.mkdir()
    exporter.ollama_host = "http://127.0.0.1:11434"
    source = tmp_path / "source.bin"
    source.write_bytes(b"weights")

    result = exporter.export_model_weights(str(source), name)
    assert result["success"] is False
    assert not (tmp_path.parent / "outside").exists()


def test_modelfile_preserves_legitimate_zero_parameter(tmp_path: Path) -> None:
    from core.training.openmythos.export_to_ollama import OllamaExporter

    exporter = OllamaExporter.__new__(OllamaExporter)
    exporter.registry_path = tmp_path / "registry"
    (exporter.registry_path / "model").mkdir(parents=True)
    exporter.ollama_host = "http://127.0.0.1:11434"

    path = exporter.create_modelfile("model", "system", {"temperature": 0})
    assert "PARAMETER temperature 0" in Path(path).read_text(encoding="utf-8")


def test_dataset_download_rejects_private_url_before_network(tmp_path: Path) -> None:
    from core.training.openmythos.data_prep import DataPreparator

    preparator = DataPreparator.__new__(DataPreparator)
    preparator.output_dir = str(tmp_path)

    class NeverCalled:
        async def get(self, *args, **kwargs):
            raise AssertionError("network must not be reached")

    preparator._client = NeverCalled()
    result = asyncio.run(preparator.download_dataset("http://169.254.169.254/latest", "data.bin"))
    assert result == ""
