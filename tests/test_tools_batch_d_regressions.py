"""Regression coverage for the vectorcode ``tools`` batch-D audit fixes."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from vectorcode.src.tools import stt_tool
from vectorcode.src.tools.tool_result_storage import maybe_persist_tool_result
from vectorcode.src.tools.worktree import WorktreeManager


class _Sandbox:
    def __init__(self) -> None:
        self.command = ""

    def get_temp_dir(self) -> str:
        return "/tmp"

    def execute(self, command: str, timeout: int) -> dict:
        self.command = command
        return {"returncode": 0}


def test_persisted_tool_result_id_cannot_escape_storage_directory() -> None:
    sandbox = _Sandbox()

    result = maybe_persist_tool_result(
        "large output",
        "test",
        "../../escaped/result",
        env=sandbox,
        threshold=0,
    )

    assert "/tmp/vector-results/escaped_result.txt" in sandbox.command
    assert "../" not in result


class _ErrorResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("HTTP 401")

    def json(self) -> dict:
        return {"text": "must not be accepted"}


class _AsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return _ErrorResponse()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,key", [("openai", "OPENAI_API_KEY"), ("groq", "GROQ_API_KEY")])
async def test_cloud_stt_does_not_report_http_errors_as_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    key: str,
) -> None:
    import httpx

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"audio")
    monkeypatch.setenv(key, "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)

    result = await stt_tool.transcribe_audio(str(audio), provider=provider)

    assert result["success"] is False
    assert "401" in result["error"]


def test_worktree_path_and_branch_are_after_end_of_options(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)
    calls: list[tuple[str, ...]] = []

    class _Result:
        stdout = ""

    def fake_git(*args: str, **_kwargs):
        calls.append(args)
        return _Result()

    manager._git = fake_git  # type: ignore[method-assign]
    assert manager.destroy(Path("-option-like-path")) is True
    manager.list_worktrees = lambda: [  # type: ignore[method-assign]
        {"path": str(tmp_path), "HEAD": "abc", "branch": "refs/heads/feature"}
    ]
    assert manager.merge_to_main(tmp_path, message="merge")["ok"] is True

    assert calls[0][-2:] == ("--", "-option-like-path")
    assert calls[1][-2:] == ("--", "feature")


def test_tirith_archive_symlink_is_not_an_installable_binary(tmp_path: Path) -> None:
    archive = tmp_path / "tirith.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("tirith")
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside"
        tar.addfile(member)

    with tarfile.open(archive, "r:gz") as tar:
        candidates = [
            member
            for member in tar.getmembers()
            if (member.name == "tirith" or member.name.endswith("/tirith"))
            and ".." not in member.name
            and member.isfile()
        ]

    assert candidates == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
