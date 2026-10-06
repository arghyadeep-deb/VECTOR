"""Regression coverage for the tools batch-B correctness fixes."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from vectorcode.src.tools.direct_executor import DirectTaskExecutor
from vectorcode.src.tools.file_tools import FileTools
from vectorcode.src.tools.git_tools import GitTools


@pytest.mark.asyncio
async def test_direct_executor_does_not_validate_failed_command(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="", stderr="command failed", returncode=7
        ),
    )

    result = await DirectTaskExecutor().execute(
        "run failing command", [{"type": "bash", "command": "false"}]
    )

    assert result.validated is False
    assert result.output == "command failed"


def test_git_blame_terminates_options_before_caller_path(monkeypatch, tmp_path) -> None:
    tools = GitTools(tmp_path)
    captured: list[str] = []

    def fake_run(args, timeout=30):
        captured.extend(args)
        return {"stdout": "ok", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tools, "_run", fake_run)
    tools.git_blame("--help")

    assert captured == ["blame", "--", "--help"]


def test_tools_file_safety_uses_platform_case_normalization(
    monkeypatch, tmp_path: Path
) -> None:
    from vectorcode.src.tools import file_safety

    home = tmp_path / "UserHome"
    monkeypatch.setattr(
        file_safety.os.path,
        "expanduser",
        lambda value: str(home) if value == "~" else value,
    )
    monkeypatch.setattr(file_safety.os.path, "normcase", lambda value: value.lower())

    assert file_safety.is_write_denied(str(home / ".SSH" / "ID_RSA")) is True


def test_filetools_blocks_absolute_and_sibling_prefix_escapes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    sibling = tmp_path / "repo-secrets"
    root.mkdir()
    sibling.mkdir()
    tools = FileTools(root)

    with pytest.raises(PermissionError):
        tools.read(str(sibling / "secret.txt"))


def test_filetools_atomic_write_preserves_original_if_replace_fails(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "state.json"
    target.write_text("original", encoding="utf-8")
    tools = FileTools(tmp_path)
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(OSError, match="boom"):
        tools.write("state.json", "replacement")

    assert target.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".state.json.*"))


def test_environment_json_store_is_atomic_and_utf8(monkeypatch, tmp_path: Path) -> None:
    from vectorcode.src.tools.environments import base

    target = tmp_path / "snapshots.json"
    target.write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr(
        base.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        base._save_json_store(target, {"label": "বাংলা"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob(".snapshots.json.*"))


def test_managed_modal_uses_httpx_and_preserves_connect_read_timeouts(monkeypatch) -> None:
    from vectorcode.src.tools.environments import managed_modal

    env = object.__new__(managed_modal.ManagedModalEnvironment)
    env._gateway_origin = "https://gateway.example"
    env._nous_user_token = "secret-token"
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(managed_modal.httpx, "request", fake_request)
    env._request("GET", "/status", timeout=(1.5, 4.0))

    timeout = captured["timeout"]
    assert isinstance(timeout, managed_modal.httpx.Timeout)
    assert timeout.connect == 1.5
    assert timeout.read == 4.0
    assert captured["headers"]["Authorization"] == "Bearer secret-token"


def test_docker_logging_does_not_render_explicit_environment_values() -> None:
    source = Path("vectorcode/src/tools/environments/docker.py").read_text(
        encoding="utf-8"
    )
    assert 'logger.info(f"Docker run_args: {all_run_args}")' not in source
    assert 'logger.debug(f"Starting container: {' not in source
