"""Task 4 — ARM B: reviewer↔fix loop exits only on approve; caps + escalates."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_review_loop_exits_only_on_approve(monkeypatch):
    from districts.growth.software_arm import SoftwareArm
    arm = SoftwareArm()
    seq = iter([False, False, True])  # approve on 3rd review
    monkeypatch.setattr(arm, "_review", lambda code: next(seq))
    monkeypatch.setattr(arm, "_fix", lambda code, review: code)
    res = await arm._review_fix_loop(code="x")
    assert res["approved"] is True and res["iterations"] == 3


async def test_review_loop_caps_and_escalates(monkeypatch):
    from districts.growth.software_arm import SoftwareArm
    arm = SoftwareArm()
    monkeypatch.setattr(arm, "_review", lambda code: False)  # never approves
    monkeypatch.setattr(arm, "_fix", lambda code, review: code)
    res = await arm._review_fix_loop(code="x")
    assert res["approved"] is False and res["escalated"] is True
    assert res["iterations"] == arm.max_iterations


if __name__ == "__main__":
    print("run via pytest")
