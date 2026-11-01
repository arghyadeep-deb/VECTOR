"""Deterministic, non-safety output contracts for local and cloud LLM calls."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence, Set
from typing import Any


class OutputContractError(ValueError):
    """Raised when a model response violates an explicitly requested contract."""


_FENCED_CODE_RE = re.compile(
    r"\A\s*```(?P<language>[^\n`]*)\n(?P<body>.*?)\n?```\s*\Z",
    re.DOTALL,
)


def _contract_type(contract: str | Mapping[str, Any]) -> str:
    if isinstance(contract, str):
        kind = contract
    elif isinstance(contract, Mapping):
        kind = contract.get("type", "")
    else:
        raise OutputContractError("output contract must be a string or mapping")
    normalized = str(kind).strip().lower()
    if normalized not in {"text", "json", "code"}:
        raise OutputContractError(f"unsupported output contract: {kind!r}")
    return normalized


def _extract_json_value(text: str) -> Any:
    candidate = str(text or "").strip()
    fenced = _FENCED_CODE_RE.fullmatch(candidate)
    if fenced:
        candidate = fenced.group("body").strip()

    decoder = json.JSONDecoder()
    for index, character in enumerate(candidate):
        if character not in "[{\"-0123456789tfn":
            continue
        try:
            value, _end = decoder.raw_decode(candidate[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise OutputContractError("response does not contain valid JSON")


def _normalize_code(text: str) -> str:
    candidate = str(text or "").strip()
    if "```" not in candidate:
        return candidate
    fenced = _FENCED_CODE_RE.fullmatch(candidate)
    if not fenced:
        raise OutputContractError("code response must contain one surrounding Markdown fence")
    return fenced.group("body").strip()


def validate_output(
    text: str,
    contract: str | Mapping[str, Any],
) -> str:
    """Validate and normalize a text response for an explicit output contract."""
    kind = _contract_type(contract)
    if kind == "text":
        return str(text or "")
    if kind == "code":
        return _normalize_code(text)

    value = _extract_json_value(text)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_tool_calls(
    tool_calls: Sequence[Mapping[str, Any]],
    *,
    allowed_names: Set[str] | set[str],
) -> list[dict[str, Any]]:
    """Validate native tool-call envelopes without executing any tool."""
    if not isinstance(tool_calls, Sequence) or isinstance(tool_calls, (str, bytes)):
        raise OutputContractError("tool_calls must be a sequence")

    normalized: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            raise OutputContractError("each tool call must be an object")

        function = call.get("function")
        if isinstance(function, Mapping):
            name = str(function.get("name", "")).strip()
            raw_arguments = function.get("arguments", {})
        else:
            name = str(call.get("name", "")).strip()
            raw_arguments = call.get("arguments", {})

        if not name:
            raise OutputContractError("tool call is missing a function name")
        if name not in allowed_names:
            raise OutputContractError(f"tool name {name!r} is not allowed")

        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise OutputContractError("tool arguments must be valid JSON") from exc
        else:
            arguments = raw_arguments
        if not isinstance(arguments, Mapping):
            raise OutputContractError("tool arguments must be a JSON object")

        item: dict[str, Any] = {
            "id": call.get("id", ""),
            "name": name,
            "arguments": dict(arguments),
        }
        normalized.append(item)
    return normalized


if __name__ == "__main__":
    assert validate_output("```json\n{\"ok\": true}\n```", "json") == '{"ok":true}'
    assert validate_tool_calls(
        [{"function": {"name": "search_web", "arguments": "{}"}}],
        allowed_names={"search_web"},
    )[0]["name"] == "search_web"
    print("OK model_contracts.py")
