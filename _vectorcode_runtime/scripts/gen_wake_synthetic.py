"""
scripts/gen_wake_synthetic.py — Generate synthetic "hey vector" positive clips
for openWakeWord training, using piper-tts (no microphone / no owner voice
needed). This is the piece OPEN_ISSUES #6 flagged as missing:
piper-sample-generator won't build on Windows (webrtcvad needs a C compiler),
so we drive piper-tts directly with varied speed / prosody / pronunciation.

Output: models/wake/synthetic/*.wav  (16 kHz mono — openWakeWord's rate)
Combine with the 15 real recordings in models/wake/samples/ for training.

Usage:
    python scripts/gen_wake_synthetic.py                 # ~150 clips
    python scripts/gen_wake_synthetic.py --n 300
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import itertools
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Multi-speaker voice (904 speakers) = the diversity a robust wake word needs.
# Falls back to the single ryan voice if libritts isn't downloaded.
_VOICE_MULTI = _ROOT / "models" / "piper" / "en_US-libritts_r-medium.onnx"
_VOICE_SINGLE = _ROOT / "models" / "piper" / "en_US-ryan-high.onnx"
_N_SPEAKERS = 904
_OUT = _ROOT / "models" / "wake" / "synthetic"
_TARGET_SR = 16000

# Phrase spellings piper pronounces slightly differently — extra acoustic spread.
_PHRASES = [
    "hey vector", "hey vector.", "hey, vector", "okay vector",
    "hey vektor", "hey vecter", "hay vector",
]
# (length_scale=speed, noise_scale, noise_w_scale) — prosody/timing spread.
_STYLES = [
    (0.85, 0.5, 0.6), (0.95, 0.6, 0.7), (1.0, 0.667, 0.8),
    (1.1, 0.7, 0.8), (1.25, 0.8, 1.0),
]


def _resample_16k(path: Path) -> None:
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != _TARGET_SR:
            # linear resample — adequate for 0.6s wake clips
            n = int(round(len(data) * _TARGET_SR / sr))
            x_old = np.linspace(0, 1, len(data), endpoint=False)
            x_new = np.linspace(0, 1, n, endpoint=False)
            data = np.interp(x_new, x_old, data)
        sf.write(path, data.astype("float32"), _TARGET_SR)
    except Exception as e:
        print(f"  resample failed for {path.name}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600, help="approx clips to generate")
    args = ap.parse_args()

    multi = _VOICE_MULTI.exists()
    voice = _VOICE_MULTI if multi else _VOICE_SINGLE
    if not voice.exists():
        print(f"ERROR: no piper voice found ({_VOICE_MULTI} / {_VOICE_SINGLE})", file=sys.stderr)
        return 1
    print(f"Using {'MULTI-speaker libritts (904 voices)' if multi else 'single ryan voice'}")
    _OUT.mkdir(parents=True, exist_ok=True)

    combos = list(itertools.product(_PHRASES, _STYLES))
    random.shuffle(combos)
    made = 0
    idx = 0
    while made < args.n:
        phrase, (ls, ns, nws) = combos[idx % len(combos)]
        idx += 1
        out = _OUT / f"syn_{made:04d}.wav"
        cmd = [sys.executable, "-m", "piper", "-m", str(voice), "-f", str(out),
               "--length-scale", str(ls), "--noise-scale", str(ns),
               "--noise-w-scale", str(nws)]
        if multi:
            # Spread across the 904 speakers — the key to a robust model.
            cmd += ["--speaker", str(random.randint(0, _N_SPEAKERS - 1))]
        try:
            proc = subprocess.run(cmd, input=phrase, capture_output=True,
                                  text=True, timeout=60)
            if proc.returncode != 0 or not out.exists():
                print(f"  clip {made} failed: {proc.stderr[:120]}", file=sys.stderr)
                continue
            _resample_16k(out)
            made += 1
            if made % 50 == 0:
                print(f"  generated {made}/{args.n} ...", flush=True)
        except Exception as e:
            print(f"  clip {made} error: {e}", file=sys.stderr)

    print(f"OK: {made} synthetic clips in {_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
