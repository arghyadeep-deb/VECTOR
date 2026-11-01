# Thin re-export for backwards compatibility.
# Canonical telemetry modules live in core.telemetry.
from core.telemetry.vllm_metrics import *  # noqa: F401, F403
from core.telemetry.vllm_metrics import __all__  # noqa: F401
