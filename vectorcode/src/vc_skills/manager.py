"""VECTOR skill manager shim."""
try:
    from vectorcode.src.skills.manager import SkillManager
except ImportError:
    class SkillManager:
        pass
