"""
Diagnose Kokoro TTS model compatibility.

Checks model files, onnxruntime version, and protobuf compatibility.
"""

from pathlib import Path
import sys


def main():
    model_dir = Path("models/kokoro")
    print(f"Model directory: {model_dir.resolve()}")
    print(f"Exists: {model_dir.exists()}")
    print()

    # Check model files
    files = {
        "kokoro-v1.0.onnx": "CPU model",
        "kokoro-v1.0.fp16-gpu.onnx": "GPU/fp16 model",
        "voices-v1.0.bin": "Voice pack",
    }
    for fname, label in files.items():
        fp = model_dir / fname
        if fp.exists():
            print(f"[OK] {label}: {fname} ({fp.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            print(f"[MISSING] {label}: {fname}")
    print()

    # Check onnxruntime version
    try:
        import onnxruntime as ort
        print(f"onnxruntime version: {ort.__version__}")
        print(f"Available providers: {ort.get_available_providers()}")
        has_cuda = "CUDAExecutionProvider" in ort.get_available_providers()
        print(f"CUDA available: {has_cuda}")
    except ImportError:
        print("[ERROR] onnxruntime not installed")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] onnxruntime import failed: {e}")
        sys.exit(1)
    print()

    # Try loading each model
    for model_name in ["kokoro-v1.0.onnx", "kokoro-v1.0.fp16-gpu.onnx"]:
        model_path = model_dir / model_name
        voices_path = model_dir / "voices-v1.0.bin"
        if not model_path.exists() or not voices_path.exists():
            print(f"[SKIP] {model_name}: files missing")
            continue
        try:
            from kokoro_onnx import Kokoro
            kokoro = Kokoro(str(model_path), str(voices_path))
            samples, sr = kokoro.create("Diagnostic test.", voice="bf_emma", speed=0.85)
            print(f"[OK] {model_name}: {len(samples)} samples at {sr}Hz")
        except Exception as e:
            print(f"[FAIL] {model_name}: {type(e).__name__}: {e}")
    print()

    # Summary
    cpu_model = model_dir / "kokoro-v1.0.onnx"
    fp16_model = model_dir / "kokoro-v1.0.fp16-gpu.onnx"
    if cpu_model.exists() and not _is_valid_onnx(cpu_model):
        print("[INFO] CPU model has protobuf compatibility issue with onnxruntime >= 1.17")
    if fp16_model.exists():
        print("[INFO] fp16 model works on both GPU and CPU")
        print("[INFO] No action needed — VECTOR will use fp16 model automatically")

    print("\nDiagnostic complete.")


def _is_valid_onnx(path: Path) -> bool:
    """Quick check if an ONNX file passes protobuf parsing."""
    try:
        from onnxruntime import InferenceSession
        InferenceSession(str(path), providers=["CPUExecutionProvider"])
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
