"""
Module: core/inference/airllm_runner.py
AirLLM runner - enables 70B+ models in 16GB without quantization.
"""

import sys

__all__ = [
    "AirLLMRunner",
    "main",
]


from core.config import CONFIG
from loguru import logger
import asyncio
import uuid
import os
from typing import Optional, List, Dict, Any


class AirLLMRunner:
    """
    AirLLM runner for loading and running large models with minimal memory.
    Falls back to standard Ollama if AirLLM is not available.
    """

    def __init__(self):
        self.airllm_config = CONFIG.get("airllm", {})
        self.ollama_host = CONFIG["ollama_host"]
        self.loaded_model: Optional[str] = None
        self.model_info: Dict[str, Any] = {}
        self._airllm_available = self._check_airllm()

        if self._airllm_available:
            logger.info("[AirLLM] AirLLM library detected, enabling 70B+ model support")
        else:
            logger.info("[AirLLM] Falling back to standard Ollama")

    def _check_airllm(self) -> bool:
        """Check if AirLLM is available."""
        try:
            import airllm
            return True
        except ImportError:
            return False

    async def load_model(
        self,
        model_name: str,
        device: str = "cuda",
        max_seq_len: int = 4096,
    ) -> Dict[str, Any]:
        """
        Load a model using AirLLM or Ollama.

        Args:
            model_name: Name of the model to load
            device: Device to load on ('cuda' or 'cpu')
            max_seq_len: Maximum sequence length

        Returns:
            Dict with load status and model info
        """
        if self.loaded_model == model_name:
            logger.info(f"[AirLLM] Model {model_name} already loaded")
            return {"success": True, "model": model_name, "already_loaded": True}

        logger.info(f"[AirLLM] Loading model: {model_name}")

        if self._airllm_available:
            return await self._load_with_airllm(model_name, device, max_seq_len)
        else:
            return await self._load_with_ollama(model_name)

    async def _load_with_airllm(
        self,
        model_name: str,
        device: str,
        max_seq_len: int,
    ) -> Dict[str, Any]:
        """Load model using AirLLM library."""
        try:
            import airllm
            from airllm import AutoModel  # airllm does not export AutoTokenizer; use model.tokenizer

            cache_dir = self.airllm_config.get("layer_shards_saving_path", "./models/airllm_cache")
            os.makedirs(cache_dir, exist_ok=True)

            logger.info(f"[AirLLM] Loading {model_name} with AirLLM (device={device})")

            model = AutoModel.from_pretrained(
                model_name,
                device=device,
                max_seq_len=max_seq_len,
                layer_shards_saving_path=cache_dir,
            )

            self.loaded_model = model_name
            self.model_info = {
                "model_name": model_name,
                "loaded_with": "airllm",
                "device": device,
                "max_seq_len": max_seq_len,
                "loaded_at": self._get_timestamp(),
            }

            logger.info(f"[AirLLM] Model {model_name} loaded successfully with AirLLM")
            return {"success": True, "model": model_name, "method": "airllm", "info": self.model_info}

        except Exception as e:
            logger.error(f"[AirLLM] AirLLM loading failed: {e}")
            logger.info("[AirLLM] Falling back to Ollama")
            return await self._load_with_ollama(model_name)

    async def _load_with_ollama(self, model_name: str) -> Dict[str, Any]:
        """Load model using standard Ollama."""
        try:
            import ollama
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed.
            with ollama.Client(self.ollama_host) as client:
                available_models = [m["name"] for m in client.list().get("models", [])]

                if model_name not in available_models:
                    logger.info(f"[AirLLM] Pulling model {model_name} from Ollama")
                    client.pull(model_name)

            self.loaded_model = model_name
            self.model_info = {
                "model_name": model_name,
                "loaded_with": "ollama",
                "host": self.ollama_host,
                "loaded_at": self._get_timestamp(),
            }

            logger.info(f"[AirLLM] Model {model_name} loaded with Ollama")
            return {"success": True, "model": model_name, "method": "ollama", "info": self.model_info}

        except Exception as e:
            logger.error(f"[AirLLM] Ollama loading failed: {e}")
            return {"success": False, "error": str(e)}

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
    ) -> Dict[str, Any]:
        """
        Generate text using the loaded model.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter

        Returns:
            Dict with generated text and metadata
        """
        if not self.loaded_model:
            return {"success": False, "error": "No model loaded"}

        logger.debug(f"[AirLLM] Generating with {self.loaded_model}: {prompt[:50]}...")

        if self.model_info.get("loaded_with") == "airllm" and self._airllm_available:
            return await self._generate_with_airllm(prompt, max_tokens, temperature, top_p, top_k)
        else:
            return await self._generate_with_ollama(prompt, max_tokens, temperature, top_p, top_k)

    async def _generate_with_airllm(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> Dict[str, Any]:
        """Generate using AirLLM."""
        try:
            import airllm
            import torch
            from airllm import AutoModel  # airllm does not export AutoTokenizer; use model.tokenizer

            cache_dir = self.airllm_config.get("layer_shards_saving_path", "./models/airllm_cache")
            model_name = self.loaded_model

            model = AutoModel.from_pretrained(model_name, layer_shards_saving_path=cache_dir)
            tokenizer = model.tokenizer

            input_ids = tokenizer(prompt, return_tensors="pt").to(model.device)

            with torch.no_grad():
                outputs = model.generate(
                    input_ids["input_ids"],
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                )

            generated_text = tokenizer.decode(outputs[0][len(input_ids["input_ids"][0]):], skip_special_tokens=True)

            return {
                "success": True,
                "model": self.loaded_model,
                "prompt": prompt,
                "generated": generated_text,
                "tokens_generated": len(outputs[0]) - len(input_ids["input_ids"][0]),
                "method": "airllm",
            }
        except Exception as e:
            logger.error(f"[AirLLM] AirLLM generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_with_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> Dict[str, Any]:
        """Generate using Ollama."""
        try:
            import ollama
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed.
            with ollama.Client(self.ollama_host) as client:
                response = client.generate(
                    model=self.loaded_model,
                    prompt=prompt,
                    options={
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                        "top_k": top_k,
                    },
                )

            return {
                "success": True,
                "model": self.loaded_model,
                "prompt": prompt,
                "generated": response.get("response", ""),
                "tokens_generated": response.get("eval_count", 0),
                "method": "ollama",
            }
        except Exception as e:
            logger.error(f"[AirLLM] Ollama generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def batch_generate(
        self,
        prompts: List[str],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
    ) -> List[Dict[str, Any]]:
        """
        Generate text for multiple prompts.

        Args:
            prompts: List of input prompts
            max_tokens: Maximum tokens per generation
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter

        Returns:
            List of generation results
        """
        results = []

        for i, prompt in enumerate(prompts):
            logger.debug(f"[AirLLM] Batch generate {i+1}/{len(prompts)}")
            result = await self.generate(prompt, max_tokens, temperature, top_p, top_k)
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"[AirLLM] Batch complete: {success_count}/{len(prompts)} successful")

        return results

    def unload_model(self) -> Dict[str, Any]:
        """
        Unload the currently loaded model.

        Returns:
            Dict with unload status
        """
        if not self.loaded_model:
            return {"success": False, "error": "No model loaded"}

        model = self.loaded_model
        self.loaded_model = None
        self.model_info = {}

        logger.info(f"[AirLLM] Model {model} unloaded")
        return {"success": True, "model": model}

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the currently loaded model."""
        return self.model_info

    def list_supported_models(self) -> List[str]:
        """List models that can benefit from AirLLM."""
        return [
            "llama2-70b",
            "llama3-70b",
            "mixtral-8x7b",
            "falcon-40b",
            "codellama-70b",
            " WizardLM-70B",
        ]

    def _get_timestamp(self) -> str:
        """Get current ISO timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


async def main():
    """Test the AirLLM runner."""
    runner = AirLLMRunner()

    logger.info(f"AirLLM available: {runner._airllm_available}")

    logger.info(f"Supported models: {runner.list_supported_models()}")


    result = await runner.load_model("llama2:7b")
    logger.info(f"Load result: {result}")


    if result.get("success"):
        gen_result = await runner.generate("What is V.E.C.T.O.R.?")
        logger.info(f"Generate result: {gen_result}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import torch
    except ImportError:
        torch = None
    asyncio.run(main())
    print("✅ airllm_runner.py OK")
