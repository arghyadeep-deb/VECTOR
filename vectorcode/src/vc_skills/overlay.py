"""VECTOR skill overlay shim."""
try:
    from vectorcode.src.skills.overlay import SkillOverlay
except ImportError:
    class SkillOverlay:
        pass
def write_overlay(name: str, content: str) -> None:
    pass

