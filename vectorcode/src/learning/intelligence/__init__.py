# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Intelligence learning — model fine-tuning via SFT and GRPO."""

from __future__ import annotations
from loguru import logger

# Import trainers so their @LearningRegistry.register decorators execute.
try:
    from vectorcode.src.learning.intelligence import sft_trainer as _sft  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] sft_trainer registration unavailable")
try:
    from vectorcode.src.learning.intelligence import grpo_trainer as _grpo  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] grpo_trainer registration unavailable")
