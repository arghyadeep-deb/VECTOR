"""Training data collection from episodic memory, user feedback, and domain sources."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from core.runtime_paths import data_path

_PACKAGED_TRAINING_ROOT = Path(__file__).resolve().parents[2] / "data" / "training"


class DataCollector:
    def __init__(self, db_path: str = ""):
        self.db_path = db_path
        self._feedback_dir = data_path("feedback")
        self._feedback_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Training] DataCollector initialized")

    def record(self, input_text: str, output_text: str, reward: float = 0.0, metadata: dict | None = None) -> None:
        path = self._feedback_dir / f"action_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        path.write_text(json.dumps({
            "instruction": input_text,
            "input": (metadata or {}).get("source", "autonomous_loop"),
            "output": output_text,
            "score": reward,
        }, ensure_ascii=False, default=str), encoding="utf-8")

    def collect_from_episodic_memory(self, days: int = 30, min_reward: float = 0.7) -> list[dict]:
        try:
            from core.memory.episodic import EpisodicMemory
            memory = EpisodicMemory()
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            entries = memory.get_training_data(limit=5000)
            if not entries:
                logger.warning("[Training] No episodic memory entries found")
                return []
            filtered = []
            for e in entries:
                ts = e.get("timestamp") or e.get("created_at", "")
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        ts = datetime.now(timezone.utc)
                if isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                reward = float(e.get("reward", 0.0) or 0.0)
                if reward >= min_reward:
                    filtered.append({
                        "instruction": e.get("instruction", e.get("prompt", e.get("situation", ""))),
                        "input": e.get("input", e.get("context", "")),
                        "output": e.get("output", e.get("response", e.get("outcome", ""))),
                        "reward": reward,
                        "source": "episodic_memory",
                    })
            logger.info("[Training] Collected {} high-reward episodes", len(filtered))
            return filtered
        except ImportError:
            logger.warning("[Training] EpisodicMemory not available, using fallback")
            return self._fallback_episodic(days, min_reward)
        except Exception as e:
            logger.warning("[Training] Episodic memory collection failed: {}", e)
            return []

    def collect_from_feedback(self, days: int = 7) -> list[dict]:
        try:
            feedback_path = Path(self.db_path) / "feedback" if self.db_path else data_path("feedback")
            if not feedback_path.exists():
                logger.warning("[Training] Feedback path not found: {}", feedback_path)
                return []
            examples = []
            cutoff = datetime.now() - timedelta(days=days)
            for f in feedback_path.glob("*.json"):
                try:
                    ts = datetime.fromtimestamp(f.stat().st_mtime)
                    if ts < cutoff:
                        continue
                    data = json.loads(f.read_text(encoding="utf-8"))
                    examples.append({
                        "instruction": data.get("instruction", ""),
                        "input": data.get("input", ""),
                        "output": data.get("output", data.get("response", "")),
                        "score": data.get("score", 0.5),
                        "source": "user_feedback",
                    })
                except Exception as e:
                    logger.warning("[Training] Failed to load feedback {}: {}", f.name, e)
            logger.info("[Training] Collected {} feedback examples", len(examples))
            return examples
        except Exception as e:
            logger.warning("[Training] Feedback collection failed: {}", e)
            return []

    def collect_from_domain(self, domain: str, count: int = 100) -> list[dict]:
        domain_paths = {
            "coding": data_path("training", "coding"),
            "research": data_path("training", "research"),
            "voice": data_path("training", "voice"),
        }
        base = domain_paths.get(domain)
        if not base or not base.exists():
            packaged_base = _PACKAGED_TRAINING_ROOT / domain
            if packaged_base.exists():
                base = packaged_base
            else:
                logger.warning("[Training] Domain path not found for '{}'", domain)
                return []
        examples = []
        for f in sorted(base.glob("*.jsonl"))[:5]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        if len(examples) >= count:
                            break
                        item = json.loads(line)
                        examples.append({
                            "instruction": item.get("instruction", item.get("prompt", "")),
                            "input": item.get("input", ""),
                            "output": item.get("output", item.get("completion", "")),
                            "source": f"domain_{domain}",
                        })
            except Exception as e:
                logger.warning("[Training] Failed to read {}: {}", f.name, e)
            if len(examples) >= count:
                break
        logger.info("[Training] Collected {} domain examples from '{}'", len(examples), domain)
        return examples[:count]

    def format_for_training(self, data: list[dict], template: str = "alpaca") -> list[dict]:
        formatted = []
        for item in data:
            instruction = item.get("instruction", "").strip()
            input_text = item.get("input", "").strip()
            output_text = item.get("output", "").strip()
            if not instruction or not output_text:
                continue
            if template == "alpaca":
                if input_text:
                    text = f"### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Response:\n{output_text}"
                else:
                    text = f"### Instruction:\n{instruction}\n\n### Response:\n{output_text}"
            elif template == "chat":
                text = json.dumps([
                    {"role": "user", "content": instruction + ("\n" + input_text if input_text else "")},
                    {"role": "assistant", "content": output_text},
                ], ensure_ascii=False)
            else:
                text = f"{instruction}\n{input_text}\n{output_text}"
            formatted.append({"text": text, "source": item.get("source", "unknown")})
        logger.info("[Training] Formatted {} examples with '{}' template", len(formatted), template)
        return formatted

    def deduplicate(self, examples: list[dict]) -> list[dict]:
        seen_hashes: set[str] = set()
        seen_word_sets: list[set[str]] = []
        deduped = []
        for ex in examples:
            text = ex.get("text", ex.get("output", ""))
            h = hashlib.md5(text.encode("utf-8")).hexdigest()
            if h in seen_hashes:
                continue
            score = int(len(text) > 50)
            words = set(text.split())
            for previous_words in seen_word_sets:
                overlap = len(words & previous_words) / max(len(words | previous_words), 1)
                if overlap > 0.85:
                    score = 0
                    break
            if score:
                seen_hashes.add(h)
                seen_word_sets.append(words)
                deduped.append(ex)
        removed = len(examples) - len(deduped)
        if removed:
            logger.info("[Training] Deduplication removed {} examples", removed)
        return deduped

    def export_dataset(self, examples: list[dict], output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                for ex in examples:
                    f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            logger.info("[Training] Dataset exported to {} ({} examples)", path, len(examples))
            return str(path)
        except Exception as e:
            logger.error("[Training] Failed to export dataset: {}", e)
            return ""

    def _fallback_episodic(self, days: int, min_reward: float) -> list[dict]:
        fallback_paths = [
            data_path("episodic_memory"),
            data_path("memory"),
            Path("memory_data"),
        ]
        for p in fallback_paths:
            if p.exists():
                try:
                    cutoff = datetime.now() - timedelta(days=days)
                    examples = []
                    for f in p.glob("*.json"):
                        ts = datetime.fromtimestamp(f.stat().st_mtime)
                        if ts < cutoff:
                            continue
                        data = json.loads(f.read_text(encoding="utf-8"))
                        reward = float(data.get("reward", 0.0) or 0.0)
                        if reward >= min_reward:
                            examples.append({
                                "instruction": data.get("instruction", data.get("prompt", "")),
                                "input": data.get("input", ""),
                                "output": data.get("output", data.get("response", "")),
                                "reward": reward,
                                "source": "memory_fallback",
                            })
                    return examples
                except Exception as e:
                    logger.warning("[Training] Fallback episodic read failed: {}", e)
        return []
