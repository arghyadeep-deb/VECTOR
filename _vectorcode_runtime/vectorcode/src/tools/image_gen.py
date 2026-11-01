"""Image generation and vision analysis tools."""

import sys
from pathlib import Path
from loguru import logger

import asyncio
import base64
import os
from typing import Optional


async def generate_image(
    prompt: str,
    model: str = "fal-ai/flux-pro",
    *,
    backend: str = "auto",
    api_key: Optional[str] = None,
    size: str = "1024x1024",
    num_images: int = 1,
    output_dir: Optional[str] = None,
) -> dict:
    """Generate one or more images from a text prompt.

    backend choices:
      "fal"       — FAL.ai cloud API (requires fal-client + api_key / FAL_KEY env var)
      "diffusers" — Local Stable Diffusion via diffusers + torch
      "auto"      — try fal first; fallback diffusers; fallback error dict

    Returns:
        {"urls": [...], "paths": [...], "model": model, "backend": backend_used, "success": True}
        {"error": "...", "success": False}  on failure
    """
    if backend == "fal":
        return await _generate_fal(prompt, model, api_key=api_key, size=size,
                                   num_images=num_images, output_dir=output_dir)
    if backend == "diffusers":
        return await _generate_diffusers(prompt, model, size=size,
                                         num_images=num_images, output_dir=output_dir)

    # auto — cascade
    fal_key = api_key or os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if fal_key:
        result = await _generate_fal(prompt, model, api_key=fal_key, size=size,
                                     num_images=num_images, output_dir=output_dir)
        if result.get("success"):
            return result
        logger.warning("[VECTOR][image_gen] FAL failed (%s), falling back to diffusers",
                       result.get("error"))

    result = await _generate_diffusers(prompt, model, size=size,
                                       num_images=num_images, output_dir=output_dir)
    if result.get("success"):
        return result

    logger.error("[VECTOR][image_gen] all backends failed")
    return {"error": "no backend available", "success": False}


async def _generate_fal(
    prompt: str,
    model: str,
    *,
    api_key: Optional[str],
    size: str,
    num_images: int,
    output_dir: Optional[str],
) -> dict:
    """Generate via FAL.ai using the fal_client package."""
    try:
        import fal_client  # type: ignore
    except ImportError:
        logger.warning("[VECTOR][image_gen] fal-client not installed: pip install fal-client")
        return {"error": "fal-client not installed", "success": False}

    try:
        if api_key:
            os.environ["FAL_KEY"] = api_key

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: fal_client.run(model, arguments={
                "prompt": prompt,
                "image_size": size,
                "num_images": num_images,
            }),
        )

        images = result.get("images", [])
        urls = [img.get("url", img) if isinstance(img, dict) else img for img in images]

        # Optionally save locally
        paths: list[str] = []
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                for idx, url in enumerate(urls):
                    resp = await client.get(url)
                    resp.raise_for_status()
                    ext = url.rsplit(".", 1)[-1].split("?")[0] or "png"
                    dest = out / f"image_{idx}.{ext}"
                    dest.write_bytes(resp.content)
                    paths.append(str(dest))
                    logger.info("[VECTOR][image_gen] saved %s", dest)

        logger.info("[VECTOR][image_gen] FAL generated %d image(s) for model %s", len(urls), model)
        return {"urls": urls, "paths": paths, "model": model, "backend": "fal", "success": True}

    except Exception as e:
        logger.error("[VECTOR][image_gen] FAL error: %s", e)
        return {"error": str(e), "success": False}


async def _generate_diffusers(
    prompt: str,
    model: str,
    *,
    size: str,
    num_images: int,
    output_dir: Optional[str],
) -> dict:
    """Generate locally using the diffusers library + torch."""
    try:
        from diffusers import StableDiffusionPipeline  # type: ignore
        import torch  # type: ignore
    except ImportError:
        logger.warning("[VECTOR][image_gen] diffusers/torch not installed")
        return {"error": "diffusers+torch not installed", "success": False}

    try:
        # Use a known SD model when the passed model is a FAL model id
        local_model = model if "/" in model and "fal" not in model else "runwayml/stable-diffusion-v1-5"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        logger.info("[VECTOR][image_gen] loading diffusers pipeline %s on %s", local_model, device)

        loop = asyncio.get_event_loop()
        pipe = await loop.run_in_executor(
            None,
            lambda: StableDiffusionPipeline.from_pretrained(
                local_model, torch_dtype=dtype
            ).to(device),
        )

        width, height = _parse_size(size)

        def _run_pipe():
            return pipe(
                prompt,
                width=width,
                height=height,
                num_images_per_prompt=num_images,
            ).images

        images = await loop.run_in_executor(None, _run_pipe)

        out_dir = Path(output_dir) if output_dir else Path.home() / ".vector" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        paths: list[str] = []
        for idx, img in enumerate(images):
            dest = out_dir / f"image_{idx}.png"
            img.save(str(dest))
            paths.append(str(dest))
            logger.info("[VECTOR][image_gen] diffusers saved %s", dest)

        logger.info("[VECTOR][image_gen] diffusers generated %d image(s)", len(paths))
        return {
            "urls": [],
            "paths": paths,
            "model": local_model,
            "backend": "diffusers",
            "success": True,
        }

    except Exception as e:
        logger.error("[VECTOR][image_gen] diffusers error: %s", e)
        return {"error": str(e), "success": False}


def _parse_size(size: str) -> tuple[int, int]:
    """Parse '1024x1024' → (1024, 1024). Falls back to (512, 512)."""
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except Exception:
        return 512, 512


# ─────────────────────────────────────────────────────────────────────────────

async def describe_image(
    image_path_or_url: str,
    *,
    question: str = "Describe this image in detail.",
    model_id: str = "ollama/llava:latest",
) -> dict:
    """Analyse an image with a vision model.

    Two routing modes:
      model_id starts with "ollama/"  → ollama.chat() with images parameter (local)
      model_id starts with "claude"   → Anthropic API messages endpoint

    Returns:
        {"description": "...", "model": model_id, "success": True}
        {"error": "...", "success": False}
    """
    if model_id.startswith("ollama/"):
        return await _describe_ollama(image_path_or_url, question=question, model_id=model_id)
    if model_id.startswith("claude"):
        return await _describe_anthropic(image_path_or_url, question=question, model_id=model_id)

    return {"error": f"Unsupported model_id prefix: {model_id}", "success": False}


async def _load_image_bytes(image_path_or_url: str) -> bytes:
    """Load image from local path or remote URL and return raw bytes."""
    if image_path_or_url.startswith("http://") or image_path_or_url.startswith("https://"):
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_path_or_url)
            resp.raise_for_status()
            return resp.content
    else:
        return Path(image_path_or_url).read_bytes()


async def _describe_ollama(
    image_path_or_url: str,
    *,
    question: str,
    model_id: str,
) -> dict:
    """Use ollama Python SDK with vision (llava or similar)."""
    try:
        import ollama  # type: ignore
    except ImportError:
        logger.warning("[VECTOR][image_gen] ollama package not installed: pip install ollama")
        return {"error": "ollama package not installed", "success": False}

    try:
        model_name = model_id.split("/", 1)[1]  # strip "ollama/" prefix
        img_bytes = await _load_image_bytes(image_path_or_url)
        b64 = base64.b64encode(img_bytes).decode()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: ollama.chat(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": question,
                    "images": [b64],
                }],
            ),
        )

        description = response["message"]["content"]
        logger.info("[VECTOR][image_gen] ollama vision OK model=%s", model_name)
        return {"description": description, "model": model_id, "success": True}

    except Exception as e:
        logger.error("[VECTOR][image_gen] ollama describe error: %s", e)
        return {"error": str(e), "success": False}


async def _describe_anthropic(
    image_path_or_url: str,
    *,
    question: str,
    model_id: str,
) -> dict:
    """Use Anthropic messages API for vision."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        logger.warning("[VECTOR][image_gen] anthropic package not installed")
        return {"error": "anthropic package not installed", "success": False}

    try:
        img_bytes = await _load_image_bytes(image_path_or_url)
        b64 = base64.b64encode(img_bytes).decode()

        # Detect media type from first bytes
        media_type = _guess_media_type(img_bytes)

        loop = asyncio.get_event_loop()
        client = anthropic.Anthropic()
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=model_id,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": question},
                    ],
                }],
            ),
        )

        description = response.content[0].text
        logger.info("[VECTOR][image_gen] anthropic vision OK model=%s", model_id)
        return {"description": description, "model": model_id, "success": True}

    except Exception as e:
        logger.error("[VECTOR][image_gen] anthropic describe error: %s", e)
        return {"error": str(e), "success": False}


def _guess_media_type(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] in (b"RIFF", b"WEBP"):
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"  # safe default


# ─────────────────────────────────────────────────────────────────────────────

def get_tool_schemas() -> list[dict]:
    """Return OpenAI-format tool schemas for generate_image and describe_image."""
    return [
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": (
                    "Generate one or more images from a text prompt. "
                    "Supports FAL.ai cloud (fast) and local Stable Diffusion (offline)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Detailed text description of the image to generate",
                        },
                        "model": {
                            "type": "string",
                            "default": "fal-ai/flux-pro",
                            "description": "Model/pipeline identifier (e.g. 'fal-ai/flux-pro')",
                        },
                        "backend": {
                            "type": "string",
                            "enum": ["auto", "fal", "diffusers"],
                            "default": "auto",
                            "description": "Backend to use: 'fal' (cloud), 'diffusers' (local), 'auto' (cascade)",
                        },
                        "size": {
                            "type": "string",
                            "default": "1024x1024",
                            "description": "Image dimensions as WIDTHxHEIGHT (e.g. '512x512')",
                        },
                        "num_images": {
                            "type": "integer",
                            "default": 1,
                            "description": "Number of images to generate",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Directory to save generated images locally (optional)",
                        },
                    },
                    "required": ["prompt"],
                },
            },
            "_meta": {"risk": "medium", "read_only": False},
        },
        {
            "type": "function",
            "function": {
                "name": "describe_image",
                "description": (
                    "Analyse an image and answer a question about it. "
                    "Supports local Ollama vision models (llava) or Claude via Anthropic API."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path_or_url": {
                            "type": "string",
                            "description": "Local file path or https:// URL of the image",
                        },
                        "question": {
                            "type": "string",
                            "default": "Describe this image in detail.",
                            "description": "Question or instruction for the vision model",
                        },
                        "model_id": {
                            "type": "string",
                            "default": "ollama/llava:latest",
                            "description": (
                                "Model to use. Prefix 'ollama/' for local (e.g. 'ollama/llava:latest'), "
                                "'claude-...' for Anthropic API."
                            ),
                        },
                    },
                    "required": ["image_path_or_url"],
                },
            },
            "_meta": {"risk": "safe", "read_only": True},
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _smoke():
        # --- describe_image: no real model available, confirm graceful failure ---
        result = await describe_image(
            "https://httpbin.org/image/png",
            question="What color is dominant?",
            model_id="ollama/llava:latest",
        )
        # ollama may not be running; either succeeds or returns structured error
        assert "success" in result, f"describe_image missing 'success' key: {result}"
        if result["success"]:
            assert "description" in result
            logger.info("[VECTOR][image_gen] describe_image OK: %s", result["description"][:80])
        else:
            logger.warning("[VECTOR][image_gen] describe_image (expected if ollama offline): %s",
                           result["error"])

        # --- generate_image: no api_key → auto cascades to error (no fal key + no diffusers) ---
        result2 = await generate_image(
            "a golden sunrise over mountains",
            backend="auto",
            api_key=None,
        )
        assert "success" in result2, f"generate_image missing 'success' key: {result2}"
        if result2["success"]:
            logger.info("[VECTOR][image_gen] generate_image OK backend=%s paths=%s",
                        result2.get("backend"), result2.get("paths"))
        else:
            logger.warning("[VECTOR][image_gen] generate_image (expected without backends): %s",
                           result2.get("error"))

        # --- schemas ---
        schemas = get_tool_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert "generate_image" in names
        assert "describe_image" in names
        logger.info("[VECTOR][image_gen] %d tool schemas OK", len(schemas))

        sys.stdout.reconfigure(encoding="utf-8")
        print("✅ tools/image_gen.py OK")

    asyncio.run(_smoke())
