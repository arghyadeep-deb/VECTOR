"""VECTOR skill manager shim."""
try:
    from vectorcode.src.skills.manager import SkillManager
except ImportError as exc:
    _IMPORT_ERROR = exc

    class SkillManager:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "SkillManager is unavailable because vectorcode.src.skills.manager "
                "could not be imported"
            ) from _IMPORT_ERROR
