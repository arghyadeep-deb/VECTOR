"""Compatibility exports for the lightweight local model profile module."""

from core.model_profiles import (
    PROFILE_PRODUCTION,
    PROFILE_UNCENSORED,
    UNCENSORED_ROLE_MODELS,
    UNCENSORED_TO_PRODUCTION,
    VALID_PROFILES,
    active_alias_for_production_model,
    build_active_model_map,
    is_uncensored_model,
    production_fallback_for,
    validate_profile,
)

__all__ = [
    "PROFILE_PRODUCTION",
    "PROFILE_UNCENSORED",
    "UNCENSORED_ROLE_MODELS",
    "UNCENSORED_TO_PRODUCTION",
    "VALID_PROFILES",
    "active_alias_for_production_model",
    "build_active_model_map",
    "is_uncensored_model",
    "production_fallback_for",
    "validate_profile",
]


if __name__ == "__main__":
    assert build_active_model_map({"focus": "vector-focus"}, PROFILE_UNCENSORED)["focus"] == "vector-uncensored-focus"
    print("OK core.inference.model_profiles.py")
