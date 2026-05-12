"""VECTOR.md reader — loads the project config file into session context.

VECTOR.md lives at the project root (like CLAUDE.md).
It's always embedded in the context and survives compaction.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from loguru import logger

_FILENAME = "VECTOR.md"

_DEFAULT_TEMPLATE = """\
# VECTOR.md — Project Configuration

## Project
Name: {name}

## Architecture
(describe your directory layout here)

## Conventions
(coding standards, naming rules, etc.)

## Build & Test
- Build: (your build command)
- Test:  (your test command)
- Lint:  (your lint command)

## Review Checklist
(things to check before committing)
"""


class VectorMD:
    """
    Reads VECTOR.md from a project directory.
    The content is injected at the top of every LLM context.
    """

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)
        self._content: str | None = None

    @property
    def path(self) -> Path:
        return self.project_dir / _FILENAME

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> str:
        """Return VECTOR.md content. Returns empty string if file is absent."""
        if not self.path.exists():
            logger.debug(f"[VECTOR][vectormd] no VECTOR.md found at {self.path}")
            return ""
        try:
            content = self.path.read_text(encoding="utf-8").strip()
            self._content = content
            logger.info(f"[VECTOR][vectormd] loaded {len(content)} chars from {self.path}")
            return content
        except Exception as e:
            logger.warning(f"[VECTOR][vectormd] failed to load {self.path}: {e}")
            return ""

    def as_system_block(self) -> str:
        """Return VECTOR.md wrapped as a system-level context block."""
        content = self.load()
        if not content:
            return ""
        return f"<project_config>\n{content}\n</project_config>"

    def create_default(self, project_name: str = "") -> None:
        """Write a starter VECTOR.md to the project root if one doesn't exist."""
        if self.path.exists():
            return
        name = project_name or self.project_dir.name
        self.path.write_text(
            _DEFAULT_TEMPLATE.format(name=name), encoding="utf-8"
        )
        logger.info(f"[VECTOR][vectormd] created starter VECTOR.md at {self.path}")

    def inject_into_messages(self, messages: list[dict]) -> list[dict]:
        """
        Prepend VECTOR.md content to the system message (or insert as first message).
        The project config is pinned and never compacted away.
        """
        content = self.as_system_block()
        if not content:
            return messages

        result = list(messages)
        for i, msg in enumerate(result):
            if msg["role"] == "system":
                if "<project_config>" not in msg["content"]:
                    result[i] = {**msg, "content": content + "\n\n" + msg["content"]}
                return result

        result.insert(0, {"role": "system", "content": content})
        return result


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        vmd = VectorMD(tmp)
        assert not vmd.exists()
        assert vmd.load() == ""
        vmd.create_default("my-api")
        assert vmd.exists()
        content = vmd.load()
        assert "my-api" in content
        block = vmd.as_system_block()
        assert block.startswith("<project_config>")
        msgs = vmd.inject_into_messages([{"role": "user", "content": "hello"}])
        assert msgs[0]["role"] == "system"
        assert "<project_config>" in msgs[0]["content"]
    print("vectormd.py OK")
