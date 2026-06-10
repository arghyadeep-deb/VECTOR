"""
Module: agents/karpathy_lab/data_prep.py
District: karpathy_lab | Focus: Dataset downloading, preprocessing, tokenization
"""

import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, hashlib, subprocess, os, re
from typing import Optional


class DataPrep(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DataPrep",
            district="karpathy_lab",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        from core.runtime_paths import data_path

        self.data_dir = data_path("datasets")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[VECTOR][karpathy_lab] DataPrep ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def _download_with_progress(self, url: str, dest: Path) -> bool:
        try:
            import httpx
            with httpx.stream("GET", url, headers={"User-Agent": "VECTOR-DataPrep/1.0"}, timeout=300) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192
                with open(dest, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and downloaded % (1024 * 1024 * 10) == 0:
                            pct = (downloaded / total) * 100
                            logger.debug(f"[VECTOR][karpathy_lab] Download {pct:.1f}%")
            logger.info(f"[VECTOR][karpathy_lab] Downloaded {dest.name} ({downloaded / 1024 / 1024:.1f} MB)")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][karpathy_lab] Download failed: {e}")
            return False

    def download_dataset(self, dataset_name: str) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Downloading dataset: {dataset_name}")
        self.add_lesson({"action": "download_dataset", "dataset": dataset_name})

        known_datasets = {
            "tiny_shakespeare": "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt",
            "wikitext-2": "https://huggingface.co/datasets/wikitext-2-v1/resolve/main/train.txt",
            "openwebtext": "https://huggingface.co/datasets/openwebtext/resolve/main/train.parquet",
            "pile": "https://huggingface.co/datasets/ThePile/resolve/main/train.parquet",
        }

        if dataset_name not in known_datasets:
            logger.warning(f"[VECTOR][karpathy_lab] Unknown dataset '{dataset_name}', using generic path")
            url = dataset_name
            dataset_dir = self.data_dir / dataset_name
        else:
            url = known_datasets[dataset_name]
            dataset_dir = self.data_dir / dataset_name

        dataset_dir.mkdir(parents=True, exist_ok=True)
        file_name = Path(url).name or f"{dataset_name}.txt"
        dest = dataset_dir / file_name

        if dest.exists():
            logger.info(f"[VECTOR][karpathy_lab] Dataset already exists at {dest}")
            result = {"status": "already_exists", "path": str(dest), "dataset": dataset_name}
        else:
            success = self._download_with_progress(url, dest)
            result = {"status": "downloaded" if success else "failed", "path": str(dest), "dataset": dataset_name}

        self.memory.store(
            event_type="dataset_downloaded",
            content=f"Downloaded dataset {dataset_name}",
            tags=["dataset", dataset_name, "training"],
            context=result,
            source="DataPrep"
        )
        return result

    def preprocess_data(self, input_path: str, output_path: str) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Preprocessing data: {input_path} -> {output_path}")
        self.add_lesson({"action": "preprocess_data", "input": input_path})

        input_p = Path(input_path)
        if not input_p.exists():
            logger.error(f"[VECTOR][karpathy_lab] Input path does not exist: {input_path}")
            return {"status": "error", "message": "Input path not found"}

        output_p = Path(output_path)
        output_p.parent.mkdir(parents=True, exist_ok=True)

        content = input_p.read_text(encoding="utf-8", errors="ignore")
        cleaned_lines = []
        for line in content.splitlines():
            line = line.strip()
            if len(line) < 10:
                continue
            line = re.sub(r'\s+', ' ', line)
            # Strip only ASCII control characters (0x00-0x08, 0x0B-0x1F, 0x7F)
            # Preserve all Unicode — Hindi, Bengali, Assamese, Japanese must survive.
            line = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', line)
            if line:
                cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        output_p.write_text(cleaned_text, encoding="utf-8")

        stats = {
            "original_lines": len(content.splitlines()),
            "cleaned_lines": len(cleaned_lines),
            "original_chars": len(content),
            "cleaned_chars": len(cleaned_text),
            "output_path": str(output_p),
        }

        self.memory.store(
            event_type="data_preprocessed",
            content=f"Preprocessed {input_p.name} -> {output_p.name}",
            tags=["preprocessing", "cleaning", "dataset"],
            context=stats,
            source="DataPrep"
        )
        logger.info(f"[VECTOR][karpathy_lab] Preprocessed: {stats['cleaned_lines']}/{stats['original_lines']} lines retained")
        return {"status": "success", **stats}

    def tokenize_data(self, text_path: str, vocab_size: int) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Tokenizing {text_path} with vocab_size={vocab_size}")
        self.add_lesson({"action": "tokenize_data", "vocab_size": vocab_size})

        text_p = Path(text_path)
        if not text_p.exists():
            logger.error(f"[VECTOR][karpathy_lab] Text file not found: {text_path}")
            return {"status": "error", "message": "Text file not found"}

        content = text_p.read_text(encoding="utf-8", errors="ignore")
        chars = sorted(set(content))
        if len(chars) > vocab_size:
            logger.warning(f"[VECTOR][karpathy_lab] Char set {len(chars)} > vocab_size {vocab_size}, using most frequent")
            char_freq = {c: content.count(c) for c in chars}
            top_chars = sorted(char_freq, key=char_freq.get, reverse=True)[:vocab_size]
            chars = top_chars

        char_to_idx = {c: i for i, c in enumerate(chars)}
        idx_to_char = {i: c for i, c in enumerate(chars)}

        token_ids = [char_to_idx.get(c, 0) for c in content]
        import json as _json
        vocab_path = text_p.parent / f"{text_p.stem}_vocab_{vocab_size}.json"
        vocab_path.write_text(_json.dumps({"char_to_idx": char_to_idx, "idx_to_char": {str(k): v for k, v in idx_to_char.items()}, "vocab_size": vocab_size}, indent=2), encoding="utf-8")

        tokens_path = text_p.parent / f"{text_p.stem}_tokens_{vocab_size}.bin"
        with open(tokens_path, "wb") as f:
            f.write(bytes(token_ids))

        stats = {
            "vocab_size": len(chars),
            "total_tokens": len(token_ids),
            "unique_chars": len(chars),
            "vocab_path": str(vocab_path),
            "tokens_path": str(tokens_path),
            "compression_ratio": round(len(token_ids) * 2 / len(content.encode("utf-8")), 3),
        }

        self.memory.store(
            event_type="data_tokenized",
            content=f"Tokenized {text_p.name} with vocab={len(chars)}",
            tags=["tokenization", "vocabulary", "dataset"],
            context=stats,
            source="DataPrep"
        )
        logger.info(f"[VECTOR][karpathy_lab] Tokenized: {stats['total_tokens']} tokens, {stats['unique_chars']} unique chars")
        return {"status": "success", **stats}


    async def run(self, task: dict) -> dict:
        if hasattr(self, "prepare"):
            result = self.prepare()
            return {"status": "ok", "result": result}
        return {"status": "ok", "agent": self.name}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = DataPrep()
    assert agent.health_points == 500
    assert agent.district == "karpathy_lab"

    result = agent.preprocess_data("C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/V.E.C.T.O.R. Codebase/core/config.py", "C:/Users/ARGHYA~1/AppData/Local/Temp/opencode/test_preprocessed.txt")
    assert result["status"] == "success"

    result2 = agent.tokenize_data("C:/Users/ARGHYA~1/AppData/Local/Temp/opencode/test_preprocessed.txt", 256)
    assert result2["status"] == "success"
    assert "total_tokens" in result2

    print("✅ data_prep.py OK")
