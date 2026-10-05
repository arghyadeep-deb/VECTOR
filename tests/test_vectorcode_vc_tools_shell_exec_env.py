"""Regression for vectorcode/src/vc_tools/shell_exec.py's ShellExecTool:

_BASE_ENV_KEYS built a replacement environment (not an extension of
os.environ) containing only PATH/HOME/USER/LANG/TERM. On Windows, Win32's
CreateProcess/Winsock initialization needs SYSTEMROOT (and WINDIR/COMSPEC)
to be present in the child's environment -- without it, any command doing
DNS resolution or other socket activity fails with
"socket.gaierror: [Errno 11001] getaddrinfo failed" regardless of whether
the command itself is otherwise fine. Confirmed live: a bare
`socket.gethostbyname("localhost")` call in a subprocess raises that error
with the old env, and succeeds once SYSTEMROOT/WINDIR/COMSPEC are included.

This is the same root-cause shape as a sibling fix this audit cycle (an
evals-harness environment that replaced os.environ instead of extending
it), just independently discovered here via a real subprocess spawn
instead of an import error.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_tools.shell_exec import _BASE_ENV_KEYS


@pytest.mark.skipif(os.name != "nt", reason="SYSTEMROOT is a Windows-specific requirement")
def test_base_env_keys_include_systemroot():
    assert "SYSTEMROOT" in _BASE_ENV_KEYS
    assert "WINDIR" in _BASE_ENV_KEYS


@pytest.mark.skipif(os.name != "nt", reason="reproduces a Windows-specific CreateProcess/Winsock gap")
def test_subprocess_network_call_fails_without_systemroot(tmp_path):
    script = tmp_path / "sock_test.py"
    script.write_text('import socket\nprint(socket.gethostbyname("localhost"))\n')

    env = {"PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=10, env=env
    )
    assert result.returncode != 0
    assert "getaddrinfo failed" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="verifies the fix for a Windows-specific gap")
def test_subprocess_network_call_succeeds_with_base_env_keys(tmp_path):
    script = tmp_path / "sock_test.py"
    script.write_text('import socket\nprint(socket.gethostbyname("localhost"))\n')

    env = {}
    for key in _BASE_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=10, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "127.0.0.1" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
