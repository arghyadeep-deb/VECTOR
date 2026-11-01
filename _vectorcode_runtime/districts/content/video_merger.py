import sys
import uuid
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class VideoMerger(AgentBase):
    """
    Merges video clips, adds background music, and applies
    transitions using ffmpeg.
    """

    TRANSITION_TYPES = [
        "fade", "dissolve", "wipe_left", "wipe_right", "wipe_up", "wipe_down",
        "slide_left", "slide_right", "zoom_in", "blur"
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "VideoMerger", "content")
        self.capabilities = ["add_background_music", "add_subtitles", "add_transitions", "content", "extract_audio", "merge", "merge_clips", "trim_video", "video"]
        if ghost:
            self.inherit_ghost(ghost)

        self._ffmpeg_available = self._check_ffmpeg()
        self._project_dir = Path(__file__).parent.parent.parent.parent / "data" / "video_projects"
        self._project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[VECTOR][video_merger] VideoMerger initialized - FFmpeg: {self._ffmpeg_available}")

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("[VECTOR][video_merger] FFmpeg not found - some features disabled")
            return False

    def merge_clips(self, clips_dir: str, output_path: str,
                    order: Optional[list[str]] = None,
                    transition: str = "dissolve",
                    transition_duration: float = 0.5) -> dict:
        """
        Merge video clips from a directory into a single video.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        clips_path = Path(clips_dir)
        if not clips_path.exists():
            return {"status": "error", "message": "Clips directory not found"}

        video_files = list(clips_path.glob("*.mp4")) + \
                      list(clips_path.glob("*.avi")) + \
                      list(clips_path.glob("*.mov")) + \
                      list(clips_path.glob("*.mkv"))

        if not video_files:
            return {"status": "error", "message": "No video files found in directory"}

        if order:
            video_files = sorted(
                video_files,
                key=lambda f: order.index(f.name) if f.name in order else 999
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            concat_list = self._project_dir / "concat_list.txt"
            with open(concat_list, "w") as f:
                for clip in video_files:
                    f.write(f"file '{clip.absolute()}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output)
            ]

            if transition != "none" and len(video_files) > 1:
                cmd = self._add_transition(cmd, transition, transition_duration)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                self.award_points(30, "clips_merged")
                logger.info(f"[VECTOR][video_merger] Merged {len(video_files)} clips to {output}")

                return {
                    "status": "success",
                    "output_path": str(output),
                    "clips_merged": len(video_files),
                    "file_size_mb": round(output.stat().st_size / (1024 * 1024), 2)
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            logger.error(f"[VECTOR][video_merger] Merge failed: {e}")
            return {"status": "error", "message": str(e)}

    def _probe_duration(self, video: Path) -> float:
        """Return the video's duration in seconds via ffprobe (0.0 on failure)."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                capture_output=True, text=True, timeout=30,
            )
            return float(result.stdout.strip())
        except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
            logger.warning("[VECTOR][video_merger] ffprobe duration failed: {}", e)
            return 0.0

    def _add_transition(self, cmd: list, transition: str, duration: float) -> list:
        """Add transition filter to ffmpeg command."""
        filter_idx = cmd.index("-c:v") + 1
        base_codec = cmd[filter_idx]

        cmd[filter_idx] = f"{base_codec},xfade=transition={transition}:duration={duration}"

        return cmd

    def add_background_music(self, video_path: str, music_path: str,
                            output_path: Optional[str] = None,
                            volume_music: float = 0.3,
                            volume_video: float = 1.0,
                            fade_out: float = 3.0) -> dict:
        """
        Add background music to a video.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        video = Path(video_path)
        music = Path(music_path)

        if not video.exists():
            return {"status": "error", "message": "Video file not found"}
        if not music.exists():
            return {"status": "error", "message": "Music file not found"}

        if output_path is None:
            output_path = video.parent / f"{video.stem}_with_music{video.suffix}"

        try:
            duration = self._probe_duration(video)
            fade_start = max(0.0, duration - 3) if duration else 0.0
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-i", str(music),
                "-filter_complex",
                f"[1:a]volume={volume_music},afade=t=out:st={fade_start}:d={fade_out}[music];"
                f"[0:a]volume={volume_video}[speech];"
                f"[speech][music]amix=inputs=2:duration=longest[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.award_points(15, "music_added")
                return {
                    "status": "success",
                    "output_path": str(output_path)
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            logger.error(f"[VECTOR][video_merger] Music addition failed: {e}")
            return {"status": "error", "message": str(e)}

    def add_transitions(self, video_path: str, transition_type: str,
                       duration: float = 0.5) -> dict:
        """
        Add transitions between all clips in a video.
        Note: This works on individual files, for batch use merge_clips with transition.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        video = Path(video_path)
        if not video.exists():
            return {"status": "error", "message": "Video file not found"}

        if transition_type not in self.TRANSITION_TYPES:
            return {
                "status": "error",
                "message": f"Unknown transition type: {transition_type}",
                "available": self.TRANSITION_TYPES
            }

        output_path = video.parent / f"{video.stem}_{transition_type}{video.suffix}"

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", f"fps=30,zoompan=z='min(zoom+0.001,1.5)':d=125:s=1280x720",
                "-c:v", "libx264",
                "-preset", "medium",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.award_points(10, "transition_added")
                return {
                    "status": "success",
                    "output_path": str(output_path),
                    "transition": transition_type
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            logger.error(f"[VECTOR][video_merger] Transition failed: {e}")
            return {"status": "error", "message": str(e)}

    def trim_video(self, video_path: str, start_time: float,
                  end_time: float, output_path: Optional[str] = None) -> dict:
        """
        Trim video to specified time range.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        video = Path(video_path)
        if not video.exists():
            return {"status": "error", "message": "Video file not found"}

        if output_path is None:
            output_path = video.parent / f"{video.stem}_trimmed{video.suffix}"

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-ss", str(start_time),
                "-to", str(end_time),
                "-c", "copy",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                return {
                    "status": "success",
                    "output_path": str(output_path),
                    "duration": end_time - start_time
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def extract_audio(self, video_path: str, output_path: Optional[str] = None) -> dict:
        """
        Extract audio track from video.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        video = Path(video_path)
        if not video.exists():
            return {"status": "error", "message": "Video file not found"}

        if output_path is None:
            output_path = video.parent / f"{video.stem}.mp3"

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                return {
                    "status": "success",
                    "audio_path": str(output_path)
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def add_subtitles(self, video_path: str, subtitle_path: str,
                     output_path: Optional[str] = None,
                     style: str = "default") -> dict:
        """
        Burn subtitles into video.
        """
        if not self._ffmpeg_available:
            return {"status": "error", "message": "FFmpeg not available"}

        video = Path(video_path)
        subs = Path(subtitle_path)

        if not video.exists():
            return {"status": "error", "message": "Video file not found"}
        if not subs.exists():
            return {"status": "error", "message": "Subtitle file not found"}

        if output_path is None:
            output_path = video.parent / f"{video.stem}_subtitled{video.suffix}"

        try:
            if subs.suffix == ".srt":
                vf = f"subtitles='{subs}':force_style='FontSize=24,PrimaryColour=&HFFFFFF&'"
            else:
                vf = f"subtitles='{subs}'"

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", vf,
                "-c:a", "copy",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.award_points(10, "subtitles_added")
                return {
                    "status": "success",
                    "output_path": str(output_path)
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "merge_clips", "add_background_music", "add_transitions",
            "trim_video", "extract_audio", "add_subtitles",
        ]

        if task_type == "merge_clips":
            return self.merge_clips(
                p.get("clips_dir", ""), p.get("output_path", ""),
                p.get("order"), p.get("transition", "dissolve"), p.get("transition_duration", 0.5),
            )
        if task_type == "add_background_music":
            return self.add_background_music(
                p.get("video_path", ""), p.get("music_path", ""), p.get("output_path"),
                p.get("volume_music", 0.3), p.get("volume_video", 1.0),
            )
        if task_type == "add_transitions":
            return self.add_transitions(p.get("video_path", ""), p.get("transition_type", ""), p.get("duration", 0.5))
        if task_type == "trim_video":
            return self.trim_video(p.get("video_path", ""), p.get("start_time", 0), p.get("end_time", 0), p.get("output_path"))
        if task_type == "extract_audio":
            return self.extract_audio(p.get("video_path", ""), p.get("output_path"))
        if task_type == "add_subtitles":
            return self.add_subtitles(p.get("video_path", ""), p.get("subtitle_path", ""), p.get("output_path"), p.get("style", "default"))

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "can you merge my video clips together with smooth transitions?"
        # previously hit the bare "unhandled type" error stub. Every real
        # capability here spawns a real ffmpeg subprocess against real files
        # on disk — there is no safe read-only capability to fall back to.
        # Never guess a clips_dir/video_path from free text; answer with a
        # grounded explanation instead of an error stub.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return {
                "status": "ok",
                "response": (
                    "I can merge clips (merge_clips + clips_dir/output_path), add "
                    "background music, add transitions, trim, extract audio, or burn "
                    "subtitles into a video — all need a real video_path/clips_dir on "
                    "disk. Tell me which operation and give me the file path(s); I "
                    "won't run ffmpeg without one."
                ),
            }

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    merger = VideoMerger()
    print(f"FFmpeg available: {merger._ffmpeg_available}")
    print(f"Available transitions: {merger.TRANSITION_TYPES[:5]}")

    print("✅ video_merger.py OK")
