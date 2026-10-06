"""Retrain hey_vector wake model with features computed by the RUNTIME pipeline.

Why v2: the Jul-03 feature files (.npy) were produced by a different embedding
backend (tflite) than the runtime uses (onnx) — a model trained on them scores
~0 on live audio (verified 2026-07-11). This script recomputes EVERYTHING with
openwakeword's onnx AudioFeatures, so training space == inference space:

  positives:  615 recorded+synthetic "hey vector" clips × gain augmentation
              (0.25x/0.5x/1x/2x — covers the owner's quiet laptop mic)
  negatives:  Kokoro-TTS spoken sentences (incl. phonetic near-misses like
              "hey doctor"), plus noise/silence beds
  head:       openwakeword.train's exact Net (dnn, 128, 1 block)
  export:     legacy exporter (dynamo=False) → single self-contained .onnx

Usage:  python scripts/train_wake_v2.py     (PYTHONIOENCODING=utf-8)
Output: models/wake/hey_vector.onnx  (+ .pt checkpoint)
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn

ROOT = Path(__file__).parent.parent
WAKE = ROOT / "models" / "wake"
OUT = WAKE / "hey_vector.onnx"
CANDIDATE = WAKE / "hey_vector.candidate.onnx"


def _promote_candidate(candidate: Path, output: Path, passed: bool) -> bool:
    """Atomically install a validated model; discard a rejected candidate."""
    if passed:
        os.replace(candidate, output)
        return True
    candidate.unlink(missing_ok=True)
    return False

NEG_TEXTS = [
    "hey doctor, how are you today", "hey nectar is a strange name",
    "the director called a meeting", "hey there, what's the weather like",
    "okay detector, that's enough", "hector went to the market",
    "hey connector cable is loose", "play some music on the speaker",
    "what time is it right now", "open the window please",
    "turn off the lights in the kitchen", "the projector is not working",
    "hey listen to this song", "did you inspect the reactor",
    "my collector's edition arrived", "the spectre of doubt remained",
    "set a timer for ten minutes", "remind me to call mom tomorrow",
    "the weather is nice today isn't it", "let's go for a walk outside",
    "i need to finish my homework", "the meeting starts at five",
    "please close the door behind you", "the coffee is getting cold",
    "he factored the equation quickly", "a sector of the economy grew",
    "the tractor plowed the field", "she is the protector of the realm",
    "erector sets were popular toys", "the defector crossed the border",
    "good morning, how did you sleep", "the train leaves in an hour",
    "can you pass the salt please", "the movie was really entertaining",
    "i'm going to the gym later", "the deadline is next friday",
    "the stock market fell today", "dinner will be ready soon",
    "the library closes at nine", "my phone battery is dying",
]
VOICES = ["am_adam", "af_sarah", "bm_george", "am_michael"]


class FCNBlock(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.fcn_layer = nn.Linear(d, d)
        self.relu = nn.ReLU()
        self.layer_norm = nn.LayerNorm(d)

    def forward(self, x):
        return self.relu(self.layer_norm(self.fcn_layer(x)))


class Net(nn.Module):
    def __init__(self, input_shape=(16, 96), layer_dim=128, n_blocks=1):
        super().__init__()
        self.flatten = nn.Flatten()
        self.layer1 = nn.Linear(input_shape[0] * input_shape[1], layer_dim)
        self.relu1 = nn.ReLU()
        self.layernorm1 = nn.LayerNorm(layer_dim)
        self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
        self.last_layer = nn.Linear(layer_dim, 1)
        self.last_act = nn.Sigmoid()

    def forward(self, x):
        x = self.relu1(self.layernorm1(self.layer1(self.flatten(x))))
        for b in self.blocks:
            x = b(x)
        return self.last_act(self.last_layer(x))


def load_16k(path: Path) -> np.ndarray:
    a, sr = sf.read(str(path), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample_poly
        a = resample_poly(a, 16000, sr).astype(np.float32)
    return a


def to_i16(a: np.ndarray) -> np.ndarray:
    return np.clip(a * 32767, -32768, 32767).astype(np.int16)


def pad_center(a: np.ndarray, min_len: int = 32000) -> np.ndarray:
    """Embedding model needs >=76 mel frames AND a length that is a multiple of
    1280 samples (openwakeword's melspec batcher miscounts frames otherwise)."""
    target = max(min_len, int(np.ceil(len(a) / 1280)) * 1280)
    if len(a) == target:
        return a
    lead = (target - len(a)) // 2
    return np.concatenate([np.zeros(lead, np.float32), a,
                           np.zeros(target - len(a) - lead, np.float32)])


def clip_windows(feats: np.ndarray, max_windows: int = 5) -> list[np.ndarray]:
    """Pick up to max_windows 16-frame windows spread over a clip's features."""
    n = len(feats)
    if n < 16:
        return []
    if n == 16:
        return [feats]
    starts = np.unique(np.linspace(0, n - 16, min(max_windows, n - 15)).astype(int))
    return [feats[s:s + 16] for s in starts]


def main() -> bool:
    from openwakeword.utils import AudioFeatures
    F = AudioFeatures(inference_framework="onnx")

    # ── positives: real+synthetic clips × gain augmentation ────────────────
    pos_clips = sorted((WAKE / "positive_all").glob("*.wav"))
    print(f"positive clips: {len(pos_clips)}", flush=True)
    pos_windows = []
    edge_negatives = []   # padding-silence edges of positive clips = hard negatives
    gains = (0.25, 0.5, 1.0, 2.0)
    for idx, p in enumerate(pos_clips):
        raw = load_16k(p)
        base = pad_center(raw)
        padded = len(base) - len(raw) > 8000   # >0.5s of silence added
        peak = float(np.max(np.abs(base))) or 1.0
        for g in gains:
            a = to_i16(np.clip(base * g / max(peak, 0.15), -1, 1) * 0.9 * min(1.0, g + 0.25))
            feats = F.embed_clips(a[None, :], batch_size=1)[0]
            # the phrase is CENTRED by pad_center — only centre windows are
            # positive; sampling the whole clip labeled pure padding-silence
            # as "hey vector" (that bug made the model fire on silence)
            c = max(0, (len(feats) - 16) // 2)
            for s0 in {max(0, c - 2), c, min(len(feats) - 16, c + 2)}:
                pos_windows.append(feats[s0:s0 + 16])
            if padded and g == 1.0 and len(feats) >= 32:
                edge_negatives.append(feats[:16])
                edge_negatives.append(feats[-16:])
        if idx % 100 == 0:
            print(f"  pos {idx}/{len(pos_clips)}", flush=True)
    pos = np.stack(pos_windows)
    print(f"pos windows: {pos.shape}", flush=True)

    # ── negatives: Kokoro speech + noise beds ───────────────────────────────
    from kokoro_onnx import Kokoro
    kok = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.fp16-gpu.onnx"),
                 str(ROOT / "models/kokoro/voices-v1.0.bin"))
    neg_windows = []
    from scipy.signal import resample_poly
    for ti, text in enumerate(NEG_TEXTS):
        for v in (VOICES[ti % 4], VOICES[(ti + 2) % 4]):
            try:
                audio, sr = kok.create(text, voice=v, speed=1.0)
            except Exception as e:
                print(f"  kokoro fail ({v}): {e}", flush=True)
                continue
            a = pad_center(resample_poly(audio, 16000, sr).astype(np.float32))
            for g in (0.25, 1.0):
                feats = F.embed_clips(to_i16(np.clip(a * g, -1, 1))[None, :], batch_size=1)[0]
                neg_windows.extend(clip_windows(feats, max_windows=8))
        if ti % 10 == 0:
            print(f"  neg text {ti}/{len(NEG_TEXTS)}", flush=True)
    # noise + silence beds
    rng = np.random.default_rng(3)
    for kind in range(30):
        n = 16000 * 3
        if kind % 3 == 0:
            a = rng.normal(0, 0.05, n)                       # white
        elif kind % 3 == 1:
            a = np.cumsum(rng.normal(0, 0.01, n)); a = 0.1 * a / (np.abs(a).max() or 1)  # brown-ish
        else:
            a = rng.normal(0, 0.002, n)                      # near-silence hum
        feats = F.embed_clips(to_i16(a.astype(np.float32))[None, :], batch_size=1)[0]
        neg_windows.extend(clip_windows(feats, max_windows=10))
    neg_windows.extend(edge_negatives)
    zero_feats = F.embed_clips(np.zeros((1, 32000), dtype=np.int16), batch_size=1)[0]
    neg_windows.extend(clip_windows(zero_feats, max_windows=6) * 5)
    neg = np.stack(neg_windows)
    print(f"neg windows: {neg.shape} (incl. {len(edge_negatives)} padding-edge hard negatives)", flush=True)

    def train(pos, neg, epochs=150):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        x = np.concatenate([pos, neg]).astype(np.float32)
        y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))]).astype(np.float32)
        order = np.random.default_rng(7).permutation(len(x))
        x, y = x[order], y[order]
        n_hold = int(0.15 * len(x))
        x_hold = torch.tensor(x[:n_hold]).to(device); y_hold = torch.tensor(y[:n_hold]).to(device)
        x_tr = torch.tensor(x[n_hold:]); y_tr = torch.tensor(y[n_hold:])
        model = Net().to(device)
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        bce = nn.BCELoss(reduction="none")
        w_pos = max(0.34, len(neg) / max(1, len(pos)))
        best = {"score": -1.0, "state": None, "recall": 0, "fpr": 1}
        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(x_tr))
            for i in range(0, len(x_tr), 4096):
                b = perm[i:i + 4096]
                xb, yb = x_tr[b].to(device), y_tr[b].to(device)
                opt.zero_grad()
                out = model(xb).squeeze(-1)
                loss = (bce(out, yb) * torch.where(yb > .5, w_pos, 1.0)).mean()
                loss.backward(); opt.step()
            model.eval()
            with torch.no_grad():
                p = model(x_hold).squeeze(-1)
                recall = float(((p > .5) & (y_hold > .5)).sum() / max(1, (y_hold > .5).sum()))
                fpr = float(((p > .5) & (y_hold < .5)).sum() / max(1, (y_hold < .5).sum()))
            score = recall - 8 * fpr
            if recall >= 0.88 and score > best["score"]:
                best = {"score": score, "recall": recall, "fpr": fpr,
                        "state": {k: v.cpu().clone() for k, v in model.state_dict().items()}}
        if best["state"] is None:
            return None
        print(f"  trained: recall={best['recall']:.3f} fpr={best['fpr']:.4f}", flush=True)
        model.load_state_dict(best["state"]); model.to("cpu").eval()
        return model

    def export(model, output_path: Path):
        torch.save(model.state_dict(), WAKE / "hey_vector_head.pt")
        torch.onnx.export(model, torch.rand(1, 16, 96), str(output_path),
                          output_names=["hey_vector"], dynamo=False)

    def mine_streaming_negatives(kok, model_path: Path):
        """Harvest windows the CURRENT model fires on, via the exact streaming
        pipeline used at inference (batch-computed features differ subtly —
        streaming silence scored 0.8+ despite batch silence being a negative)."""
        from openwakeword.model import Model as OWW
        import onnxruntime as ort
        sess = ort.InferenceSession(str(model_path))
        iname = sess.get_inputs()[0].name
        m = OWW(wakeword_models=[str(model_path)], inference_framework="onnx")
        rng = np.random.default_rng(11)
        mined = []
        beds = [np.zeros(16000 * 4, np.float32),
                rng.normal(0, 0.05, 16000 * 4).astype(np.float32),
                rng.normal(0, 0.002, 16000 * 4).astype(np.float32)]
        b = np.cumsum(rng.normal(0, 0.01, 16000 * 4)); beds.append((0.1 * b / (np.abs(b).max() or 1)).astype(np.float32))
        for text, v in [("the quick brown fox jumps over the lazy dog", "am_adam"),
                        ("hey doctor can you check the reactor sector", "af_sarah"),
                        ("good evening sir how may i help you today", "bm_george")]:
            try:
                audio, sr = kok.create(text, voice=v, speed=1.0)
                from scipy.signal import resample_poly
                beds.append(pad_center(resample_poly(audio, 16000, sr).astype(np.float32)))
            except Exception:
                pass
        for bed in beds:
            m.reset()
            for pr in m.predict_clip(to_i16(np.clip(bed, -1, 1))):
                pass
            fb = np.asarray(m.preprocessor.feature_buffer)
            for i in range(0, max(1, len(fb) - 16), 2):
                w = fb[i:i + 16]
                if w.shape != (16, 96):
                    continue
                score = float(np.asarray(sess.run(None, {iname: w[None].astype(np.float32)})[0]).flatten()[0])
                if score > 0.15:
                    mined.append(w)
        print(f"  mined {len(mined)} streaming hard negatives", flush=True)
        return mined

    # ── train ────────────────────────────────────────────────────────────────
    model = train(pos, neg)
    if model is None:
        print("FAILED: recall never reached 0.88")
        return False
    CANDIDATE.unlink(missing_ok=True)
    export(model, CANDIDATE)
    # hard-negative mining rounds through the streaming pipeline
    for rnd in range(3):
        mined = mine_streaming_negatives(kok, CANDIDATE)
        if len(mined) < 3:
            print(f"  round {rnd}: streaming pipeline clean", flush=True)
            break
        neg = np.concatenate([neg, np.stack(mined)])
        # oversample mined negatives so they actually move the loss
        neg = np.concatenate([neg, np.stack(mined * 4)])
        model = train(pos, neg)
        if model is None:
            print("FAILED after mining round")
            return False
        export(model, CANDIDATE)

    # ── sanity through the REAL runtime ─────────────────────────────────────
    from openwakeword.model import Model as OWW
    m = OWW(wakeword_models=[str(CANDIDATE)], inference_framework="onnx")
    model_key = next(iter(m.models))
    def clip_score(path, gain=1.0):
        a = load_16k(Path(path))
        m.reset()
        return max(pr[model_key] for pr in m.predict_clip(to_i16(np.clip(a * gain, -1, 1))))
    s_syn = clip_score(WAKE / "synthetic/syn_0000.wav")
    s_real = clip_score(WAKE / "samples/sample_001.wav")
    s_real_q = clip_score(WAKE / "samples/sample_001.wav", 0.4)
    print(f"scores: synthetic={s_syn:.3f} real={s_real:.3f} real-quiet={s_real_q:.3f}", flush=True)
    neg_a = np.zeros(16000 * 2, dtype=np.int16)
    m.reset()
    s_sil = max(pr[model_key] for pr in m.predict_clip(neg_a))
    print(f"silence={s_sil:.3f}", flush=True)
    passed = s_syn > 0.5 and s_real > 0.5 and s_sil < 0.2
    return _promote_candidate(CANDIDATE, OUT, passed)


if __name__ == "__main__":
    ok = main()
    print("OK train_wake_v2" if ok else "FAILED train_wake_v2")
    sys.exit(0 if ok else 1)
