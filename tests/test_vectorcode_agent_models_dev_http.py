"""Regression tests for the models.dev HTTP client policy."""

from __future__ import annotations

import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import models_dev


def test_fetch_models_dev_uses_httpx_and_populates_cache(monkeypatch) -> None:
    payload = {"provider": {"models": {"model": {"tool_call": True}}}}
    calls: list[tuple[str, int]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    def get(url: str, *, timeout: int):
        calls.append((url, timeout))
        return Response()

    monkeypatch.setattr(models_dev.httpx, "get", get)
    monkeypatch.setattr(models_dev, "_save_disk_cache", lambda data: None)
    models_dev._models_dev_cache = {}
    models_dev._models_dev_cache_time = 0

    assert models_dev.fetch_models_dev(force_refresh=True) == payload
    assert calls == [(models_dev.MODELS_DEV_URL, 15)]
