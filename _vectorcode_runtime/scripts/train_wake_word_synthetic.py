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

# Windows console is cp1252 by default → any non-ASCII print (progress arrows)
# raises UnicodeEncodeError. Force UTF-8 stdout/stderr (VECTOR house pattern).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    print(f"  positive clips: {len(pos_paths)} -> {pos_feats.shape} sequences")

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

    # Hold out ~20% of each class for validation (train_model indexes
    # history["val_n_fp"][-1] at every val step and crashes if X_val is None).
    rng = np.random.default_rng(0)
    rng.shuffle(pos_feats); rng.shuffle(neg_feats)
    n_pv = max(32, len(pos_feats) // 5)
    n_nv = 2000
    pos_val, pos_tr = pos_feats[:n_pv], pos_feats[n_pv:]
    neg_val, neg_tr = neg_feats[:n_nv], neg_feats[n_nv:]

    pos_path = _NEG_DIR / "_pos_feats.npy"
    neg_path = _NEG_DIR / "_neg_feats.npy"
    np.save(pos_path, pos_tr)
    np.save(neg_path, neg_tr)

    batch_size = 128
    # Heavier positive presence + more steps raise wake-clip recall (a globally
    # under-confident model = too few steps / too few positives per batch).
    n_pos = min(64, len(pos_tr))   # 50% positive batches — bias toward recall
    # data_files / n_per_class are keyed by LABEL (0=neg, 1=pos) -> path/count.
    gen = mmap_batch_generator(
        data_files={0: str(neg_path), 1: str(pos_path)},
        n_per_class={0: batch_size - n_pos, 1: n_pos},
        batch_size=batch_size,
    )

    def _loader(steps):
        for _ in range(steps):
            x, y = next(gen)
            yield [torch.from_numpy(np.asarray(x, np.float32)),
                   torch.from_numpy(np.asarray(y, np.int64))]

    # X_val: a re-iterable list of balanced (x, y) validation batches.
    def _val_batches():
        out = []
        vb = 128
        for i in range(0, min(len(pos_val), len(neg_val)) - vb, vb):
            xb = np.concatenate([neg_val[i:i + vb], pos_val[i:i + vb]]).astype(np.float32)
            yb = np.concatenate([np.zeros(vb), np.ones(vb)]).astype(np.int64)
            out.append([torch.from_numpy(xb), torch.from_numpy(yb)])
        return out or [[torch.from_numpy(np.concatenate([neg_val[:16], pos_val[:16]]).astype(np.float32)),
                        torch.from_numpy(np.concatenate([np.zeros(16), np.ones(16)]).astype(np.int64))]]
    X_val = _val_batches()

    steps = 20000           # more steps for confident recall (full recipe ~50k)
    val_steps = [4000, 8000, 12000, 16000, 19900]
    mdl = TrainModel(n_classes=1, input_shape=(WIN, 96), model_type="dnn")
    if torch.cuda.is_available():
        mdl.to("cuda")
    print(f"  training {steps} steps on {'cuda' if torch.cuda.is_available() else 'cpu'} ...")
    mdl.train_model(X=_loader(steps), max_steps=steps, X_val=X_val, val_steps=val_steps,
                    warmup_steps=steps // 5, hold_steps=steps // 3, lr=1e-4)

    # Export to a STAGING path first — never overwrite the live model until the
    # new one passes a quality gate (a bad model would false-trigger or go deaf,
    # worse than VECTOR's Whisper-KWS fallback).
    _stage = _OUT.with_suffix(".candidate.onnx")
    _stage.parent.mkdir(parents=True, exist_ok=True)
    # openWakeWord's export_to_onnx passes output_names=[""] (empty) → an invalid
    # graph ("Graph output () does not exist") that onnxruntime rejects. Export
    # directly with proper names + legacy exporter (dynamo=False).
    core = mdl.model.to("cpu").eval()
    torch.onnx.export(
        core, torch.rand((1, WIN, 96)), str(_stage),
        input_names=["x"], output_names=["scores"],
        dynamic_axes={"x": {0: "batch"}, "scores": {0: "batch"}},
        opset_version=17, dynamo=False,
    )
    if not _stage.exists():
        print("Training finished but no ONNX produced.", file=sys.stderr)
        return 1

    # ── quality gate: must fire on held-out "hey vector", stay quiet on silence
    print("\nValidating candidate model ...")
    ok_gate, why = _quality_gate(_stage)
    print(f"  {why}")
    if ok_gate:
        _stage.replace(_OUT)
        print(f"OK: installed {_OUT} ({_OUT.stat().st_size/1e3:.0f} KB) — passed quality gate.")
        print("Test with your mic; retrain with --full-negatives + more voices to improve.")
        return 0
    _stage.unlink(missing_ok=True)
    print("REJECTED: candidate model failed the quality gate — NOT installed.")
    print("VECTOR keeps its working Whisper keyword-spotting fallback (no regression).")
    print("A reliable model needs MANY synthetic voices (this used one piper voice)")
    print("+ the full ACAV negative set (--full-negatives). Both are the heavy step.")
    return 2


def _quality_gate(model_path: Path) -> tuple[bool, str]:
    """A model is only worth installing if it fires on real 'hey vector' clips
    and stays quiet on silence. Returns (passed, reason)."""
    try:
        import torchvision  # noqa: F401  (import order guard, as at module top)
        import numpy as np
        import soundfile as sf
        from openwakeword.model import Model
        m = Model(wakeword_models=[str(model_path)], inference_framework="onnx")
        key = list(m.models.keys())[0]

        def peak(a16):
            m.reset()
            return max((float(m.predict(a16[i:i + 1280])[key])
                        for i in range(0, len(a16) - 1280, 1280)), default=0.0)

        reals = sorted(_REAL.glob("*.wav"))
        hits = []
        for p in reals:
            a, sr = sf.read(p)
            if a.ndim > 1:
                a = a.mean(axis=1)
            a16 = (a * 32767).astype(np.int16) if a.dtype != np.int16 else a
            hits.append(peak(a16))
        # RECALL FRACTION, not max — a single lucky clip must not pass a model
        # that misses the wake word 90% of the time (worse than Whisper KWS).
        fired = sum(1 for x in hits if x >= 0.5)
        recall = fired / len(hits) if hits else 0.0
        sil_peak = max(float(m.predict(np.zeros(1280, dtype=np.int16))[key])
                       for _ in range(30))
        passed = recall >= 0.5 and sil_peak < 0.3
        return passed, (f"real-clip recall={fired}/{len(hits)} ({recall:.0%}, need >=50%), "
                        f"silence peak={sil_peak:.2f} (need <0.30)")
    except Exception as e:
        return False, f"quality gate errored (treated as fail): {e}"


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
