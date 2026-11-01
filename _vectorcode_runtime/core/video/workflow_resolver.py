"""Resolve local media workflow JSON files without path traversal."""
from __future__ import annotations

import json
from pathlib import Path

__all__ = ["WorkflowResolutionError", "resolve_workflow"]


class WorkflowResolutionError(ValueError):
    pass


def resolve_workflow(source: str, service: str, roots: list[str | Path] | None = None) -> dict:
    if any(part in {source, service} for part in ("..", "", ".", "/", "\\")):
        raise WorkflowResolutionError("invalid workflow source/service")
    if Path(source).is_absolute() or Path(service).is_absolute():
        raise WorkflowResolutionError("absolute workflow paths are not allowed")
    if any(token in source + service for token in ("..", "/", "\\")):
        raise WorkflowResolutionError("workflow path traversal is not allowed")

    if roots is None:
        repo_root = Path(__file__).resolve().parents[2]
        roots = [repo_root / "data" / "video_workflows", repo_root / "core" / "video" / "workflows"]

    for root_like in roots:
        root = Path(root_like).resolve()
        candidate = (root / source / f"{service}.json").resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise WorkflowResolutionError("resolved workflow escaped allowed root")
        if candidate.exists() and candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"workflow not found: {source}/{service}.json")
