"""
VECTOR Stealth Browser — YouTube Transcript Extraction
Two-mode transcript extraction:
  Mode 1 (fast, free): yt-dlp subprocess — no browser needed
  Mode 2 (browser fallback): StealthBrowserClient → /youtube/transcript endpoint

Usage:
    result = asyncio.run(get_youtube_transcript("https://youtu.be/dQw4w9WgXcQ"))
    logger.info(result["transcript"])

"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from typing import Optional

from loguru import logger


def _is_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url, re.IGNORECASE))


def _extract_video_id(url: str) -> str | None:
    patterns = [
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


# â”€â”€ Mode 1: yt-dlp â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _yt_dlp_available() -> bool:
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _extract_via_ytdlp(url: str) -> dict | None:
    """Extract transcript using yt-dlp subprocess (fast, no browser needed)."""
    try:
        # url is caller-supplied and reaches yt-dlp as a bare positional argv
        # (reachable via Governor dispatch -> districts/research/
        # stealth_scout_agent.py's youtube_transcript action). _is_youtube_url()
        # only checks substring presence anywhere in the string, so it does
        # NOT stop a value starting with "-" -- e.g. "--exec=<cmd> #youtube.com"
        # would be parsed as a yt-dlp option, and --exec runs an arbitrary
        # shell command after "download" (real RCE). Same argument-injection
        # shape fixed 25+ times elsewhere this cycle (git tools, mcp_tools).
        if url.startswith("-"):
            logger.warning("[VECTOR][transcripts] rejected option-like url: {}", url[:60])
            return None
        # Get video info + auto-generated subtitles
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-subs",
                "--sub-format", "vtt",
                "--sub-langs", "en.*",
                "--skip-download",
                "--print-json",
                "--no-playlist",
                "--",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.debug("[VECTOR][transcripts] yt-dlp failed: {}", result.stderr[:100])
            return None

        info = json.loads(result.stdout.strip().split("\n")[-1])

        # Try to get transcript from subtitles
        transcript_text = ""
        subs = info.get("requested_subtitles") or info.get("subtitles") or {}
        if not subs:
            # No subs available
            return {
                "url": url,
                "video_id": info.get("id"),
                "title": info.get("title", ""),
                "duration": info.get("duration"),
                "transcript": "",
                "chapters": info.get("chapters", []),
                "source": "yt-dlp",
                "error": "no subtitles available",
            }

        # Parse VTT format from the first available subtitle
        for lang, sub_info in subs.items():
            if isinstance(sub_info, list):
                sub_info = sub_info[0]
            sub_url = sub_info.get("url", "")
            if sub_url:
                try:
                    import httpx
                    vtt = httpx.get(sub_url, timeout=15.0).text
                    # Strip VTT markup → plain text
                    lines = []
                    for line in vtt.split("\n"):
                        line = line.strip()
                        if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                            continue
                        # Remove VTT tags
                        line = re.sub(r"<[^>]+>", "", line)
                        line = re.sub(r"&amp;", "&", line)
                        line = re.sub(r"&lt;", "<", line)
                        line = re.sub(r"&gt;", ">", line)
                        if line and line not in lines[-3:]:  # simple dedup
                            lines.append(line)
                    transcript_text = " ".join(lines)
                    break
                except Exception as e:
                    logger.warning("[VECTOR][transcripts] subtitle fetch/parse failed for {}: {}", sub_url[:60], e)

        return {
            "url": url,
            "video_id": info.get("id"),
            "title": info.get("title", ""),
            "duration": info.get("duration"),
            "transcript": transcript_text,
            "chapters": info.get("chapters", []),
            "source": "yt-dlp",
        }

    except Exception as e:
        logger.debug("[VECTOR][transcripts] yt-dlp error: {}", e)
        return None


# â”€â”€ Mode 2: Browser fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _extract_via_browser(url: str) -> dict | None:
    """Extract transcript via stealth browser server's /youtube/transcript endpoint."""
    try:
        from core.stealth_browser.client import StealthBrowserClient
        async with StealthBrowserClient() as client:
            healthy = await client.is_healthy()
            if not healthy:
                logger.debug("[VECTOR][transcripts] stealth server not running — skipping browser fallback")
                return None
            result = await client.youtube_transcript(url)
            result["source"] = "browser"
            return result
    except Exception as e:
        logger.debug("[VECTOR][transcripts] browser transcript failed: {}", e)
        return None


# â”€â”€ Main entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def get_youtube_transcript(
    url: str,
    prefer_yt_dlp: bool = True,
) -> dict:
    """
    Extract YouTube video transcript/captions.

    Args:
        url: YouTube video URL
        prefer_yt_dlp: try yt-dlp first (fast, no browser) then browser fallback

    Returns:
        {url, video_id, title, duration, transcript, chapters, source}
    """
    if not _is_youtube_url(url):
        return {"url": url, "error": "not a YouTube URL", "transcript": ""}

    video_id = _extract_video_id(url)
    logger.info("[VECTOR][transcripts] extracting transcript for {}", video_id or url[:60])

    if prefer_yt_dlp and _yt_dlp_available():
        result = _extract_via_ytdlp(url)
        if result and result.get("transcript"):
            logger.info("[VECTOR][transcripts] got {} chars via yt-dlp", len(result["transcript"]))
            return result

    # Browser fallback
    result = await _extract_via_browser(url)
    if result:
        logger.info("[VECTOR][transcripts] got transcript via browser")
        return result

    # yt-dlp without transcript (metadata only)
    if _yt_dlp_available():
        result = _extract_via_ytdlp(url)
        if result:
            return result

    return {
        "url": url,
        "video_id": video_id,
        "transcript": "",
        "error": "no transcript available (no yt-dlp or stealth browser running)",
        "source": "none",
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        ytdlp = _yt_dlp_available()
        print(f"OK transcripts.py")
        print(f"  yt-dlp available: {ytdlp}")
        if not ytdlp:
            print(f"  install: pip install yt-dlp")
        print(f"  video_id extraction: {_extract_video_id('https://youtu.be/dQw4w9WgXcQ')}")
        print(f"  browser fallback: requires stealth server running")

    asyncio.run(_smoke())
