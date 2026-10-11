"""FL-026 — SoftwareArm._security_audit() must report an observed review.

Previously it set reviewed=True merely because SecurityReviewer was
importable, and always returned passed=False, regardless of whether any
scan actually ran. This tests that reviewed/passed now reflect a real,
observed SecurityReviewer.review() call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_security_audit_reports_real_clean_scan_as_passed():
    from districts.growth.software_arm import SoftwareArm

    arm = SoftwareArm()
    clean_code = "def add(a, b):\n    return a + b\n"
    result = await arm._security_audit({"code": clean_code})
    assert result["reviewed"] is True
    assert result["issue_count"] == 0
    assert result["passed"] is True


async def test_security_audit_reports_real_vulnerable_scan_as_not_passed():
    from districts.growth.software_arm import SoftwareArm

    arm = SoftwareArm()
    vulnerable_code = "import os\nos.system(user_input)\n"
    result = await arm._security_audit({"code": vulnerable_code})
    assert result["reviewed"] is True
    assert result["issue_count"] > 0
    assert result["passed"] is False


async def test_security_audit_reviewed_false_when_reviewer_unavailable(monkeypatch):
    from districts.growth import software_arm as mod

    arm = mod.SoftwareArm()

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "districts.coding.security_reviewer":
            raise ImportError("simulated unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = await arm._security_audit({"code": "def f(): pass"})
    assert result == {"passed": False, "reviewed": False}


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
