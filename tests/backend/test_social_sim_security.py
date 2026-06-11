"""Task 05 — social sim Flask security defaults.

No hardcoded production secret, DEBUG off by default, CORS not wildcard in
production.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "districts" / "intelligence" / "vector_social_sim" / "app" / "config.py"
)


def _load_config(monkeypatch, env: dict):
    for k in ("FLASK_ENV", "VECTOR_ENV", "SECRET_KEY", "FLASK_DEBUG", "CORS_ORIGINS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("social_sim_config_test", _CONFIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Config


def test_debug_defaults_false(monkeypatch):
    cfg = _load_config(monkeypatch, {})
    assert cfg.DEBUG is False


def test_no_hardcoded_secret_in_production(monkeypatch):
    cfg = _load_config(monkeypatch, {"FLASK_ENV": "production"})
    assert cfg.SECRET_KEY == ""  # no fallback constant
    errors = cfg.validate_security()
    assert any("SECRET_KEY" in e for e in errors)


def test_production_with_secret_and_cors_passes(monkeypatch):
    cfg = _load_config(monkeypatch, {
        "FLASK_ENV": "production",
        "SECRET_KEY": "s" * 40,
        "CORS_ORIGINS": "https://hud.example.com",
    })
    assert cfg.validate_security() == []
    assert cfg.cors_resource_origins() == ["https://hud.example.com"]


def test_production_cors_not_wildcard(monkeypatch):
    cfg = _load_config(monkeypatch, {"FLASK_ENV": "production", "SECRET_KEY": "s" * 40})
    # empty CORS in production resolves to [] (never "*")
    assert cfg.cors_resource_origins() == []
    assert any("CORS" in e for e in cfg.validate_security())


def test_production_debug_rejected(monkeypatch):
    cfg = _load_config(monkeypatch, {
        "FLASK_ENV": "production",
        "SECRET_KEY": "s" * 40,
        "CORS_ORIGINS": "https://hud.example.com",
        "FLASK_DEBUG": "true",
    })
    assert any("DEBUG" in e for e in cfg.validate_security())


def test_dev_has_random_secret_and_wildcard_cors(monkeypatch):
    cfg = _load_config(monkeypatch, {})
    assert cfg.SECRET_KEY and cfg.SECRET_KEY != "vector_social_sim-secret-key"
    assert cfg.cors_resource_origins() == "*"  # dev convenience
    assert cfg.validate_security() == []  # dev never blocks


def test_dev_explicit_debug_opt_in(monkeypatch):
    cfg = _load_config(monkeypatch, {"FLASK_DEBUG": "true"})
    assert cfg.DEBUG is True
