"""Post-training dataset builders from VECTOR reasoning outcomes."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

__all__ = ["AlignmentExample", "build_dpo_pairs", "build_sft_examples", "export_jsonl"]


@dataclass(frozen=True)
class AlignmentExample:
    prompt: str
    chosen: str
    rejected: str = ""
    reward: float = 0.0
    source: str = "vector_reasoning"

    def to_sft(self) -> dict:
        return {
            "messages": [
                {"role": "user", "content": self.prompt},
                {"role": "assistant", "content": self.chosen},
            ],
            "reward": self.reward,
            "source": self.source,
        }

    def to_dpo(self) -> dict:
        return asdict(self)


def build_sft_examples(records: Iterable[dict], min_reward: float = 0.7) -> list[dict]:
    examples: list[dict] = []
    for record in records:
        reward = float(record.get("reward", record.get("score", 0.0)) or 0.0)
        if reward < min_reward:
            continue
        prompt = str(record.get("prompt") or record.get("instruction") or record.get("situation") or "").strip()
        output = str(record.get("output") or record.get("response") or record.get("outcome") or "").strip()
        if prompt and output:
            examples.append(AlignmentExample(prompt, output, reward=reward, source=str(record.get("source", "vector_reasoning"))).to_sft())
    return examples


def build_dpo_pairs(records: Iterable[dict], min_chosen_reward: float = 0.7, max_rejected_reward: float = 0.3) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        prompt = str(record.get("prompt") or record.get("instruction") or record.get("situation") or "").strip()
        if prompt:
            grouped.setdefault(prompt, []).append(record)

    pairs: list[dict] = []
    for prompt, items in grouped.items():
        chosen = [
            r for r in items
            if float(r.get("reward", r.get("score", 0.0)) or 0.0) >= min_chosen_reward
            and str(r.get("output") or r.get("response") or r.get("outcome") or "").strip()
        ]
        rejected = [
            r for r in items
            if float(r.get("reward", r.get("score", 0.0)) or 0.0) <= max_rejected_reward
            and str(r.get("output") or r.get("response") or r.get("outcome") or "").strip()
        ]
        if not chosen or not rejected:
            continue
        best = max(chosen, key=lambda r: float(r.get("reward", r.get("score", 0.0)) or 0.0))
        worst = min(rejected, key=lambda r: float(r.get("reward", r.get("score", 0.0)) or 0.0))
        pairs.append(AlignmentExample(
            prompt=prompt,
            chosen=str(best.get("output") or best.get("response") or best.get("outcome")),
            rejected=str(worst.get("output") or worst.get("response") or worst.get("outcome")),
            reward=float(best.get("reward", best.get("score", 0.0)) or 0.0),
            source=str(best.get("source", "vector_reasoning")),
        ).to_dpo())
    return pairs


def export_jsonl(rows: Iterable[dict], path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(target)
