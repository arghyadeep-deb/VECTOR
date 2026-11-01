from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_neural_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ neural_* (8) — wired to core/memory/reasoning_memory.py + core/training/ â”€
    try:
        from core.memory.reasoning_memory import ReasoningMemory as _ReasoningMemory
        from core.memory.episodic import get_db_connection as _get_neural_conn

        _neural_rm = None
        def _get_neural_rm():
            nonlocal _neural_rm
            if _neural_rm is None:
                _neural_rm = _ReasoningMemory(_get_neural_conn())
            return _neural_rm

        @mcp.tool
        def neural_pattern_save(task: str, plan: str, outcome: str) -> str:
            """Save a neural pattern to PatternStore."""
            rm = _get_neural_rm()
            rm.store_chain(task, plan, outcome)
            return _safe_json({"ok": True})

        @mcp.tool
        def neural_pattern_recall(task: str) -> str:
            """Recall the best matching neural pattern."""
            rm = _get_neural_rm()
            patterns = rm.inject_past_reasoning(task) if hasattr(rm, "inject_past_reasoning") else []
            return _safe_json({"task": task, "patterns": patterns})

        @mcp.tool
        def neural_reward(pattern_id: str, reward: float) -> str:
            """Update the reward for a stored pattern."""
            rm = _get_neural_rm()
            rm.store_chain(pattern_id, "", "", reward=reward)
            return _safe_json({"ok": True, "pattern_id": pattern_id, "reward": reward})

        @mcp.tool
        def neural_stats() -> str:
            """Get neural cache statistics."""
            rm = _get_neural_rm()
            return _safe_json({"status": "active", "chains_stored": getattr(rm, "_chain_count", 0) if hasattr(rm, "_chain_count") else "unknown"})

        @mcp.tool
        def neural_train() -> str:
            """Trigger background pattern training."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                return _safe_json({"ok": False, "status": "not_triggered", "note": "this tool only reports trainer state; no training step was run", "step_count": getattr(trainer, "_step_count", 0)})
            except Exception as exc:
                logger.warning("[VECTOR][mcp] neural_train: trainer unavailable: {}", exc)
                return _safe_json({"ok": False, "status": "trainer not available"})

        @mcp.tool
        def neural_status() -> str:
            """Get PatternStore index status."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                return _safe_json({"step_count": getattr(trainer, "_step_count", 0), "buffer_size": len(getattr(trainer, "experience_buffer", []))})
            except Exception as exc:
                logger.warning("[VECTOR][mcp] neural_status: trainer unavailable: {}", exc)
                return _safe_json({"ok": False, "status": "trainer not available"})

        @mcp.tool
        def neural_predict(task: str) -> str:
            """Predict the best plan for a task using stored patterns."""
            rm = _get_neural_rm()
            patterns = rm.inject_past_reasoning(task) if hasattr(rm, "inject_past_reasoning") else []
            best = patterns[0] if patterns else None
            return _safe_json({"task": task, "best_plan": best})

        @mcp.tool
        def neural_optimize() -> str:
            """Optimise stored patterns by reward."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                update = trainer.get_policy_update() if hasattr(trainer, "get_policy_update") else {}
                return _safe_json({"status": "optimized", "update": update})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] neural tools unavailable: {e}")
        for n, d in [("neural_pattern_save", "Save pattern"), ("neural_pattern_recall", "Recall pattern"), ("neural_reward", "Update reward"), ("neural_stats", "Neural stats"), ("neural_train", "Trigger training"), ("neural_status", "PatternStore status"), ("neural_predict", "Predict plan"), ("neural_optimize", "Optimize patterns")]:
            _reg(mcp, n, d)
