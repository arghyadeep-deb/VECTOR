"""Lightweight SPARC methodology coordinator."""

from __future__ import annotations

SPARC_STAGES = ("specification", "pseudocode", "architecture", "refinement", "completion")


def run_sparc_stage(stage: str, prompt: str = "") -> dict[str, str]:
    normalized = stage.lower().strip()
    if normalized not in SPARC_STAGES:
        raise ValueError(f"Unknown SPARC stage: {stage}")
    return {"stage": normalized, "prompt": prompt, "status": "ready"}


def run_sparc_full(prompt: str = "") -> dict[str, list[dict[str, str]]]:
    return {"stages": [run_sparc_stage(stage, prompt) for stage in SPARC_STAGES]}


def sparc_slash_command(args: str = "") -> dict[str, list[dict[str, str]]]:
    return run_sparc_full(args)


__all__ = ["SPARC_STAGES", "run_sparc_stage", "run_sparc_full", "sparc_slash_command"]

