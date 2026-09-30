"""Regression test for AirLLM generation outside the module self-test.

``torch`` was imported only under ``if __name__ == '__main__'`` so the live
fallback path raised NameError whenever AirLLM was actually available.
"""
from __future__ import annotations

import asyncio
import sys
import types

from core.inference.airllm_runner import AirLLMRunner


def test_airllm_generation_imports_torch_in_live_module_path(monkeypatch):
    class FakeInputs(dict):
        def to(self, _device):
            return self

    class FakeTokenizer:
        def __call__(self, prompt, return_tensors):
            return FakeInputs(input_ids=[[1, 2]])

        def decode(self, values, skip_special_tokens):
            return "generated"

    class FakeModel:
        device = "cpu"
        tokenizer = FakeTokenizer()

        def generate(self, input_ids, **kwargs):
            return [[1, 2, 3]]

    fake_airllm = types.SimpleNamespace(
        AutoModel=types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeModel())
    )
    monkeypatch.setitem(sys.modules, "airllm", fake_airllm)

    runner = object.__new__(AirLLMRunner)
    runner.airllm_config = {}
    runner.loaded_model = "fake/model"
    result = asyncio.run(runner._generate_with_airllm("hello", 8, 0.1, 0.9, 10))

    assert result["success"] is True
    assert result["generated"] == "generated"


if __name__ == "__main__":
    raise SystemExit("Run with: pytest tests/test_airllm_runtime_torch_import.py -v")
