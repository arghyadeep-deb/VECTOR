"""Idempotently add a DORMANT banner comment to core/ modules that duplicate a live mechanism.

Comment-only (compiled code is checked unchanged). Nothing is deleted or wired in: adding a
second live path beside the Governor / PermissionGateway / provider_client would bypass them.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# module -> live mechanism that already does this job
DORMANT = {
    "core/api/auth.py": "the API auth middleware (validates VECTOR_API_KEY) and core/api/routers/auth_jwt.py",
    "core/brain/router.py": "Governor routing (core/city/governor.py)",
    "core/brain/self_evolve.py": "core/city/evolution_engine.py",
    "core/city/point_system.py": "the HP system in core/city/agent_base.py",
    "core/city/task_router.py": "Governor routing (core/city/governor.py)",
    "core/inference/model_router.py": "core/inference/provider_client.py + model_pool",
    "core/inference/provider_registry.py": "core/inference/llm_providers.py (PROVIDERS) and model_catalog.yaml",
    "core/inference/district_llm.py": "vectorcode_llm / provider_client via AgentBase",
    "core/communications/hub.py": "the vectorcode channel gateway",
    "core/loop/planner.py": "core/runtime/plans.py (PlanStore/PlanRunner)",
}

MARK = "# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR."


def banner(reason: str) -> str:
    return (
        f"{MARK}\n"
        f"# Superseded by {reason}. Kept on purpose (personal-use build); do not add a second live path --\n"
        f"# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.\n"
    )


def apply(dry_run: bool = False) -> int:
    changed = 0
    for rel, reason in DORMANT.items():
        path = ROOT / rel
        if not path.exists():
            continue
        raw = path.read_bytes().decode("utf-8")
        if MARK in raw:
            continue
        crlf = "\r\n" in raw
        text = banner(reason)
        new = (text.replace("\n", "\r\n") if crlf else text) + raw
        try:
            same = compile(raw, rel, "exec").co_code == compile(new, rel, "exec").co_code
        except SyntaxError:
            same = False
        if not same:
            continue
        if not dry_run:
            path.write_bytes(new.encode("utf-8"))
        changed += 1
    return changed


if __name__ == "__main__":
    import sys

    print("banners added:", apply("--dry-run" in sys.argv))
