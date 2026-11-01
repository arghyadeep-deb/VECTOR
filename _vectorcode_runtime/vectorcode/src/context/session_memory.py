"""Session memory auto-generator — writes/updates .vector/memory.md.

Extracts learnings from conversation history and persists them between sessions.
Sections: Build Commands, Known Issues, Architecture Notes, Preferences.
"""

import sys
import re
import os
import tempfile

from loguru import logger
from config import VECTOR_DATA_DIR

_MEMORY_PATH = VECTOR_DATA_DIR / "memory.md"

_SECTION_PATTERNS = {
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


def _extract_learnings(messages: list[dict]) -> dict[str, list[str]]:
    """Scan conversation for patterns worth remembering."""
    sections: dict[str, list[str]] = {k: [] for k in _SECTION_PATTERNS}
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


def _read_memory() -> dict[str, list[str]]:
    if not _MEMORY_PATH.exists():
        return {k: [] for k in _SECTION_PATTERNS}
    content = _MEMORY_PATH.read_text(encoding="utf-8")
    sections: dict[str, list[str]] = {k: [] for k in _SECTION_PATTERNS}
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            if current not in sections:
                sections[current] = []
        elif current and line.startswith("- "):
            sections[current].append(line[2:].strip())
    return sections


def _write_memory(sections: dict[str, list[str]]) -> None:
    VECTOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Vector Code Memory\n"]
    for section, items in sections.items():
        if items:
            lines.append(f"## {section}")
            for item in items[:20]:
                lines.append(f"- {item}")
            lines.append("")
    payload = "\n".join(lines)
    fd, temp_name = tempfile.mkstemp(
        dir=_MEMORY_PATH.parent,
        prefix=f".{_MEMORY_PATH.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, _MEMORY_PATH)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    logger.info(f"[VECTOR][memory] wrote memory.md ({sum(len(v) for v in sections.values())} entries)")


def update_session_memory(messages: list[dict]) -> None:
    """Extract learnings from messages and merge into .vector/memory.md."""
    try:
        existing = _read_memory()
        new_learnings = _extract_learnings(messages)
        for section, items in new_learnings.items():
            for item in items:
                if item not in existing[section]:
                    existing[section].append(item)
        _write_memory(existing)
    except Exception as e:
        logger.warning(f"[VECTOR][memory] update failed: {e}")


def read_memory_md() -> str:
    """Return the contents of .vector/memory.md as a string."""
    if not _MEMORY_PATH.exists():
        return "(no memory yet)"
    return _MEMORY_PATH.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    msgs = [
        {"role": "user",      "content": "run the tests with: `pytest tests/ -v`"},
        {"role": "assistant", "content": "Build command: `npm run build`"},
        {"role": "assistant", "content": "NOTE: the auth module is broken pending JWT fix"},
        {"role": "assistant", "content": "The database pool is located in src/db/connection.ts"},
    ]
    update_session_memory(msgs)
    content = read_memory_md()
    assert "# Vector Code Memory" in content
    print(f"session_memory.py OK\n{content[:300]}")


