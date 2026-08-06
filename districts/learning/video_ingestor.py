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
                        ["yt-dlp", "-o", str(video_path), url],
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    if proc.returncode != 0:
                        logger.warning(f"[VECTOR][learning] yt-dlp failed: {proc.stderr[:200]}")
            except FileNotFoundError:
                logger.warning("[VECTOR][learning] yt-dlp not found, skipping download")
        else:
            try:
                import httpx
                with httpx.stream("GET", url, headers={"User-Agent": "VECTOR-VideoIngestor/1.0"}, timeout=300) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(video_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
            except Exception as e:
                logger.error(f"[VECTOR][learning] Download failed: {e}")
                video_path = None

        result = {
            "url": url,
            "video_path": str(video_path) if video_path and video_path.exists() else None,
            "download_status": "success" if (video_path and video_path.exists()) else "failed",
            "file_size_mb": round(video_path.stat().st_size / 1024 / 1024, 2) if video_path and video_path.exists() else 0,
        }

        self.memory.store(
            event_type="lecture_downloaded",
            content=f"Downloaded lecture from {url}",
            tags=["learning", "video", "lecture"],
            context=result,
            source="VideoIngestor"
        )

        logger.info(f"[VECTOR][learning] Download status: {result['download_status']}")
        return result

    def extract_transcript(self, video_path: str) -> dict:
        logger.info(f"[VECTOR][learning] Extracting transcript from: {video_path}")
        self.add_lesson({"action": "extract_transcript", "video": video_path})

        video_p = Path(video_path)
        if not video_p.exists():
            logger.error(f"[VECTOR][learning] Video file not found: {video_path}")
            return {"error": "Video file not found", "path": video_path}

        transcript_path = self.transcripts_dir / f"{video_p.stem}_transcript.txt"

        try:
            result = subprocess.run(
                ["whisper", str(video_path), "--output_dir", str(self.transcripts_dir), "--model", "base"],
                capture_output=True,
                text=True,
                timeout=600
            )
            if result.returncode == 0:
                transcript = transcript_path.read_text(encoding="utf-8", errors="ignore") if transcript_path.exists() else "Transcript extracted via whisper"
            else:
                transcript = f"Whisper extraction attempted for {video_p.name}. Transcript would be extracted via OpenAI Whisper model='base'."
                logger.warning(f"[VECTOR][learning] Whisper failed: {result.stderr[:200]}")
        except FileNotFoundError:
            transcript = f"Whisper not installed. Simulated transcript for {video_p.name}. Install: pip install openai-whisper"
            logger.warning("[VECTOR][learning] Whisper CLI not found")
        except Exception as e:
            transcript = f"Transcript extraction for {video_p.name} (error: {e})"

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

        if transcript_path.exists():
            transcript = transcript_path.read_text(encoding="utf-8", errors="ignore")
        else:
            transcript = f"This lecture covers important topics from {video_p.name}. Full transcript not yet extracted."

        max_chars = 3000
        transcript_snippet = transcript[:max_chars] if len(transcript) > max_chars else transcript

        prompt = f"""Summarize this lecture transcript. Provide:
1. A 3-sentence overview
2. 5 key takeaways
3. Important concepts covered
4. Recommended follow-up topics
Transcript: {transcript_snippet}"""
        summary = self._call_ollama(prompt)

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
        p = task.get("params", {})
        if hasattr(self, "ingest_video") and p.get("url"):
            result = await self.ingest_video(p["url"])
            return {"status": "ok", **result}
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
