"""Regression: HTMLFrameRenderer.capture()'s file server leaked its listening
socket (Phase 3 whole-repo audit, 2026-10-02).

The `finally` block called server.shutdown() -- which only stops
serve_forever()'s loop -- but never server.server_close(), which actually
releases the socket. Every real capture() call (each picking a fresh port
via _find_free_port()) left a bound socket open forever; enough renders
would exhaust the free-port range or the process's file-descriptor limit.
tests/test_regression_composer_serves_project_dir.py's own test already
modeled the correct shutdown()+server_close() pattern in its test cleanup,
proving the pattern was known -- it just wasn't applied in the actual
production code path.
"""
from __future__ import annotations

import socket

from core.video.html_renderer import _find_free_port, _start_file_server


def test_shutdown_alone_does_not_release_the_socket(tmp_path):
    """Documents the bug: shutdown() alone leaves the port bound."""
    port = _find_free_port()
    server = _start_file_server(str(tmp_path), port)
    server.shutdown()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
        rebound = True
    except OSError:
        rebound = False
    assert not rebound, "shutdown() alone should still leave the port bound (documents the pre-fix bug)"
    server.server_close()  # real cleanup, so this test doesn't itself leak


def test_shutdown_then_server_close_releases_the_socket(tmp_path):
    """The real fix: server_close() after shutdown() actually frees the port."""
    port = _find_free_port()
    server = _start_file_server(str(tmp_path), port)
    server.shutdown()
    server.server_close()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))  # raises OSError if still bound


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
