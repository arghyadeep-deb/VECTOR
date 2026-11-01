"""SkillOverlay -- sidecar storage for optimization output (Plan 2A).

Optimization results from DSPy/GEPA are written to
``~/.vector/learning/skills/<skill-name>/optimized.toml``.  This module
provides a small loader and writer for that overlay format.

The overlay is a strict TOML file with a single ``[optimized]`` section
followed by zero or more ``[[optimized.few_shot]]`` array tables.

Example:

    [optimized]
    skill_name = "research-and-summarize"
    optimizer = "dspy"
    optimized_at = "2026-04-08T14:30:00Z"
    trace_count = 47
    description = "Search the web for a topic and produce a structured summary"

    [[optimized.few_shot]]
    input = "transformer attention mechanisms"
    output = "## Recent Advances ..."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

@dataclass(slots=True)
class SkillOverlay:
    """A single optimization overlay for one skill."""

    skill_name: str
    optimizer: str  # "dspy" or "gepa"
    optimized_at: str  # ISO 8601 UTC timestamp
    trace_count: int
    description: str
    few_shot: List[Dict[str, str]] = field(default_factory=list)

class SkillOverlayLoader:
    """Read overlay files from a sidecar directory tree.

    Layout: ``<root>/<skill-name>/optimized.toml``
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root).expanduser()

    def load(self, skill_name: str) -> Optional[SkillOverlay]:
        """Load the overlay for *skill_name*.

        Returns ``None`` if the overlay file is missing or malformed.
        Never raises -- bad overlay files should not break skill loading.
        """
        path = self._root / skill_name / "optimized.toml"
        if not path.exists():
            return None
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except Exception as exc:
            logger.warning(
                "Failed to load overlay for skill '{}' at {}: {}",
                skill_name,
                path,
                exc,
            )
            return None

        opt = data.get("optimized", {})
        if not isinstance(opt, dict) or not opt:
            logger.warning(
                "Overlay file {} missing [optimized] section",
                path,
            )
            return None

        few_shot_raw = opt.get("few_shot", []) or []
        few_shot: List[Dict[str, str]] = []
        if isinstance(few_shot_raw, list):
            for item in few_shot_raw:
                if isinstance(item, dict):
                    few_shot.append(
                        {
                            "input": str(item.get("input", "")),
                            "output": str(item.get("output", "")),
                        }
                    )

        return SkillOverlay(
            skill_name=str(opt.get("skill_name", skill_name)),
            optimizer=str(opt.get("optimizer", "")),
            optimized_at=str(opt.get("optimized_at", "")),
            trace_count=int(opt.get("trace_count", 0)),
            description=str(opt.get("description", "")),
            few_shot=few_shot,
        )

def write_overlay(overlay: SkillOverlay, root: Path) -> Path:
    """Write *overlay* to ``<root>/<skill-name>/optimized.toml``.

    Creates the directory structure if needed.  Returns the path written.

    ``overlay.skill_name`` is not fully trusted: its one real caller
    (``learning/agents/skill_optimizer.py``) derives it from trace-step
    tool-call metadata (``_extract_skill_names()``'s ``metadata.get("skill")``),
    not an internally-generated identifier. Without confinement, a
    ``skill_name`` containing ``..`` or an absolute path could write
    ``optimized.toml`` outside the intended overlay directory -- the same
    unconfined-identifier-into-path shape fixed elsewhere this audit cycle
    (``importer.py``, ``learning/distillation/{pending_queue,
    execute/appliers/agent,diagnose/tools,orchestrator}.py``).
    """
    root = Path(root).expanduser().resolve()
    skill_dir = (root / overlay.skill_name).resolve()
    if skill_dir.parent != root:
        raise ValueError(
            f"Refusing to write overlay for unsafe skill_name {overlay.skill_name!r}: "
            f"must resolve to a direct child of {root}"
        )
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "optimized.toml"

    lines: List[str] = ["[optimized]"]
    lines.append(f'skill_name = "{_escape(overlay.skill_name)}"')
    lines.append(f'optimizer = "{_escape(overlay.optimizer)}"')
    lines.append(f'optimized_at = "{_escape(overlay.optimized_at)}"')
    lines.append(f"trace_count = {int(overlay.trace_count)}")
    lines.append(f'description = "{_escape(overlay.description)}"')
    lines.append("")

    for example in overlay.few_shot:
        lines.append("[[optimized.few_shot]]")
        lines.append(f'input = "{_escape(example.get("input", ""))}"')
        lines.append(f'output = "{_escape(example.get("output", ""))}"')
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path

def _escape(text: str) -> str:
    """TOML basic-string escaping.

    Covers every control character the TOML spec forbids unescaped inside a
    basic string (U+0000-U+0008, U+000B-U+001F, U+007F), not just the common
    \\n/\\r/\\t cases. An unescaped control character (e.g. a stray \\x0b in
    DSPy/GEPA-generated optimizer output) previously produced a syntactically
    invalid TOML file that silently failed to load back via
    SkillOverlayLoader.load() -- the optimization result was written once
    and then permanently unreadable, with only a logged warning as the trace.
    """
    text = str(text)
    out: list[str] = []
    simple = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}
    for ch in text:
        if ch in simple:
            out.append(simple[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)

__all__ = ["SkillOverlay", "SkillOverlayLoader", "write_overlay"]
