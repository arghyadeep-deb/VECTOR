# Canonical source is _stubs.py (better docstrings, spec references).
# This file is a backward-compat re-export so existing imports keep working.
from core.mining._stubs import *  # noqa: F401, F403
from core.mining._stubs import (
    MiningCapabilities, SoloTarget, PoolTarget, SubmitTarget,
    MiningConfig, MiningStats, MiningProvider, Sidecar,
)
