"""Regression tests: builtin TOML tool templates must do what they claim.

Four of the builtin templates (base64_encode, hash_compute, regex_extract,
date_info) were registered under names/descriptions promising real behavior,
but their "python" action expressions were broken stubs:
  - base64_encode.toml / hash_compute.toml / regex_extract.toml: the
    expression was just ``str(input)`` -- it echoed the raw input back
    unchanged instead of base64-encoding, SHA-256-hashing, or
    regex-extracting anything. A caller trusting "hash_compute" to return a
    hash got the plaintext back instead, silently.
  - date_info.toml: declared ZERO parameters in its schema, yet its
    expression referenced an undeclared ``input`` name -- calling it with no
    arguments (the only schema-compliant way to call it) raised
    ValueError("unknown name: input") instead of returning the current time.

Fixed by adding real base64_encode()/sha256()/regex_extract()/now_iso()
helpers to the sandboxed expression evaluator's function allowlist and
pointing each template's expression at the correct one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re

from vectorcode.src.vc_tools.templates.loader import load_template

_BUILTIN_DIR = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "vectorcode"
    / "src"
    / "vc_tools"
    / "templates"
    / "builtin"
)


def test_base64_encode_actually_encodes() -> None:
    tool = load_template(_BUILTIN_DIR / "base64_encode.toml")
    result = tool.execute(input="hello world")

    assert result.success
    assert result.content == base64.b64encode(b"hello world").decode("ascii")
    assert result.content != "hello world"


def test_hash_compute_actually_hashes() -> None:
    tool = load_template(_BUILTIN_DIR / "hash_compute.toml")
    result = tool.execute(input="hello world")

    assert result.success
    assert result.content == hashlib.sha256(b"hello world").hexdigest()
    assert result.content != "hello world"


def test_regex_extract_actually_extracts() -> None:
    tool = load_template(_BUILTIN_DIR / "regex_extract.toml")
    result = tool.execute(input="order #123 and order #456", pattern=r"#(\d+)")

    assert result.success
    assert json.loads(result.content) == ["123", "456"]


def test_date_info_returns_real_timestamp_with_no_args() -> None:
    tool = load_template(_BUILTIN_DIR / "date_info.toml")
    result = tool.execute()

    assert result.success
    # Must parse as a real ISO-8601 timestamp, not an echoed/placeholder string.
    from datetime import datetime

    datetime.fromisoformat(result.content)


def test_text_transforms_still_work_unaffected() -> None:
    tool = load_template(_BUILTIN_DIR / "text_upper.toml")
    result = tool.execute(input="shout")
    assert result.success
    assert result.content == "SHOUT"
