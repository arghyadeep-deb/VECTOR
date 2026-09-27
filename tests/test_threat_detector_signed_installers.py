"""A validly signed installer running from a temp directory must not raise the HUD's threat level (2026-09-27; the VS Code installer did).

An unsigned executable in a temp dir, a name fragment like 'xmrig', and a script whose command line points into temp stay suspicious."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.control.security import threat_detector as td


def _proc(name, exe, cmdline=()):
    return SimpleNamespace(info={"pid": 4242, "name": name, "exe": exe, "cmdline": list(cmdline)})


def _scan(monkeypatch, procs, signed):
    import psutil

    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(procs))
    monkeypatch.setattr(td, "_is_validly_signed", lambda path: signed)
    return {r["name"]: r for r in td.scan_processes_inprocess()}


TEMP_EXE = r"C:\Users\me\AppData\Local\Temp\vscode-inno\VSCodeSetup.tmp"


def test_a_signed_installer_in_temp_is_not_suspicious(monkeypatch):
    rows = _scan(monkeypatch, [_proc("VSCodeSetup.tmp", TEMP_EXE, [TEMP_EXE, "/silent"])], signed=True)
    assert rows["VSCodeSetup.tmp"]["suspicious"] is False
    assert "signed" in rows["VSCodeSetup.tmp"]["reason"]


def test_an_unsigned_executable_in_temp_is_still_suspicious(monkeypatch):
    rows = _scan(monkeypatch, [_proc("dropper.exe", TEMP_EXE.replace("VSCodeSetup.tmp", "dropper.exe"))], signed=False)
    assert rows["dropper.exe"]["suspicious"] is True and "temp dir" in rows["dropper.exe"]["reason"]


def test_a_bad_name_is_suspicious_even_when_signed(monkeypatch):
    rows = _scan(monkeypatch, [_proc("xmrig.exe", r"C:\Program Files\x\xmrig.exe")], signed=True)
    assert rows["xmrig.exe"]["suspicious"] is True


def test_a_script_launched_from_temp_is_still_flagged_even_with_a_signed_interpreter(monkeypatch):
    rows = _scan(monkeypatch, [_proc("python.exe", r"C:\Python313\python.exe", [r"C:\Users\me\AppData\Local\Temp\evil.py"])], signed=True)
    assert rows["python.exe"]["suspicious"] is True


def test_signature_check_is_false_off_windows_or_on_error_and_cache_tracks_file_identity(monkeypatch, tmp_path):
    td._SIGNATURE_CACHE.clear()
    monkeypatch.setattr(td.sys, "platform", "linux")
    fake = tmp_path / "a.exe"
    fake.write_bytes(b"first")
    assert td._is_validly_signed(str(fake)) is False
    monkeypatch.setattr(td.sys, "platform", "win32")
    calls = []

    def boom(path):
        calls.append(path)
        raise OSError("no wintrust")

    monkeypatch.setattr(td, "_win_verify_trust", boom)
    assert td._is_validly_signed(str(fake)) is False and td._is_validly_signed(str(fake)) is False
    assert len(calls) == 1
    fake.write_bytes(b"replacement executable")
    assert td._is_validly_signed(str(fake)) is False
    assert len(calls) == 2                       # replacing the file invalidates the path's old signature result


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_check_accepts_an_embedded_signature_and_rejects_an_unsigned_file(tmp_path):
    import os
    import time

    td._SIGNATURE_CACHE.clear()
    unsigned = tmp_path / "unsigned.exe"
    unsigned.write_bytes(b"MZ" + bytes(1000))
    started = time.perf_counter()
    assert td._is_validly_signed(str(unsigned)) is False
    assert time.perf_counter() - started < 5, "the native check must be fast (PowerShell took 15 s+ under load)"
    candidates = [sys.executable, r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Git\git-bash.exe", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")]
    assert any(td._is_validly_signed(c) for c in candidates if os.path.exists(c)), "no known signed binary verified"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
