"""
Module: agents/learning/video_ingestor.py
District: learning | Focus: Download lecture videos, extract transcripts, summarize
"""

import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, subprocess, re
from typing import Optional


class VideoIngestor(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="VideoIngestor",
            district="learning",
            generation=1
        )
        self.capabilities = ["course", "ingest", "learn", "learning", "video"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        from core.runtime_paths import data_path

        self.download_dir = data_path("lectures")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir = data_path("transcripts")
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[VECTOR][learning] VideoIngestor ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def download_lecture(self, url: str) -> dict:
        logger.info(f"[VECTOR][learning] Downloading lecture from: {url}")
        self.add_lesson({"action": "download_lecture", "url": url})

        video_path = self.download_dir / f"lecture_{uuid.uuid4().hex[:8]}.mp4"

        # Caller-supplied URL: block SSRF targets / non-http schemes (a URL
        # starting with '-' also fails the scheme check, so it can never reach
        # yt-dlp as an option).
        from core.security.ssrf_guard import get_ssrf_guard
        check = get_ssrf_guard().check_url(url)
        if not check.safe:
            logger.warning("[VECTOR][learning] Download blocked by SSRF guard: {}", check.reason)
            return {"url": url, "video_path": None, "download_status": "failed",
                    "file_size_mb": 0, "error": f"blocked: {check.reason}"}

        if "youtube.com" in url or "youtu.be" in url:
            try:
                result = subprocess.run(
                    ["yt-dlp", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    proc = subprocess.run(
                        ["yt-dlp", "-o", str(video_path), "--", url],
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    if proc.returncode != 0:
                        logger.warning("[VECTOR][learning] yt-dlp failed: {}", proc.stderr[:200])
            except FileNotFoundError:
                logger.warning("[VECTOR][learning] yt-dlp not found, skipping download")
        else:
            try:
                import httpx
                with httpx.stream("GET", url, headers={"User-Agent": "VECTOR-VideoIngestor/1.0"}, timeout=300) as resp:
                    resp.raise_for_status()
                    with open(video_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
            except Exception as e:
                logger.error("[VECTOR][learning] Download failed: {}", e)
                video_path.unlink(missing_ok=True)

        ok = video_path.exists() and video_path.stat().st_size > 0
        if not ok:
            video_path.unlink(missing_ok=True)
        result = {
            "url": url,
            "video_path": str(video_path) if ok else None,
            "download_status": "success" if ok else "failed",
            "file_size_mb": round(video_path.stat().st_size / 1024 / 1024, 2) if ok else 0,
        }

        self.memory.store(
            event_type="lecture_downloaded" if ok else "lecture_download_failed",
            content=f"Downloaded lecture from {url}" if ok else f"Lecture download FAILED for {url}",
            tags=["learning", "video", "lecture"],
            context=result,
            source="VideoIngestor"
        )

        logger.info("[VECTOR][learning] Download status: {}", result["download_status"])
        return result

    def extract_transcript(self, video_path: str) -> dict:
        logger.info(f"[VECTOR][learning] Extracting transcript from: {video_path}")
        self.add_lesson({"action": "extract_transcript", "video": video_path})

        video_p = Path(video_path)
        if not video_p.exists():
            logger.error(f"[VECTOR][learning] Video file not found: {video_path}")
            return {"error": "Video file not found", "path": video_path}

        transcript_path = self.transcripts_dir / f"{video_p.stem}_transcript.txt"
        # whisper CLI names its output <stem>.txt, not <stem>_transcript.txt.
        whisper_txt = self.transcripts_dir / f"{video_p.stem}.txt"

        try:
            proc = subprocess.run(
                ["whisper", str(video_p.resolve()), "--output_dir", str(self.transcripts_dir),
                 "--model", "base", "--output_format", "txt"],
                capture_output=True,
                text=True,
                timeout=600
            )
        except FileNotFoundError:
            logger.warning("[VECTOR][learning] Whisper CLI not found")
            return {"error": "Whisper not installed (pip install openai-whisper)", "path": video_path}
        except Exception as e:
            logger.error("[VECTOR][learning] Whisper error: {}", e)
            return {"error": f"Transcript extraction failed: {e}", "path": video_path}
        if proc.returncode != 0:
            logger.warning("[VECTOR][learning] Whisper failed: {}", proc.stderr[:200])
            return {"error": f"Whisper failed: {proc.stderr[:200]}", "path": video_path}

        transcript = ""
        for cand in (whisper_txt, transcript_path):
            if cand.exists():
                transcript = cand.read_text(encoding="utf-8", errors="ignore")
                break
        if not transcript.strip():
            logger.warning("[VECTOR][learning] Whisper produced no transcript for {}", video_p.name)
            return {"error": "Whisper produced an empty or missing transcript", "path": video_path}
        if not transcript_path.exists():
            transcript_path.write_text(transcript, encoding="utf-8")

        result = {
            "video_path": video_path,
            "transcript_path": str(transcript_path),
            "transcript_preview": transcript[:500],
            "transcript_length": len(transcript),
        }

        self.memory.store(
            event_type="transcript_extracted",
            content=f"Extracted transcript from {video_p.name}",
            tags=["learning", "transcript", "video"],
            context=result,
            source="VideoIngestor"
        )

        return result

    def summarize_lecture(self, video_path: str) -> dict:
        logger.info(f"[VECTOR][learning] Summarizing lecture: {video_path}")
        self.add_lesson({"action": "summarize_lecture", "video": video_path})

        video_p = Path(video_path)
        transcript_path = self.transcripts_dir / f"{video_p.stem}_transcript.txt"

        transcript = transcript_path.read_text(encoding="utf-8", errors="ignore") if transcript_path.exists() else ""
        if not transcript.strip():
            logger.warning("[VECTOR][learning] No transcript for {}; not summarizing", video_p.name)
            return {"error": "No transcript available; run extract_transcript first", "video_path": video_path}

        max_chars = 3000
        transcript_snippet = transcript[:max_chars] if len(transcript) > max_chars else transcript

        prompt = f"""Summarize this lecture transcript. Provide:
1. A 3-sentence overview
2. 5 key takeaways
3. Important concepts covered
4. Recommended follow-up topics
Transcript: {transcript_snippet}"""
        summary = self._call_ollama(prompt)
        if not (summary or "").strip():
            logger.warning("[VECTOR][learning] Empty summary for {}", video_p.name)
            return {"error": "Summarization produced no output", "video_path": video_path}

        result = {
            "video_path": video_path,
            "video_name": video_p.name,
            "summary": summary,
            "transcript_length": len(transcript),
            "summarized_at": self.last_active,
        }

        self.memory.store(
            event_type="lecture_summarized",
            content=f"Summarized lecture: {video_p.name}",
            tags=["learning", "lecture", "summary"],
            context=result,
            source="VideoIngestor"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params", {}) or {}
        if hasattr(self, "ingest_video") and p.get("url"):
            result = await self.ingest_video(p["url"])
            return {"status": "ok", **result}
        if p.get("url"):
            # No ingest pipeline exists; never report an ignored URL as ok.
            return {"status": "not_implemented", "note": "VideoIngestor.ingest_video is not implemented"}
        return {"status": "ok", "agent": self.name}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = VideoIngestor()
    assert agent.district == "learning"

    result = agent.download_lecture("https://example.com/sample.mp4")
    assert "download_status" in result

    transcript = agent.extract_transcript("C:/Users/ARGHYA~1/AppData/Local/Temp/test_video.mp4")
    assert "error" in transcript or "transcript_preview" in transcript

    summary = agent.summarize_lecture("C:/Users/ARGHYA~1/AppData/Local/Temp/test_video.mp4")
    assert "summary" in summary

    print("✅ video_ingestor.py OK")
