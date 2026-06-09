from __future__ import annotations

from fastapi.testclient import TestClient


def test_hud_serves_development_entrypoint_by_default(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.delenv("VECTOR_ENV", raising=False)
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    response = client.get("/hud/")

    assert response.status_code == 200
    assert '<script src="js/demo.js"></script>' in response.text
    assert 'id="director"' in response.text


def test_hud_serves_production_entrypoint_in_production(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.setenv("VECTOR_ENV", "production")
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    response = client.get("/hud/")

    assert response.status_code == 200
    assert "VECTOR Production" in response.text
    assert '<script src="js/demo.js"></script>' not in response.text
    assert 'id="director"' not in response.text


def test_hud_rewrites_dev_entrypoint_and_blocks_demo_js_in_production(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.setenv("VECTOR_ENV", "production")
    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    old_bookmark = client.get("/hud/VECTOR.html")
    demo_script = client.get("/hud/js/demo.js")

    assert old_bookmark.status_code == 200
    assert "VECTOR Production" in old_bookmark.text
    assert '<script src="js/demo.js"></script>' not in old_bookmark.text
    assert demo_script.status_code == 404
