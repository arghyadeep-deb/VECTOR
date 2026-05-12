"""Ollama provider adapter."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.providers.base import (
    BaseProvider, CompletionResult, ModelCapabilities, Message, TokenUsage
)


class OllamaProvider(BaseProvider):
    """Ollama local model provider — OpenAI-compat REST at localhost:11434."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        try:
            import ollama as _ollama

            kwargs: dict = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools

            if stream:
                chunks = []
                print(f"\033[2m[{model}]\033[0m ", end="", flush=True)
                for chunk in _ollama.chat(stream=True, **kwargs):
                    token = chunk["message"]["content"]
                    print(token, end="", flush=True)
                    chunks.append(token)
                print()
                content = "".join(chunks)
            else:
                resp = _ollama.chat(**kwargs)
                content = resp["message"]["content"]

            usage = TokenUsage()
            return self._make_result(content, model, usage)

        except Exception as e:
            logger.error(f"[VECTOR][ollama] completion failed for {model}: {e}")
            err = f"[Ollama error: {e}. Is Ollama running? Try: ollama serve]"
            return self._make_result(err, model, TokenUsage())

    def probe_capabilities(self, model: str) -> ModelCapabilities:
        try:
            import ollama as _ollama
            info = _ollama.show(model)
            params = info.get("parameters", "")
            ctx = 4096
            for line in str(params).splitlines():
                if "num_ctx" in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            ctx = int(parts[-1])
                        except ValueError:
                            pass
            return ModelCapabilities(
                context_window=ctx,
                tool_use=True,
                vision=False,
                structured_output=False,
            )
        except Exception as e:
            logger.debug(f"[VECTOR][ollama] probe failed for {model}: {e}")
            return ModelCapabilities()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = OllamaProvider()
    caps = p.probe_capabilities("vector-focus")
    assert isinstance(caps.context_window, int)
    print(f"ollama.py OK — context_window={caps.context_window}")
