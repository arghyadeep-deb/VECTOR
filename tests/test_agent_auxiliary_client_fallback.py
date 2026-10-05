"""Regression tests for auxiliary-provider fallback routing."""

import sys
from pathlib import Path
from types import SimpleNamespace


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))

from agent import auxiliary_client


def test_auto_openrouter_failure_excludes_openrouter_from_fallback(monkeypatch):
    """Auto mode must not immediately retry the backend that just failed."""
    openrouter_client = SimpleNamespace(base_url="https://openrouter.ai/api/v1")
    fallback_client = object()
    attempts = []

    def try_openrouter():
        attempts.append("openrouter")
        return openrouter_client, "openrouter/model"

    def try_nous():
        attempts.append("nous")
        return fallback_client, "nous/model"

    monkeypatch.setattr(
        auxiliary_client,
        "_get_provider_chain",
        lambda: [("openrouter", try_openrouter), ("nous", try_nous)],
    )
    monkeypatch.setattr(auxiliary_client, "_read_main_provider", lambda: "")

    failed_label = auxiliary_client._failed_provider_label("auto", openrouter_client)
    client, model, label = auxiliary_client._try_payment_fallback(failed_label)

    assert failed_label == "openrouter"
    assert attempts == ["nous"]
    assert (client, model, label) == (fallback_client, "nous/model", "nous")


def test_auxiliary_logging_uses_loguru_formatting():
    """Provider diagnostics must interpolate values under the project logger."""
    rendered = []
    sink_id = auxiliary_client.logger.add(rendered.append, format="{message}")
    try:
        auxiliary_client._fixed_temperature_for_model("kimi-regression")
    finally:
        auxiliary_client.logger.remove(sink_id)

    assert any(
        "Kimi model 'kimi-regression'" in message for message in rendered
    ), rendered
    assert all("%r" not in message for message in rendered)


def test_nous_product_tag_does_not_mutate_caller_extra_body():
    """Adding attribution must not alter a reusable caller-owned tag list."""
    extra_body = {"tags": ["caller=regression"]}

    kwargs = auxiliary_client._build_call_kwargs(
        "nous",
        "test-model",
        [{"role": "user", "content": "test"}],
        extra_body=extra_body,
    )

    assert extra_body == {"tags": ["caller=regression"]}
    assert kwargs["extra_body"]["tags"] == [
        "caller=regression",
        "product=vectorcode",
    ]


if __name__ == "__main__":
    raise SystemExit("Run with pytest: tests/test_agent_auxiliary_client_fallback.py")
