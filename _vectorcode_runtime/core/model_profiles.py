"""Validated local model profiles used by VECTOR's Ollama routing.

This module deliberately lives directly under ``core`` so configuration can
load it without importing the heavy ``core.inference`` package initializer.
The profile layer only chooses model aliases. It does not change permissions,
tool dispatch, privacy routing, or safety evaluation.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


PROFILE_PRODUCTION = "production"
PROFILE_UNCENSORED = "uncensored"
VALID_PROFILES = frozenset({PROFILE_PRODUCTION, PROFILE_UNCENSORED})

UNCENSORED_ROLE_MODELS = MappingProxyType(
    {
        "focus": "vector-uncensored-focus",
        "coder": "vector-uncensored-coder",
        "reasoning": "vector-uncensored-reasoning",
        "r1": "vector-uncensored-r1",
    }
)

UNCENSORED_TO_PRODUCTION = MappingProxyType(
    {
        "vector-uncensored-focus": "vector-focus",
        "vector-uncensored-coder": "vector-coder",
        "vector-uncensored-reasoning": "vector-reasoning",
        "vector-uncensored-r1": "vector-r1",
    }
)

_DERIVED_ROLE_SOURCES = MappingProxyType(
    {
        "deep": "reasoning",
        "chairman": "reasoning",
        "dev": "coder",
        "fast": "focus",
        "cloud_coder": "coder",
        "cloud_orchestrator": "r1",
    }
)


def validate_profile(profile: str) -> str:
    """Return a normalized profile name or reject an unknown value."""
    normalized = str(profile).strip().lower()
    if normalized not in VALID_PROFILES:
        allowed = ", ".join(sorted(VALID_PROFILES))
        raise ValueError(f"unknown model profile {profile!r}; expected one of: {allowed}")
    return normalized


def build_active_model_map(
    base_models: Mapping[str, str],
    profile: str,
) -> dict[str, str]:
    """Build the runtime model map without mutating the settings input."""
    normalized = validate_profile(profile)
    active = dict(base_models)
    if normalized != PROFILE_UNCENSORED:
        return active

    active.update(UNCENSORED_ROLE_MODELS)
    for derived_role, source_role in _DERIVED_ROLE_SOURCES.items():
        active[derived_role] = UNCENSORED_ROLE_MODELS[source_role]
    return active


def production_fallback_for(model: str) -> str | None:
    """Return the production alias for an uncensored alias, if one exists."""
    return UNCENSORED_TO_PRODUCTION.get(str(model).strip())


def is_uncensored_model(model: str) -> bool:
    """Return whether ``model`` is one of VECTOR's isolated raw aliases."""
    return str(model).strip() in UNCENSORED_TO_PRODUCTION


def active_alias_for_production_model(model: str, active_models: Mapping[str, str]) -> str:
    """Resolve a stable production alias through the active local profile."""
    role_by_production = {
        "vector-focus": "focus",
        "vector-coder": "coder",
        "vector-reasoning": "reasoning",
        "vector-r1": "r1",
    }
    role = role_by_production.get(str(model).strip())
    return active_models.get(role, model) if role else model


if __name__ == "__main__":
    _base = {
        "focus": "vector-focus",
        "coder": "vector-coder",
        "reasoning": "vector-reasoning",
        "r1": "vector-r1",
    }
    _active = build_active_model_map(_base, PROFILE_UNCENSORED)
    assert _active["focus"] == "vector-uncensored-focus"
    assert production_fallback_for(_active["focus"]) == "vector-focus"
    print("OK model_profiles.py")
