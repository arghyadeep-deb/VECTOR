from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _toml(path: str) -> dict:
    return tomllib.loads((ROOT / path).read_text(encoding="utf-8"))


def test_comms_service_fly_config_references_repo_root_dockerfile() -> None:
    cfg = _toml("cloud/comms_service/fly.toml")
    dockerfile = ROOT / cfg["build"]["dockerfile"]

    assert cfg["http_service"]["internal_port"] == 8001
    assert cfg["http_service"]["force_https"] is True
    assert dockerfile.exists()
    text = dockerfile.read_text(encoding="utf-8")
    assert "cloud/comms_service/service.py" in text
    assert "test -d /app/core" in text


def test_agent_workers_fly_config_references_repo_root_dockerfile() -> None:
    cfg = _toml("cloud/agent_workers/fly.toml")
    dockerfile = ROOT / cfg["build"]["dockerfile"]

    assert dockerfile.exists()
    text = dockerfile.read_text(encoding="utf-8")
    assert "cloud/agent_workers/workers.py" in text
    assert "-d /app/districts" in text


def test_cloudflare_worker_config_keeps_secret_names_out_of_source() -> None:
    text = (ROOT / "api/wrangler.toml").read_text(encoding="utf-8")

    assert "wrangler secret put SUPABASE_URL" in text
    assert "wrangler secret put SUPABASE_KEY" in text
    assert "wrangler secret put VECTOR_API_KEY" in text
    assert "SUPABASE_SERVICE_ROLE" not in text
