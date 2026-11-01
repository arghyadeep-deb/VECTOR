"""Bounded local image snapshots, with explicit approval before file content reads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import stat
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.config import CONFIG
from vectorcode.src.editor_context import validate_workspace_path


@dataclass(frozen=True)
class ImageAttachment:
    id: str
    project: str
    name: str
    mime: str
    width: int
    height: int
    data: bytes
    sha256: str

    def metadata(self):
        return {
            "id": self.id,
            "name": self.name,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "bytes": len(self.data),
            "sha256": self.sha256,
        }


def _path_metadata(name, project):
    root, relative = validate_workspace_path(str(Path(project).resolve()), name, project)
    path = root / relative
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise ValueError("Image attachment must not traverse links.")
        current = current.parent
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size > CONFIG["vectorcode"]["image_attachment_max_bytes"]:
        raise ValueError("Image attachment must be a bounded regular workspace file.")
    return root, relative, path, info


def _verify_bytes(raw):
    from PIL import Image

    settings = CONFIG["vectorcode"]
    if not raw or len(raw) > settings["image_attachment_max_bytes"]:
        raise ValueError("Image attachment exceeds the configured limit.")
    try:
        with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG"]) as image:
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width * height > settings["image_attachment_max_pixels"]
                or getattr(image, "is_animated", False)
            ):
                raise ValueError
            mime = {"PNG": "image/png", "JPEG": "image/jpeg"}[image.format]
            image.verify()
        return mime, width, height
    except Exception:
        raise ValueError("Image attachment must be a valid bounded static PNG or JPEG.") from None


def capture_image(name, project, approve):
    """Only the explicit human approval boundary may authorize the subsequent read."""
    try:
        root, relative, _, _ = _path_metadata(name, project)
    except (ValueError, OSError, RuntimeError):
        raise ValueError("Image attachment path or size is invalid.") from None
    if approve("image_attachment", "attach_image", {"path": relative, "project": str(root)}) is not True:
        raise PermissionError("Image attachment denied.")
    try:
        checked_root, checked_relative, path, expected = _path_metadata(name, project)
        if checked_root != root or checked_relative != relative:
            raise ValueError
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
                or opened.st_size > CONFIG["vectorcode"]["image_attachment_max_bytes"]
            ):
                raise ValueError
            raw = stream.read(CONFIG["vectorcode"]["image_attachment_max_bytes"] + 1)
        mime, width, height = _verify_bytes(raw)
    except (ValueError, OSError, RuntimeError):
        raise ValueError("Image attachment could not be read as a valid bounded workspace image.") from None
    return ImageAttachment(
        uuid.uuid4().hex, str(root), relative, mime, width, height, raw, hashlib.sha256(raw).hexdigest()
    )


def content_has_images(content):
    return isinstance(content, list) and any(
        isinstance(part, dict) and part.get("type") in {"image_url", "image", "input_image"} for part in content
    )


def saved_image_privacy(data):
    """A missing/false marker cannot erase pixels; malformed markers fail closed."""
    marker = data.get("local_images", False)
    if type(marker) is not bool:
        raise ValueError("Saved image privacy marker is invalid.")
    history = data.get("history", [])
    if not isinstance(history, list):
        raise ValueError("Saved conversation history is invalid.")
    return marker or any(isinstance(message, dict) and content_has_images(message.get("content"))
                         for message in history)


def image_content(question, images):
    if not isinstance(question, str):
        raise ValueError("Image question must be text.")
    try:
        question.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("Image question contains invalid Unicode.") from None
    if len(images) > CONFIG["vectorcode"]["image_attachment_max_count"]:
        raise ValueError("Too many image attachments.")
    if not images:
        return question
    return [{"type": "text", "text": question}] + [
        {
            "type": "image_url",
            "name": image.name,
            "image_url": {"url": f"data:{image.mime};base64," + base64.b64encode(image.data).decode("ascii")},
        }
        for image in images
    ]


def _decode_url(value):
    if not isinstance(value, dict) or set(value) != {"url"} or not isinstance(value["url"], str):
        raise ValueError("Invalid native image content.")
    url = value["url"]
    header, separator, encoded = url.partition(",")
    limit = CONFIG["vectorcode"]["image_attachment_max_bytes"]
    if (
        not separator
        or header not in {"data:image/png;base64", "data:image/jpeg;base64"}
        or len(encoded) > ((limit + 2) // 3) * 4
    ):
        raise ValueError("Only bounded embedded PNG/JPEG images are supported.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid native image encoding.") from None
    mime, _, _ = _verify_bytes(raw)
    if header != f"data:{mime};base64":
        raise ValueError("Native image MIME does not match its bytes.")
    return encoded, len(raw)


def ollama_content(content):
    """Translate canonical content parts without URL/file fetch or lossy stringification."""
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        raise ValueError("Unsupported message content.")
    texts, images = [], []
    for part in content:
        if not isinstance(part, dict):
            raise ValueError("Unsupported message content part.")
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif part.get("type") == "image_url":
            encoded, _ = _decode_url(part.get("image_url"))
            images.append(encoded)
        else:
            raise ValueError("Unsupported message content part.")
    if len(images) > CONFIG["vectorcode"]["image_attachment_max_count"]:
        raise ValueError("Too many images in one message.")
    return "\n".join(texts), images


def image_context_bytes(messages):
    total = 0
    for message in messages:
        content = message.get("content")
        if not content_has_images(content):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                _, size = _decode_url(part.get("image_url"))
                total += size
                if total > CONFIG["vectorcode"]["image_session_max_bytes"]:
                    raise ValueError("Image conversation exceeds the configured retained-data limit.")
            elif isinstance(part, dict) and part.get("type") in {"image", "input_image"}:
                raise ValueError("Unsupported native image content.")
    return total


def content_preview(content):
    """Terminal display projection never includes raw image bytes or data URLs."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "[Unsupported content]"
    pieces = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            pieces.append(part["text"])
        elif isinstance(part, dict) and part.get("type") in {"image_url", "image", "input_image"}:
            name = part.get("name")
            name = name if isinstance(name, str) else "image"
            name = "".join(c for c in name if not unicodedata.category(c).startswith("C"))
            pieces.append(f"[Image: {name[: CONFIG['vectorcode']['editor_metadata_max_chars']]}]")
    return "\n".join(pieces)


if __name__ == "__main__":
    assert ollama_content("public text") == ("public text", [])
