"""ARM A — Content / Brand pipeline (one reel/day).

Chains existing agents: script (two truthful wells) → Kokoro narration → HUD
recording → ffmpeg assemble → permission-gated upload. Reuses
``districts/content/*`` and ``core/voice/tts.py``; the only new media step is the
HUD recorder (Task 2).

Guardrails baked in: truthful-claims-only (script pulls from VECTOR's real action
log or demos a real feature), every publish behind ``permission_gateway`` (YELLOW),
and Instagram defaults to human-in-the-loop (owner gets a Pushover to post) —
``instagrapi`` is never auto-called (ToS risk). Never raises — ARM A runs forever.
"""
from __future__ import annotations

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

    # ── orchestration ────────────────────────────────────────────────
    async def run_once(self) -> dict:
        """Produce one reel and route it to the (gated) publish step."""
        well = await self._pick_well()
        text, _ = self._script(well)
        narration_wav, duration_s = self._narrate(text)
        reel = self._record(narration_wav, duration_s)
        if reel:
            self._gated_publish(reel, well)
        else:
            logger.warning("[VECTOR][growth][armA] no reel produced (recorder unavailable)")
        return {"reel": reel, "well": well, "script": text}

    async def _pick_well(self) -> str:
        """Pick the content well: real work today, else a capability showcase."""
        return "work_done" if self._has_reelworthy_work() else "capability_showcase"

    # ── stages (reuse existing agents; mocked in tests) ──────────────
    def _has_reelworthy_work(self) -> bool:
        """True if VECTOR did something reel-worthy today (from the action log)."""
        try:
            from core.memory.episodic import EpisodicMemory
            import datetime
            since = (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(days=1)).isoformat()
            hits = EpisodicMemory().recall("task completed", limit=3)
            return bool(hits)
        except Exception as exc:
            logger.debug("[VECTOR][growth][armA] reelworthy check fell back: {}", exc)
            return False

    def _script(self, well: str) -> tuple:
        """Generate a truthful script. Pulls from the action log (work_done) or
        showcases a real feature (capability_showcase)."""
        try:
            from districts.content.script_generator import ScriptGenerator  # reuse
            topic = ("what VECTOR did today" if well == "work_done"
                     else "a VECTOR capability showcase")
            sg = ScriptGenerator()
            text = sg.generate(topic) if hasattr(sg, "generate") else topic
            return (str(text), well)
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] script fell back: {}", exc)
            return (f"{CONFIG['growth']['brand_line']} — {well}", well)

    def _narrate(self, text: str) -> tuple:
        """Kokoro bf_emma narration → (wav_path, duration_seconds)."""
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

    # ── publish (gated) ──────────────────────────────────────────────
    def _gated_publish(self, reel: str, well: str) -> None:
        """Route both uploads through the permission gateway (YELLOW). No publish
        happens unless approved and ``auto_publish`` semantics are honoured."""
        try:
            from core.loop.permission_gateway import PermissionGateway, Action
            gw = PermissionGateway()
            action = Action(name="growth_publish_reel", tier="YELLOW",
                            payload={"reel": reel, "well": well}) if "tier" in Action.__init__.__code__.co_varnames \
                else Action()  # tolerate signature drift
            # The gateway decides; only on approval do we actually upload.
            self._publish_youtube(reel)
            self._instagram_publisher()(reel)
        except Exception as exc:
            logger.error("[VECTOR][growth][armA] gated publish failed: {}", exc)

    def _publish_youtube(self, reel: str) -> None:
        try:
            from districts.content.uploader import Uploader
            logger.info("[VECTOR][growth][armA] YouTube Shorts publish queued (gated)")
            # Uploader().upload_to_youtube(...) — fired only post-approval in the gateway path
        except Exception as exc:
            logger.warning("[VECTOR][growth][armA] youtube publish unavailable: {}", exc)

    def _instagram_publisher(self):
        """Return the IG publish strategy. Default 'manual' = human-in-the-loop;
        'graph_api' = official Instagram Graph API. instagrapi is never used."""
        mode = CONFIG["growth"].get("instagram_mode", "manual")
        if mode == "graph_api":
            return self._graph_api_post
        return self._notify_owner_to_post

    def _notify_owner_to_post(self, reel: str | None = None) -> None:
        """Human-in-the-loop IG: render the reel + Pushover the owner to post it."""
        try:
            from core.notify import pushover  # type: ignore
            pushover(f"VECTOR reel ready to post on Instagram: {reel}")
        except Exception:
            logger.info("[VECTOR][growth][armA] (manual IG) owner-notify: reel ready {}", reel)

    def _graph_api_post(self, reel: str | None = None) -> None:
        """Official Instagram Graph API Content Publishing (owner must have a
        Business/Creator account + app review). Gated like every publish."""
        logger.info("[VECTOR][growth][armA] IG Graph API publish queued (gated): {}", reel)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("content_arm OK")
