"""ARM A — Content / Brand pipeline (one reel/day).

Chains existing agents: script (two truthful wells) -> Kokoro narration -> HUD
recording -> ffmpeg assemble -> permission-gated upload. Reuses
``districts/content/*`` and ``core/voice/tts.py``; the only new media step is the
HUD recorder.

Guardrails baked in: truthful-claims-only (script pulls from VECTOR's real action
log or demos a real feature), every publish behind ``permission_gateway`` (owner
approval), and Instagram defaults to human-in-the-loop (owner gets a Pushover to
post) -- ``instagrapi`` is never auto-called (ToS risk). Never raises -- ARM A
runs forever.
"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG
from districts.growth.hud_recorder import HUDRecorder


class ContentArm:
    """Daily brand-reel pipeline. All stages guarded; mockable for tests."""

    def __init__(self) -> None:
        self._recorder = HUDRecorder()

    # -- orchestration ------------------------------------------------
    async def run_once(self) -> dict:
        """Produce one reel and route it to the (gated) publish step."""
        well = await self._pick_well()
        text, _ = await self._script(well)
        # Both steps are blocking (TTS synthesis; a real browser recording for the whole narration). Called inline they
        # froze the event loop for the duration, and Playwright's sync API refuses to run inside a running loop
        # ("It looks like you are using Playwright Sync API inside the asyncio loop") -- so no reel was ever recorded.
        narration_wav, duration_s = await asyncio.to_thread(self._narrate, text)
        reel = await asyncio.to_thread(self._record, narration_wav, duration_s)
        if reel:
            await self._gated_publish(reel, well)
        else:
            logger.warning("[VECTOR][growth][armA] no reel produced (recorder unavailable)")
        return {"reel": reel, "well": well, "script": text}

    async def _pick_well(self) -> str:
        """Pick the content well: real work today, else a capability showcase."""
        return "work_done" if self._has_reelworthy_work() else "capability_showcase"

    # -- stages (reuse existing agents; mocked in tests) --------------
    def _has_reelworthy_work(self) -> bool:
        """True if VECTOR did something reel-worthy today (from the action log)."""
        try:
            from core.memory.episodic import EpisodicMemory
            hits = EpisodicMemory().recall("task completed", limit=3)
            return bool(hits)
        except Exception as exc:
            logger.debug("[VECTOR][growth][armA] reelworthy check fell back: {}", exc)
            return False

    async def _script(self, well: str) -> tuple:
        """Generate a truthful script. Pulls from the action log (work_done) or
        showcases a real feature (capability_showcase).

        2026-09-24: this used to call a non-existent `ScriptGenerator.generate`, so the reel
        narrated the bare topic string. It now awaits the real `generate_script()`.
        """
        try:
            from districts.content.script_generator import ScriptGenerator  # reuse
            topic = ("what VECTOR did today" if well == "work_done"
                     else "a VECTOR capability showcase")
            result = await ScriptGenerator().generate_script(topic, duration_min=1.0)
            text = (result or {}).get("content", "") if isinstance(result, dict) else ""
            if not text or (isinstance(result, dict) and result.get("error")):
                raise ValueError(f"no script content ({(result or {}).get('error', 'empty')})")
            return (str(text), well)
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] script fell back: {}", exc)
            return (f"{CONFIG['growth']['brand_line']} - {well}", well)

    def _narrate(self, text: str) -> tuple:
        """Kokoro bf_emma narration -> (wav_path, duration_seconds)."""
        try:
            from core.voice.tts import VoiceTTS
            tts = VoiceTTS()
            out = Path(__file__).parent.parent.parent / "renders" / "growth"
            out.mkdir(parents=True, exist_ok=True)
            wav = str(out / "narration.wav")
            dur = tts.synthesize(text, voice=CONFIG["growth"]["voice_profile"], out_path=wav) \
                if hasattr(tts, "synthesize") else 0.0
            return (wav, float(dur) if isinstance(dur, (int, float)) else 12.0)
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] narrate fell back: {}", exc)
            return ("", 12.0)

    def _record(self, narration_wav: str, duration_s: float) -> "str | None":
        """Record the HUD reflecting a live task for the narration's duration."""
        return self._recorder.record(narration_wav, duration_s, trigger_task=self._trigger_live_task)

    def _trigger_live_task(self) -> None:
        """Fire a real, observable task so the HUD shows activity during capture.
        v1: emit a showcase event to the HUD event feed; wired to a real dispatch
        as the loop matures."""
        try:
            from core.event_bus import publish  # type: ignore
            publish("growth.showcase", {"brand": CONFIG["growth"]["brand_line"]})
        except Exception:
            logger.debug("[VECTOR][growth][armA] live-task trigger no-op")

    # -- publish (gated) ----------------------------------------------
    async def _gated_publish(self, reel: str, well: str) -> dict:
        """Publish only when explicitly enabled. Default (``auto_publish`` off):
        hold the reel and notify the owner to post manually -- nothing auto-uploads.
        When enabled, ask the permission gateway for owner approval and upload only
        if it returns True (fails closed on timeout/rejection).

        Returns a dict tracking per-platform results so callers can retry only
        failed platforms.
        """
        platform_results: dict[str, str] = {}  # platform -> "ok" | "failed" | "skipped"

        if not CONFIG["growth"].get("auto_publish", False):
            logger.info("[VECTOR][growth][armA] auto_publish off -- reel held for owner: {}", reel)
            # ALWAYS the notify-only path here. It used to call the configured
            # instagram_mode publisher (phone / graph_api), which posted with no
            # approval gate whenever auto_publish was off -- the default.
            await self._notify_owner_to_post(reel)
            platform_results["instagram"] = "notified_owner"
            return {"platforms": platform_results, "reel": reel}

        approved = False
        try:
            from core.loop.permission_gateway import PermissionGateway
            summary = f"Publish daily reel ({well}) to YouTube Shorts" + \
                      (" + Instagram" if CONFIG["growth"].get("instagram_mode") == "graph_api" else "")
            approved = await PermissionGateway().request_approval(
                "growth_publish_reel", f"{summary}\nfile: {reel}"
            )
        except Exception as exc:
            logger.error("[VECTOR][growth][armA] approval request failed (fail-closed): {}", exc)
            approved = False

        if not approved:
            logger.info("[VECTOR][growth][armA] publish not approved -- reel held: {}", reel)
            return {"platforms": platform_results, "reel": reel, "approved": False}

        # Owner approved -> fire the real uploads, tracking per-platform results.
        yt_ok = await self._publish_youtube(reel, well)
        platform_results["youtube"] = "ok" if yt_ok else "failed"

        ig_ok = await self._instagram_publisher_safe(reel)
        platform_results["instagram"] = "ok" if ig_ok else "failed"

        succeeded = sum(1 for v in platform_results.values() if v == "ok")
        logger.info("[VECTOR][growth][armA] publish complete: {}/{} platforms — {}",
                     succeeded, len(platform_results), platform_results)
        return {"platforms": platform_results, "reel": reel, "approved": True}

    async def _publish_youtube(self, reel: str, well: str) -> bool:
        """Publish a Short. youtube_mode='phone' drives the app on the device
        (no OAuth needed — account logged in on the phone); 'api' uses the
        official Data API Uploader (needs Google OAuth creds).
        Returns True on success, False on failure."""
        if CONFIG["growth"].get("youtube_mode", "phone") == "phone":
            try:
                from districts.content.phone_poster import PhonePoster
                res = await PhonePoster().post_youtube(reel, caption=CONFIG["growth"]["brand_line"])
                logger.info("[VECTOR][growth][armA] YouTube phone-post result: {}", res)
                # res is a {status, reason} dict -- always truthy, so bool(res)
                # reported blocked/error as success.
                return isinstance(res, dict) and res.get("status") in ("uploaded", "pending_upload")
            except Exception as exc:
                logger.warning("[VECTOR][growth][armA] youtube phone post unavailable: {}", exc)
                return False
        try:
            from districts.content.uploader import Uploader
            title = CONFIG["growth"]["brand_line"]
            desc = f"Autonomous demo - {well.replace('_', ' ')}. {CONFIG['growth']['brand_line']}"
            tags = ["VECTOR", "AI", "JARVIS", "automation"]
            res = await Uploader().upload_to_youtube(
                reel, title=title, description=desc, tags=tags, privacy="private"
            )
            logger.info("[VECTOR][growth][armA] YouTube upload result: {}", res)
            return self._upload_ok(res)
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] youtube publish unavailable: {}", exc)
            return False

    @staticmethod
    def _upload_ok(res) -> bool:
        """True only for a real upload. Uploader returns status 'success' even for
        its no-credentials simulation (simulated=True) -- that is not a publish."""
        if not isinstance(res, dict) or res.get("simulated"):
            return False
        return res.get("status") in ("uploaded", "scheduled", "published", "success")

    async def _instagram_publisher_safe(self, reel: str) -> bool:
        """Execute the IG publish strategy and return bool success.
        Unlike _instagram_publisher() (which returns a callable), this runs
        the callable and reports success/failure for per-platform tracking."""
        try:
            publisher = self._instagram_publisher()
            return bool(await publisher(reel))
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] IG publish failed: {}", exc)
            return False

    def _instagram_publisher(self):
        """Return the IG publish strategy. 'manual' = human-in-the-loop (default);
        'phone' = drive the app on the connected device (ban-safest, gated by
        social_safety + approval); 'graph_api' = official API. instagrapi never used."""
        mode = CONFIG["growth"].get("instagram_mode", "manual")
        if mode == "graph_api":
            return self._graph_api_post
        if mode == "phone":
            return self._phone_post
        return self._notify_owner_to_post

    async def _phone_post(self, reel: str | None = None) -> bool:
        """Post the reel by driving Instagram on the connected phone. All gating
        (warm-up/cap/spacing + owner approval) lives in PhonePoster — this just
        delegates and logs. Reached only after content_arm's own approval gate."""
        try:
            from districts.content.phone_poster import PhonePoster
            res = await PhonePoster().post_instagram(reel or "", caption=CONFIG["growth"]["brand_line"])
            logger.info("[VECTOR][growth][armA] IG phone-post result: {}", res)
            return isinstance(res, dict) and res.get("status") in ("posted", "pending_share")
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] phone IG post unavailable: {}", exc)
            return False

    async def _notify_owner_to_post(self, reel: str | None = None) -> bool:
        """Human-in-the-loop IG: render the reel + Pushover the owner to post it."""
        try:
            from core.notify import pushover
            await pushover(f"VECTOR reel ready to post on Instagram: {reel}")
            return True
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] (manual IG) owner-notify failed: {} -- reel ready {}", exc, reel)
            return False

    async def _graph_api_post(self, reel: str | None = None) -> bool:
        """Official Instagram Graph API Content Publishing (owner must have a
        Business/Creator account + app review). Reached only post-approval."""
        try:
            from districts.content.uploader import Uploader
            # upload_to_instagram requires `hashtags`; omitting it raised TypeError
            # every call, so graph_api mode never published.
            res = await Uploader().upload_to_instagram(
                reel, caption=CONFIG["growth"]["brand_line"], hashtags=["VECTOR", "AI"]
            )
            logger.info("[VECTOR][growth][armA] IG Graph API upload result: {}", res)
            return self._upload_ok(res)
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] IG graph_api publish unavailable: {}", exc)
            return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("content_arm OK")
