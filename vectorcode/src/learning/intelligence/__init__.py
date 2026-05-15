# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/learning/intelligence/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Intelligence learning — model fine-tuning via SFT and GRPO."""

from __future__ import annotations

# Import trainers so their @LearningRegistry.register decorators execute.
try:
    from vector.learning.intelligence import sft_trainer as _sft  # noqa: F401
except ImportError:
    pass
try:
    from vector.learning.intelligence import grpo_trainer as _grpo  # noqa: F401
except ImportError:
    pass
