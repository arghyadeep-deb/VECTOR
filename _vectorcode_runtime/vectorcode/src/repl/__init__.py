"""
vectorcode/src/repl/__init__.py
VECTOR REPL package — drop-in replacement for repl.py monolith.
"""
from ._loop import VectorREPL, _Spinner
from ._helpers import (
    _fetch_ollama_models, _pick_best_ollama_model, _load_soul,
    _build_system_prompt, _scan_skills, _build_skills_index, _load_skill,
    _history_size, _compress_history, _save_session, _load_last_session,
    _save_trajectory, _list_sessions, _detect_project_config,
    _ask_ollama, _ask_model,
)

__all__ = [
    "VectorREPL", "_Spinner",
    "_fetch_ollama_models", "_pick_best_ollama_model", "_load_soul",
    "_build_system_prompt", "_scan_skills", "_build_skills_index", "_load_skill",
    "_history_size", "_compress_history", "_save_session", "_load_last_session",
    "_save_trajectory", "_list_sessions", "_detect_project_config",
    "_ask_ollama", "_ask_model",
]
