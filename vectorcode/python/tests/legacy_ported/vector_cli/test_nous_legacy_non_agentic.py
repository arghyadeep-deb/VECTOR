"""Tests for the Nous-VectorCode-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"vector"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``vector-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "vector" tag namespace.

``is_nous_vector_non_agentic`` should only match the actual Nous Research
VectorCode-3 / VectorCode-4 chat family.
"""

from __future__ import annotations

import pytest

from vector_cli.model_switch import (
    _VECTOR_MODEL_WARNING,
    _check_vector_model_warning,
    is_nous_vector_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "VectorCode/VectorCode-3-Llama-3.1-70B",
        "VectorCode/VectorCode-3-Llama-3.1-405B",
        "vector-3",
        "VectorCode-3",
        "vector-4",
        "vector-4-405b",
        "vector_4_70b",
        "openrouter/vector3:70b",
        "openrouter/nousresearch/vector-4-405b",
        "VectorCode/VectorCode3",
        "vector-3.1",
    ],
)
def test_matches_real_nous_vector_chat_models(model_name: str) -> None:
    assert is_nous_vector_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous VectorCode 3/4"
    )
    assert _check_vector_model_warning(model_name) == _VECTOR_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "vector-brain:qwen3-14b-ctx16k",
        "vector-brain:qwen3-14b-ctx32k",
        "vector-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat VectorCode models we don't warn about
        "vector-llm-2",
        "vector2-pro",
        "nous-vector-2-mistral",
        # Edge cases
        "",
        "vector",  # bare "vector" isn't the 3/4 family
        "vector-brain",
        "brain-vector-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_vector_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous VectorCode 3/4"
    )
    assert _check_vector_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_vector_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_vector_model_warning("") == ""
