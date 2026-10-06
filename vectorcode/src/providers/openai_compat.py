"""Generic OpenAI-compatible provider adapter.

Covers: OpenAI, Groq, Mistral, Together AI, OpenRouter, LM Studio,
        llama.cpp server, any server implementing the OpenAI REST API.
"""

import sys
import os
import json

from loguru import logger
from providers.base import (
    BaseProvider, CompletionResult, ModelCapabilities, Message,
    TokenUsage, ToolCall
)

# Known capabilities per cloud provider family
_CAPS: dict[str, ModelCapabilities] = {
    "gpt-5":         ModelCapabilities(context_window=128_000, tool_use=True,  vision=True,  structured_output=True),
    "gpt-4o":        ModelCapabilities(context_window=128_000, tool_use=True,  vision=True,  structured_output=True),
    "gpt-4o-mini":   ModelCapabilities(context_window=128_000, tool_use=True,  vision=True,  structured_output=True),
    "o3":            ModelCapabilities(context_window=200_000, tool_use=True,  vision=False, structured_output=True),
    "o4-mini":       ModelCapabilities(context_window=200_000, tool_use=True,  vision=False, structured_output=True),
    "llama-4-scout": ModelCapabilities(context_window=128_000, tool_use=True,  vision=False, structured_output=False),
    "llama-3.3-70b": ModelCapabilities(context_window=128_000, tool_use=True,  vision=False, structured_output=False),
    "mistral-large": ModelCapabilities(context_window=128_000, tool_use=True,  vision=False, structured_output=True),
    "codestral":     ModelCapabilities(context_window=32_000,  tool_use=False, vision=False, structured_output=False),
    "command-r-plus":ModelCapabilities(context_window=128_000, tool_use=True,  vision=False, structured_output=False),
    "grok-3":        ModelCapabilities(context_window=131_072, tool_use=True,  vision=False, structured_output=False),
}


class OpenAICompatProvider(BaseProvider):
    """
    Provider for any OpenAI-compatible REST endpoint.
    Pass base_url="https://api.openai.com/v1" for OpenAI proper,
    or base_url="http://localhost:8080/v1" for a local server.
    """

    provider_name = "openai_compat"

    def __init__(self, base_url: str, api_key: str = "", api_key_env: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key or (os.environ.get(api_key_env, "") if api_key_env else "")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        try:
            import httpx

            payload: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": stream,
            }
            if tools:
                payload["tools"] = tools

            if stream:
                content_parts: list[str] = []
                sys.stdout.write(f"\033[2m[{model}]\033[0m ")
                sys.stdout.flush()
                with httpx.Client(timeout=120.0) as client:
                    with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    ) as resp:
                        resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line or line == "data: [DONE]":
                                continue
                            if line.startswith("data: "):
                                line = line[6:]
                            try:
                                chunk = json.loads(line)
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta:
                                    sys.stdout.write(delta)
                                    sys.stdout.flush()
                                    content_parts.append(delta)
                            except Exception as _sve:
                                logger.debug(
                                    "[VECTOR][providers.openai_compat] invalid stream chunk: {}",
                                    _sve,
                                )
                sys.stdout.write("\n")
                content = "".join(content_parts)
                usage = TokenUsage()
            else:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json={**payload, "stream": False},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                content = data["choices"][0]["message"]["content"] or ""
                u = data.get("usage", {})
                usage = TokenUsage(
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    total_tokens=u.get("total_tokens", 0),
                )

            return self._make_result(content, model, usage)

        except Exception as e:
            logger.opt(exception=True).error(
                "[VECTOR][openai_compat] completion failed for {}: {}", model, e
            )
            raise

    def probe_capabilities(self, model: str) -> ModelCapabilities:
        for key, caps in _CAPS.items():
            if key in model:
                return caps
        return ModelCapabilities(context_window=4096, tool_use=False)


# ── Named subclasses for each cloud provider ──────────────────────────────────

class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider using the anthropic SDK."""

    provider_name = "anthropic"

    _CAPS: dict[str, ModelCapabilities] = {
        "claude-opus-4":    ModelCapabilities(200_000, True, True, True),
        "claude-sonnet-4-6":ModelCapabilities(200_000, True, True, True),
        "claude-haiku-4-5": ModelCapabilities(200_000, True, True, True),
    }

    def __init__(self, api_key: str = "", api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self._api_key = api_key or os.environ.get(api_key_env, "")

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            sys_msgs = [m for m in messages if m["role"] == "system"]
            chat_msgs = [m for m in messages if m["role"] != "system"]
            system_text = sys_msgs[0]["content"] if sys_msgs else None

            kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": chat_msgs}
            if system_text:
                kwargs["system"] = system_text
            if tools:
                kwargs["tools"] = tools

            if stream:
                sys.stdout.write(f"\033[2m[{model}]\033[0m ")
                sys.stdout.flush()
                chunks: list[str] = []
                with client.messages.stream(**kwargs) as s:
                    for text in s.text_stream:
                        sys.stdout.write(text)
                        sys.stdout.flush()
                        chunks.append(text)
                sys.stdout.write("\n")
                content = "".join(chunks)
                usage = TokenUsage()
            else:
                resp = client.messages.create(**kwargs)
                content = resp.content[0].text if resp.content else ""
                usage = TokenUsage(
                    prompt_tokens=resp.usage.input_tokens,
                    completion_tokens=resp.usage.output_tokens,
                    total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
                )

            return self._make_result(content, model, usage)

        except Exception as e:
            logger.opt(exception=True).error(
                "[VECTOR][anthropic] completion failed for {}: {}", model, e
            )
            raise

    def probe_capabilities(self, model: str) -> ModelCapabilities:
        for key, caps in self._CAPS.items():
            if key in model:
                return caps
        return ModelCapabilities(context_window=200_000, tool_use=True, vision=True)


class GoogleProvider(BaseProvider):
    """Google Gemini provider using google-generativeai SDK."""

    provider_name = "google"

    def __init__(self, api_key: str = "", api_key_env: str = "GOOGLE_API_KEY") -> None:
        self._api_key = api_key or os.environ.get(api_key_env, "")

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        try:
            import google.generativeai as genai  # type: ignore
            if tools:
                raise NotImplementedError(
                    "GoogleProvider does not implement tool-call conversion"
                )
            genai.configure(api_key=self._api_key)
            gclient = genai.GenerativeModel(model)
            prompt = "\n\n".join(
                f"{message.get('role', 'user')}: {message.get('content', '')}"
                for message in messages
            )
            if stream:
                sys.stdout.write(f"\033[2m[{model}]\033[0m ")
                sys.stdout.flush()
                parts: list[str] = []
                for chunk in gclient.generate_content(prompt, stream=True):
                    t = chunk.text or ""
                    sys.stdout.write(t)
                    sys.stdout.flush()
                    parts.append(t)
                sys.stdout.write("\n")
                content = "".join(parts)
            else:
                resp = gclient.generate_content(prompt)
                content = resp.text or ""
            return self._make_result(content, model, TokenUsage())
        except Exception as e:
            logger.opt(exception=True).error(
                "[VECTOR][google] completion failed for {}: {}", model, e
            )
            raise

    def probe_capabilities(self, model: str) -> ModelCapabilities:
        if "2.5-pro" in model:
            return ModelCapabilities(1_000_000, True, True, True)
        return ModelCapabilities(1_000_000, True, True, False)


class GroqProvider(OpenAICompatProvider):
    provider_name = "groq"

    def __init__(self, api_key: str = "", api_key_env: str = "GROQ_API_KEY") -> None:
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key or os.environ.get(api_key_env, ""),
        )


class MistralProvider(OpenAICompatProvider):
    provider_name = "mistral"

    def __init__(self, api_key: str = "", api_key_env: str = "MISTRAL_API_KEY") -> None:
        super().__init__(
            base_url="https://api.mistral.ai/v1",
            api_key=api_key or os.environ.get(api_key_env, ""),
        )


class OpenAIProvider(OpenAICompatProvider):
    provider_name = "openai"

    def __init__(self, api_key: str = "", api_key_env: str = "OPENAI_API_KEY") -> None:
        super().__init__(
            base_url="https://api.openai.com/v1",
            api_key=api_key or os.environ.get(api_key_env, ""),
        )


class DeepSeekProvider(OpenAICompatProvider):
    provider_name = "deepseek"

    def __init__(self, api_key: str = "", api_key_env: str = "DEEPSEEK_API_KEY") -> None:
        super().__init__(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key or os.environ.get(api_key_env, ""),
        )


class OpenRouterProvider(OpenAICompatProvider):
    provider_name = "openrouter"

    def __init__(self, api_key: str = "", api_key_env: str = "OPENROUTER_API_KEY") -> None:
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ.get(api_key_env, ""),
        )


class LMStudioProvider(OpenAICompatProvider):
    """LM Studio local server (default port 1234)."""

    provider_name = "lmstudio"

    def __init__(self, base_url: str = "http://localhost:1234/v1") -> None:
        super().__init__(base_url=base_url, api_key="lm-studio")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = OpenAICompatProvider(base_url="http://localhost:11434/v1", api_key="none")
    caps = p.probe_capabilities("gpt-4o")
    assert caps.tool_use is True
    assert caps.context_window == 128_000
    print("openai_compat.py OK")


