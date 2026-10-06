# Thin re-export for backwards compatibility.
# Canonical telemetry modules live in core.telemetry.
from core.telemetry.itl import *  # noqa: F401, F403

__all__ = ["compute_itl_stats"]
