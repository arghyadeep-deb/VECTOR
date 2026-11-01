"""vectorcode/src/repl/_loop.py — VectorREPL and helpers from the canonical repl.py monolith."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

_KEY = "_vector_repl_monolith"
if _KEY not in sys.modules:
    _path = Path(__file__).parent.parent / "repl.py"
    _spec = importlib.util.spec_from_file_location(_KEY, str(_path))
    assert _spec is not None
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_KEY] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_mod = sys.modules[_KEY]

VectorREPL = _mod.VectorREPL
_Spinner = _mod._Spinner
_fetch_ollama_models = _mod._fetch_ollama_models
_pick_best_ollama_model = _mod._pick_best_ollama_model
_load_soul = _mod._load_soul
_build_system_prompt = _mod._build_system_prompt
_scan_skills = _mod._scan_skills
_build_skills_index = _mod._build_skills_index
_load_skill = _mod._load_skill
_history_size = _mod._history_size
_compress_history = _mod._compress_history
_save_session = _mod._save_session
_load_last_session = _mod._load_last_session
_save_trajectory = _mod._save_trajectory
_list_sessions = _mod._list_sessions
_detect_project_config = _mod._detect_project_config
_ask_ollama = _mod._ask_ollama
_ask_model = _mod._ask_model
