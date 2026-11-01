"""Train the hey_vector wake-word classifier head on ALREADY-PREPARED features.

The full openwakeword.train pipeline (piper TTS, noise augmentation, feature
extraction) was run on 2026-07-03/04 and left its products in
models/wake/negative_features/:
    _pos_feats.npy              (N, 16, 96)  positive embedding windows
    _neg_feats.npy              (M, 16, 96)  negative embedding windows
    validation_set_features.npy (T, 96)      long stream for FP-rate selection
Only the final classifier training + ONNX export was missing — this script does
exactly that, mirroring openwakeword.train's Net architecture and export
signature so core/voice/wake_word.py loads the result unchanged.

Usage: python scripts/train_wake_head.py
Output: models/wake/hey_vector.onnx
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).parent.parent
WAKE = ROOT / "models" / "wake"
FEATS = WAKE / "negative_features"
OUT = WAKE / "hey_vector.onnx"
CANDIDATE = WAKE / "hey_vector.candidate.onnx"


def _promote_candidate(candidate: Path, output: Path, passed: bool) -> bool:
    """Atomically install a validated model; discard a rejected candidate."""
    if passed:
        os.replace(candidate, output)
        return True
    candidate.unlink(missing_ok=True)
    return False


class FCNBlock(nn.Module):
    def __init__(self, layer_dim):
        super().__init__()
        self.fcn_layer = nn.Linear(layer_dim, layer_dim)
        self.relu = nn.ReLU()
        self.layer_norm = nn.LayerNorm(layer_dim)

    def forward(self, x):
        return self.relu(self.layer_norm(self.fcn_layer(x)))


class Net(nn.Module):
    """Identical to openwakeword.train's dnn Net (layer_dim=128, n_blocks=1)."""

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
        for block in self.blocks:
            x = block(x)
        return self.last_act(self.last_layer(x))


def window_stream(stream: np.ndarray, win: int = 16, hop: int = 8) -> np.ndarray:
    """Slice a (T, 96) embedding stream into (N, 16, 96) windows."""
    if win <= 0 or hop <= 0:
        raise ValueError("win and hop must be positive")
    n = max(0, (len(stream) - win) // hop + 1)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return stream[idx]


def main() -> bool:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pos = np.load(FEATS / "_pos_feats.npy").astype(np.float32)
    neg = np.load(FEATS / "_neg_feats.npy").astype(np.float32)
    val_stream = np.load(FEATS / "validation_set_features.npy").astype(np.float32)
    val_windows = window_stream(val_stream)  # negatives-only stream → FP counter
    print(f"pos={pos.shape} neg={neg.shape} val_windows={val_windows.shape} device={device}")

    x = np.concatenate([pos, neg])
    y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))]).astype(np.float32)

    # hold out 10% for accuracy/recall tracking
    rng = np.random.default_rng(7)
    order = rng.permutation(len(x))
    x, y = x[order], y[order]
    n_hold = int(0.1 * len(x))
    x_hold, y_hold = torch.tensor(x[:n_hold]), torch.tensor(y[:n_hold])
    x_tr, y_tr = torch.tensor(x[n_hold:]), torch.tensor(y[n_hold:])

    model = Net().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    # positives are ~8x rarer — weight them up so recall doesn't collapse
    pos_weight = len(neg) / max(1, len(pos))
    bce = nn.BCELoss(reduction="none")

    val_t = torch.tensor(val_windows).to(device)
    best = {"fp_per_hr": float("inf"), "recall": 0.0, "state": None}
    # validation stream length in hours: hop=8 frames ≈ 8*80ms = 0.64s per window
    stream_hours = (len(val_stream) * 0.08) / 3600.0

    batch = 4096
    for epoch in range(120):
        model.train()
        perm = torch.randperm(len(x_tr))
        for i in range(0, len(x_tr), batch):
            b = perm[i:i + batch]
            xb, yb = x_tr[b].to(device), y_tr[b].to(device)
            opt.zero_grad()
            out = model(xb).squeeze(-1)
            w = torch.where(yb > 0.5, pos_weight, 1.0)
            loss = (bce(out, yb) * w).mean()
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            hold_pred = model(x_hold.to(device)).squeeze(-1).cpu()
            recall = float(((hold_pred > 0.5) & (y_hold > 0.5)).sum() / max(1, (y_hold > 0.5).sum()))
            acc = float(((hold_pred > 0.5) == (y_hold > 0.5)).float().mean())
            fps = 0
            for i in range(0, len(val_t), 8192):
                fps += int((model(val_t[i:i + 8192]).squeeze(-1) > 0.5).sum())
            fp_per_hr = fps / max(stream_hours, 1e-6)

        if epoch % 10 == 0 or epoch == 119:
            print(f"epoch {epoch:3d} acc={acc:.3f} recall={recall:.3f} fp/hr={fp_per_hr:.2f}")

        # selection: require strong recall, then minimize false positives
        if recall >= 0.85 and (fp_per_hr < best["fp_per_hr"] or
                               (fp_per_hr == best["fp_per_hr"] and recall > best["recall"])):
            best = {"fp_per_hr": fp_per_hr, "recall": recall,
                    "state": {k: v.cpu().clone() for k, v in model.state_dict().items()}}

    if best["state"] is None:
        print("FAILED: no epoch reached recall >= 0.85")
        return False

    print(f"BEST: recall={best['recall']:.3f} fp/hr={best['fp_per_hr']:.2f}")
    model.load_state_dict(best["state"])
    model.to("cpu").eval()
    torch.save(best["state"], WAKE / "hey_vector_head.pt")  # re-exportable without retraining
    # dynamo=False: the legacy exporter writes ONE self-contained .onnx. The new
    # dynamo exporter split weights into hey_vector.onnx.data AND crashes printing
    # an emoji on Windows cp1252 consoles — exactly how the Jul 3 attempt died.
    CANDIDATE.unlink(missing_ok=True)
    torch.onnx.export(model, torch.rand(1, 16, 96), str(CANDIDATE),
                      output_names=["hey_vector"], dynamo=False)
    size = CANDIDATE.stat().st_size
    print(f"exported candidate {CANDIDATE} ({size} bytes)")

    # sanity: load through openwakeword and score a REAL recorded sample
    from openwakeword.model import Model as OWWModel
    import soundfile as sf
    m = OWWModel(wakeword_models=[str(CANDIDATE)], inference_framework="onnx")
    model_key = next(iter(m.models))
    sample, sr = sf.read(str(WAKE / "samples" / "sample_001.wav"), dtype="int16")
    scores = [p[model_key] for p in m.predict_clip(sample)]
    print(f"real-sample max score: {max(scores):.3f} (threshold 0.5)")
    return _promote_candidate(CANDIDATE, OUT, max(scores) > 0.5)


if __name__ == "__main__":
    ok = main()
    print("OK train_wake_head" if ok else "FAILED train_wake_head")
    sys.exit(0 if ok else 1)
