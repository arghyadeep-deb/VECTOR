"""Simple multi-engine wrapper used when local and cloud engines coexist."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from vectorcode.src.vc_core.types import Message


class MultiEngine:
    engine_id = "multi"

    def __init__(self, engines: list[tuple[str, Any]]) -> None:
        self._engines = engines
        self.is_cloud = any(getattr(engine, "is_cloud", False) for _, engine in engines)

    def _select(self, model: str | None = None) -> tuple[str, Any]:
        if model and ":" in model:
            prefix, rest = model.split(":", 1)
            for name, engine in self._engines:
                if name == prefix:
                    return rest, engine
        for name, engine in self._engines:
            try:
                if engine.health():
                    return model or "", engine
            except Exception:
                continue
        return model or "", self._engines[0][1]

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> dict[str, Any]:
        selected_model, engine = self._select(model)
        return engine.generate(
            messages,
            model=selected_model or model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        selected_model, engine = self._select(model)
        async for token in engine.stream(
            messages,
            model=selected_model or model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield token

    def list_models(self) -> list[str]:
        models: list[str] = []
        for name, engine in self._engines:
            try:
                models.extend(f"{name}:{model}" for model in engine.list_models())
            except Exception:
                continue
        return models

    def health(self) -> bool:
        for _, engine in self._engines:
            try:
                if engine.health():
                    return True
            except Exception:
                continue
        return False

    def close(self) -> None:
        for _, engine in self._engines:
            close = getattr(engine, "close", None)
            if callable(close):
                close()


__all__ = ["MultiEngine"]

