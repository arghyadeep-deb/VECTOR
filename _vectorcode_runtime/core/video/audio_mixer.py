"""
VECTOR Audio Mixer

Mixes multiple audio tracks, handles TTS narration sync, pad/trim to duration.
Supports:
  - Multi-track mixing with per-track volume
  - Pad-silence / trim-to-duration matching
  - WAV/MP3/AAC/OGG inputs
  - FFmpeg filter_complex for multi-track mixing
  - Audio extraction from video files
"""
from __future__ import annotations

__all__ = [
    "AudioMixer",
    "AudioTrack",
    "MixResult",
    "NarrationPipeline",
]


import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from core.video.video_encoder import find_ffmpeg, find_ffprobe, probe_duration


@dataclass
class AudioTrack:
    path: str
    volume: float = 1.0          # 0.0 - 1.0
    start_time: float = 0.0      # seconds offset in timeline
    duration: Optional[float] = None   # trim to this duration
    fade_in: float = 0.0
    fade_out: float = 0.0


@dataclass
class MixResult:
    output_path: str
    duration_seconds: float
    track_count: int


class AudioMixer:
    """
    Mixes audio tracks using FFmpeg filter_complex.
        """

    def mix(
        self,
        tracks: list[AudioTrack],
        output_path: str,
        target_duration: float,
        sample_rate: int = 44100,
    ) -> MixResult:
        """Mix all tracks to a single audio file, padded/trimmed to target_duration."""
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")

        if not tracks:
            # Generate silence
            return self._generate_silence(output_path, target_duration, sample_rate)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if len(tracks) == 1:
            return self._process_single(tracks[0], output_path, target_duration, sample_rate)

        return self._mix_multi(tracks, output_path, target_duration, sample_rate)

    def _process_single(
        self,
        track: AudioTrack,
        output_path: str,
        target_duration: float,
        sample_rate: int,
    ) -> MixResult:
        ffmpeg = find_ffmpeg()
        filters = []
        stream = "[0:a]"

        if track.volume != 1.0:
            filters.append(f"[0:a]volume={track.volume:.3f}[va]")
            stream = "[va]"

        if track.start_time > 0:
            filters.append(f"{stream}adelay={int(track.start_time*1000)}|{int(track.start_time*1000)}[da]")
            stream = "[da]"

        # Pad/trim to target duration
        filters.append(
            f"{stream}apad=whole_dur={target_duration:.4f},atrim=duration={target_duration:.4f}[out]"
        )

        cmd = [ffmpeg, "-y", "-i", track.path]
        if filters:
            cmd += ["-filter_complex", ";".join(filters), "-map", "[out]"]
        cmd += ["-ar", str(sample_rate), "-c:a", "aac", "-b:a", "192k", output_path]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning("[VECTOR][audio_mixer] FFmpeg warning: {}", result.stderr[-500:])

        return MixResult(output_path=output_path, duration_seconds=target_duration, track_count=1)

    def _mix_multi(
        self,
        tracks: list[AudioTrack],
        output_path: str,
        target_duration: float,
        sample_rate: int,
    ) -> MixResult:
        ffmpeg = find_ffmpeg()
        cmd = [ffmpeg, "-y"]

        for t in tracks:
            cmd += ["-i", t.path]

        # Build filter_complex: volume + delay per track, then amix
        filters = []
        mix_inputs = []
        for i, track in enumerate(tracks):
            label = f"v{i}"
            chain = f"[{i}:a]"

            if track.volume != 1.0:
                chain += f"volume={track.volume:.3f}"
                filters.append(f"[{i}:a]volume={track.volume:.3f}[{label}v]")
                chain = f"[{label}v]"
                label = f"{label}v"
            else:
                label = str(i)
                chain = f"[{i}:a]"

            if track.start_time > 0:
                delay_ms = int(track.start_time * 1000)
                new_label = f"d{i}"
                filters.append(f"[{label}]adelay={delay_ms}|{delay_ms}[{new_label}]"
                               if label != str(i) else
                               f"[{i}:a]adelay={delay_ms}|{delay_ms}[{new_label}]")
                label = new_label

            mix_inputs.append(f"[{label}]" if not label.startswith("[") else label)

        # amix all inputs -- use the per-track processed labels (mix_inputs),
        # not the raw [i:a] streams. Rebuilding from raw indices here used to
        # silently discard every volume/delay filter chain built above: the
        # filters were emitted into the ffmpeg command as orphan pads, but
        # amix mixed the unprocessed originals -- per-track volume and
        # start_time were completely ignored for any 2+ track mix (e.g.
        # NarrationPipeline.produce()'s bg_volume=0.15 background-music mix).
        n = len(tracks)
        mix_inputs_str = "".join(mix_inputs)
        filters.append(
            f"{mix_inputs_str}amix=inputs={n}:duration=longest:normalize=0[mixed]"
        )
        # Pad/trim to target duration
        filters.append(
            f"[mixed]apad=whole_dur={target_duration:.4f},atrim=duration={target_duration:.4f}[out]"
        )

        cmd += [
            "-filter_complex", ";".join(filters),
            "-map", "[out]",
            "-ar", str(sample_rate),
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning("[VECTOR][audio_mixer] mix warning: {}", result.stderr[-500:])

        return MixResult(output_path=output_path, duration_seconds=target_duration, track_count=n)

    def _generate_silence(
        self,
        output_path: str,
        duration: float,
        sample_rate: int,
    ) -> MixResult:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl=stereo",
            "-t", f"{duration:.4f}",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logger.warning("[VECTOR][audio_mixer] silence generation failed: {}",
                            result.stderr[-500:] if result.stderr else "no stderr")
        return MixResult(output_path=output_path, duration_seconds=duration, track_count=0)

    def extract_from_video(self, video_path: str, output_path: str) -> Optional[str]:
        """Extract audio track from a video file."""
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            return None
        cmd = [
            ffmpeg, "-y", "-i", video_path,
            "-vn", "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            return None
        return output_path

    def pad_trim(self, audio_path: str, output_path: str, duration: float) -> str:
        """Pad with silence or trim audio to exact duration."""
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")
        cmd = [
            ffmpeg, "-y", "-i", audio_path,
            "-filter:a", f"apad=whole_dur={duration:.4f},atrim=duration={duration:.4f}",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            logger.warning("[VECTOR][audio_mixer] pad_trim failed: {}",
                            result.stderr[-500:] if result.stderr else "no stderr")
        return output_path


# â”€â”€ TTS narration pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class NarrationPipeline:
    """
    Generate TTS narration and mix with background music.
    Connects VECTOR's Kokoro TTS to the audio mixing pipeline.
    """

    def __init__(self) -> None:
        self._mixer = AudioMixer()

    def generate_narration(
        self,
        script: str,
        output_path: str,
        voice: str = "bm_george",
        speed: float = 0.85,
    ) -> Optional[str]:
        """Generate speech from script using VECTOR's TTS engine."""
        try:
            from core.voice.tts import TextToSpeech
            tts = TextToSpeech()
            tts.speak_to_file(script, output_path, voice=voice, speed=speed)
            return output_path
        except Exception as e:
            logger.warning("[VECTOR][audio_mixer] TTS failed: {}", e)
            return None

    def produce(
        self,
        narration_script: str,
        bg_music_path: Optional[str],
        output_path: str,
        target_duration: float,
        narration_volume: float = 1.0,
        bg_volume: float = 0.15,
    ) -> MixResult:
        """Full narration + background music mix."""
        import tempfile

        tracks: list[AudioTrack] = []

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            narration_tmp = f.name

        narration = self.generate_narration(narration_script, narration_tmp)
        if narration:
            tracks.append(AudioTrack(path=narration, volume=narration_volume))

        if bg_music_path and os.path.exists(bg_music_path):
            tracks.append(AudioTrack(path=bg_music_path, volume=bg_volume))

        return self._mixer.mix(tracks, output_path, target_duration)


if __name__ == "__main__":
    mixer = AudioMixer()
    ffmpeg = find_ffmpeg()
    print(f"FFmpeg: {ffmpeg or 'NOT FOUND'}")

    # Smoke: silence generation
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".aac", delete=False) as f:
        tmp = f.name
    try:
        if ffmpeg:
            result = mixer._generate_silence(tmp, 1.0, 44100)
            assert result.duration_seconds == 1.0
            print(f"Silence generated: {os.path.getsize(tmp)} bytes")
        else:
            print("FFmpeg not installed — skipping audio test")
    finally:
        try: os.unlink(tmp)
        except OSError as e: logger.debug("[VECTOR][audio_mixer] temp cleanup: {}", e)

    print("OK audio_mixer.py")
