"""VECTOR skill overlay shim."""
try:
    from vectorcode.src.skills.overlay import SkillOverlay, write_overlay
except ImportError as exc:
    _IMPORT_ERROR = exc

    class SkillOverlay:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "SkillOverlay is unavailable because vectorcode.src.skills.overlay "
                "could not be imported"
            ) from _IMPORT_ERROR

    def write_overlay(*args, **kwargs):
        raise RuntimeError(
            "write_overlay is unavailable because vectorcode.src.skills.overlay "
            "could not be imported"
        ) from _IMPORT_ERROR

