"""Regression tests for audited round-8 standalone clients."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path: str, module_name: str):
    path = ROOT / relative_path
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_solana_wallet_prices_native_sol_without_spl_tokens(monkeypatch):
    module = _load(
        "vectorcode/src/skills/optional/blockchain/solana/scripts/solana_client.py",
        "round8_solana_client",
    )
    responses = iter([{"value": 2_000_000_000}, {"value": []}])
    monkeypatch.setattr(module, "rpc", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(module, "fetch_sol_price", lambda: 150.0)
    captured = []
    monkeypatch.setattr(module, "print_json", captured.append)

    module.cmd_wallet(
        SimpleNamespace(address="wallet", all=False, limit=20, no_prices=False)
    )

    assert captured[0]["sol_price_usd"] == 150.0
    assert captured[0]["sol_value_usd"] == 300.0
    assert captured[0]["portfolio_total_usd"] == 300.0


def test_overpass_fallback_does_not_emit_phantom_error(monkeypatch):
    module = _load(
        "vectorcode/src/skills/productivity/maps/scripts/maps_client.py",
        "round8_maps_client",
    )
    calls = []

    def fake_post(url, data, retries, silent):
        calls.append((url, data, retries, silent))
        if len(calls) == 1:
            raise RuntimeError("first mirror unavailable")
        return {"elements": []}

    monkeypatch.setattr(module, "http_post", fake_post)
    monkeypatch.setattr(
        module, "print_json", lambda *_args: pytest.fail("must not print an error")
    )

    assert module.overpass_query("node;") == {"elements": []}
    assert len(calls) == 2
    assert all(call[3] is True for call in calls)


def test_google_atomic_write_preserves_existing_token_on_replace_failure(
    tmp_path, monkeypatch
):
    module = _load(
        "vectorcode/src/skills/productivity/google-workspace/scripts/_vector_home.py",
        "round8_vector_home",
    )
    token_path = tmp_path / "google_token.json"
    token_path.write_text("original", encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("crash")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="crash"):
        module.atomic_write_text(token_path, "replacement")

    assert token_path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_drive_search_escapes_literal_query_for_google_syntax(monkeypatch, capsys):
    module = _load(
        "vectorcode/src/skills/productivity/google-workspace/scripts/google_api.py",
        "round8_google_api",
    )
    captured = {}
    monkeypatch.setattr(module, "_gws_binary", lambda: "gws")

    def fake_run(parts, *, params=None, body=None):
        captured.update({"parts": parts, "params": params, "body": body})
        return {"files": []}

    monkeypatch.setattr(module, "_run_gws", fake_run)
    module.drive_search(SimpleNamespace(query=r"owner's\\report", raw_query=False, max=5))

    assert captured["params"]["q"] == r"fullText contains 'owner\'s\\\\report'"
    assert json.loads(capsys.readouterr().out) == []

