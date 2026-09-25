"""The video composer's file server must serve the COMPOSITION's folder, not the current working directory.

Found 2026-09-25 rendering a reel with core.video.vector_composer: every frame was Chrome's
"Error response 404 - File not found" page. `_start_file_server` passed `directory` as a class
attribute, but SimpleHTTPRequestHandler.__init__ sets `self.directory = os.getcwd()` when it is
not given as a constructor argument, so the instance attribute shadowed it and the server always
served the process's cwd. Any composition outside the cwd (e.g. the pipeline's temp dirs) 404'd.
"""
import os
import urllib.request

from core.video.html_renderer import _find_free_port, _start_file_server


def test_server_serves_the_given_directory_not_the_cwd(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "comp.html").write_text("<html>composition-ok</html>", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)               # cwd deliberately differs from the composition folder

    port = _find_free_port()
    server = _start_file_server(str(project), port)
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/comp.html", timeout=5).read().decode()
        assert "composition-ok" in body
        assert os.getcwd() == str(elsewhere)
    finally:
        server.shutdown()
        server.server_close()
