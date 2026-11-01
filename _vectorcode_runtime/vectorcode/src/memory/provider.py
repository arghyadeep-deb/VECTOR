"""MemoryProvider ABC + VectorBuiltinMemoryProvider — ported from reference memory_provider.py.

MemoryProvider: abstract base class for all pluggable memory backends.
VectorBuiltinMemoryProvider: always-on provider that reads/writes ~/.vector/memory.md.
"""

from __future__ import annotations

import re
import sys
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


try:
    from core.config import CONFIG  # noqa: F401
except ImportError:
    CONFIG = {}

from loguru import logger


# ── Abstract base class ───────────────────────────────────────────────────────


class MemoryProvider(ABC):
    """Abstract base class for pluggable memory providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider (e.g. 'builtin', 'mem0')."""

    # -- Core lifecycle (implement these) ------------------------------------

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and ready.

        Should not make network calls — only check config and installed deps.
        """

    @abstractmethod
    def initialize(self, session_id: str, **kwargs) -> None:
        """Initialize for a session.

        kwargs always include:
          - vector_home (str): The active VECTOR_HOME directory path.
          - platform (str): 'cli', 'telegram', 'cron', etc.
        """

    def system_prompt_block(self) -> str:
        """Return static text to include in the system prompt. Empty string to skip."""
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant context for the upcoming turn.

        Return formatted text to inject as context, or empty string if nothing relevant.
        """
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Queue a background recall for the NEXT turn (default no-op)."""

    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """Persist a completed turn to the backend."""

    @abstractmethod
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas this provider exposes (OpenAI function calling format).

        Return empty list if this provider has no tools.
        """

    def handle_tool_call(
        self, tool_name: str, args: Dict[str, Any], **kwargs
    ) -> str:
        """Handle a tool call for one of this provider's tools. Returns JSON string."""
        raise NotImplementedError(
            f"Provider {self.name} does not handle tool {tool_name}"
        )

    def shutdown(self) -> None:
        """Clean shutdown — flush queues, close connections."""

    # -- Optional hooks (override to opt in) ---------------------------------

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        """Called at the start of each turn."""

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Called when a session ends."""

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Called before context compression. Return text to include in summary prompt."""
        return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when the built-in memory tool writes an entry."""

    def on_delegation(
        self, task: str, result: str, *, child_session_id: str = "", **kwargs
    ) -> None:
        """Called on the parent agent when a subagent completes."""


# ── Extraction patterns (shared with session_memory.py) ──────────────────────

_SECTION_PATTERNS: Dict[str, List[str]] = {
    "Build Commands": [
        r"(?:build|test|lint|run)[\s:]+`([^`]+)`",
        r"(?:command|cmd)[\s:]+`([^`]+)`",
        r"`((?:npm|pnpm|yarn|cargo|go|make|python|pytest)\s[^`]+)`",
    ],
    "Known Issues": [
        r"(?:bug|issue|problem|broken|skipped|flaky)[\s:]+(.{10,80})",
        r"TODO[\s:]+(.{10,80})",
        r"(?:NOTE|FIXME)[\s:]+(.{10,80})",
    ],
    "Architecture Notes": [
        r"(?:architecture|design|pattern|located|lives in|stored in)[\s:]+(.{10,120})",
        r"`([^`]+)`\s+(?:is|handles|manages|contains)\s+(.{10,80})",
    ],
}


def _extract_learnings(messages: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Scan conversation messages for patterns worth remembering."""
    sections: Dict[str, List[str]] = {k: [] for k in _SECTION_PATTERNS}
    full_text = " ".join(
        (m.get("content") or "")
        for m in messages
        if m.get("role") in ("user", "assistant")
    )
    for section, patterns in _SECTION_PATTERNS.items():
        for pat in patterns:
            for match in re.finditer(pat, full_text, re.IGNORECASE):
                candidate = " ".join(g for g in match.groups() if g).strip()
                if candidate and candidate not in sections[section]:
                    sections[section].append(candidate[:120])
    return sections


# ── VectorBuiltinMemoryProvider ───────────────────────────────────────────────


class VectorBuiltinMemoryProvider(MemoryProvider):
    """Always-on provider that reads/writes ~/.vector/memory.md.

    Mirrors the logic in vectorcode/context/session_memory.py but wrapped
    inside the MemoryProvider interface so MemoryManager can orchestrate it.
    """

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "builtin"

    def is_available(self) -> bool:
        """Always available — no external deps."""
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        """Resolve the memory path from kwargs or fall back to ~/.vector/memory.md."""
        from vector_constants import get_vector_home

        vector_home_str = kwargs.get("vector_home", "")
        if vector_home_str:
            self._memory_path = Path(vector_home_str) / "memory.md"
        else:
            self._memory_path = get_vector_home() / "memory.md"
        self._session_id = session_id
        logger.debug(
            f"[VECTOR][memory.provider] builtin initialized, path={self._memory_path}"
        )

    def _memory_path_safe(self) -> Path:
        """Return memory path, initializing with defaults if not yet set."""
        if not hasattr(self, "_memory_path"):
            from vector_constants import get_vector_home

            self._memory_path = get_vector_home() / "memory.md"
        return self._memory_path

    def system_prompt_block(self) -> str:
        """Return contents of memory.md as a system-prompt context block."""
        path = self._memory_path_safe()
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return ""
            return (
                "## Persistent Memory (from previous sessions)\n\n"
                f"{content}\n"
            )
        except Exception as e:
            logger.warning(f"[VECTOR][memory.provider] system_prompt_block failed: {e}")
            return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return lines from memory.md that match any keyword in query."""
        path = self._memory_path_safe()
        if not path.exists():
            return ""
        try:
            keywords = [kw.lower() for kw in re.split(r"\W+", query) if len(kw) > 2]
            if not keywords:
                return ""
            matching: List[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line_lower = line.lower()
                if any(kw in line_lower for kw in keywords):
                    matching.append(line)
            if not matching:
                return ""
            return "\n".join(matching)
        except Exception as e:
            logger.debug(f"[VECTOR][memory.provider] prefetch failed: {e}")
            return ""

    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """Extract learnings from a completed turn and merge into memory.md."""
        try:
            messages = [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            ]
            new_learnings = _extract_learnings(messages)
            existing = self._read_memory()
            changed = False
            for section, items in new_learnings.items():
                for item in items:
                    if item not in existing.get(section, []):
                        existing.setdefault(section, []).append(item)
                        changed = True
            if changed:
                self._write_memory(existing)
        except Exception as e:
            logger.warning(f"[VECTOR][memory.provider] sync_turn failed: {e}")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """No extra tool schemas — the builtin provider is context-only."""
        return []

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Extract learnings from the full session and persist to memory.md."""
        try:
            new_learnings = _extract_learnings(messages)
            existing = self._read_memory()
            for section, items in new_learnings.items():
                for item in items:
                    if item not in existing.get(section, []):
                        existing.setdefault(section, []).append(item)
            self._write_memory(existing)
        except Exception as e:
            logger.warning(f"[VECTOR][memory.provider] on_session_end failed: {e}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _read_memory(self) -> Dict[str, List[str]]:
        """Parse memory.md into {section: [items]} dict."""
        path = self._memory_path_safe()
        if not path.exists():
            return {k: [] for k in _SECTION_PATTERNS}
        content = path.read_text(encoding="utf-8")
        sections: Dict[str, List[str]] = {}
        current: Optional[str] = None
        for line in content.splitlines():
            if line.startswith("## "):
                current = line[3:].strip()
                sections.setdefault(current, [])
            elif current and line.startswith("- "):
                sections[current].append(line[2:].strip())
        return sections

    def _write_memory(self, sections: Dict[str, List[str]]) -> None:
        """Write {section: [items]} to memory.md."""
        path = self._memory_path_safe()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = ["# Vector Code Memory\n"]
            for section, items in sections.items():
                if items:
                    lines.append(f"## {section}")
                    for item in items[:20]:
                        lines.append(f"- {item}")
                    lines.append("")
            payload = "\n".join(lines)
            fd, temp_name = tempfile.mkstemp(
                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as temp_file:
                    temp_file.write(payload)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                os.replace(temp_name, path)
            except BaseException:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                raise
            total = sum(len(v) for v in sections.values())
            logger.info(
                f"[VECTOR][memory.provider] wrote memory.md ({total} entries)"
            )
        except Exception as e:
            logger.warning(f"[VECTOR][memory.provider] _write_memory failed: {e}")


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # ABC cannot be instantiated directly
    try:
        MemoryProvider()  # type: ignore[abstract]
        assert False, "should have raised TypeError"
    except TypeError as _sve:
        logger.debug("[VECTOR][memory.provider] suppressed TypeError: %s", _sve)

    with tempfile.TemporaryDirectory() as tmp:
        provider = VectorBuiltinMemoryProvider()
        assert provider.name == "builtin"
        assert provider.is_available() is True

        provider.initialize(
            session_id="test-123", vector_home=tmp
        )

        # system_prompt_block on empty memory
        block = provider.system_prompt_block()
        assert block == "", f"expected empty, got: {block!r}"

        # sync_turn should create memory.md
        provider.sync_turn(
            "run the tests with `pytest tests/ -v`",
            "Build command: `npm run build`",
        )
        mem_path = Path(tmp) / "memory.md"
        assert mem_path.exists(), "memory.md not created"

        content = mem_path.read_text(encoding="utf-8")
        assert "# Vector Code Memory" in content

        # prefetch should find relevant lines
        result = provider.prefetch("pytest build tests")
        assert result != "", f"prefetch returned nothing, memory content:\n{content}"

        # system_prompt_block should now have content
        block2 = provider.system_prompt_block()
        assert "Persistent Memory" in block2

        # tool schemas — builtin has none
        assert provider.get_tool_schemas() == []

    print("memory/provider.py OK")

