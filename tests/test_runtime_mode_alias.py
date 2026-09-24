"""VECTOR_ENV=vector is the owner's name for the hardened runtime mode formerly called "production"."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("value,expected", [("vector", True), ("production", True), ("prod", True), ("VECTOR", True),
                                            ("development", False), ("", False)])
def test_every_mode_check_treats_vector_like_production(monkeypatch, value, expected):
    monkeypatch.setenv("VECTOR_ENV", value)
    from core.api import app as app_module
    from core.runtime import doctor, readiness_check

    assert app_module._is_hardened_env() is expected
    assert doctor._is_hardened_env() is expected
    assert readiness_check._is_hardened() is expected
