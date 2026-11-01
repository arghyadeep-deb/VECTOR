"""
VECTOR Local Inference — Python port of Open-Generative-AI/electron/lib/localInference.js

Manages sd.cpp binary for offline Stable Diffusion image generation.
No ComfyUI needed — direct subprocess inference with platform-specific binaries.

Supported models: SD 1.5 (512px), SDXL (1024px), Flux (requires LLM + VAE).

Usage:
    inf = LocalInference()
    if inf.is_available():
        result = asyncio.run(inf.generate("A futuristic city", model="sdxl"))
        logger.info(result["image_path"])

"""
from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from loguru import logger

# Directories
_DATA_DIR = Path.home() / ".vector" / "local-ai"
_BIN_DIR  = _DATA_DIR / "bin"
_MODEL_DIR = _DATA_DIR / "models"
_TMP_DIR   = _DATA_DIR / "tmp"

for _d in (_BIN_DIR, _MODEL_DIR, _TMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_IS_WINDOWS = sys.platform == "win32"
_IS_MAC     = sys.platform == "darwin"
_IS_LINUX   = sys.platform.startswith("linux")
_ARCH       = platform.machine().lower()

_BIN_NAME   = "sd-cli.exe" if _IS_WINDOWS else "sd-cli"
_BIN_PATH   = _BIN_DIR / _BIN_NAME

# Model catalog — id → {name, sd_version, base_dim, hf_repo, filename}
LOCAL_MODEL_CATALOG: dict[str, dict] = {
    "sd15": {
        "name": "Stable Diffusion 1.5",
        "sd_version": "1",
        "base_dim": 512,
        "hf_repo": "runwayml/stable-diffusion-v1-5",
        "filename": "v1-5-pruned-emaonly.safetensors",
        "hf_url": "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors",
    },
    "sdxl": {
        "name": "Stable Diffusion XL",
        "sd_version": "xl",
        "base_dim": 1024,
        "hf_repo": "stabilityai/stable-diffusion-xl-base-1.0",
        "filename": "sd_xl_base_1.0.safetensors",
        "hf_url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
    },
}

_AR_TO_DIMS: dict[str, tuple[int, int]] = {
    "1:1":  (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3":  (4, 3),
    "3:4":  (3, 4),
}

_ACTIVE_PROC: Optional[subprocess.Popen] = None


def _ar_to_size(ar: str, base: int) -> tuple[int, int]:
    w_r, h_r = _AR_TO_DIMS.get(ar, (1, 1))
    if w_r == h_r:
        return base, base
    long = base
    short = round(long * min(w_r, h_r) / max(w_r, h_r) / 64) * 64
    if w_r >= h_r:
        return long, short
    return short, long


def _select_binary_variant() -> str | None:
    """
    Pick the correct sd.cpp release binary URL for this platform.
    Returns None if unsupported.
    """
    # GitHub releases: leejet/stable-diffusion.cpp
    BASE = "https://github.com/leejet/stable-diffusion.cpp/releases/latest/download"
    if _IS_WINDOWS:
        # Prefer CUDA, fall back to AVX2
        import subprocess as sp
        has_cuda = False
        try:
            sp.run(["nvcc", "--version"], capture_output=True, timeout=3)
            has_cuda = True
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        if has_cuda:
            return f"{BASE}/sd-master-win-cuda12-x64.zip"
        return f"{BASE}/sd-master-win-avx2-x64.zip"
    if _IS_MAC:
        if "arm" in _ARCH or "aarch64" in _ARCH:
            return f"{BASE}/sd-master-macos-arm64.zip"
        return None  # Intel macOS not supported
    if _IS_LINUX:
        if "x86_64" in _ARCH:
            return f"{BASE}/sd-master-linux-x86_64.zip"
    return None


class LocalInference:
    """
    VECTOR's local Stable Diffusion inference via sd.cpp binary.
    Works without ComfyUI — useful as offline fallback.
    """

    def is_available(self) -> bool:
        return _BIN_PATH.exists() and _BIN_PATH.stat().st_size > 100_000

    def model_path(self, model_id: str = "sdxl") -> Path:
        info = LOCAL_MODEL_CATALOG.get(model_id, {})
        return _MODEL_DIR / info.get("filename", f"{model_id}.safetensors")

    def model_downloaded(self, model_id: str = "sdxl") -> bool:
        p = self.model_path(model_id)
        return p.exists() and p.stat().st_size > 1_000_000

    def list_models(self) -> list[dict]:
        result = []
        for mid, info in LOCAL_MODEL_CATALOG.items():
            result.append({
                "id": mid,
                "name": info["name"],
                "downloaded": self.model_downloaded(mid),
                "path": str(self.model_path(mid)),
            })
        return result

    # â”€â”€ Binary management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def download_binary(self) -> bool:
        url = _select_binary_variant()
        if not url:
            logger.warning("[VECTOR][local_inf] Unsupported platform for sd.cpp: {} {}", sys.platform, _ARCH)
            return False
        logger.info("[VECTOR][local_inf] Downloading sd.cpp binary from {}", url[:80])
        zip_path = _TMP_DIR / "sd.zip"
        try:
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as c:
                async with c.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with zip_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(65536):
                            f.write(chunk)
            # Extract binary
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if _BIN_NAME in name or name.endswith(_BIN_NAME):
                        data = zf.read(name)
                        _BIN_PATH.write_bytes(data)
                        if not _IS_WINDOWS:
                            _BIN_PATH.chmod(0o755)
                        logger.info("[VECTOR][local_inf] Binary extracted to {}", _BIN_PATH)
                        return True
            logger.warning("[VECTOR][local_inf] Binary not found in archive")
            return False
        except Exception as e:
            logger.error("[VECTOR][local_inf] Binary download failed: {}", e)
            return False
        finally:
            if zip_path.exists():
                zip_path.unlink(missing_ok=True)

    async def download_model(self, model_id: str = "sdxl") -> bool:
        info = LOCAL_MODEL_CATALOG.get(model_id)
        if not info:
            raise ValueError(f"Unknown local model: {model_id}. Choose from: {list(LOCAL_MODEL_CATALOG)}")
        out_path = self.model_path(model_id)
        if self.model_downloaded(model_id):
            logger.info("[VECTOR][local_inf] {} already downloaded", model_id)
            return True
        url = info["hf_url"]
        logger.info("[VECTOR][local_inf] Downloading {} (~2-7GB) ...", info["name"])
        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as c:
                async with c.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    with out_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(1 << 20):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = round(downloaded / total * 100)
                                if pct % 10 == 0:
                                    logger.debug("[VECTOR][local_inf] {} {}%", model_id, pct)
            logger.info("[VECTOR][local_inf] {} downloaded → {}", model_id, out_path)
            return True
        except Exception as e:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            logger.error("[VECTOR][local_inf] Model download failed: {}", e)
            return False

    # â”€â”€ Inference â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def generate(
        self,
        prompt: str,
        model: str = "sdxl",
        negative_prompt: str = "",
        aspect_ratio: str = "1:1",
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int = -1,
        sampler: str = "euler_a",
    ) -> dict:
        global _ACTIVE_PROC
        if not self.is_available():
            raise RuntimeError(
                "sd.cpp binary not found. Run: await LocalInference().download_binary()"
            )
        if not self.model_downloaded(model):
            raise RuntimeError(
                f"Model '{model}' not downloaded. Run: await LocalInference().download_model('{model}')"
            )

        info = LOCAL_MODEL_CATALOG[model]
        base_dim = info["base_dim"]
        width, height = _ar_to_size(aspect_ratio, base_dim)
        output_path = _TMP_DIR / f"sd_output_{os.getpid()}.png"

        cmd = [
            str(_BIN_PATH),
            "-m", str(self.model_path(model)),
            "-p", prompt,
            "--negative-prompt", negative_prompt,
            "-W", str(width),
            "-H", str(height),
            "--steps", str(steps),
            "--cfg-scale", str(cfg_scale),
            "--seed", str(seed),
            "--sampling-method", sampler,
            "--sd-version", info["sd_version"],
            "-o", str(output_path),
        ]

        logger.info("[VECTOR][local_inf] {} {}x{} steps={}", model, width, height, steps)

        loop = asyncio.get_event_loop()

        def _run() -> tuple[int, list[str]]:
            global _ACTIVE_PROC
            progress_lines: list[str] = []
            with subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env={**os.environ, "LD_LIBRARY_PATH": str(_BIN_DIR)},
            ) as proc:
                _ACTIVE_PROC = proc
                for line in proc.stdout:  # type: ignore[union-attr]
                    line = line.rstrip()
                    if line:
                        progress_lines.append(line)
                        if "step" in line.lower():
                            logger.debug("[VECTOR][local_inf] {}", line)
                proc.wait()
                _ACTIVE_PROC = None
                return proc.returncode, progress_lines

        returncode, logs = await loop.run_in_executor(None, _run)
        if returncode != 0:
            raise RuntimeError(f"sd.cpp exited with code {returncode}. Logs: {chr(10).join(logs[-5:])}")
        if not output_path.exists():
            raise RuntimeError("sd.cpp completed but output PNG not found")
        logger.info("[VECTOR][local_inf] Generated → {}", output_path)
        return {"image_path": str(output_path), "model": model, "width": width, "height": height}

    async def cancel(self) -> None:
        global _ACTIVE_PROC
        if _ACTIVE_PROC and _ACTIVE_PROC.poll() is None:
            _ACTIVE_PROC.terminate()
            _ACTIVE_PROC = None
            logger.info("[VECTOR][local_inf] Generation cancelled")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    inf = LocalInference()
    available = inf.is_available()
    models = inf.list_models()
    print(f"OK local_inference.py — binary={'present' if available else 'missing (run download_binary())'}")
    print(f"  data_dir={_DATA_DIR}")
    for m in models:
        dl = "downloaded" if m["downloaded"] else "not downloaded"
        print(f"  {m['id']}: {m['name']} — {dl}")
