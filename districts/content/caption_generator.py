import sys
import uuid
import asyncio as _asyncio
import concurrent.futures as _cf
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, tier: str = "agentic", max_tokens: int = 800, temperature: float = 0.88) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    from core.prompt_library import get_library as _gl
    _sys = _gl().get_for_agent("caption_generator") or ""
    messages = [{"role": "user", "content": prompt}]
    if _sys:
        messages = [{"role": "system", "content": _sys}] + messages
    async def _call():
        r = await _PC().chat(
            messages=messages,
            model="domain:content.script",   # caption is short-form scripting
            tier=tier, temperature=temperature, max_tokens=max_tokens,
            caller_id="caption_generator",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class CaptionGenerator(AgentBase):
    """
    Generates video captions and subtitles in various formats.
    Supports multiple caption styles and formats.
    """

    CAPTION_STYLES = {
        "standard": {
            "font_size": "medium",
            "position": "bottom",
            "max_chars_per_line": 42,
            "max_lines": 2
        },
        "large": {
            "font_size": "large",
            "position": "center",
            "max_chars_per_line": 35,
            "max_lines": 2
        },
        "minimal": {
            "font_size": "small",
            "position": "bottom",
            "max_chars_per_line": 50,
            "max_lines": 1
        },
        " karaoke": {
            "font_size": "medium",
            "position": "center",
            "highlight": True,
            "max_chars_per_line": 40,
            "max_lines": 2
        }
    }

    OUTPUT_FORMATS = ["srt", "vtt", "ass", "txt", "json"]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "CaptionGenerator", "content")
        self.capabilities = ["caption", "content", "generate", "generate_captions", "generate_highlight_captions", "generate_subtitles", "translate_captions", "video"]
        if ghost:
            self.inherit_ghost(ghost)

        self._generated_captions: list[dict] = []
        logger.info("[VECTOR][caption_generator] CaptionGenerator initialized")

    def generate_captions(self, transcript: str, style: str = "standard") -> dict:
        """
        Generate formatted captions from transcript.
        Automatically splits text into timed caption blocks.
        """
        style_config = self.CAPTION_STYLES.get(style, self.CAPTION_STYLES["standard"])

        prompt = f"""Convert this transcript into timed caption blocks.

Style: {style}
Max characters per line: {style_config['max_chars_per_line']}
Max lines per caption: {style_config['max_lines']}

Transcript:
{transcript[:4000]}

Format each caption as:
[TIMESTAMP] Text content

Use natural break points. Keep each caption concise.
Timestamps in format: 00:00:00 --> 00:00:03
"""

        try:
            caption_text = _llm(prompt, tier="fast", max_tokens=1000)
            captions = self._parse_caption_blocks(caption_text, style)

            caption_data = {
                "id": str(uuid.uuid4()),
                "style": style,
                "blocks": captions,
                "count": len(captions),
                "created_at": self._get_timestamp()
            }

            self._generated_captions.append(caption_data)
            self.award_points(10, "captions_generated")

            return {
                "status": "success",
                **caption_data
            }

        except Exception as e:
            logger.error(f"[VECTOR][caption_generator] Caption generation failed: {e}")
            return {"transcript": transcript, "error": str(e)}

    def _parse_caption_blocks(self, caption_text: str, style: str) -> list[dict]:
        """Parse caption blocks from LLM response."""
        blocks = []
        import re

        timestamp_pattern = r'(\d{2}:\d{2}:\d{2})\s*-->\s*(\d{2}:\d{2}:\d{2})'
        lines = caption_text.split('\n')

        current_start = None
        current_end = None
        current_text = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.search(timestamp_pattern, line)
            if match:
                if current_start and current_text:
                    blocks.append({
                        "start": current_start,
                        "end": current_end,
                        "text": " ".join(current_text),
                        "style": style
                    })

                current_start = match.group(1)
                current_end = match.group(2)
                current_text = []
            else:
                current_text.append(line)

        if current_start and current_text:
            blocks.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_text),
                "style": style
            })

        return blocks

    def generate_subtitles(self, video_path: str, style: str = "standard",
                          output_format: str = "srt") -> dict:
        """
        Generate subtitle file from video.
        First transcribes video, then generates timed captions.
        """
        from ..calls.transcription_bot import TranscriptionBot

        if not Path(video_path).exists():
            return {"status": "error", "message": "Video file not found"}

        transcriber = TranscriptionBot()
        transcription = transcriber.transcribe_audio(video_path)

        if transcription.get("status") != "success":
            return {
                "status": "error",
                "message": "Transcription failed",
                "details": transcription
            }

        captions = self.generate_captions(transcription["text"], style)

        if output_format != "json":
            formatted = self._format_captions(
                captions.get("blocks", []),
                output_format
            )
            return {
                "status": "success",
                "video_path": video_path,
                "format": output_format,
                "content": formatted,
                "block_count": captions.get("count", 0)
            }

        return captions

    def _format_captions(self, blocks: list[dict], format_type: str) -> str:
        """Format caption blocks to specified format."""
        if format_type == "srt":
            return self._to_srt(blocks)
        elif format_type == "vtt":
            return self._to_vtt(blocks)
        elif format_type == "txt":
            return self._to_txt(blocks)
        return self._to_srt(blocks)

    def _to_srt(self, blocks: list[dict]) -> str:
        """Convert to SRT format."""
        output = []
        for i, block in enumerate(blocks, 1):
            output.append(str(i))
            output.append(f"{block['start']} --> {block['end']}")
            output.append(block['text'])
            output.append("")
        return "\n".join(output)

    def _to_vtt(self, blocks: list[dict]) -> str:
        """Convert to WebVTT format."""
        output = ["WEBVTT", ""]
        for block in blocks:
            output.append(f"{block['start']} --> {block['end']}")
            output.append(block['text'])
            output.append("")
        return "\n".join(output)

    def _to_txt(self, blocks: list[dict]) -> str:
        """Convert to plain text."""
        return "\n".join(block['text'] for block in blocks)

    def save_captions(self, captions: dict, output_path: str, format_type: str = "srt") -> bool:
        """
        Save captions to file.
        """
        blocks = captions.get("blocks", [])
        content = self._format_captions(blocks, format_type)

        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(content, encoding="utf-8")

            self.award_points(5, "captions_saved")
            logger.info(f"[VECTOR][caption_generator] Saved captions to {output_path}")
            return True

        except Exception as e:
            logger.error(f"[VECTOR][caption_generator] Failed to save captions: {e}")
            return False

    def generate_highlight_captions(self, transcript: str, keywords: list[str]) -> dict:
        """
        Generate captions that highlight specific keywords.
        Useful for educational content.
        """
        prompt = f"""Create caption blocks that highlight these keywords: {', '.join(keywords)}

Transcript:
{transcript[:4000]}

Format each caption showing which keyword is highlighted:
[TIMESTAMP] Text with **KEYWORD** highlighted

Use **double asterisks** to mark keywords.
"""

        try:
            captions_text = _llm(prompt, tier="fast", max_tokens=1000)
            return {
                "status": "success",
                "captions": captions_text,
                "keywords": keywords,
                "style": "highlight"
            }
        except Exception as e:
            logger.error(f"[VECTOR][caption_generator] Highlight caption generation failed: {e}")
            return {"error": str(e)}

    def translate_captions(self, captions: dict, target_language: str) -> dict:
        """
        Translate existing captions to another language.
        """
        blocks = captions.get("blocks", [])
        transcript = "\n".join(block['text'] for block in blocks)

        prompt = f"""Translate these captions to {target_language}.
Keep the same line breaks and timing structure.

Original:
{transcript}

Translation:"""

        try:
            translation = _llm(prompt, tier="multilingual", max_tokens=1500, temperature=0.3)
            self.award_points(15, "captions_translated")
            return {
                "status": "success",
                "original_language": "auto",
                "target_language": target_language,
                "translation": translation
            }
        except Exception as e:
            logger.error(f"[VECTOR][caption_generator] Translation failed: {e}")
            return {"error": str(e)}

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["generate_captions", "generate_subtitles", "generate_highlight_captions", "translate_captions"]

        if task_type == "generate_captions":
            return self.generate_captions(p.get("transcript", ""), p.get("style", "standard"))
        if task_type == "generate_subtitles":
            return self.generate_subtitles(p.get("video_path", ""), p.get("style", "standard"), p.get("output_format", "srt"))
        if task_type == "generate_highlight_captions":
            return self.generate_highlight_captions(p.get("transcript", ""), p.get("keywords", []))
        if task_type == "translate_captions":
            return self.translate_captions(p.get("captions", {}), p.get("target_language", ""))

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "can you generate captions for my video transcript?" previously
        # hit the bare "unhandled type" error stub. Every real capability
        # here needs an actual transcript/video_path/captions object we
        # don't have from free text alone — only take a branch when the
        # caller actually supplied the input; never invent transcript text
        # or guess a video path. Otherwise answer with a grounded
        # explanation instead of an error stub.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            if p.get("transcript"):
                return self.generate_captions(p["transcript"], p.get("style", "standard"))
            if p.get("video_path"):
                return self.generate_subtitles(p["video_path"], p.get("style", "standard"), p.get("output_format", "srt"))
            return {
                "status": "ok",
                "response": (
                    "Send me the video transcript text (params.transcript) and I'll "
                    "generate timed caption blocks, or a video_path if you want me to "
                    "transcribe and caption it directly."
                ),
            }

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    generator = CaptionGenerator()

    sample_transcript = "Welcome to this tutorial. Today we're going to learn about Python programming. Let's start with the basics."

    captions = generator.generate_captions(sample_transcript, "standard")
    print(f"Generated {captions.get('count', 0)} caption blocks")

    print("✅ caption_generator.py OK")
