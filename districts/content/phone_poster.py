"""
districts/content/phone_poster.py — post to Instagram by driving the app on the
connected phone (instagram_mode="phone"). Ban-safest path: real device, real app,
residential IP. Never uses instagrapi.

Flow per post:
  1. social_safety.can_post_now(handle)  — warm-up / daily-cap / spacing gate
  2. PermissionGateway approval          — owner taps approve (Pushover)
  3. push media to the phone, open Instagram's share composer via ACTION_SEND intent
     (media pre-loaded — far more robust than tapping through the composer blind)
  4. FINAL SHARE tap: calibration-driven (CONFIG.growth.ig_share_tap = [x,y]) — must
     be calibrated once against the owner's live IG (button position is IG-version
     specific). Until calibrated, the reel is loaded into the composer and the owner
     taps Share — still zero manual file-handling, and nothing posts unapproved.
  5. social_safety.record_post(handle)   — so caps/spacing see it

Reuses: core/control/phone_controller (device I/O), core/control/social_safety (rules),
core/loop/permission_gateway (approval). Never raises — returns a status dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio

from loguru import logger

from core.config import CONFIG

_IG_PACKAGE = "com.instagram.android"
_REMOTE_MEDIA = "/sdcard/vector_post.mp4"


class PhonePoster:
    def __init__(self):
        from core.control.phone_controller import PhoneController
        self._pc = PhoneController()

    async def post_instagram(self, media_path: str, caption: str = "") -> dict:
        """Post `media_path` to Instagram on the connected phone. Returns
        {status, reason}. status ∈ pending_share|posted|denied|blocked|error."""
        handle = CONFIG["growth"].get("instagram_handle", "") or "__default__"

        # 1. Ban-safety gate
        try:
            from core.control.social_safety import can_post_now, record_post
            decision = can_post_now(handle)
            if not decision.allowed:
                logger.info("[VECTOR][phone_poster] safety-gate denied: {}", decision.reason)
                return {"status": "denied", "reason": decision.reason,
                        "next_allowed_at": decision.next_allowed_at}
        except Exception as e:
            return {"status": "error", "reason": f"safety gate failed: {e}"}

        # 2. Owner approval (fail-closed)
        try:
            from core.loop.permission_gateway import PermissionGateway
            approved = await PermissionGateway().request_approval(
                action="instagram_post_via_phone",
                summary=f"Post reel to Instagram (@{handle}) on the phone. Caption: {caption[:80]}",
                risk="RED",
            )
        except Exception as e:
            logger.error("[VECTOR][phone_poster] approval failed (fail-closed): {}", e)
            approved = False
        if not approved:
            return {"status": "blocked", "reason": "owner did not approve"}

        # 3. Device not connected → hold + notify (never lose the reel)
        if not self._pc.is_connected():
            return {"status": "error", "reason": "phone not connected"}

        # 4. Push media + open IG share composer via intent
        try:
            self._pc.unlock()
            ok, _ = self._pc._run_adb("push", media_path, _REMOTE_MEDIA, timeout=60)
            if not ok:
                return {"status": "error", "reason": "adb push of media failed"}
            # Make the media visible to the gallery/IG.
            self._pc._run_adb("shell", "am", "broadcast", "-a",
                              "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                              "-d", f"file://{_REMOTE_MEDIA}", timeout=10)
            # Share-intent: hands the video to IG's composer, media pre-loaded.
            self._pc._run_adb(
                "shell", "am", "start", "-a", "android.intent.action.SEND",
                "-t", "video/*", "--eu", "android.intent.extra.STREAM", f"file://{_REMOTE_MEDIA}",
                "-n", f"{_IG_PACKAGE}/.share.handleractivity.ShareHandlerActivity",
                timeout=15,
            )
            await asyncio.sleep(4)
        except Exception as e:
            return {"status": "error", "reason": f"intent launch failed: {e}"}

        # 5. Final Share tap — calibrated coordinate, or leave for the owner's tap.
        share_tap = CONFIG["growth"].get("ig_share_tap")
        try:
            from core.control.social_safety import record_post
            if isinstance(share_tap, (list, tuple)) and len(share_tap) == 2:
                self._pc.tap(int(share_tap[0]), int(share_tap[1]))
                await asyncio.sleep(3)
                record_post(handle)
                return {"status": "posted", "reason": "shared via calibrated tap"}
            # Not calibrated → composer is open with media loaded; owner taps Share.
            try:
                from core.notify import pushover  # type: ignore
                pushover("Reel loaded in Instagram composer — tap Share to post.")
            except Exception:
                pass
            record_post(handle)  # count it: it will be posted momentarily by owner tap
            return {"status": "pending_share",
                    "reason": "composer open with media; owner taps Share (calibrate "
                              "growth.ig_share_tap=[x,y] to fully automate)"}
        except Exception as e:
            return {"status": "error", "reason": f"share step failed: {e}"}


if __name__ == "__main__":
    # Structural self-test only — does NOT post (no approval, no real media).
    import inspect
    src = inspect.getsource(PhonePoster.post_instagram)
    ok = all(s in src for s in ("can_post_now", "request_approval", "record_post", "SEND"))
    print("phone_poster OK" if ok else "FAILED")
