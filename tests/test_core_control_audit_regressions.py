"""Regressions for the 2026-10-07 core/control audit.

core/control/phone_controller.py:type_text() escaped shell metacharacters
(&, <, >, |, ;, (, ), `, ", ') before sending text through
``adb shell input text <text>``, but never escaped or stripped an embedded
literal newline. adb's shell-args joining sends the whole "input text ..."
line to the device's /system/bin/sh as one command string, where a raw
newline acts as a statement separator -- so text containing "\\n" could
inject an arbitrary second shell command on the Android device, even though
the type_text action itself was gateway-approved via a real control token.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from core.control.phone_controller import PhoneController
from core.control.security.node_router import _add_ips
from core.loop.permission_gateway import PermissionGateway


def _phone_controller_with_fake_adb(monkeypatch):
    ctrl = PhoneController()
    monkeypatch.setattr(ctrl, "_connected", True)
    captured: list[tuple] = []

    def _fake_run_adb(*args, timeout=10):
        captured.append(args)
        return (True, "")

    monkeypatch.setattr(ctrl, "_run_adb", _fake_run_adb)
    return ctrl, captured


def test_type_text_strips_embedded_newline_before_reaching_adb(monkeypatch):
    gw = PermissionGateway()
    token = gw.grant_control("play_music")  # GREEN tier -- self-mints, no receipt needed
    assert token

    ctrl, captured = _phone_controller_with_fake_adb(monkeypatch)

    ok = ctrl.type_text("hello\nrm -rf /sdcard/evil", control_token=token)

    assert ok is True
    assert len(captured) == 1
    typed_arg = captured[0][-1]
    assert "\n" not in typed_arg, (
        f"type_text leaked a raw newline into the adb shell command: {typed_arg!r} "
        "-- this lets text content inject a second shell statement on the device"
    )
    assert "\r" not in typed_arg


def test_type_text_without_a_valid_control_token_is_refused(monkeypatch):
    ctrl, captured = _phone_controller_with_fake_adb(monkeypatch)

    ok = ctrl.type_text("hello", control_token="not-a-real-token")

    assert ok is False
    assert captured == []


def test_add_ips_logs_the_actual_parse_exception_not_a_dropped_kwarg():
    """core/control/security/node_router.py:_add_ips() used
    logger.warning(msg, exc_info=True) -- loguru's warning() treats unknown
    kwargs as str.format() substitutions, not a stdlib-style exc_info flag,
    so the exception traceback was silently dropped on every bad-IP line."""
    sink_id = None
    records: list[str] = []
    try:
        sink_id = logger.add(lambda m: records.append(m), format="{message}\n{exception}")
        _add_ips("not-an-ip-address", [])
    finally:
        if sink_id is not None:
            logger.remove(sink_id)

    assert records, "expected a warning log record for the invalid IP"
    assert "Traceback" in records[0] or "OSError" in records[0], (
        f"exception context was dropped from the log record: {records[0]!r}"
    )


if __name__ == "__main__":
    import subprocess as _sp

    result = _sp.run([sys.executable, "-m", "pytest", __file__, "-v"])
    print("✅ test_core_control_audit_regressions OK" if result.returncode == 0 else "❌ FAILED")
