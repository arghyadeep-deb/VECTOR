# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""GuardrailsEngine — security-aware inference engine wrapper."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

from vectorcode.src.vc_core.events import EventBus, EventType
from vectorcode.src.vc_core.types import Message
from vectorcode.src.vc_engine._abc import InferenceEngine, StreamChunk
from vectorcode.src.vc_security._abc import BaseScanner
from vectorcode.src.vc_security.scanner import PIIScanner, SecretScanner
from vectorcode.src.vc_security.types import RedactionMode, ScanResult

class SecurityBlockError(Exception):
    """Raised when mode is BLOCK and security findings are detected."""

class GuardrailsEngine(InferenceEngine):
    """Wraps an existing ``InferenceEngine`` with security scanning.

    Not registered in ``EngineRegistry`` — instantiated dynamically to wrap
    any engine at runtime.

    Parameters
    ----------
    engine:
        The wrapped inference engine.
    scanners:
        List of scanners to run.  Defaults to ``SecretScanner`` + ``PIIScanner``.
    mode:
        Action taken on findings: WARN, REDACT, or BLOCK.
    scan_input:
        Whether to scan input messages.
    scan_output:
        Whether to scan output content.
    bus:
        Optional event bus for publishing security events.
    """

    def __init__(
        self,
        engine: InferenceEngine,
        *,
        scanners: Optional[List[BaseScanner]] = None,
        mode: RedactionMode = RedactionMode.WARN,
        scan_input: bool = True,
        scan_output: bool = True,
        max_stream_buffer_chars: int = 1_048_576,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._engine = engine
        self._scanners: List[BaseScanner] = (
            scanners
            if scanners is not None
            else [
                SecretScanner(),
                PIIScanner(),
            ]
        )
        self._mode = mode
        self._scan_input = scan_input
        self._scan_output = scan_output
        if max_stream_buffer_chars < 1:
            raise ValueError("max_stream_buffer_chars must be positive")
        self._max_stream_buffer_chars = max_stream_buffer_chars
        self._bus = bus

    # -- properties ----------------------------------------------------------

    @property
    def engine_id(self) -> str:  # type: ignore[override]
        """Delegate to the wrapped engine."""
        return self._engine.engine_id

    # -- scanning helpers ----------------------------------------------------

    def _scan_text(self, text: str) -> ScanResult:
        """Run all scanners on *text* and merge findings."""
        merged = ScanResult()
        for scanner in self._scanners:
            result = scanner.scan(text)
            merged.findings.extend(result.findings)
        return merged

    def _redact_text(self, text: str) -> str:
        """Run all scanners' redact() on *text*."""
        result = text
        for scanner in self._scanners:
            result = scanner.redact(result)
        return result

    def _handle_findings(
        self,
        text: str,
        result: ScanResult,
        direction: str,
    ) -> str:
        """Apply the configured mode to findings.

        Parameters
        ----------
        text:
            The original text.
        result:
            Scan result containing findings.
        direction:
            ``"input"`` or ``"output"`` — used in event data.

        Returns
        -------
        str
            Possibly modified text (unchanged for WARN, redacted for REDACT).

        Raises
        ------
        SecurityBlockError
            If mode is BLOCK.
        """
        finding_dicts = [
            {
                "pattern": f.pattern_name,
                "threat": f.threat_level.value,
                "description": f.description,
            }
            for f in result.findings
        ]

        if self._mode == RedactionMode.WARN:
            if self._bus:
                self._bus.publish(
                    EventType.SECURITY_ALERT,
                    {
                        "direction": direction,
                        "findings": finding_dicts,
                        "mode": "warn",
                    },
                )
            return text

        if self._mode == RedactionMode.REDACT:
            if self._bus:
                self._bus.publish(
                    EventType.SECURITY_ALERT,
                    {
                        "direction": direction,
                        "findings": finding_dicts,
                        "mode": "redact",
                    },
                )
            return self._redact_text(text)

        # BLOCK mode
        if self._bus:
            self._bus.publish(
                EventType.SECURITY_BLOCK,
                {
                    "direction": direction,
                    "findings": finding_dicts,
                    "mode": "block",
                },
            )
        raise SecurityBlockError(
            f"Security scan blocked {direction}: "
            f"{len(result.findings)} finding(s) detected"
        )

    # -- InferenceEngine interface -------------------------------------------

    def _process_input_messages(
        self, messages: Sequence[Message]
    ) -> Sequence[Message]:
        """Scan input before any wrapped-engine call."""
        if not self._scan_input:
            return messages
        processed = list(messages)
        for i, msg in enumerate(processed):
            if not msg.content:
                continue
            result = self._scan_text(msg.content)
            if not result.clean:
                processed[i] = Message(
                    role=msg.role,
                    content=self._handle_findings(msg.content, result, "input"),
                    name=msg.name,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    metadata=msg.metadata,
                )
        return processed

    def _check_stream_buffer_size(self, size: int) -> None:
        if size > self._max_stream_buffer_chars:
            raise SecurityBlockError(
                "Security scan blocked output: stream buffer limit exceeded"
            )

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Scan input, call wrapped engine, scan output."""
        messages = self._process_input_messages(messages)

        # Call wrapped engine
        response = self._engine.generate(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # Scan output
        if self._scan_output:
            content = response.get("content", "")
            if content:
                result = self._scan_text(content)
                if not result.clean:
                    response["content"] = self._handle_findings(
                        content, result, "output"
                    )

        return response

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Enforce output scanning before release in REDACT/BLOCK modes."""
        messages = self._process_input_messages(messages)
        accumulated: list[str] = []
        buffered_size = 0
        enforce_before_release = self._scan_output and self._mode in {
            RedactionMode.REDACT,
            RedactionMode.BLOCK,
        }
        async for token in self._engine.stream(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            accumulated.append(token)
            buffered_size += len(token)
            if enforce_before_release:
                self._check_stream_buffer_size(buffered_size)
            else:
                yield token

        if self._scan_output:
            full_output = "".join(accumulated)
            if full_output:
                result = self._scan_text(full_output)
                if not result.clean:
                    processed = self._handle_findings(full_output, result, "output")
                    if enforce_before_release:
                        yield processed
                elif enforce_before_release:
                    for token in accumulated:
                        yield token

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator["StreamChunk"]:
        """Enforce output scanning before releasing rich stream chunks."""
        messages = self._process_input_messages(messages)
        accumulated: list[str] = []
        chunks: list[StreamChunk] = []
        buffered_size = 0
        enforce_before_release = self._scan_output and self._mode in {
            RedactionMode.REDACT,
            RedactionMode.BLOCK,
        }
        async for chunk in self._engine.stream_full(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            chunks.append(chunk)
            if chunk.content:
                accumulated.append(chunk.content)
                buffered_size += len(chunk.content)
                if enforce_before_release:
                    self._check_stream_buffer_size(buffered_size)
            if not enforce_before_release:
                yield chunk

        if self._scan_output:
            full_output = "".join(accumulated)
            if full_output:
                result = self._scan_text(full_output)
                if not result.clean:
                    processed = self._handle_findings(full_output, result, "output")
                    if enforce_before_release:
                        content_replaced = False
                        for chunk in chunks:
                            if chunk.content and not content_replaced:
                                yield replace(chunk, content=processed)
                                content_replaced = True
                            elif chunk.content:
                                yield replace(chunk, content=None)
                            else:
                                yield chunk
                elif enforce_before_release:
                    for chunk in chunks:
                        yield chunk
            elif enforce_before_release:
                for chunk in chunks:
                    yield chunk

    def list_models(self) -> List[str]:
        """Delegate to wrapped engine."""
        return self._engine.list_models()

    def health(self) -> bool:
        """Delegate to wrapped engine."""
        return self._engine.health()

__all__ = ["GuardrailsEngine", "SecurityBlockError"]
