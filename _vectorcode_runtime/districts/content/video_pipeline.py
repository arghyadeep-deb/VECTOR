"""
VECTOR VideoPipelineAgent — District 18: content
Full autonomous video creation + upload pipeline.

Chain:
  topic idea → script → TTS narration → YouTube HTML composition
  → render MP4 (RTX GPU) → burn captions → 30min safety window
  → auto-upload YouTube + Instagram Reel

Nightly cron (22:00): autonomous_loop._fire_vnative_cron_jobs
Governor routes: make_video, create_video, upload_video, video_pipeline, daily_video

Usage (direct):
    agent = VideoPipelineAgent()
    result = asyncio.run(agent.create_and_upload("Top 5 AI tools this week"))

Usage (governor):
    governor.dispatch({"type": "make_video", "params": {"topic": "AI in 2026", "niche": "AI"}})
"""

from __future__ import annotations

from core.memory.db_utils import apply_pragmas, configured_db_path
import asyncio
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger

# ── Job tracking (SQLite) ─────────────────────────────────────────────────────

# Tests write here too; VECTOR_TEST_DATA_DIR keeps them out of the live queue.
_TEST_DIR = os.environ.get("VECTOR_TEST_DATA_DIR")
_DB_PATH = (Path(_TEST_DIR) / "content_jobs.db") if _TEST_DIR else configured_db_path().with_name("content_jobs.db")
_DB_LOCK = threading.RLock()

def _get_job_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    apply_pragmas(conn)
    return conn

def _init_db() -> None:
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS content_jobs (
                    id TEXT PRIMARY KEY,
                    topic TEXT,
                    niche TEXT,
                    platform TEXT,
                    status TEXT,
                    stage_pct INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    youtube_url TEXT,
                    instagram_url TEXT,
                    video_path TEXT,
                    error TEXT,
                    upload_after TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

def _upsert_job(job: dict) -> None:
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO content_jobs
                (id, topic, niche, platform, status, stage_pct, created_at, updated_at,
                 youtube_url, instagram_url, video_path, error, upload_after)
                VALUES (:id,:topic,:niche,:platform,:status,:stage_pct,:created_at,:updated_at,
                        :youtube_url,:instagram_url,:video_path,:error,:upload_after)
            """, job)
            conn.commit()
        finally:
            conn.close()

def get_job_queue(limit: int = 20) -> list[dict]:
    _init_db()
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM content_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]

def list_resumable_jobs(limit: int = 20) -> list[dict]:
    """Errored jobs whose finished render still exists on disk. Resuming their upload is an
    owner action through the existing gated upload path; nothing here uploads anything."""
    return [j for j in get_job_queue(limit=limit * 5)
            if j.get("status") == "error" and j.get("video_path") and Path(j["video_path"]).exists()][:limit]


def get_job_history(limit: int = 10) -> list[dict]:
    _init_db()
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM content_jobs WHERE status IN ('done','error','cancelled') "
                "ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]

def cancel_job(job_id: str) -> bool:
    _init_db()
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.execute(
                "UPDATE content_jobs SET status='cancelled', updated_at=? WHERE id=? AND status='uploading'",
                (datetime.datetime.now(datetime.timezone.utc).isoformat(), job_id)
            )
            conn.commit()
        finally:
            conn.close()
    return True


def recover_interrupted_jobs(max_age_hours: float = 2.0) -> int:
    """Mark stale in-flight jobs as errored (2026-07-19).

    If the process dies during render/safety-window/upload, jobs sat at
    'uploading' (or another non-terminal stage) forever — with the rendered
    video usually gone from %TEMP%. On startup, anything non-terminal that
    hasn't been touched in `max_age_hours` is marked 'error' so the queue
    tells the truth. Returns number of jobs recovered.
    """
    _init_db()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=max_age_hours)
    ).isoformat()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    n = 0
    with _DB_LOCK:
        conn = _get_job_conn()
        try:
            conn.row_factory = sqlite3.Row
            stale = conn.execute(
                "SELECT id, video_path FROM content_jobs "
                "WHERE status NOT IN ('done','error','cancelled','pending') AND updated_at < ?",
                (cutoff,),
            ).fetchall()
            for row in stale:
                # A finished render persisted to renders/ survives the restart: say so, so the
                # owner can resume the (gated) upload instead of regenerating the video.
                saved = row["video_path"] if row["video_path"] and Path(row["video_path"]).exists() else ""
                note = ("interrupted — process restarted mid-pipeline (auto-recovery)"
                        + (f" (render saved: {saved})" if saved else ""))
                conn.execute(
                    "UPDATE content_jobs SET status='error', error=?, updated_at=? WHERE id=?",
                    (note, now, row["id"]),
                )
                n += 1
            conn.commit()
        finally:
            conn.close()
    if n:
        logger.warning("[VECTOR][video_pipeline] recovered {} interrupted job(s)", n)
    return n

# ── Pipeline Agent ────────────────────────────────────────────────────────────

class VideoPipelineAgent(AgentBase):
    """
    Orchestrates the full video creation + upload pipeline.
    Chains ScriptGenerator → VoiceGenerator → VectorComposer → CaptionGenerator
    → VideoMerger → Uploader with a 30-minute safety window before upload.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="VideoPipelineAgent",
            district="content",
            generation=generation,
        )
        self.capabilities = ["content", "create_and_upload", "instagram", "job_history", "job_queue", "job_status", "pipeline", "posted", "video", "youtube"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        _init_db()
        try:
            recover_interrupted_jobs()
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] stale-job recovery failed: {}", e)
        logger.info("[VECTOR][video_pipeline] ready gen={} hp={}", generation, self.health_points)

    # ── Top-level entry point ─────────────────────────────────────────────────

    async def create_and_upload(
        self,
        topic: Optional[str] = None,
        platform: str = "both",       # "youtube" | "instagram" | "both"
        niche: str = "AI",
        duration_min: float = 8.0,
        dry_run: bool = False,         # skip upload, just render
    ) -> dict:
        """
        Full pipeline: topic → script → voice → render → captions → upload.
        Returns dict with status, youtube_url, instagram_url, video_path.
        """
        job_id = str(uuid.uuid4())
        now    = datetime.datetime.now(datetime.timezone.utc).isoformat()
        delay  = CONFIG.get("video_upload_delay_minutes", 30)
        upload_after = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=delay)
        ).isoformat()

        job = {
            "id": job_id, "topic": topic or "auto", "niche": niche,
            "platform": platform, "status": "pending", "stage_pct": 0,
            "created_at": now, "updated_at": now,
            "youtube_url": None, "instagram_url": None,
            "video_path": None, "error": None, "upload_after": upload_after,
        }
        _upsert_job(job)

        try:
            with tempfile.TemporaryDirectory(prefix="vector_video_") as tmp:
                # Stage 1: Pick topic
                topic = await self._pick_topic(topic, niche)
                self._update_job(job, status="scripting", stage_pct=10, topic=topic)

                # Stage 2: Script
                script_data = await self._generate_script(topic, duration_min)
                self._update_job(job, status="narrating", stage_pct=25)

                # Stage 3: TTS narration
                narration_path = os.path.join(tmp, "narration.wav")
                narration_text = self._extract_narration(script_data)
                await self._generate_narration(narration_text, narration_path)
                self._update_job(job, status="rendering", stage_pct=40)

                # Stage 3.5: AI thumbnail (optional — uses Muapi.ai if key set)
                ai_thumbnail_url = await self._generate_ai_thumbnail(script_data, niche)

                # Stage 3.7: Lip sync avatar (optional — uses Muapi.ai lipsync if configured)
                lipsync_path = await self._generate_lipsync_avatar(narration_path)

                # Stage 4: Render composition → MP4
                comp_path  = os.path.join(tmp, "composition.html")
                raw_mp4    = os.path.join(tmp, "raw.mp4")
                total_dur  = self._script_duration_seconds(script_data)
                sections   = self._script_to_sections(script_data)
                title      = script_data.get("title", topic)

                from core.video.vector_composer import CompositionTemplate, VectorComposer, ComposerJob
                from core.video.composition_types import Fps
                CompositionTemplate.youtube_video(
                    title=title,
                    sections=sections,
                    channel_name=CONFIG.get("content_niche", niche) + " by VECTOR",
                    niche=niche,
                    output_path=comp_path,
                )
                # ai_thumbnail_url and lipsync_path are available for future template injection
                composer = VectorComposer(
                    on_progress=lambda p, m: self._update_job(
                        job, stage_pct=int(40 + p * 30)
                    )
                )
                compose_job = ComposerJob(
                    composition_path=comp_path,
                    output_path=raw_mp4,
                    fps=Fps(30, 1),
                    resolution="landscape",
                    duration_seconds=total_dur,
                    quality="standard",
                    use_gpu=False,
                    narration=narration_text,
                )
                await composer.render(compose_job)
                self._update_job(job, status="captioning", stage_pct=72)

                # Stage 5: Captions → burn into video
                final_mp4 = os.path.join(tmp, "final.mp4")
                srt_path  = os.path.join(tmp, "captions.srt")
                self._write_simple_srt(sections, srt_path)
                final_mp4 = await self._burn_captions(raw_mp4, srt_path, final_mp4)

                # Persist the finished render OUTSIDE the temp dir (2026-07-19):
                # jobs interrupted during the 30-min safety window used to lose
                # their video forever — %TEMP% was cleaned and the job sat at
                # 'uploading' 85% with a dangling path (two real jobs found
                # stuck like this from Jul 13 + Jul 15).
                try:
                    renders_dir = Path(__file__).resolve().parents[2] / "renders"
                    renders_dir.mkdir(exist_ok=True)
                    persistent_mp4 = str(renders_dir / f"{job_id}.mp4")
                    shutil.copy2(final_mp4, persistent_mp4)
                    final_mp4 = persistent_mp4
                except Exception as e:
                    logger.warning("[VECTOR][video_pipeline] could not persist render: {}", e)

                self._update_job(job, status="uploading", stage_pct=85, video_path=final_mp4)

                # Stage 6: Safety window notification
                if not dry_run:
                    await self._notify_pending_upload(title, job_id, delay)
                    await self._wait_for_safety_window(job_id, delay)

                # Re-check: was it cancelled during window?
                current = self._get_job(job_id)
                if current and current["status"] == "cancelled":
                    logger.info("[VECTOR][video_pipeline] upload cancelled by owner: {}", title)
                    self.deduct_points(5, "upload cancelled")
                    return {"status": "cancelled", "job_id": job_id, "title": title}

                # Stage 7: Upload
                youtube_url = instagram_url = None
                if not dry_run:
                    tags = script_data.get("tags", [niche, "AI", "tutorial"])
                    description = script_data.get("description", title)

                    if platform in ("youtube", "both"):
                        youtube_url = await self._upload_youtube(
                            final_mp4, title, description, tags
                        )
                    if platform in ("instagram", "both"):
                        instagram_url = await self._upload_instagram(
                            final_mp4, title, tags
                        )

                self._update_job(
                    job, status="done", stage_pct=100,
                    youtube_url=youtube_url, instagram_url=instagram_url,
                )
                self.award_points(100, f"video pipeline complete: {title}")

                self._memory.store(
                    event_type="video_created",
                    content=f"VideoPipeline: '{title}' → {youtube_url or instagram_url or 'dry_run'}",
                    tags=["content", "video", niche, "pipeline"],
                    source="video_pipeline",
                )

                if not dry_run and (youtube_url or instagram_url):
                    await self._notify_upload_complete(title, youtube_url, instagram_url)

                return {
                    "status": "ok",
                    "job_id": job_id,
                    "title": title,
                    "youtube_url": youtube_url,
                    "instagram_url": instagram_url,
                    "video_path": final_mp4 if dry_run else None,
                    "duration_seconds": total_dur,
                }

        except Exception as e:
            logger.error("[VECTOR][video_pipeline] pipeline failed: {}", e)
            self._update_job(job, status="error", error=str(e)[:500])
            self.deduct_points(30, f"pipeline failed: {e}")
            return {"status": "error", "error": str(e), "job_id": job_id}

    # ── Media Studio hooks ────────────────────────────────────────────────────

    async def _generate_ai_thumbnail(self, script_data: dict, niche: str) -> str:
        """Generate an AI thumbnail image for the video. Returns URL or empty string."""
        try:
            from core.media.generative_studio import GenerativeStudio
            studio = GenerativeStudio()
            if not studio._wan2gp._base_url and not studio._local.is_available():
                return ""
            title = script_data.get("title", "")
            prompt = (
                f"Cinematic YouTube thumbnail for a {niche} video titled '{title}'. "
                "Bold text, high contrast, professional composition, 16:9 aspect ratio."
            )
            result = await studio.generate_image(prompt, model="flux-dev", aspect_ratio="16:9")
            url = result.get("url") or result.get("image_path") or ""
            if url:
                logger.info("[VECTOR][video_pipeline] AI thumbnail generated: {}", url[:80])
            return url
        except Exception as e:
            logger.debug("[VECTOR][video_pipeline] AI thumbnail skipped: {}", e)
            return ""

    async def _generate_lipsync_avatar(self, narration_path: str) -> str:
        """Generate a lipsync avatar video from narration. Returns local path or empty string."""
        try:
            media_cfg = CONFIG.get("media", {})
            if not media_cfg.get("use_lipsync_avatar"):
                return ""
            portrait = media_cfg.get("portrait_image", "")
            if not portrait or not narration_path or not Path(narration_path).exists():
                return ""
            from core.media.generative_studio import GenerativeStudio
            studio = GenerativeStudio()
            result = await studio.lipsync(portrait, narration_path)
            return result.get("url") or ""
        except Exception as e:
            logger.debug("[VECTOR][video_pipeline] Lipsync avatar skipped: {}", e)
            return ""

    # ── Stage implementations ─────────────────────────────────────────────────

    async def _pick_topic(self, topic: Optional[str], niche: str) -> str:
        if topic:
            return topic
        try:
            from districts.startups.market_scanner import MarketScanner
            scanner = MarketScanner()
            data = await scanner.scan_market(niche) if asyncio.iscoroutinefunction(scanner.scan_market) \
                else scanner.scan_market(niche)
            if isinstance(data, dict) and data.get("emerging_niches"):
                niches = data["emerging_niches"]
                if isinstance(niches, list) and niches:
                    return str(niches[0])
            return f"Top 5 {niche} breakthroughs this week"
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] market scan failed: {} — using default", e)
            return f"Top {niche} trends you need to know"

    async def _generate_script(self, topic: str, duration_min: float) -> dict:
        try:
            from districts.content.script_generator import ScriptGenerator
            gen = ScriptGenerator()
            result = await gen.generate_script(topic, duration_min=duration_min, script_type="youtube_tutorial")
            if isinstance(result, dict) and result.get("status") == "success":
                script = result.get("script", {})
                # Generate supporting metadata
                desc_data = gen.generate_video_description(str(script), "youtube") \
                    if hasattr(gen, "generate_video_description") else {}
                tags_data = []
                try:
                    from districts.content.video_generator import VideoGenerator
                    vg = VideoGenerator()
                    tags_data = vg.generate_tags(topic, count=15)
                    if isinstance(tags_data, dict):
                        tags_data = tags_data.get("tags", [])
                except Exception:
                    tags_data = [topic, "AI", "tutorial"]

                return {
                    "title": topic,
                    "script": script,
                    "description": desc_data.get("description", topic) if isinstance(desc_data, dict) else topic,
                    "tags": tags_data[:15] if tags_data else [topic],
                    "duration_min": duration_min,
                }
            return {"title": topic, "script": {}, "description": topic,
                    "tags": [topic], "duration_min": duration_min}
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] script gen failed: {}", e)
            return {"title": topic, "script": {}, "description": topic,
                    "tags": [topic], "duration_min": duration_min}

    async def _generate_narration(self, text: str, output_path: str) -> Optional[str]:
        try:
            from districts.content.voice_generator import VoiceGenerator
            vg = VoiceGenerator()
            # generate_voice() is synchronous and CPU/GPU heavy: awaiting it raised "object dict can't be used in
            # 'await' expression" (caught below), so narration was never produced. Run it off the event loop instead;
            # no voice_name means VECTOR's configured voice (owner rule: male voices only).
            result = await asyncio.to_thread(vg.generate_voice, text, None, output_path)
            if isinstance(result, dict) and result.get("status") == "success":
                return output_path
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] voice gen failed: {}", e)
        return None

    async def _burn_captions(self, video_path: str, srt_path: str, output_path: str) -> str:
        try:
            from districts.content.video_merger import VideoMerger
            merger = VideoMerger()
            result = merger.add_subtitles(video_path, srt_path, output_path, style="standard")
            if isinstance(result, dict) and result.get("status") == "success":
                return output_path
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] caption burn failed: {} — using raw", e)
        return video_path

    async def _upload_youtube(self, path: str, title: str, desc: str, tags: list) -> Optional[str]:
        try:
            # Honor growth.youtube_mode (2026-07-19): config says "phone"
            # (drive the real app over ADB — no OAuth), but this method always
            # used the API Uploader, which silently SIMULATES uploads when no
            # Google OAuth creds exist. Result: pipeline reported success,
            # nothing ever reached the channel.
            mode = str(CONFIG.get("growth", {}).get("youtube_mode", "api")).lower()
            if mode == "phone":
                from districts.content.phone_poster import PhonePoster
                result = await PhonePoster().post_youtube(path, caption=title)
                if isinstance(result, dict) and result.get("status") in ("posted", "pending_upload", "pending_share"):
                    logger.info("[VECTOR][video_pipeline] YouTube phone post: {}", result.get("reason", "ok"))
                    return result.get("url")
                logger.warning("[VECTOR][video_pipeline] YouTube phone post failed: {}", result)
                return None
            from districts.content.uploader import Uploader
            up = Uploader()
            result = await up.upload_to_youtube(path, title, desc, tags, privacy="public")
            if isinstance(result, dict):
                vid_id = result.get("video_id") or result.get("id")
                if vid_id and not vid_id.startswith("sim_"):
                    return f"https://youtube.com/watch?v={vid_id}"
                logger.warning("[VECTOR][video_pipeline] YouTube simulation — no real credentials")
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] YouTube upload failed: {}", e)
        return None

    async def _upload_instagram(self, path: str, title: str, tags: list) -> Optional[str]:
        try:
            hashtags = [f"#{t.replace(' ','')}" for t in tags[:10]]
            caption = f"{title}\n\n{' '.join(hashtags)}"
            # Honor growth.instagram_mode (2026-07-19) — see _upload_youtube.
            mode = str(CONFIG.get("growth", {}).get("instagram_mode", "graph_api")).lower()
            if mode == "phone":
                from districts.content.phone_poster import PhonePoster
                result = await PhonePoster().post_instagram(path, caption=caption)
                if isinstance(result, dict) and result.get("status") in ("posted", "pending_upload", "pending_share"):
                    logger.info("[VECTOR][video_pipeline] Instagram phone post: {}", result.get("reason", "ok"))
                    return result.get("url")
                logger.warning("[VECTOR][video_pipeline] Instagram phone post failed: {}", result)
                return None
            from districts.content.uploader import Uploader
            up = Uploader()
            result = await up.upload_to_instagram(path, caption, hashtags)
            if isinstance(result, dict):
                media_id = result.get("media_id") or result.get("id")
                if media_id and not str(media_id).startswith("sim_"):
                    return f"https://instagram.com/p/{media_id}"
                logger.warning("[VECTOR][video_pipeline] Instagram simulation — no real credentials")
        except Exception as e:
            logger.warning("[VECTOR][video_pipeline] Instagram upload failed: {}", e)
        return None

    # ── Safety window ─────────────────────────────────────────────────────────

    async def _wait_for_safety_window(self, job_id: str, delay_min: int) -> None:
        if delay_min <= 0:
            return
        logger.info("[VECTOR][video_pipeline] safety window: {}min before upload", delay_min)
        waited = 0
        while waited < delay_min * 60:
            await asyncio.sleep(30)
            waited += 30
            current = self._get_job(job_id)
            if current and current["status"] == "cancelled":
                return

    async def _notify_pending_upload(self, title: str, job_id: str, delay: int) -> None:
        # Sends via Telegram now (2026-10-30, owner decision — Pushover is a
        # paid service); see core/notify.py for the shared implementation.
        try:
            from core.notify import send_telegram
            token = CONFIG["api_keys"].get("telegram_bot_token", "")
            chat_id = CONFIG["api_keys"].get("telegram_chat_id", "")
            if token and chat_id:
                await send_telegram(
                    f"VECTOR: Video Ready\n'{title}' renders done. "
                    f"Uploading in {delay}min. Cancel: send 'cancel {job_id[:8]}' to VECTOR.",
                    priority=0,
                )
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
        logger.info("[VECTOR][video_pipeline] notified owner: '{}' uploading in {}min", title, delay)

    async def _notify_upload_complete(self, title: str, yt_url: Optional[str], ig_url: Optional[str]) -> None:
        try:
            from core.notify import send_telegram
            token = CONFIG["api_keys"].get("telegram_bot_token", "")
            chat_id = CONFIG["api_keys"].get("telegram_chat_id", "")
            if token and chat_id:
                links = " | ".join(filter(None, [yt_url, ig_url]))
                await send_telegram(
                    f"VECTOR: Uploaded!\n'{title}' is live!\n{links}",
                    priority=0, url=yt_url or ig_url or "", url_title="Watch",
                )
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

    # ── Helper utilities ──────────────────────────────────────────────────────

    def _extract_narration(self, script_data: dict) -> str:
        script = script_data.get("script", {})
        if isinstance(script, dict):
            parts = []
            for key in ["hook", "intro", "main_content", "sections", "summary", "cta"]:
                val = script.get(key, "")
                if isinstance(val, str):
                    parts.append(val)
                elif isinstance(val, list):
                    parts.extend(str(v) for v in val)
                elif isinstance(val, dict):
                    parts.append(str(val.get("content", val.get("text", ""))))
            text = " ".join(p for p in parts if p)
            return text[:3000] or script_data.get("title", "")
        if isinstance(script, str):
            return script[:3000]
        return script_data.get("title", "")

    def _script_to_sections(self, script_data: dict) -> list[dict]:
        script = script_data.get("script", {})
        duration_min = script_data.get("duration_min", 8.0)
        sections = []

        if isinstance(script, dict):
            raw_sections = script.get("sections", script.get("main_content", []))
            if isinstance(raw_sections, list):
                for sec in raw_sections[:8]:
                    if isinstance(sec, dict):
                        sections.append({
                            "heading": str(sec.get("title", sec.get("heading", "Key Point"))),
                            "body":    str(sec.get("content", sec.get("body", "")))[:300],
                            "duration": float(sec.get("duration", (duration_min * 60 - 8) / max(len(raw_sections), 1))),
                        })

        if not sections:
            # Fallback: single section with narration text
            narration = self._extract_narration(script_data)
            words = narration.split()
            chunk = 50
            for i in range(0, min(len(words), 400), chunk):
                sections.append({
                    "heading": f"Part {i//chunk + 1}",
                    "body": " ".join(words[i:i+chunk]),
                    "duration": 8.0,
                })

        return sections or [{"heading": script_data.get("title", ""), "body": "", "duration": 8.0}]

    def _script_duration_seconds(self, script_data: dict) -> float:
        dur_min = script_data.get("duration_min", 8.0)
        sections = self._script_to_sections(script_data)
        section_total = sum(s.get("duration", 8.0) for s in sections)
        return max(section_total + 8.0, dur_min * 60)  # +8 for intro+outro

    def _write_simple_srt(self, sections: list[dict], srt_path: str) -> None:
        lines = []
        t = 3.0  # after intro
        for i, sec in enumerate(sections, 1):
            start = t
            dur = sec.get("duration", 8.0)
            end = start + dur
            lines.append(f"{i}")
            lines.append(f"{self._srt_ts(start)} --> {self._srt_ts(end)}")
            lines.append(sec.get("heading", ""))
            lines.append("")
            t += dur
        Path(srt_path).write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _srt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _update_job(self, job: dict, **kwargs) -> None:
        job.update(kwargs)
        job["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        _upsert_job(job)

    def _get_job(self, job_id: str) -> Optional[dict]:
        with _DB_LOCK:
            conn = _get_job_conn()
            try:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM content_jobs WHERE id=?", (job_id,)).fetchone()
            finally:
                conn.close()
        return dict(row) if row else None

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def answer_content_question(self, query: str) -> str:
        """Answer a free-text question instead of silently kicking off the
        real autonomous video creation + auto-upload-to-YouTube/Instagram
        pipeline for any content-district message with no explicit type
        (KNOWN_ISSUES bug pattern — the highest-risk shape: a real,
        unrelated, potentially public-facing side effect from a stray
        conversational message, the same class as the already-fixed
        karpathy_lab/autoresearch_runner training+commit bug)."""
        context = (
            "VideoPipelineAgent runs the full topic -> script -> TTS -> "
            "render -> caption -> upload pipeline for YouTube/Instagram. "
            "It does not have cached results to report without actually "
            "running a job."
        )
        prompt = (
            "You are VECTOR's VideoPipelineAgent in the content district. "
            "Answer the owner's question using this real context — do not "
            f"invent data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning(f"[VECTOR][video_pipeline] answer_content_question failed: {e}")
            return context

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["create_and_upload", "job_status", "job_queue", "job_history"]

        if task_type == "job_status":
            job = self._get_job(p.get("job_id", ""))
            if job is None:
                return {"status": "error", "error": "job not found"}
            return {"status": "ok", "job": job}
        if task_type == "job_queue":
            return {"status": "ok", "jobs": get_job_queue(p.get("limit", 20))}
        if task_type == "job_history":
            return {"status": "ok", "jobs": get_job_history(p.get("limit", 10))}

        # KNOWN_ISSUES bug pattern: an empty/unmatched task_type (e.g. a
        # stray conversational question routed here with no real "type")
        # used to unconditionally kick off the real video-generation +
        # auto-upload pipeline. A genuinely content-free structured call
        # (the documented "create_and_upload"/"" default) still runs it
        # exactly as before; real free text with no explicit topic gets
        # answered in words instead.
        #
        # 2026-08-05: this gate only fired when task_type was the EXACT
        # empty string. Real chat dispatch always supplies a non-empty,
        # classifier-invented task_type (e.g. "ask_video_pipeline"), so
        # "what's a good topic for my next AI video?" never matched and fell
        # through to the unhandled-type error instead of getting a safe
        # answer — a narrower variant of the same bug class. Broadened to
        # fire on ANY unmatched task_type, not just "". This makes the
        # pipeline safer, not less safe: create_and_upload (the real
        # render+upload job) still only fires on an EXACT
        # "create_and_upload"/"" match below — unchanged.
        query = (
            p.get("query")
            or p.get("content")
            or task.get("query")
            or task.get("text")
            or ""
        ).strip()
        if (
            query
            and not p.get("topic")
            and task_type not in ("create_and_upload", "job_status", "job_queue", "job_history")
        ):
            answer = await self.answer_content_question(query)
            if answer:
                return {"status": "ok", "response": answer}

        if task_type in ("create_and_upload", ""):
            return await self.create_and_upload(
                topic=p.get("topic"),
                platform=p.get("platform", "both"),
                niche=p.get("niche", CONFIG.get("content_niche", "AI")),
                duration_min=float(p.get("duration_min", 8.0)),
                dry_run=bool(p.get("dry_run", False)),
            )

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][video_pipeline] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][video_pipeline] died — HP=0")

# ── Nightly cron job function (called by autonomous_loop) ─────────────────────

async def job_generate_daily_video() -> None:
    """Called by autonomous_loop nightly at 22:00."""
    logger.info("[VECTOR][cron] daily video generation starting")
    niche = CONFIG.get("content_niche", "AI")
    agent = VideoPipelineAgent()
    result = await agent.create_and_upload(topic=None, platform="both", niche=niche)
    logger.info("[VECTOR][cron] daily video done: status={} url={}",
                result.get("status"), result.get("youtube_url"))

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = VideoPipelineAgent()
        assert agent.health_points == 500
        assert agent.name == "VideoPipelineAgent"
        assert agent.district == "content"

        # Test job tracking
        job = {
            "id": "test-001", "topic": "AI tools", "niche": "AI",
            "platform": "both", "status": "pending", "stage_pct": 0,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "youtube_url": None, "instagram_url": None,
            "video_path": None, "error": None, "upload_after": None,
        }
        _upsert_job(job)
        retrieved = agent._get_job("test-001")
        assert retrieved is not None
        assert retrieved["topic"] == "AI tools"

        # Test section extraction
        script_data = {
            "title": "Top 5 AI tools",
            "script": {
                "sections": [
                    {"title": "GPT-4o", "content": "OpenAI released...", "duration": 60},
                    {"title": "Claude 3", "content": "Anthropic's model...", "duration": 60},
                ]
            },
            "duration_min": 3.0,
        }
        sections = agent._script_to_sections(script_data)
        assert len(sections) == 2
        assert sections[0]["heading"] == "GPT-4o"

        # Test SRT generation
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            srt = os.path.join(tmp, "test.srt")
            agent._write_simple_srt(sections, srt)
            content = open(srt, encoding="utf-8").read()
            assert "GPT-4o" in content
            assert "-->" in content

        # Test youtube_video template
        from core.video.vector_composer import CompositionTemplate
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "yt.html")
            CompositionTemplate.youtube_video(
                title="Top 5 AI tools",
                sections=sections,
                niche="AI",
                output_path=html_path,
            )
            html = open(html_path, encoding="utf-8").read()
            assert "Top 5 AI tools" in html
            assert "window.__vector" in html
            assert "GPT-4o" in html

        print(f"OK video_pipeline.py HP={agent.health_points}")

    asyncio.run(_smoke())
