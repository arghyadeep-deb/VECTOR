"""
scripts/train_wake_word_synthetic.py — Train a custom "Hey VECTOR" openWakeWord
model from SYNTHETIC clips (no microphone needed), the modern openWakeWord
recipe that OPEN_ISSUES #6 described.

Pipeline:
  positives = models/wake/synthetic/*.wav  (piper-tts, ~150 — run gen_wake_synthetic.py first)
            + models/wake/samples/*.wav     (your 15 real recordings)
  negatives = openWakeWord's precomputed ACAV100M feature set (auto-downloaded)
  train     -> models/wake/hey_vector.onnx  (what core/voice/wake_word.py loads)

HEADS UP — this is the genuinely heavy step:
  * The negative feature set is LARGE (~2 GB "small" set to ~30 GB full set).
  * Feature extraction + training runs for tens of minutes to a few hours on GPU.
  * Best run when you can dedicate the machine; it is NOT a 30-second task.
Until this produces hey_vector.onnx, VECTOR falls back to Whisper keyword
spotting ("Hey Vector"), which already works — so nothing is broken meanwhile.

Usage:
    python scripts/gen_wake_synthetic.py            # 1. make synthetic positives
    python scripts/train_wake_word_synthetic.py     # 2. download negatives + train
    python scripts/train_wake_word_synthetic.py --check   # just verify prerequisites
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

# MUST precede any openwakeword import. openwakeword.train pulls torchmetrics→
# torchvision; torchvision's register_fake frame-walk calls hasattr(m,'__file__')
# on every loaded module, which detonates speechbrain's broken lazy imports
# (k2_fsa / huggingface.wordemb) under this torch 2.11 build. Importing
# torchvision FIRST — before openwakeword loads speechbrain — lets its meta
# registration complete cleanly; later imports are then cached no-ops.
try:
    import torchvision  # noqa: F401
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
_WAKE = _ROOT / "models" / "wake"
_SYN = _WAKE / "synthetic"
_REAL = _WAKE / "samples"
_NEG_DIR = _WAKE / "negative_features"
_OUT = _WAKE / "hey_vector.onnx"

# openWakeWord-hosted precomputed negative features (HuggingFace). The "small"
# validation + a features shard are enough for a usable model; the full ACAV
# set gives best false-accept rates. URLs per the openWakeWord training notebook.
_NEG_URLS = {
    "validation_set_features.npy":
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy",
    "openwakeword_features_ACAV100M_2000_hrs_16bit.npy":
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy",
}


def _count(p: Path, pat: str = "*.wav") -> int:
    return len(list(p.glob(pat))) if p.exists() else 0


def check() -> bool:
    ok = True
    print("Prerequisites:")
    for name, mod in [("openwakeword", "openwakeword"), ("torch", "torch"),
                      ("soundfile", "soundfile"), ("numpy", "numpy")]:
        try:
            __import__(mod); print(f"  [ok] {name}")
        except ImportError:
            print(f"  [MISSING] {name} — pip install {name}"); ok = False
    n_syn, n_real = _count(_SYN), _count(_REAL)
    print(f"  synthetic positives: {n_syn}  (run gen_wake_synthetic.py if 0)")
    print(f"  real positives:      {n_real}")
    if n_syn + n_real < 50:
        print("  [WARN] <50 positive clips — generate more for a robust model"); ok = False
    try:
        import torch
        print(f"  CUDA: {torch.cuda.is_available()}")
    except Exception:
        pass
    return ok


def _download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [cached] {dest.name}")
        return True
    print(f"  downloading {dest.name} (large — this is the slow part) ...", flush=True)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        print(f"  [done] {dest.name} ({dest.stat().st_size/1e6:.0f} MB)")
        return True
    except Exception as e:
        print(f"  [FAIL] {dest.name}: {e}", file=sys.stderr)
        return False


def train(full_negatives: bool) -> int:
    if not check():
        print("\nFix prerequisites above, then re-run.")
        return 1
    import numpy as np
    import openwakeword.data as owd
    from openwakeword.train import Model as TrainModel

    # 1. positive clips → features
    print("\n[1/3] Extracting features from positive clips ...")
    pos_paths = sorted(_SYN.glob("*.wav")) + sorted(_REAL.glob("*.wav"))
    if not pos_paths:
        print("No positive clips. Run gen_wake_synthetic.py first.", file=sys.stderr)
        return 1
    import soundfile as sf
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures()
    WIN = 16               # model input = 16 feature windows x 96
    N = 48000             # 3s @ 16kHz — long enough to yield >=16 windows
    seqs = []             # (M, 16, 96) positive sequences (augmented by sliding)
    for p in pos_paths:
        try:
            audio, sr = sf.read(p)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            a16 = (audio * 32767).astype(np.int16) if audio.dtype != np.int16 else audio
            a16 = np.pad(a16, (0, max(0, N - len(a16))))[:N]
            w = np.array(af.embed_clips(a16[None, :], batch_size=1))[0]  # (windows, 96)
            # sliding 16-window sequences = cheap time-shift augmentation
            for start in range(0, max(1, len(w) - WIN + 1), 2):
                chunk = w[start:start + WIN]
                if len(chunk) == WIN:
                    seqs.append(chunk)
        except Exception as e:
            print(f"  skip {p.name}: {e}", file=sys.stderr)
    pos_feats = np.stack(seqs).astype(np.float32) if seqs else np.zeros((0, WIN, 96), np.float32)
    print(f"  positive clips: {len(pos_paths)} → {pos_feats.shape} sequences")

    # 2. negative features (download + reshape to (M,16,96))
    print("\n[2/3] Fetching negative features ...")
    want = ["validation_set_features.npy"]
    if full_negatives:
        want.append("openwakeword_features_ACAV100M_2000_hrs_16bit.npy")
    for name in want:
        if not _download(_NEG_URLS[name], _NEG_DIR / name):
            print("Negative download failed — cannot train without it.", file=sys.stderr)
            return 1
    neg_raw = np.load(_NEG_DIR / want[-1], mmap_mode="r")          # (K, 96)
    n_seq = len(neg_raw) // WIN
    neg_feats = np.ascontiguousarray(
        neg_raw[: n_seq * WIN].reshape(n_seq, WIN, 96).astype(np.float32))
    print(f"  negative sequences: {neg_feats.shape}")

    # 3. train (bounded: modest steps → PRELIMINARY model; retrain with more
    #    voices + full ACAV negatives for production quality)
    print("\n[3/3] Training ...")
    import torch   # speechbrain stub already installed at module load (top of file)
    from openwakeword.train import Model as TrainModel
    from openwakeword.data import mmap_batch_generator

    pos_path = _NEG_DIR / "_pos_feats.npy"
    neg_path = _NEG_DIR / "_neg_feats.npy"
    np.save(pos_path, pos_feats)
    np.save(neg_path, neg_feats)

    batch_size = 128
    n_pos = min(32, len(pos_feats))
    gen = mmap_batch_generator(
        data_files={str(neg_path): 0, str(pos_path): 1},
        n_per_class={str(neg_path): batch_size - n_pos, str(pos_path): n_pos},
        batch_size=batch_size,
    )

    def _loader(steps):
        for _ in range(steps):
            x, y = next(gen)
            yield [torch.from_numpy(np.asarray(x, np.float32)),
                   torch.from_numpy(np.asarray(y, np.int64))]

    steps = 5000            # bounded run; full recipe uses ~50k
    mdl = TrainModel(n_classes=1, input_shape=(WIN, 96), model_type="dnn")
    if torch.cuda.is_available():
        mdl.to("cuda")
    print(f"  training {steps} steps on {'cuda' if torch.cuda.is_available() else 'cpu'} ...")
    mdl.train_model(X=_loader(steps), max_steps=steps,
                    warmup_steps=steps // 5, hold_steps=steps // 3, lr=1e-4)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    mdl.export_to_onnx(str(_OUT))
    if _OUT.exists():
        print(f"\nOK: wrote {_OUT} ({_OUT.stat().st_size/1e3:.0f} KB)")
        print("PRELIMINARY model (150 single-voice synthetic + 15 real, small")
        print("negatives). Test with your mic; retrain with --full-negatives +")
        print("more piper voices for production reliability.")
        return 0
    print("Training finished but no ONNX produced.", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify prerequisites only")
    ap.add_argument("--full-negatives", action="store_true",
                    help="download the full ~30GB ACAV set (best quality)")
    args = ap.parse_args()
    if args.check:
        return 0 if check() else 1
    return train(args.full_negatives)


if __name__ == "__main__":
    sys.exit(main())
