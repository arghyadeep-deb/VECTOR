"""vectorcode/src/repl/_helpers.py — re-exports helpers from _loop for backward compat."""
from ._loop import (  # noqa: F401
    _fetch_ollama_models, _pick_best_ollama_model, _load_soul,
    _build_system_prompt, _scan_skills, _build_skills_index, _load_skill,
    _history_size, _compress_history, _save_session, _load_last_session,
    _save_trajectory, _list_sessions, _detect_project_config,
    _ask_ollama, _ask_model,
)
