"""ECC-inspired local skill/hook inventory without installing external hooks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["SkillInventoryItem", "audit_skill_inventory", "audit_hook_configs"]


@dataclass(frozen=True)
class SkillInventoryItem:
    path: str
    name: str
    has_skill_md: bool
    status: str


def audit_skill_inventory(root: str | Path) -> list[SkillInventoryItem]:
    base = Path(root)
    if not base.exists():
        return []
    items: list[SkillInventoryItem] = []
    for child in sorted(p for p in base.rglob("*") if p.is_dir()):
        skill = child / "SKILL.md"
        if skill.exists():
            items.append(SkillInventoryItem(str(child), child.name, True, "present"))
    return items


def audit_hook_configs(paths: list[str | Path]) -> list[dict]:
    findings: list[dict] = []
    for path_like in paths:
        path = Path(path_like).expanduser()
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        if any(token in lowered for token in ("curl ", "wget ", "invoke-webrequest", "powershell -enc", "rm -rf")):
            findings.append({"path": str(path), "status": "review", "reason": "hook contains shell/network mutation pattern"})
    return findings
