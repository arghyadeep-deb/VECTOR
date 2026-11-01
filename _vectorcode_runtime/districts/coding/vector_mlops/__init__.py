"""
VECTOR ML Engineer — core/ml_intern

Autonomous ML engineering suite with deep HuggingFace ecosystem integration.
Provides:
- HF Papers research sub-agent (citation graphs, methodology extraction, training recipe mining)
- HF Jobs GPU/CPU submission (Python scripts or Docker)
- Trackio experiment tracking with alert system
- HF Hub file management (upload, git branches, PRs, tags)
- HF dataset inspection (schema, samples, column validation)
- GitHub ML code search (semantic + keyword)
- LiteLLM unified multi-model interface (Claude/GPT/HF-router/local)
- Context auto-compaction at 170k tokens for long ML sessions
- Reasoning effort probing per model

Usage via VECTOR governor:
  ml_research, hf_train, hf_dataset, hf_hub, github_ml, ml_plan
"""
import sys
from pathlib import Path

# Add core/ml_intern/ to sys.path so all "from agent.X" and "from backend.X"
# imports resolve correctly — same pattern as the original repo root.
_MLOPS_DIR = Path(__file__).resolve().parent
if str(_MLOPS_DIR) not in sys.path:
    sys.path.insert(0, str(_MLOPS_DIR))
