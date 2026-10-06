"""Regression tests for the batch-C tools audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_mcp_oauth_json_write_replaces_existing_file_atomically(tmp_path: Path) -> None:
    from tools.mcp_oauth import _write_json

    target = tmp_path / "tokens.json"
    target.write_text('{"access_token": "old"}', encoding="utf-8")

    _write_json(target, {"access_token": "new"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "access_token": "new"
    }
    assert not list(tmp_path.glob(".tokens.json.*.tmp"))


def test_graph_client_rejects_cross_origin_absolute_url() -> None:
    from tools.microsoft_graph_client import (
        MicrosoftGraphClient,
        MicrosoftGraphClientError,
    )

    client = MicrosoftGraphClient(object())

    with pytest.raises(MicrosoftGraphClientError, match="outside the configured"):
        client._resolve_url("https://attacker.example/collect")


def test_graph_client_allows_same_origin_pagination_url() -> None:
    from tools.microsoft_graph_client import MicrosoftGraphClient

    client = MicrosoftGraphClient(object())
    url = "https://graph.microsoft.com/v1.0/users?$skiptoken=next"

    assert client._resolve_url(url) == url


def test_process_wait_honors_explicit_zero_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.process_registry import ProcessRegistry

    registry = ProcessRegistry()
    session = SimpleNamespace(output_buffer=[], exited=False)
    monkeypatch.setattr(registry, "get", lambda _session_id: session)

    result = registry.wait("running", timeout=0)

    assert result["status"] == "timeout"
