"""Skill security -- capability validation and trust tiers."""

from __future__ import annotations

from enum import Enum
from typing import List, Set

from vectorcode.src.skills.types import SkillManifest

DANGEROUS_CAPABILITIES: frozenset[str] = frozenset(
    {"shell:execute", "network:listen", "filesystem:write"}
)

class TrustTier(str, Enum):
    """Trust tier for a skill, ordered from most to least trusted."""

    BUNDLED = "bundled"
    INDEXED = "indexed"
    WORKSPACE = "workspace"
    UNREVIEWED = "unreviewed"

def classify_trust_tier(
    *,
    is_bundled: bool = False,
    is_workspace: bool = False,
    has_signature: bool = False,
    in_index: bool = False,
) -> TrustTier:
    """Return the trust tier for a skill based on its provenance.

    Priority (highest to lowest): bundled > workspace > indexed > unreviewed.
    """
    if is_bundled:
        return TrustTier.BUNDLED
    if is_workspace:
        return TrustTier.WORKSPACE
    if has_signature and in_index:
        return TrustTier.INDEXED
    return TrustTier.UNREVIEWED

def validate_capabilities(manifest: SkillManifest, allowed: Set[str]) -> List[str]:
    """Return a list of capabilities required by *manifest* that are not in *allowed*.

    An empty list means the manifest is fully authorized.

    FLAGGED (owner decision, not fixed): confirmed via repo-wide grep that
    neither this function nor has_dangerous_capabilities() below has any
    caller anywhere in vectorcode/src/skills/ -- required_capabilities is
    parsed (parser.py), stored (types.py), even resolved transitively
    across the dependency graph (dependency.py) and exposed to tools
    (tool_adapter.py), but SkillExecutor.run() (executor.py) invokes every
    step with zero capability check. This capability/trust-tier gate is
    fully data-plumbed but entirely unenforced at the one place that
    actually runs skill code. Wiring it in is an owner decision (where:
    executor.run(), or earlier at manager.py load/registration time?
    on violation: raise, skip the step, or require approval?), not a safe
    narrow fix.
    """
    return [cap for cap in manifest.required_capabilities if cap not in allowed]

def has_dangerous_capabilities(manifest: SkillManifest) -> List[str]:
    """Return the subset of *manifest*'s required capabilities that are dangerous.

    See the FLAGGED note on validate_capabilities() above -- same unwired gap.
    """
    return [
        cap for cap in manifest.required_capabilities if cap in DANGEROUS_CAPABILITIES
    ]

__all__ = [
    "DANGEROUS_CAPABILITIES",
    "TrustTier",
    "classify_trust_tier",
    "validate_capabilities",
    "has_dangerous_capabilities",
]
