"""Focused regressions for FL-032 and the FL-035 media-tool decisions."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from core.config import CONFIG
from core.loop.permission_gateway import Action, PermissionGateway


def test_api_source_gets_only_generic_run_capability() -> None:
    gateway = PermissionGateway()

    assert gateway._check_capability(
        Action("camera_activate", {}, "api_camera")
    ) == (True, "api_camera has generic.run")
    assert gateway._check_capability(
        Action("camera_activate", {}, "some_llm_proposed_source")
    ) == (False, "some_llm_proposed_source lacks generic.run")
    assert gateway._check_capability(
        Action("push_github", {}, "api_something")
    ) == (False, "api_something lacks vcs.push")


@pytest.fixture
def media_root(monkeypatch, tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    monkeypatch.setitem(CONFIG["media"], "allowed_root", str(root))
    return root


@pytest.mark.parametrize(
    ("tool_module", "tool_class", "path_param", "filename", "extra_params"),
    [
        ("audio_tool", "AudioTranscribeTool", "file_path", "clip.wav", {"provider": "local"}),
        ("image_tool", "ImageGenerateTool", "output_path", "image.png", {"prompt": "test"}),
        ("pdf_tool", "PDFExtractTool", "file_path", "document.pdf", {}),
    ],
)
def test_media_tool_rejects_path_outside_allowed_root(
    media_root, tool_module, tool_class, path_param, filename, extra_params
) -> None:
    module = __import__(f"vectorcode.src.vc_tools.{tool_module}", fromlist=[tool_class])
    tool = getattr(module, tool_class)()
    outside = media_root.parent / "outside" / filename
    outside.parent.mkdir(exist_ok=True)
    if path_param == "file_path":
        outside.write_bytes(b"not real media")

    result = tool.execute(**extra_params, **{path_param: str(outside)})

    assert result.success is False
    assert "outside the allowed" in result.content.lower()


@pytest.mark.parametrize(
    ("tool_module", "tool_class", "path_param", "filename", "extra_params"),
    [
        ("audio_tool", "AudioTranscribeTool", "file_path", "missing.wav", {"provider": "local"}),
        ("image_tool", "ImageGenerateTool", "output_path", "image.png", {"prompt": "test"}),
        ("pdf_tool", "PDFExtractTool", "file_path", "missing.pdf", {}),
    ],
)
def test_media_tool_allows_path_inside_allowed_root_past_confinement(
    media_root, tool_module, tool_class, path_param, filename, extra_params
) -> None:
    module = __import__(f"vectorcode.src.vc_tools.{tool_module}", fromlist=[tool_class])
    result = getattr(module, tool_class)().execute(
        **extra_params, **{path_param: str(media_root / filename)}
    )

    assert "outside the allowed" not in result.content.lower()


@pytest.mark.parametrize(
    ("tool_module", "tool_class", "path_param", "filename", "extra_params"),
    [
        ("audio_tool", "AudioTranscribeTool", "file_path", "clip.wav", {"provider": "local"}),
        ("image_tool", "ImageGenerateTool", "output_path", "image.png", {"prompt": "test"}),
        ("pdf_tool", "PDFExtractTool", "file_path", "document.pdf", {}),
    ],
)
def test_media_tool_rejects_sibling_prefix_bypass(
    media_root, tool_module, tool_class, path_param, filename, extra_params
) -> None:
    module = __import__(f"vectorcode.src.vc_tools.{tool_module}", fromlist=[tool_class])
    sibling = media_root.parent / "mediaEVIL" / filename
    sibling.parent.mkdir()
    if path_param == "file_path":
        sibling.write_bytes(b"not real media")

    result = getattr(module, tool_class)().execute(
        **extra_params, **{path_param: str(sibling)}
    )

    assert result.success is False
    assert "outside the allowed" in result.content.lower()


def test_openai_whisper_is_disabled_without_constructing_client(
    monkeypatch, media_root
) -> None:
    from vectorcode.src.vc_tools.audio_tool import AudioTranscribeTool

    audio = media_root / "clip.wav"
    audio.write_bytes(b"not real audio")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda: pytest.fail("OpenAI client must not be constructed")),
    )

    result = AudioTranscribeTool().execute(file_path=str(audio), provider="openai")

    assert result.success is False
    assert "disabled" in result.content.lower()
    assert "free-tier" in result.content.lower()


def test_dall_e_is_disabled_without_constructing_client(monkeypatch) -> None:
    from vectorcode.src.vc_tools.image_tool import ImageGenerateTool

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda: pytest.fail("OpenAI client must not be constructed")),
    )

    result = ImageGenerateTool().execute(prompt="test", provider="openai")

    assert result.success is False
    assert "disabled" in result.content.lower()
    assert "free-tier" in result.content.lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
