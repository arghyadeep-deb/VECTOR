"""ContentArm's blocking steps (TTS, browser recording) must run off the event loop.

Found live 2026-09-25: `_record()` ran Playwright's SYNC API inside the running loop, which Playwright refuses
("It looks like you are using Playwright Sync API inside the asyncio loop"), so no reel was ever recorded -- and
inline, both steps froze the loop for the whole narration.
"""
from __future__ import annotations

import asyncio

from districts.growth.content_arm import ContentArm


def test_narrate_and_record_run_without_a_running_event_loop(monkeypatch):
    seen = {}
    arm = ContentArm()

    async def _fake_pick():
        return "well"

    async def _fake_script(well):
        return ("script text", None)

    def _no_loop():
        try:
            asyncio.get_running_loop()
            return False
        except RuntimeError:
            return True

    def _fake_narrate(text):
        seen["narrate_off_loop"] = _no_loop()
        return ("n.wav", 1.0)

    def _fake_record(wav, dur):
        seen["record_off_loop"] = _no_loop()
        return None  # no reel -> run_once skips publishing

    monkeypatch.setattr(arm, "_pick_well", _fake_pick)
    monkeypatch.setattr(arm, "_script", _fake_script)
    monkeypatch.setattr(arm, "_narrate", _fake_narrate)
    monkeypatch.setattr(arm, "_record", _fake_record)
    out = asyncio.run(arm.run_once())
    assert seen == {"narrate_off_loop": True, "record_off_loop": True}
    assert out["reel"] is None
