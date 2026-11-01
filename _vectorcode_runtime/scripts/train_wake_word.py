"""
scripts/train_wake_word.py — Record samples and train a custom openWakeWord model.

Usage:
    python scripts/train_wake_word.py                         # 15 samples, phrase "hey_vector"
    python scripts/train_wake_word.py --n-samples 5           # fewer samples (quick test)
    python scripts/train_wake_word.py --phrase hey_vector     # explicit phrase
    python scripts/train_wake_word.py --dry-run               # env check only, no audio
    python scripts/train_wake_word.py --check                 # verify model exists at output path

Output: models/wake/hey_vector.onnx
After training, restart VECTOR — _init_model() will prefer the custom model.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _check_deps() -> list[str]:
    missing = []
    for pkg in ("openwakeword", "sounddevice", "soundfile", "numpy"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def _record_sample(idx: int, n_total: int, phrase: str, sample_rate: int,
                   duration: float, out_path: Path) -> bool:
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np

        print(f"  [{idx+1}/{n_total}] Say \"{phrase}\" now...", flush=True)
        time.sleep(0.4)
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        audio_flat = audio.flatten()
        rms = float(np.sqrt(np.mean(audio_flat.astype(float) ** 2)))
        if rms < 50:
            print(f"  [{idx+1}] Too quiet (rms={rms:.0f}) — skipping sample")
            return False
        sf.write(str(out_path), audio_flat, sample_rate)
        print(f"  [{idx+1}] Saved ({out_path.name}, rms={rms:.0f})")
        return True
    except Exception as e:
        print(f"  [{idx+1}] Record error: {e}")
        return False


_SPH_HARM_SHIM = (
    "import scipy.special as _sp\n"
    "if not hasattr(_sp, 'sph_harm'):\n"
    "    def _sph_harm(m, n, theta, phi):\n"
    "        return _sp.sph_harm_y(n, m, phi, theta)\n"
    "    _sp.sph_harm = _sph_harm\n"
    "import runpy, sys\n"
    "sys.argv = ['openwakeword.train'] + sys.argv[1:]\n"
    "runpy.run_module('openwakeword.train', run_name='__main__')\n"
)


def _run_training(phrase: str, samples_dir: Path, output_dir: Path) -> bool:
    """
    Runs openwakeword.train in a subprocess, via an inline bootstrap that
    shims scipy.special.sph_harm (removed in scipy>=1.15) before import.
    The `acoustics` package — an openwakeword dependency for noise
    augmentation — still imports an unmaintained submodule that references
    the removed function, even though that submodule is never called here.
    Shimming in-process (not editing the installed acoustics package) keeps
    the fix local to VECTOR and survives any future package reinstall.
    """
    print("\nStarting openWakeWord training (this may take 5-20 minutes)...")
    try:
        result = subprocess.run(
            [
                sys.executable, "-c", _SPH_HARM_SHIM,
                "--positive_reference_clips", str(samples_dir),
                "--output_dir", str(output_dir),
                "--model_name", phrase,
            ],
            capture_output=False,
            timeout=1200,
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("ERROR: openwakeword.train module not found.")
        print("       pip install openwakeword")
        return False
    except subprocess.TimeoutExpired:
        print("ERROR: Training timed out after 20 minutes.")
        return False
    except Exception as e:
        print(f"ERROR: Training failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Train custom 'Hey Vector' wake word model")
    parser.add_argument("--phrase", default="hey_vector",
                        help="Wake word phrase slug (default: hey_vector)")
    parser.add_argument("--n-samples", type=int, default=15,
                        help="Number of voice samples to record (default: 15, minimum: 5)")
    parser.add_argument("--duration", type=float, default=1.5,
                        help="Duration of each sample in seconds (default: 1.5)")
    parser.add_argument("--sample-rate", type=int, default=16000,
                        help="Sample rate in Hz (default: 16000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check environment only, do not record audio")
    parser.add_argument("--check", action="store_true",
                        help="Check if trained model already exists at output path")
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    output_dir = root / "models" / "wake"
    samples_dir = output_dir / "samples"
    model_out = output_dir / f"{args.phrase}.onnx"

    if args.check:
        if model_out.exists():
            print(f"OK: Custom model found at {model_out}")
            return 0
        else:
            print(f"MISSING: {model_out} not found")
            print("Run without --check to train the model.")
            return 1

    print(f"VECTOR Wake Word Trainer")
    print(f"  Phrase:    {args.phrase}")
    print(f"  Samples:   {args.n_samples}")
    print(f"  Output:    {model_out}")
    print()

    missing = _check_deps()
    if missing:
        print(f"ERROR: Missing packages: {', '.join(missing)}")
        print(f"       pip install {' '.join(missing)}")
        return 1
    print("Dependencies OK")

    if args.dry_run:
        print("Dry run complete. Environment is ready for training.")
        return 0

    if args.n_samples < 5:
        print("ERROR: --n-samples must be at least 5 for reliable training.")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nRecording {args.n_samples} samples of \"{args.phrase}\"")
    print("Tip: speak naturally, vary your tone slightly between samples.")
    print()

    recorded: list[Path] = []
    attempts = 0
    while len(recorded) < args.n_samples and attempts < args.n_samples * 2:
        sample_path = samples_dir / f"sample_{attempts:03d}.wav"
        ok = _record_sample(
            idx=attempts, n_total=args.n_samples,
            phrase=args.phrase.replace("_", " "),
            sample_rate=args.sample_rate,
            duration=args.duration,
            out_path=sample_path,
        )
        if ok:
            recorded.append(sample_path)
        attempts += 1
        time.sleep(0.3)

    print(f"\nRecorded {len(recorded)}/{args.n_samples} samples.")

    if len(recorded) < 5:
        print(f"ERROR: Only {len(recorded)} samples recorded. Need at least 5.")
        return 1

    success = _run_training(args.phrase, samples_dir, output_dir)

    if success and model_out.exists():
        print(f"\nOK: Model trained and saved to {model_out}")
        print("Restart VECTOR to activate the custom wake word.")
        return 0
    elif success:
        print(f"\nERROR: Training finished but {model_out} not found.")
        return 1
    else:
        print("\nERROR: Training failed. Check openwakeword installation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
