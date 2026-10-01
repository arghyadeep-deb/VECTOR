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
        self.capabilities = ["download_dataset", "karpathy_lab", "preprocess_data", "tokenize_data"]
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
        part = dest.with_name(dest.name + ".part")
        try:
            import httpx
            from core.security.ssrf_guard import get_ssrf_guard
            check = get_ssrf_guard().check_url(url)
            if not check.safe:
                logger.error(f"[VECTOR][karpathy_lab] Download blocked by SSRF guard: {check}")
                return False
            with httpx.stream(
                "GET", url, headers={"User-Agent": "VECTOR-DataPrep/1.0"},
                timeout=300, follow_redirects=True,
            ) as response:
                # A 404/500 body is an HTML error page, not a dataset — never
                # persist it as one.
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192
                with open(part, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and downloaded % (1024 * 1024 * 10) == 0:
                            pct = (downloaded / total) * 100
                            logger.debug(f"[VECTOR][karpathy_lab] Download {pct:.1f}%")
            part.replace(dest)
            logger.info(f"[VECTOR][karpathy_lab] Downloaded {dest.name} ({downloaded / 1024 / 1024:.1f} MB)")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][karpathy_lab] Download failed: {e}")
            try:
                part.unlink(missing_ok=True)
            except OSError:
                logger.warning(f"[VECTOR][karpathy_lab] could not remove partial download {part}")
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
            if not url.lower().startswith(("http://", "https://")):
                return {"status": "failed", "path": "", "dataset": dataset_name,
                        "error": "unknown dataset and not an http(s) URL"}
            # dataset_name is caller-controlled: never use it as a path
            # component verbatim (absolute path / ".." escape data_dir).
            safe_dir = re.sub(r"[^A-Za-z0-9._-]+", "_", dataset_name).strip("._")[:80] or "dataset"
            dataset_dir = self.data_dir / safe_dir
        else:
            url = known_datasets[dataset_name]
            dataset_dir = self.data_dir / dataset_name

        dataset_dir.mkdir(parents=True, exist_ok=True)
        file_name = Path(url.split("?", 1)[0]).name
        if file_name in ("", ".", "..") or not file_name.isprintable():
            file_name = f"{dataset_name}.txt" if dataset_name in known_datasets else "download.txt"
        dest = (dataset_dir / file_name).resolve()
        if not dest.is_relative_to(self.data_dir.resolve()):
            return {"status": "failed", "path": "", "dataset": dataset_name, "error": "path escapes data_dir"}

        if dest.exists():
            logger.info(f"[VECTOR][karpathy_lab] Dataset already exists at {dest}")
            result = {"status": "already_exists", "path": str(dest), "dataset": dataset_name}
        else:
            success = self._download_with_progress(url, dest)
            result = {"status": "downloaded" if success else "failed", "path": str(dest), "dataset": dataset_name}

        self.memory.store(
            event_type="dataset_downloaded",
            content=f"Dataset {dataset_name}: {result['status']}",
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

        if not cleaned_lines:
            logger.error(f"[VECTOR][karpathy_lab] Preprocess of {input_path} kept 0 lines — not writing output")
            return {"status": "error", "message": "no usable lines after cleaning"}

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

        if not text_p.is_file():
            return {"status": "error", "message": "Text path is not a file"}
        content = text_p.read_text(encoding="utf-8", errors="ignore")
        if not content:
            return {"status": "error", "message": "Text file is empty"}
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
        # bytes(token_ids) raises ValueError once a vocab has >256 symbols
        # (any Hindi/Bengali/Japanese corpus) — use uint16 then.
        if len(chars) > 256:
            import array
            arr = array.array("H", token_ids)
            if sys.byteorder == "big":
                arr.byteswap()
            payload = arr.tobytes()
        else:
            payload = bytes(token_ids)
        with open(tokens_path, "wb") as f:
            f.write(payload)

        stats = {
            "vocab_size": len(chars),
            "total_tokens": len(token_ids),
            "unique_chars": len(chars),
            "vocab_path": str(vocab_path),
            "tokens_path": str(tokens_path),
            "token_dtype": "uint16" if len(chars) > 256 else "uint8",
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
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["download_dataset", "preprocess_data", "tokenize_data"]

        if task_type == "download_dataset":
            return self.download_dataset(p.get("dataset_name", ""))
        if task_type == "preprocess_data":
            return self.preprocess_data(p.get("input_path", ""), p.get("output_path", ""))
        if task_type == "tokenize_data":
            return self.tokenize_data(p.get("text_path", ""), p.get("vocab_size", 8000))

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "how do I preprocess a text dataset before tokenizing it for
        # training?" previously hit the bare "unhandled type" error stub.
        # Unlike the languages/interview_prep coaches, DataPrep has NO safe
        # no-argument capability: download_dataset() makes a real network
        # call, preprocess_data()/tokenize_data() need a real file on disk.
        # Only take those branches when the caller actually supplied the
        # required path/name (never guess a path or trigger a download from
        # free text); otherwise answer with a grounded explanation instead
        # of an error stub, per the content-district safety contract.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            if p.get("input_path") and p.get("output_path"):
                return self.preprocess_data(p["input_path"], p["output_path"])
            if p.get("text_path"):
                return self.tokenize_data(p["text_path"], p.get("vocab_size", 8000))
            if p.get("dataset_name"):
                return self.download_dataset(p["dataset_name"])
            return {
                "status": "ok",
                "response": (
                    "I can preprocess a text file (preprocess_data with input_path + "
                    "output_path), tokenize a text file into a char-level vocab "
                    "(tokenize_data with text_path), or download a known dataset "
                    "(download_dataset with dataset_name: tiny_shakespeare/wikitext-2/"
                    "openwebtext/pile). Tell me which one and give me the path or name."
                ),
            }

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


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
