"""Regression for run_vector.py's _start_sidecars():

The shadowbroker sidecar launched via a bare "python" argv[0] instead of
sys.executable, unlike every other sidecar (which resolves an explicit
venv-aware interpreter via _venv_python()). shadowbroker has no isolated
.venv of its own -- it is meant to run under the exact same interpreter as
the main VECTOR process. A bare "python" on PATH can resolve to a
different Python installation (or nothing at all) than the one actually
running VECTOR, silently failing to start the sidecar (stdout/stderr are
DEVNULL'd, so the failure is invisible).
"""
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_shadowbroker_cmd_uses_sys_executable(monkeypatch):
    import run_vector

    monkeypatch.setenv("VECTOR_SIDECARS", "shadowbroker")

    captured = {}

    class _FakeProc:
        pid = 12345

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    class _FakeThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

    # _start_sidecars() does `import subprocess`/uses threading.Thread locally,
    # but both resolve to the same cached module objects in sys.modules, so
    # patching the real modules here affects it regardless of import style.
    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(threading, "Thread", _FakeThread)

    run_vector._start_sidecars()

    assert captured, "shadowbroker sidecar was not launched"
    assert captured["cmd"][0] == sys.executable, (
        f"shadowbroker must launch under sys.executable, not {captured['cmd'][0]!r}"
    )
