"""There is ONE HUD, frontend/VECTOR.html, served in every environment.

The separate "VECTOR Production" page (VECTOR.prod.html, its bundle and its build) was removed 2026-09-25 by owner
decision: it dropped the subsystem dock, so the owner's HUD offered five buttons instead of the real interface.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"Authorization": "Bearer test-hud-key"}


@pytest.mark.parametrize("env", ["development", "production"])
def test_hud_serves_the_one_full_hud_in_every_environment(monkeypatch, env) -> None:
    from core.api.app import create_app

    # os.getenv("VECTOR_ENV") wins over the CONFIG-derived default (which is "production" on this machine), so set it
    # explicitly.
    monkeypatch.setenv("VECTOR_ENV", env)
    monkeypatch.setenv("VECTOR_API_KEY", "test-hud-key")
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    response = client.get("/hud/", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert "<title>VECTOR</title>" in response.text
    assert "VECTOR Production" not in response.text
    assert '<script src="js/demo.js"></script>' in response.text  # builds the subsystem dock
    assert 'id="dock"' in response.text


@pytest.mark.parametrize("env", ["development", "production"])
def test_hud_scripts_are_served_in_every_environment(monkeypatch, env) -> None:
    from core.api.app import create_app

    monkeypatch.setenv("VECTOR_ENV", env)
    monkeypatch.setenv("VECTOR_API_KEY", "test-hud-key")
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    for path in ("js/demo.js", "js/widgets.js", "js/city3d.js", "styles/core.css"):
        assert client.get(f"/hud/{path}", headers=AUTH_HEADERS).status_code == 200, path
    assert client.get("/hud/VECTOR.html", headers=AUTH_HEADERS).status_code == 200


def test_the_production_page_is_gone(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("VECTOR_API_KEY", "test-hud-key")
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    # An old bookmark falls through to the one HUD instead of a 404.
    old = client.get("/hud/VECTOR.prod.html", headers=AUTH_HEADERS)
    assert old.status_code == 200 and "<title>VECTOR</title>" in old.text
