"""Native Gemini generateContent conversion; execution remains in the coding engine."""

import json
import uuid
from copy import deepcopy

from . import register_transport
from .base import ProviderTransport
from .types import NormalizedResponse, ToolCall, Usage


class GeminiTransport(ProviderTransport):
    api_mode = "gemini_generate_content"

    def convert_messages(self, messages, **kwargs):
        system, contents, names = [], [], {}
        native_ids = set()
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise ValueError("Native Gemini coding currently accepts text messages only.")
            if role in {"system", "developer"}:
                if content:
                    system.append({"text": content})
                continue
            parts = []
            if role == "tool":
                name = message.get("name") or names.get(message.get("tool_call_id"))
                if not name:
                    raise ValueError("Gemini tool result has no matching function name.")
                try:
                    value = json.loads(content)
                except ValueError:
                    value = {"result": content}
                if not isinstance(value, dict):
                    value = {"result": value}
                response = {"name": name, "response": value}
                if message.get("tool_call_id") in native_ids:
                    response["id"] = message["tool_call_id"]
                parts = [{"functionResponse": response}]
            else:
                calls = message.get("tool_calls") or []
                for call in calls:
                    function = call.get("function") or call
                    names[call.get("id")] = function["name"]
                original = next(
                    (
                        (call.get("provider_data") or {}).get("gemini_parts")
                        for call in calls
                        if (call.get("provider_data") or {}).get("gemini_parts")
                    ),
                    None,
                )
                if original:
                    parts = deepcopy(original)
                    native_ids.update(
                        part["functionCall"]["id"] for part in parts if (part.get("functionCall") or {}).get("id")
                    )
                else:
                    if content:
                        parts.append({"text": content})
                    for call in calls:
                        function = call.get("function") or call
                        arguments = function.get("arguments") or {}
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        parts.append({"functionCall": {"name": function["name"], "args": arguments}})
            if not parts:
                continue
            native_role = "model" if role == "assistant" else "user"
            if contents and contents[-1]["role"] == native_role:
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": native_role, "parts": parts})
        return system, contents

    def convert_tools(self, tools):
        declarations = []
        for tool in tools or []:
            function = tool.get("function") or tool
            declaration = {
                "name": function["name"],
                "parametersJsonSchema": deepcopy(function.get("parameters") or {"type": "object"}),
            }
            if function.get("description"):
                declaration["description"] = function["description"]
            declarations.append(declaration)
        return [{"functionDeclarations": declarations}] if declarations else []

    def build_kwargs(self, model, messages, tools=None, **params):
        system, contents = self.convert_messages(messages)
        payload = {"contents": contents, "generationConfig": {"maxOutputTokens": params.get("max_tokens", 4096)}}
        if system:
            payload["systemInstruction"] = {"parts": system}
        if tools:
            payload["tools"] = self.convert_tools(tools)
        return payload

    def validate_response(self, response):
        return isinstance(response, dict) and bool(response.get("candidates") or response.get("promptFeedback"))

    def normalize_response(self, response, **kwargs):
        candidate = next(iter(response.get("candidates") or []), {})
        parts = (candidate.get("content") or {}).get("parts") or []
        calls = []
        for part in parts:
            function = part.get("functionCall")
            if function:
                calls.append(
                    ToolCall(
                        function.get("id") or uuid.uuid4().hex,
                        function["name"],
                        json.dumps(function.get("args") or {}),
                        {"gemini_parts": deepcopy(parts)} if not calls else None,
                    )
                )
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        reason = candidate.get("finishReason", "")
        if reason == "MAX_TOKENS":
            finish = "length"
        elif reason != "STOP" or not candidate:
            # Only a completed native response may propose executable calls.
            # Unknown/new rejection reasons fail closed too.
            finish = "content_filter"
        else:
            finish = "tool_calls" if calls else "stop"
        usage = response.get("usageMetadata") or {}
        prompt = usage.get("promptTokenCount", 0)
        output = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        return NormalizedResponse(
            text,
            (calls or None) if finish == "tool_calls" else None,
            finish,
            usage=Usage(
                prompt, output, usage.get("totalTokenCount", prompt + output), usage.get("cachedContentTokenCount", 0)
            ),
        )


register_transport("gemini_generate_content", GeminiTransport)

if __name__ == "__main__":
    assert GeminiTransport().build_kwargs("example", [{"role": "user", "content": "Hello"}])["contents"]
