"""Regression tests for the meme generator's HTTP client."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "vectorcode/src/skills/optional/creative/meme-generation/scripts/generate_meme.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("vectorcode_meme_generator", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_url_uses_httpx_and_returns_response_bytes(monkeypatch):
    module = _load_module()
    request = httpx.Request("GET", "https://example.test/template.png")
    response = httpx.Response(200, content=b"image-bytes", request=request)
    calls = []

    def fake_get(url, *, timeout):
        calls.append((url, timeout))
        return response

    monkeypatch.setattr(module.httpx, "get", fake_get)

    assert module._fetch_url(str(request.url), timeout=7) == b"image-bytes"
    assert calls == [(str(request.url), 7)]


def test_fetch_url_rejects_http_errors(monkeypatch):
    module = _load_module()
    request = httpx.Request("GET", "https://example.test/missing.png")
    response = httpx.Response(404, request=request)
    monkeypatch.setattr(module.httpx, "get", lambda *args, **kwargs: response)

    with pytest.raises(httpx.HTTPStatusError):
        module._fetch_url(str(request.url))
