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
import random

from loguru import logger

from core.config import CONFIG

_IG_PACKAGE = "com.instagram.android"
_YT_PACKAGE = "com.google.android.youtube"
_REMOTE_MEDIA = "/sdcard/vector_post.mp4"


async def _human_pause(lo: float, hi: float) -> None:
    """Sleep a randomized, human-scale interval instead of a fixed duration —
    back-to-back fixed-timing ADB taps read as bot activity to platforms
    (confirmed 2026-07-21: rapid scripted taps during a profile edit tripped
    Instagram's 'confirm you're human' challenge)."""
    await asyncio.sleep(random.uniform(lo, hi))


def _jitter(x: int, y: int, radius: int = 6) -> tuple[int, int]:
    """Offset a tap target by a few px — humans never hit the exact same pixel twice."""
    return (x + random.randint(-radius, radius), y + random.randint(-radius, radius))


async def _notify_owner(message: str) -> None:
    """Best-effort Pushover notification to the owner.

    2026-07-21: this used to do `from core.notify import pushover` — that
    module has never existed anywhere in the codebase, so the import always
    raised, was swallowed by a bare `except Exception: pass`, and the owner
    was never actually told to tap Share. Confirmed as the reason the one
    real Instagram test post never got a final confirmed status: the reel
    sat loaded in IG's composer with no nudge to finish it. Fixed by reusing
    the Pushover sender that already works elsewhere (PermissionGateway's
    RED-tier approval notifications) instead of a phantom module.
    """
    try:
        from core.loop.permission_gateway import PermissionGateway
        await PermissionGateway.get_shared()._notify(message)
    except Exception as e:
        logger.warning("[VECTOR][phone_poster] owner notify failed: {}", e)


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
            decision = can_post_now(handle, media_path=media_path, caption=caption)
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
                action_type="instagram_post_via_phone",
                summary=f"Post reel to Instagram (@{handle}) on the phone. Caption: {caption[:80]}",
            )
        except Exception as e:
            logger.error("[VECTOR][phone_poster] approval failed (fail-closed): {}", e)
            approved = False
        if not approved:
            return {"status": "blocked", "reason": "owner did not approve"}

        # F-7: mint a control token after approval; the gated phone primitives
        # (unlock/tap/swipe/type_text/launch_app) require it.
        # 2026-09-23 (round 2): grant_control() no longer accepts a
        # caller-asserted `approved` bool (forgeable -- an independent
        # review correctly flagged that). request_approval() above
        # already issued a real, unforgeable receipt for
        # "instagram_post_via_phone" the instant it returned True (same
        # process-wide PermissionGateway singleton), so this plain call
        # succeeds without needing to thread anything through by hand.
        from core.loop.permission_gateway import PermissionGateway
        _ct = PermissionGateway().grant_control("instagram_post_via_phone", uses=32, ttl=300)

        # 3. Device not connected → hold + notify (never lose the reel)
        if not self._pc.is_connected():
            return {"status": "error", "reason": "phone not connected"}

        # 4. Push media + open IG share composer via intent
        try:
            self._pc.unlock(control_token=_ct)
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
            await _human_pause(4.0, 7.5)
        except Exception as e:
            return {"status": "error", "reason": f"intent launch failed: {e}"}

        # 5. Final Share tap — calibrated coordinate, or leave for the owner's tap.
        share_tap = CONFIG["growth"].get("ig_share_tap")
        try:
            from core.control.social_safety import record_post
            if isinstance(share_tap, (list, tuple)) and len(share_tap) == 2:
                tx, ty = _jitter(int(share_tap[0]), int(share_tap[1]))
                self._pc.tap(tx, ty, control_token=_ct)
                await _human_pause(2.5, 4.5)
                record_post(handle, media_path=media_path, caption=caption)
                return {"status": "posted", "reason": "shared via calibrated tap"}
            # Not calibrated → composer is open with media loaded; owner taps Share.
            #
            # 2026-07-21: this used to call record_post(handle) right here,
            # before any confirmation the owner actually tapped Share — so an
            # uncalibrated post that may never have been published still
            # consumed the day's post cap (growth.max_posts_per_day), and
            # every retry that day was denied by the safety gate on a post
            # that was never verified to exist. Combined with the dead
            # core.notify.pushover import above (owner never got the nudge
            # to tap Share), this is why the one real test post never got a
            # confirmed status. Fixed: do NOT record_post() here — only the
            # calibrated-tap branch above (which VECTOR itself performed and
            # can verify) counts as a confirmed post. Calibrate
            # growth.ig_share_tap=[x,y] to get real cap tracking on this path.
            await _notify_owner("Reel loaded in Instagram composer — tap Share to post.")
            return {"status": "pending_share",
                    "reason": "composer open with media; owner taps Share (not "
                              "counted against the daily cap since it isn't "
                              "confirmed — calibrate growth.ig_share_tap=[x,y] "
                              "to fully automate and get real cap tracking)"}
        except Exception as e:
            return {"status": "error", "reason": f"share step failed: {e}"}


    async def post_youtube(self, media_path: str, caption: str = "") -> dict:
        """Upload a Short to YouTube by driving the app (account already logged in
        on the phone — no OAuth/Cloud Console needed). YouTube is the official
        platform so ban-risk is minimal; still owner-approval-gated. Returns
        {status, reason}. status ∈ pending_upload|uploaded|blocked|error.

        No warm-up/cap gate here (YouTube tolerates uploads; those rules exist for
        Instagram's stricter new-account bot detection)."""
        handle = CONFIG["growth"].get("youtube_handle", "") or "__yt__"

        # Owner approval (fail-closed)
        try:
            from core.loop.permission_gateway import PermissionGateway
            approved = await PermissionGateway().request_approval(
                action_type="youtube_upload_via_phone",
                summary=f"Upload Short to YouTube (@{handle}) on the phone. {caption[:80]}",
            )
        except Exception as e:
            logger.error("[VECTOR][phone_poster] YT approval failed (fail-closed): {}", e)
            approved = False
        if not approved:
            return {"status": "blocked", "reason": "owner did not approve"}

        # F-7: mint a control token after approval for the gated phone primitives.
        # 2026-09-23 (round 2): see the identical comment on the Instagram
        # path above -- request_approval() already issued a real receipt.
        from core.loop.permission_gateway import PermissionGateway
        _ct = PermissionGateway().grant_control("youtube_upload_via_phone", uses=32, ttl=300)

        if not self._pc.is_connected():
            return {"status": "error", "reason": "phone not connected"}

        try:
            self._pc.unlock(control_token=_ct)
            ok, _ = self._pc._run_adb("push", media_path, _REMOTE_MEDIA, timeout=60)
            if not ok:
                return {"status": "error", "reason": "adb push of media failed"}
            self._pc._run_adb("shell", "am", "broadcast", "-a",
                              "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                              "-d", f"file://{_REMOTE_MEDIA}", timeout=10)
            # Share-intent hands the video to YouTube's upload composer.
            self._pc._run_adb(
                "shell", "am", "start", "-a", "android.intent.action.SEND",
                "-t", "video/*", "--eu", "android.intent.extra.STREAM", f"file://{_REMOTE_MEDIA}",
                "-p", _YT_PACKAGE, timeout=15,
            )
            await _human_pause(4.0, 7.5)
        except Exception as e:
            return {"status": "error", "reason": f"intent launch failed: {e}"}

        # Final Next→Upload taps are calibration-driven (composer is multi-step).
        # Until calibrated, composer is open with the video; owner taps through Upload.
        await _notify_owner("Short loaded in YouTube composer — tap Next → Upload to publish.")
        return {"status": "pending_upload",
                "reason": "composer open with video; owner taps Next→Upload "
                          "(calibrate growth.yt_upload_taps to automate)"}


if __name__ == "__main__":
    # Structural self-test only — does NOT post (no approval, no real media).
    import inspect
    src = inspect.getsource(PhonePoster.post_instagram) + inspect.getsource(PhonePoster.post_youtube)
    ok = all(s in src for s in ("can_post_now", "request_approval", "record_post", "SEND", "_YT_PACKAGE"))
    print("phone_poster OK" if ok else "FAILED")
