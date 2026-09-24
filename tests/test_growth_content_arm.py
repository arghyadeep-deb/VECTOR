"""Task 3 — ARM A content pipeline: chains stages, gates publish, two content
wells, IG default is human-in-the-loop (never instagrapi)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_arm_a_chains_and_gates(monkeypatch):
    from districts.growth.content_arm import ContentArm
    arm = ContentArm()
    async def _fake_script(well):
        return ("hi", well)

    monkeypatch.setattr(arm, "_script", _fake_script)
    monkeypatch.setattr(arm, "_narrate", lambda txt: ("/n.wav", 10.0))
    monkeypatch.setattr(arm, "_record", lambda wav, dur: "/reel.mp4")
    gate = {}

    async def _fake_publish(*a, **k):
        gate.setdefault("called", True)

    monkeypatch.setattr(arm, "_gated_publish", _fake_publish)
    r = await arm.run_once()
    assert r["reel"] == "/reel.mp4" and gate["called"] is True


async def test_arm_a_falls_back_to_showcase_when_no_work(monkeypatch):
    from districts.growth.content_arm import ContentArm
    arm = ContentArm()
    monkeypatch.setattr(arm, "_has_reelworthy_work", lambda: False)
    assert (await arm._pick_well()) == "capability_showcase"


def test_arm_a_instagram_default_is_phone():
    from districts.growth.content_arm import ContentArm
    # instagram_mode default deliberately changed "manual" -> "phone": VECTOR
    # now drives the connected phone (ban-safest), gated by social_safety +
    # owner approval inside _phone_post itself. instagrapi still never used.
    assert ContentArm()._instagram_publisher().__name__ == "_phone_post"


if __name__ == "__main__":
    print("run via pytest")
