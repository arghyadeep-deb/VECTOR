"""
Module: core/training/openmythos/export_to_ollama.py
Export trained models to Ollama registry.
"""

import sys

__all__ = [
    "main",
    "OllamaExporter",
]

from pathlib import Path

from core.config import CONFIG
from loguru import logger
import ollama
import json
import shutil
import os
import re
from typing import List, Dict, Any, Optional


_SAFE_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _is_safe_model_name(model_name: str) -> bool:
    return isinstance(model_name, str) and _SAFE_MODEL_NAME.fullmatch(model_name) is not None


class OllamaExporter:
    """Export utility for trained models to Ollama registry."""

    def __init__(self):
        self.ollama_host = CONFIG["ollama_host"]
        self.model_dir = CONFIG.get("openmythos", {}).get("model_dir", "./models/custom")
        self.registry_path = Path(self.model_dir) / "registry"
        self.registry_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"[OpenMythos] Ollama exporter initialized at {self.ollama_host}")

    def export_model_weights(
        self,
        src_path: str,
        model_name: str,
    ) -> Dict[str, Any]:
        """
        Copy model weights from source to Ollama registry.

        Args:
            src_path: Path to the source model weights
            model_name: Name for the model in registry

        Returns:
            Dict with export status and path
        """
        src = Path(src_path)
        if not _is_safe_model_name(model_name):
            logger.error("[OpenMythos] Invalid model name")
            return {"success": False, "error": "Invalid model name"}
        if not src.exists():
            logger.error(f"[OpenMythos] Source model not found: {src_path}")
            return {"success": False, "error": "Source not found"}

        dest = self.registry_path / model_name
        if dest.exists():
            logger.warning(f"[OpenMythos] Model {model_name} already exists, overwriting")

        try:
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

            logger.info(f"[OpenMythos] Model weights exported to {dest}")
            return {"success": True, "path": str(dest), "model_name": model_name}
        except Exception as e:
            logger.error(f"[OpenMythos] Export failed: {e}")
            return {"success": False, "error": str(e)}

    def create_modelfile(
        self,
        model_name: str,
        system_prompt: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create an Ollama Modelfile for the exported model.

        Args:
            model_name: Name of the model
            system_prompt: System prompt for the model
            parameters: Optional model parameters (temperature, top_p, etc.)

        Returns:
            Path to the created Modelfile
        """
        if not _is_safe_model_name(model_name):
            logger.error("[OpenMythos] Invalid model name")
            return ""
        model_path = self.registry_path / model_name
        if not model_path.exists():
            logger.error(f"[OpenMythos] Model not found: {model_name}")
            return ""

        modelfile_path = model_path / "Modelfile"

        base_model = "llama2"
        if parameters and "base_model" in parameters:
            base_model = parameters["base_model"]

        content = f"FROM {base_model}\n\n"
        content += f"SYSTEM \"\"\"\n{system_prompt}\n\"\"\"\n\n"

        if parameters:
            param_mapping = {
                "temperature": "temperature",
                "top_p": "top_p",
                "top_k": "top_k",
                "num_predict": "num_predict",
                "repeat_penalty": "repeat_penalty",
                "presence_penalty": "presence_penalty",
                "frequency_penalty": "frequency_penalty",
            }

            for param_name, config_key in param_mapping.items():
                config_value = parameters.get(config_key)
                if config_value is not None:
                    content += f"PARAMETER {param_name} {config_value}\n"

        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"[OpenMythos] Modelfile created at {modelfile_path}")
        return str(modelfile_path)

    def push_to_ollama(self, model_name: str) -> Dict[str, Any]:
        """
        Push a model to the local Ollama registry.

        Args:
            model_name: Name of the model to push

        Returns:
            Dict with push status
        """
        if not _is_safe_model_name(model_name):
            return {"success": False, "error": "Invalid model name"}
        model_path = self.registry_path / model_name
        if not model_path.exists():
            logger.error(f"[OpenMythos] Model not found: {model_name}")
            return {"success": False, "error": "Model not found"}

        try:
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed.
            with ollama.Client(self.ollama_host) as client:
                modelfile_path = model_path / "Modelfile"
                if modelfile_path.exists():
                    with open(modelfile_path, "r", encoding="utf-8") as f:
                        modelfile_content = f.read()

                    logger.info(f"[OpenMythos] Creating model {model_name} from Modelfile")
                    client.create(
                        model=model_name,
                        modelfile=modelfile_content,
                        path=str(model_path),
                    )
                else:
                    logger.info(f"[OpenMythos] Creating model {model_name} from path")
                    client.create(
                        model=model_name,
                        path=str(model_path),
                    )

            logger.info(f"[OpenMythos] Model {model_name} pushed to Ollama")
            return {"success": True, "model_name": model_name}

        except Exception as e:
            logger.error(f"[OpenMythos] Push failed: {e}")
            return {"success": False, "error": str(e)}

    def list_ollama_models(self) -> List[Dict[str, Any]]:
        """
        List all available models in the local Ollama registry.

        Returns:
            List of model information dicts
        """
        try:
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py).
            with ollama.Client(self.ollama_host) as client:
                response = client.list()
            models = response.get("models", [])

            logger.info(f"[OpenMythos] Found {len(models)} Ollama models")
            return models
        except Exception as e:
            logger.error(f"[OpenMythos] Failed to list models: {e}")
            return []

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """
        Pull a model from Ollama.

        Args:
            model_name: Name of the model to pull

        Returns:
            Dict with pull status
        """
        try:
            logger.info(f"[OpenMythos] Pulling model: {model_name}")

            # 2026-08-05 (connection-leak fix, same as ollama_safe.py). Not
            # streamed (stream defaults False), so `response` is a fully
            # resolved Mapping by the time the client closes — safe to
            # iterate after the `with` block exits.
            with ollama.Client(self.ollama_host) as client:
                response = client.pull(model_name)
            for part in response:
                status = part.get("status", "")
                logger.debug(f"[OpenMythos] Pull status: {status}")

            logger.info(f"[OpenMythos] Model {model_name} pulled successfully")
            return {"success": True, "model_name": model_name}
        except Exception as e:
            logger.error(f"[OpenMythos] Pull failed: {e}")
            return {"success": False, "error": str(e)}

    def delete_model(self, model_name: str) -> Dict[str, Any]:
        """
        Delete a model from the local registry.

        Args:
            model_name: Name of the model to delete

        Returns:
            Dict with deletion status
        """
        try:
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py).
            with ollama.Client(self.ollama_host) as client:
                client.delete(model_name)

            # Ollama names may legitimately contain namespaces/tags. Only map
            # the name to a local directory when it is a single safe segment.
            if _is_safe_model_name(model_name):
                local_path = self.registry_path / model_name
                if local_path.exists():
                    shutil.rmtree(local_path)

            logger.info(f"[OpenMythos] Model {model_name} deleted")
            return {"success": True, "model_name": model_name}
        except Exception as e:
            logger.error(f"[OpenMythos] Delete failed: {e}")
            return {"success": False, "error": str(e)}

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a model.

        Args:
            model_name: Name of the model

        Returns:
            Dict with model information
        """
        try:
            # 2026-08-05 connection-leak fix (same as the other sites in this
            # file): must be `with ... as client:`, not a bare assignment —
            # ollama.Client() wraps an httpx.Client with its own pool, and
            # httpx.Client has no __del__, so an unclosed one leaks its socket
            # until a cyclic-GC sweep happens to collect it.
            with ollama.Client(self.ollama_host) as client:
                response = client.show(model_name)

            return {
                "success": True,
                "model_name": model_name,
                "info": response,
            }
        except Exception as e:
            logger.error(f"[OpenMythos] Get info failed: {e}")
            return {"success": False, "error": str(e)}

    def list_local_models(self) -> List[str]:
        """
        List models stored in the local registry directory.

        Returns:
            List of model names
        """
        models = []
        if self.registry_path.exists():
            for item in self.registry_path.iterdir():
                if item.is_dir():
                    models.append(item.name)
        return models


async def main():
    """Test the Ollama exporter."""
    exporter = OllamaExporter()

    logger.info("Local registry models:", exporter.list_local_models())

    logger.info("Ollama models:", exporter.list_ollama_models())


    result = exporter.export_model_weights(
        "./models/test",
        "test-model",
    )
    logger.info(f"Export result: {result}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio
    asyncio.run(main())
    print("✅ export_to_ollama.py OK")
