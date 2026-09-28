"""ComfyUIAdapter must hand back files that actually exist.

Root causes (found 2026-09-25 running the real adapter against a live ComfyUI):
  1. `_wait_for_images` / `_wait_for_video` guessed the output path as
     `CONFIG["comfyui"]["output_dir"]/<subfolder>/<filename>` (default
     ~/.vector/comfyui/output), but ComfyUI writes into its own install's
     `output/`. The adapter reported status "ok" with a path that did not exist.
  2. `ImageProviderRegistry._comfyui` calls `adapter.generate_image(...)`, which
     did not exist, so the registry's "primary" provider always failed silently.
Fix: fetch every output through ComfyUI's `/view` endpoint into `_output_dir`,
and add `generate_image()` returning `image_bytes`.
"""
import json

import httpx
import pytest

from districts.content import comfyui_adapter as mod
from districts.content.comfyui_adapter import ComfyUIAdapter

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"
MP4 = b"\x00\x00\x00\x18ftypmp42fake-video-bytes"


def _fake_comfy(monkeypatch, outputs, view_status=200, seen=None):
    """Point the adapter's httpx clients at an in-process fake ComfyUI."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if seen is not None:
            seen.append((request.method, path, dict(request.url.params)))
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {}})
        if path.startswith("/object_info"):
            return httpx.Response(200, json={"CheckpointLoaderSimple": {
                "input": {"required": {"ckpt_name": [["m.safetensors"]]}}}})
        if path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "pid1"})
        if path == "/history/pid1":
            return httpx.Response(200, json={"pid1": {"outputs": outputs}})
        if path == "/view":
            if view_status != 200:
                return httpx.Response(view_status, text="nope")
            name = request.url.params.get("filename", "")
            return httpx.Response(200, content=MP4 if name.endswith(".mp4") else PNG)
        return httpx.Response(404)

    real = httpx.AsyncClient
    monkeypatch.setattr(mod.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.fixture
def adapter(tmp_path):
    a = ComfyUIAdapter()
    a._output_dir = tmp_path / "out"
    a._poll_interval = 0
    return a


async def test_generate_returns_existing_files_with_the_real_bytes(adapter, monkeypatch):
    _fake_comfy(monkeypatch, {"9": {"images": [
        {"filename": "VECTOR_00001_.png", "subfolder": "", "type": "output"}]}})
    result = await adapter.generate("a city", steps=1)
    assert result["status"] == "ok"
    (path,) = result["images"]
    assert path.startswith(str(adapter._output_dir))
    with open(path, "rb") as fh:
        assert fh.read() == PNG


async def test_subfolder_and_type_are_requested_from_comfy(adapter, monkeypatch):
    seen = []
    _fake_comfy(monkeypatch, {"9": {"images": [
        {"filename": "a.png", "subfolder": "reels", "type": "output"}]}}, seen=seen)
    result = await adapter.generate("a city", steps=1)
    view = [p for (_m, path, p) in seen if path == "/view"]
    assert view == [{"filename": "a.png", "subfolder": "reels", "type": "output"}]
    assert result["images"][0].replace("\\", "/").endswith("out/reels/a.png")


async def test_failed_download_is_an_error_not_a_ghost_path(adapter, monkeypatch):
    _fake_comfy(monkeypatch, {"9": {"images": [
        {"filename": "a.png", "subfolder": "", "type": "output"}]}}, view_status=404)
    result = await adapter.generate("a city", steps=1)
    assert result["status"] == "error"
    assert result["images"] == []


async def test_generate_image_returns_bytes_for_the_registry(adapter, monkeypatch):
    _fake_comfy(monkeypatch, {"9": {"images": [
        {"filename": "a.png", "subfolder": "", "type": "output"}]}})
    result = await adapter.generate_image("a city", 512, 512, 1)
    assert result["status"] == "ok"
    assert result["image_bytes"] == PNG


async def test_video_path_exists_and_holds_the_video(adapter, monkeypatch):
    _fake_comfy(monkeypatch, {"5": {"gifs": [
        {"filename": "clip.mp4", "subfolder": "", "type": "output", "format": "video/h264-mp4"}]}})
    path = await adapter._wait_for_video("pid1")
    with open(path, "rb") as fh:
        assert fh.read() == MP4


async def test_registry_comfyui_provider_now_works(monkeypatch, tmp_path):
    from core.media.image_provider_registry import ImageProviderRegistry
    _fake_comfy(monkeypatch, {"9": {"images": [
        {"filename": "a.png", "subfolder": "", "type": "output"}]}})
    monkeypatch.setitem(mod.CONFIG["comfyui"], "output_dir", str(tmp_path / "reg"))
    monkeypatch.setitem(mod.CONFIG["comfyui"], "poll_interval", 0)
    data = await ImageProviderRegistry()._comfyui("a city", 512, 512, 1)
    assert data == PNG
