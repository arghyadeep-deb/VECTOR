"""
VECTOR Tool Dispatcher — three pluggable tool-call formats.

Ported from vector's agent/dispatcher.rs.

Formats:
  Native    : structured tool_calls array (OpenAI/Anthropic API native)
  XML       : <tool_call>{"name": ..., "arguments": ...}</tool_call> tags
  PFormat   : compact tool_name[arg1|arg2|...] inline syntax

VECTOR default: Native (supported by all Ollama models with tool support).
XML is used as fallback for models without native tool calling.
PFormat is for ultra-compact prompts to small models.
"""
from __future__ import annotations

__all__ = [
    "make_dispatcher",
    "NativeDispatcher",
    "ParsedToolCall",
    "PermissionLevel",
    "PFormatDispatcher",
    "ToolDispatcher",
    "ToolExecutionResult",
    "ToolScope",
    "XmlDispatcher",
]


import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class ToolScope(str, Enum):
    ALL        = "all"         # agent loop + CLI + RPC
    AGENT_ONLY = "agent_only"  # autonomous agent only
    CLI_RPC    = "cli_rpc"     # explicit CLI/RPC calls only


class PermissionLevel(int, Enum):
    NONE      = 0
    READ_ONLY = 1
    WRITE     = 2
    EXECUTE   = 3
    DANGEROUS = 4


@dataclass
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "arguments": self.arguments, "id": self.call_id}


@dataclass
class ToolExecutionResult:
    call_id: str
    name: str
    output: str
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_message(self) -> dict:
        content = f"ERROR: {self.error}" if self.error else self.output
        return {"role": "tool", "tool_call_id": self.call_id,
                "name": self.name, "content": content}


# â”€â”€ Base dispatcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ToolDispatcher(ABC):
    """Parse tool calls from LLM responses and format results back."""

    @abstractmethod
    def parse_response(self, response_text: str, raw_response: dict | None = None) -> tuple[str, list[ParsedToolCall]]:
        """Extract (clean_text, tool_calls) from a model response."""

    @abstractmethod
    def format_results(self, results: list[ToolExecutionResult]) -> dict:
        """Format tool results as a conversation message."""

    def prompt_instructions(self, tool_specs: list[dict]) -> str:
        """Optional: extra instructions for the model about tool format."""
        return ""

    def sends_tool_specs(self) -> bool:
        """True if this dispatcher sends tool JSON schemas in the API call."""
        return False


# â”€â”€ Native dispatcher (OpenAI/Anthropic structured tool_calls) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class NativeDispatcher(ToolDispatcher):
    """
    Parses structured tool_calls from the API response object.
    Falls back to XmlDispatcher if no structured calls found.
    Used with Ollama models that support native tool calling.
    """

    def __init__(self) -> None:
        self._xml_fallback = XmlDispatcher()

    def sends_tool_specs(self) -> bool:
        return True

    def parse_response(self, response_text: str, raw_response: dict | None = None) -> tuple[str, list[ParsedToolCall]]:
        calls: list[ParsedToolCall] = []

        # Try structured tool_calls first
        if raw_response:
            choices = raw_response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                for tc in msg.get("tool_calls", []):
                    try:
                        fn = tc.get("function", tc)
                        args = fn.get("arguments", "{}")
                        if isinstance(args, str):
                            args = json.loads(args)
                        calls.append(ParsedToolCall(
                            name=fn.get("name", ""),
                            arguments=args,
                            call_id=tc.get("id", ""),
                        ))
                    except Exception as e:
                        logger.warning("[VECTOR][dispatcher] tool_call parse failed: {}", e)

        if calls:
            return response_text, calls

        # Fallback to XML parsing
        return self._xml_fallback.parse_response(response_text)

    def format_results(self, results: list[ToolExecutionResult]) -> dict:
        return {"role": "tool", "content": json.dumps([r.to_dict() for r in results])}


# â”€â”€ XML dispatcher (<tool_call> tags) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_XML_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL,
)
_XML_ALT_PATTERN = re.compile(
    r"<function_calls>\s*<invoke name=['\"](\w+)['\"]>(.*?)</invoke>\s*</function_calls>",
    re.DOTALL,
)


class XmlDispatcher(ToolDispatcher):
    """
    Parses <tool_call>{"name": ..., "arguments": ...}</tool_call> XML tags.
    Used as fallback for models without native tool calling.
    """

    def parse_response(self, response_text: str, raw_response: dict | None = None) -> tuple[str, list[ParsedToolCall]]:
        calls: list[ParsedToolCall] = []
        clean = response_text

        # Standard <tool_call> pattern
        for m in _XML_PATTERN.finditer(response_text):
            try:
                payload = json.loads(m.group(1))
                name = payload.get("name") or payload.get("function", "")
                args = payload.get("arguments") or payload.get("parameters") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                calls.append(ParsedToolCall(name=name, arguments=args))
                clean = clean.replace(m.group(0), "").strip()
            except Exception as e:
                logger.warning("[VECTOR][xml_dispatcher] parse failed: {}", e)

        # Alt <function_calls> pattern (Anthropic XML)
        if not calls:
            for m in _XML_ALT_PATTERN.finditer(response_text):
                try:
                    name = m.group(1)
                    body = m.group(2)
                    args = {}
                    for param in re.finditer(r"<parameter name=['\"](\w+)['\"]>(.*?)</parameter>", body, re.DOTALL):
                        args[param.group(1)] = param.group(2).strip()
                    calls.append(ParsedToolCall(name=name, arguments=args))
                    clean = clean.replace(m.group(0), "").strip()
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        return clean, calls

    def format_results(self, results: list[ToolExecutionResult]) -> dict:
        parts = []
        for r in results:
            status = "error" if r.is_error else "success"
            content = r.error if r.is_error else r.output
            parts.append(f"<tool_response name=\"{r.name}\" status=\"{status}\">{content}</tool_response>")
        return {"role": "user", "content": "\n".join(parts)}

    def prompt_instructions(self, tool_specs: list[dict]) -> str:
        if not tool_specs:
            return ""
        specs_json = json.dumps(tool_specs, indent=2)
        return (
            f"\n\nAvailable tools:\n```json\n{specs_json}\n```\n"
            "To call a tool, respond with:\n"
            "<tool_call>{\"name\": \"tool_name\", \"arguments\": {...}}</tool_call>"
        )


# â”€â”€ P-Format dispatcher (compact inline syntax) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PFORMAT_PATTERN = re.compile(r"(\w[\w_]*)\[([^\]]*)\]")


class PFormatDispatcher(ToolDispatcher):
    """
    Parses compact P-Format: tool_name[arg1|arg2|key=value]
    Used for ultra-small models where JSON overhead is costly.
    Falls back to XML if no P-Format calls found.
    """

    def __init__(self, schema_registry: dict[str, list[str]] | None = None) -> None:
        self._schemas = schema_registry or {}   # {tool_name: [param_names]}
        self._xml_fallback = XmlDispatcher()

    def parse_response(self, response_text: str, raw_response: dict | None = None) -> tuple[str, list[ParsedToolCall]]:
        calls: list[ParsedToolCall] = []
        clean = response_text

        for m in _PFORMAT_PATTERN.finditer(response_text):
            name = m.group(1)
            if name not in self._schemas and name.lower() == name:
                continue  # likely a word, not a tool call
            raw_args = m.group(2)
            args = self._parse_args(name, raw_args)
            calls.append(ParsedToolCall(name=name, arguments=args))
            clean = clean.replace(m.group(0), "").strip()

        if not calls:
            return self._xml_fallback.parse_response(response_text)

        return clean, calls

    def _parse_args(self, tool_name: str, raw: str) -> dict[str, Any]:
        params = self._schemas.get(tool_name, [])
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        args: dict[str, Any] = {}
        for i, part in enumerate(parts):
            if "=" in part:
                k, v = part.split("=", 1)
                args[k.strip()] = v.strip()
            elif i < len(params):
                args[params[i]] = part
            else:
                args[f"arg{i}"] = part
        return args

    def format_results(self, results: list[ToolExecutionResult]) -> dict:
        parts = [f"{r.name}={'ERROR:'+r.error if r.is_error else r.output[:200]}" for r in results]
        return {"role": "user", "content": "Tool results: " + " | ".join(parts)}

    def prompt_instructions(self, tool_specs: list[dict]) -> str:
        if not tool_specs:
            return ""
        lines = ["Available tools (format: tool_name[arg1|arg2|...]):"]
        for spec in tool_specs:
            params = list(spec.get("parameters", {}).get("properties", {}).keys())
            lines.append(f"  {spec['name']}[{'|'.join(params)}] — {spec.get('description','')[:60]}")
        return "\n" + "\n".join(lines)


# â”€â”€ Factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def make_dispatcher(format_name: str = "native", **kwargs) -> ToolDispatcher:
    """Create a dispatcher by name: 'native' | 'xml' | 'pformat'."""
    match format_name.lower():
        case "native": return NativeDispatcher()
        case "xml":    return XmlDispatcher()
        case "pformat": return PFormatDispatcher(**kwargs)
        case _:
            logger.warning("[VECTOR][dispatcher] unknown format '{}', using native", format_name)
            return NativeDispatcher()


if __name__ == "__main__":
    # Native — no structured calls, falls back to XML
    nd = NativeDispatcher()
    text = 'Let me help. <tool_call>{"name": "read_file", "arguments": {"path": "x.py"}}</tool_call>'
    clean, calls = nd.parse_response(text)
    assert len(calls) == 1 and calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "x.py"}

    # XML dispatcher
    xd = XmlDispatcher()
    clean2, calls2 = xd.parse_response('<tool_call>{"name": "bash", "arguments": {"cmd": "ls"}}</tool_call>')
    assert len(calls2) == 1 and calls2[0].name == "bash"

    # PFormat dispatcher
    pd = PFormatDispatcher(schema_registry={"read_file": ["path"], "bash": ["cmd"]})
    _, calls3 = pd.parse_response("read_file[src/main.py]")
    assert len(calls3) == 1 and calls3[0].arguments["path"] == "src/main.py"

    # Results formatting
    result = ToolExecutionResult(call_id="1", name="bash", output="hello")
    msg = xd.format_results([result])
    assert "bash" in msg["content"]

    print("OK dispatcher.py — Native/XML/PFormat all verified")
