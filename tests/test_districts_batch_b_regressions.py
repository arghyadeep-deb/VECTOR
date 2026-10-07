from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_metrics_store_honors_zero_day_retention(tmp_path: Path) -> None:
    from districts.health.metrics_store import MetricsStore

    store = MetricsStore(tmp_path / "health.db", retention_days=90)
    try:
        store.store_metric("test", "steps", 1, timestamp="2000-01-01T00:00:00")
        counts = store.prune_old_data(retention_days=0)
        assert counts["health_metrics"] == 1
    finally:
        store.close()


def test_trend_analyzer_honors_zero_threshold() -> None:
    from districts.health.trend_analyzer import TrendAnalyzer

    analyzer = TrendAnalyzer(store=object(), anomaly_threshold=99.0)
    assert analyzer.detect_anomalies("heart_rate", [1.0, 2.0], threshold=0.0)


def test_api_tester_reads_api_key_through_secret_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    import districts.qa.api_tester as module

    monkeypatch.setattr(module, "get_secret", lambda name: "keyring-secret")
    assert module.APITester()._api_key == "keyring-secret"


def test_ads_image_key_uses_secret_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    from districts.marketing.ads.scripts import generate_image

    monkeypatch.setattr(generate_image, "get_secret", lambda name: f"secret:{name}")
    assert generate_image._get_api_key("gemini") == "secret:GOOGLE_API_KEY"


def test_web_scout_uses_secret_manager_for_firecrawl() -> None:
    source = Path("districts/research/web_scout.py").read_text(encoding="utf-8")
    assert 'get_secret("FIRECRAWL_API_KEY")' in source
    assert 'os.getenv("FIRECRAWL_API_KEY")' not in source


def test_comfy_output_atomic_replace_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import districts.content.comfyui_adapter as module

    class Response:
        content = b"replacement"

        def raise_for_status(self) -> None:
            return None

    class Client:
        async def get(self, *args, **kwargs):
            return Response()

    adapter = module.ComfyUIAdapter()
    adapter._output_dir = tmp_path
    target = tmp_path / "image.png"
    target.write_bytes(b"original")
    monkeypatch.setattr(module.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(OSError, match="boom"):
        asyncio.run(adapter._fetch_output(Client(), {"filename": "image.png"}))
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.tmp"))


def test_comfy_path_confinement_normalizes_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import districts.content.comfyui_adapter as module

    monkeypatch.setattr(module.os.path, "normcase", lambda value: str(value).lower())
    root = tmp_path / "Output"
    child = tmp_path / "output" / "nested" / "image.png"
    assert module._is_path_within(child, root)


def test_ads_batch_json_is_explicitly_utf8() -> None:
    source = Path("districts/marketing/ads/scripts/generate_image.py").read_text(encoding="utf-8")
    assert 'open(batch_file, encoding="utf-8")' in source
    assert "import requests" not in source
