"""Enroll the owner's voiceprint for speaker verification.

Usage:
  python scripts/enroll_owner_voice.py                 # record 3 x 10s from mic
  python scripts/enroll_owner_voice.py a.wav b.wav     # enroll from wav files

Records (or loads) clips of YOUR voice, builds an averaged embedding via
core/voice/speaker_verify.py, and saves data/voice_profiles/owner_voiceprint.npz.
The realtime voice layer auto-enables verification once this file exists:
unknown voices can still chat, but action commands are refused.

Tips for good enrollment: speak normally (not reading-voice), in the room and
mic you actually use, with a little variety — a question, a command, a sentence.
Re-run any time; it overwrites. Delete the .npz to disable verification.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

SR = 16000
CLIPS = 3
SECONDS = 10


def record_clips() -> list[np.ndarray]:
    import sounddevice as sd
    clips = []
    print(f"Recording {CLIPS} clips of {SECONDS}s at {SR}Hz. Speak naturally.")
    for i in range(CLIPS):
        input(f"\n[{i + 1}/{CLIPS}] Press Enter, then talk for {SECONDS}s...")
        audio = sd.rec(int(SECONDS * SR), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        clip = audio.flatten()
        rms = float(np.sqrt(np.mean(clip ** 2)))
        print(f"   captured (rms={rms:.4f}{' — very quiet, check mic!' if rms < 0.005 else ''})")
        clips.append(clip)
    return clips


def load_clips(paths: list[str]) -> list[np.ndarray]:
    import soundfile as sf
    clips = []
    for p in paths:
        audio, sr = sf.read(p, dtype="float32")
        if audio.ndim > 1:
            audio = audio[:, 0]
        if sr != SR:  # naive resample — fine for enrollment
            idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / sr)).astype(int)
            audio = audio[idx]
        clips.append(audio)
        print(f"   loaded {p} ({len(audio) / SR:.1f}s)")
    return clips


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from core.voice.speaker_verify import get_verifier
    v = get_verifier()
    clips = load_clips(sys.argv[1:]) if len(sys.argv) > 1 else record_clips()
    result = v.enroll(clips, SR)
    print(f"\n{result}")
    if result.get("status") == "ok":
        if result.get("engine") == "fallback":
            print("\nNOTE: enrolled with the WEAK numpy fallback. For real "
                  "verification:  pip install resemblyzer  then re-run this script.")
        ok, sim = v.verify(clips[0], SR)
        print(f"Self-check: owner clip verifies={ok} (similarity={sim:.3f}, "
              f"threshold={v.threshold})")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
