"""Regression tests for GW-2 Tirith fail-closed gateway startup."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vectorcode" / "src"))

from tools import tirith_security


def _security_config(**overrides):
    config = {
        "tirith_enabled": True,
        "tirith_path": "tirith",
        "tirith_timeout": 5,
        "tirith_fail_open": True,
    }
    config.update(overrides)
    return config


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("tirith missing"),
        PermissionError("tirith not executable"),
        subprocess.TimeoutExpired(cmd="tirith", timeout=5),
    ],
)
def test_scanner_operational_failures_block_even_with_legacy_fail_open(failure):
    with patch.object(tirith_security, "_load_security_config", return_value=_security_config()), \
         patch.object(tirith_security, "_resolve_tirith_path", return_value="tirith"), \
         patch.object(tirith_security.subprocess, "run", side_effect=failure):
        verdict = tirith_security.check_command_security("echo hello")

    assert verdict["action"] == "block"
    assert "fail-closed" in verdict["summary"]


def test_scanner_unknown_exit_code_blocks_even_with_legacy_fail_open():
    completed = subprocess.CompletedProcess(args=["tirith"], returncode=99, stdout="", stderr="")
    with patch.object(tirith_security, "_load_security_config", return_value=_security_config()), \
         patch.object(tirith_security, "_resolve_tirith_path", return_value="tirith"), \
         patch.object(tirith_security.subprocess, "run", return_value=completed):
        verdict = tirith_security.check_command_security("echo hello")

    assert verdict["action"] == "block"
    assert "fail-closed" in verdict["summary"]


def test_require_installed_marks_scanner_unhealthy_when_binary_is_unavailable():
    tirith_security._resolved_path = None
    tirith_security._install_failure_reason = ""
    with patch.object(tirith_security, "_load_security_config", return_value=_security_config()), \
         patch.object(tirith_security, "_resolve_tirith_path", return_value="tirith"), \
         patch.object(tirith_security.os.path, "isfile", return_value=False), \
         patch.object(tirith_security.shutil, "which", return_value=None):
        with pytest.raises(tirith_security.TirithUnavailableError, match="unavailable"):
            tirith_security.require_installed()

    assert tirith_security.get_scanner_health() == {
        "status": "unhealthy",
        "reason": "binary_unavailable",
    }


def test_gateway_uses_blocking_scanner_prerequisite():
    source = (
        __import__("pathlib").Path("vectorcode/src/gateway/run.py")
        .read_text(encoding="utf-8")
    )
    assert "require_installed(log_failures=False)" in source
    assert "ensure_installed(log_failures=False)" not in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
