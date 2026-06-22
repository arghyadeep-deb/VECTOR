from pathlib import Path

from fastapi.testclient import TestClient


def test_studio_server_blocks_composition_path_traversal(tmp_path: Path) -> None:
    from core.video import studio_server

    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "escape.html"
    outside.write_text("<html>outside</html>", encoding="utf-8")

    studio_server.set_project_dir(str(project))
    client = TestClient(studio_server.app)

    read_response = client.get("/compositions/%2e%2e/escape.html")
    assert read_response.status_code == 400

    write_response = client.put(
        "/compositions/%2e%2e/escape.html",
        json={"html": "<html>owned</html>"},
    )
    assert write_response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "<html>outside</html>"


def test_studio_server_allows_project_local_html(tmp_path: Path) -> None:
    from core.video import studio_server

    project = tmp_path / "project"
    project.mkdir()
    studio_server.set_project_dir(str(project))
    client = TestClient(studio_server.app)

    response = client.put(
        "/compositions/scenes/intro.html",
        json={"html": "<!DOCTYPE html><html><body>ok</body></html>"},
    )
    assert response.status_code == 200
    assert (project / "scenes" / "intro.html").exists()
