# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Load system prompt and few-shot overrides from $VECTOR_HOME.

Distillation (M1) proposes edits that get written to disk by appliers.
This module lets agents pick those overrides up at runtime:

- System prompts: ``$VECTOR_HOME/agents/{name}/system_prompt.md``
- Few-shot exemplars: ``$VECTOR_HOME/agents/{name}/few_shot.json``

Override files are templates — they may contain ``{tool_descriptions}`` and
other format placeholders that the agent fills in via ``.format()``, exactly
like the hardcoded constants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

def _vector_home() -> Path:
    """Resolve $VECTOR_HOME, defaulting to ~/.vector."""
    return Path(os.environ.get("VECTOR_HOME", "~/.vector")).expanduser()

def load_system_prompt_override(agent_name: str) -> str | None:
    """Return the override prompt for *agent_name*, or ``None``.

    Looks for ``$VECTOR_HOME/agents/<agent_name>/system_prompt.md``.
    ``VECTOR_HOME`` defaults to ``~/.vector`` when unset.
    """
    home = _vector_home()
    prompt_path = home / "agents" / agent_name / "system_prompt.md"
    if not prompt_path.exists():
        return None
    try:
        content = prompt_path.read_text(encoding="utf-8")
        logger.info(
            "Loaded system prompt override for {} from {}", agent_name, prompt_path
        )
        return content
    except Exception:
        logger.opt(exception=True).warning(
            "Failed to read system prompt override at {}", prompt_path
        )
        return None

def load_few_shot_exemplars(
    agent_name: str,
) -> list[dict[str, Any]]:
    """Return few-shot exemplars for *agent_name*, or empty list.

    Looks for ``$VECTOR_HOME/agents/<agent_name>/few_shot.json``.
    Expected format: ``[{"input": "Q", "output": "A"}, ...]``.
    """
    home = _vector_home()
    fs_path = home / "agents" / agent_name / "few_shot.json"
    if not fs_path.exists():
        return []
    try:
        data = json.loads(fs_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("few_shot.json for {} is not a list", agent_name)
            return []
        logger.info(
            "Loaded {} few-shot exemplars for {} from {}",
            len(data),
            agent_name,
            fs_path,
        )
        return data
    except Exception:
        logger.opt(exception=True).warning(
            "Failed to read few-shot exemplars at {}",
            fs_path,
        )
        return []
