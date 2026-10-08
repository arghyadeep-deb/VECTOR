"""Regression tests for OD-59 VectorSandbox container routing."""

from __future__ import annotations

import asyncio

from core.sandbox import vector_sandbox
from core.sandbox.runner import ContainerRunner


def _run(coro):
    return asyncio.run(coro)


def _enable_container_routing(monkeypatch, canned_result, calls):
    monkeypatch.setattr(
        vector_sandbox,
        "_container_runtime_available",
        lambda: True,
        raising=False,
    )

    def fake_run(self, input_data, **kwargs):
        calls.append((self, input_data, kwargs))
        return canned_result

    monkeypatch.setattr(ContainerRunner, "run", fake_run)


def test_run_code_safe_routes_through_container(monkeypatch):
    calls = []
    canned = {
        "success": True,
        "stdout": "4\n",
        "stderr": "",
        "exit_code": 0,
        "elapsed_secs": 0.125,
        "timed_out": False,
        "truncated": False,
    }
    _enable_container_routing(monkeypatch, canned, calls)

    result = _run(vector_sandbox.VectorSandbox().run_code_safe("print(2 + 2)", timeout=7))

    assert result == vector_sandbox.SandboxResult(**canned)
    assert len(calls) == 1
    runner, payload, kwargs = calls[0]
    assert runner._timeout == 7
    assert payload["timeout"] == 7
    assert payload["cmd"][:2] == ["python3", "-c"]
    assert "print(2 + 2)" in payload["cmd"][2]
    assert kwargs["mounts"] is None
    assert kwargs["env"] == {}


def test_run_shell_routes_through_container_and_forwards_env(monkeypatch):
    calls = []
    canned = {
        "success": True,
        "stdout": "container-shell\n",
        "stderr": "",
        "exit_code": 0,
        "elapsed_secs": 0.25,
        "timed_out": False,
        "truncated": False,
    }
    _enable_container_routing(monkeypatch, canned, calls)

    result = _run(
        vector_sandbox.VectorSandbox().run_shell(
            "printf container-shell",
            timeout=9,
            extra_env={
                "VECTOR_TEST_VALUE": "preserved",
                "PATH": "/caller/explicit/path",
            },
        )
    )

    assert result == vector_sandbox.SandboxResult(**canned)
    _, payload, kwargs = calls[0]
    assert payload == {
        "cmd": ["/bin/sh", "-c", "printf container-shell"],
        "timeout": 9,
    }
    assert kwargs["env"] == {
        "VECTOR_TEST_VALUE": "preserved",
        "PATH": "/caller/explicit/path",
    }


def test_container_env_excludes_host_defaults_without_explicit_extra_env(
    monkeypatch,
):
    calls = []
    canned = {
        "success": True,
        "stdout": "container-shell\n",
        "stderr": "",
        "exit_code": 0,
        "elapsed_secs": 0.25,
        "timed_out": False,
        "truncated": False,
    }
    _enable_container_routing(monkeypatch, canned, calls)
    host_only_keys = (
        "PATH",
        "SYSTEMROOT",
        "SystemRoot",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
    )
    for key in host_only_keys:
        monkeypatch.setenv(key, f"host-{key}")

    result = _run(vector_sandbox.VectorSandbox().run_shell("echo hi"))

    assert result == vector_sandbox.SandboxResult(**canned)
    assert calls[0][2]["env"] == {}


def test_container_nonzero_exit_maps_to_failed_sandbox_result(monkeypatch):
    calls = []
    canned = {
        "success": False,
        "stdout": "",
        "stderr": "bad command",
        "exit_code": 23,
        "elapsed_secs": 0.5,
        "timed_out": False,
        "truncated": False,
    }
    _enable_container_routing(monkeypatch, canned, calls)

    result = _run(vector_sandbox.VectorSandbox().run_shell("exit 23"))

    assert result == vector_sandbox.SandboxResult(**canned)
    assert not result.success
    assert result.exit_code == 23


def test_container_timeout_error_maps_to_timed_out_result(monkeypatch):
    calls = []
    canned = {
        "content": "Container timed out after 3s.",
        "error": True,
        "error_type": "timeout",
    }
    _enable_container_routing(monkeypatch, canned, calls)

    result = _run(vector_sandbox.VectorSandbox().run_shell("sleep 60", timeout=3))

    assert not result.success
    assert result.stdout == ""
    assert result.stderr == canned["content"]
    assert result.exit_code == -1
    assert result.elapsed_secs >= 0.0
    assert result.timed_out
    assert not result.truncated


def test_unavailable_container_uses_real_subprocess_and_warns_once(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        vector_sandbox,
        "_container_runtime_available",
        lambda: False,
        raising=False,
    )
    monkeypatch.setattr(
        vector_sandbox,
        "_container_unavailable_reason",
        "container runtime binary not found",
        raising=False,
    )
    monkeypatch.setattr(
        vector_sandbox,
        "_fallback_warning_emitted",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        vector_sandbox.logger,
        "warning",
        lambda message, *args: warnings.append(message.format(*args)),
    )
    sandbox = vector_sandbox.VectorSandbox()

    first = _run(sandbox.run_code_safe("print('host-fallback-one')"))
    second = _run(sandbox.run_code_safe("print('host-fallback-two')"))

    assert first.success and first.stdout.strip() == "host-fallback-one"
    assert second.success and second.stdout.strip() == "host-fallback-two"
    assert len(warnings) == 1
    assert "without container isolation" in warnings[0]
    assert "container runtime binary not found" in warnings[0]


def test_run_file_stays_on_real_host_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(
        vector_sandbox,
        "_container_runtime_available",
        lambda: True,
        raising=False,
    )

    def unexpected_container_run(*args, **kwargs):
        raise AssertionError("run_file must not route through the container")

    monkeypatch.setattr(ContainerRunner, "run", unexpected_container_run)
    script = tmp_path / "host_script.py"
    script.write_text("print('host-file')\n", encoding="utf-8")

    result = _run(vector_sandbox.VectorSandbox().run_file(str(script)))

    assert result.success
    assert result.stdout.strip() == "host-file"


if __name__ == "__main__":
    raise SystemExit("Run with: python -m pytest tests/test_vector_sandbox_container_routing.py -v")
