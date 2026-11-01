"""
Testing and CI environment settings.

These settings control test mode behavior and CI/testing flags.
"""

import os

__all__ = [
    "CI",
    "GITHUB_ACTIONS",
    "TESTING",
    "TESTING_SETTINGS",
]

from ..env_settings import BooleanSetting


# External environment variables (not LDR-prefixed, set by external systems)
# These are read directly since we don't control them
CI = os.environ.get("CI", "false").lower() in ("true", "1", "yes")
GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "false").lower() in (
    "true",
    "1",
    "yes",
)
TESTING = os.environ.get("TESTING", "false").lower() in ("true", "1", "yes")


# VRE Testing settings (our application's test configuration)
TESTING_SETTINGS = [
    BooleanSetting(
        key="testing.test_mode",
        description="Enable test mode (adds delays for testing concurrency)",
        default=False,
    ),
]
