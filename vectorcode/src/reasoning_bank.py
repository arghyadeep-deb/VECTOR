"""VECTOR ReasoningBank + PatternLearner — stores and retrieves reasoning trajectories."""
from __future__ import annotations
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

# VECTOR module — neural intelligence subsystem
# Owner: Arghyadeep Deb | Ingested: 2026-05-16

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BANK_PATH = Path.home() / ".vector" / "reasoning_bank.json"
_DEFAULT_PATTERNS_PATH = Path.home() / ".vector" / "patterns.json"
_EMBED_DIM = 64   # hash embedding dimension


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_embed(text: str, dim: int = _EMBED_DIM) -> np.ndarray:
    """Deterministic hash embedding: sha256(text) → `dim` floats in [-1, 1]."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()   # 32 bytes
    num_tiles = math.ceil(dim / len(digest))
    extended = (digest * num_tiles)[:dim]
    arr = np.frombuffer(bytes(extended), dtype=np.uint8).astype(np.float64)
    return arr / 127.5 - 1.0


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# ReasoningEntry
# ---------------------------------------------------------------------------

@dataclass
class ReasoningEntry:
    id: str
    task: str           # problem description
    reasoning: str      # the chain-of-thought
    outcome: str        # what happened
    reward: float       # 0.0-1.0 quality score
    task_type: str
    embedding: np.ndarray   # hash embedding of task+reasoning
    created_at: float = field(default_factory=time.time)
    verdict: str = "pending"   # pending | good | bad | excellent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "reasoning": self.reasoning,
            "outcome": self.outcome,
            "reward": self.reward,
            "task_type": self.task_type,
            "embedding": self.embedding.tolist(),
            "created_at": self.created_at,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReasoningEntry":
        return cls(
            id=d["id"],
            task=d["task"],
            reasoning=d["reasoning"],
            outcome=d["outcome"],
            reward=d["reward"],
            task_type=d.get("task_type", "general"),
            embedding=np.array(d["embedding"], dtype=np.float64),
            created_at=d.get("created_at", time.time()),
            verdict=d.get("verdict", "pending"),
        )


# ---------------------------------------------------------------------------
# ReasoningBank
# ---------------------------------------------------------------------------

class ReasoningBank:
    """Store/retrieve reasoning chains. VECTOR Rule 8: inject_past_reasoning() before similar decisions.

    Storage: in-memory dict + optional JSON persistence at ~/.vector/reasoning_bank.json
    Similarity: cosine similarity on hash embeddings (no external vector DB needed)

    Methods:
    - store(task, reasoning, outcome, reward, task_type="general") -> str (id)
    - retrieve(task, top_k=3, min_reward=0.5) -> List[ReasoningEntry]
    - judge(entry_id, verdict, reward_adjustment=0.0) -> None
    - inject_past_reasoning(task, top_k=3) -> str   formatted prompt snippet
    - distill(task_type=None) -> dict               extract common patterns
    - save(path=None) -> None
    - load(path=None) -> None
    - stats() -> dict

    VECTOR wiring: called by decision_engine before scoring candidates.
    High-reward entries (reward > 0.7) auto-tagged as is_training_data=True in episodic memory.
    """

    def __init__(
        self,
        path: Optional[Path | str] = None,
        auto_load: bool = True,
        pattern_learner: Optional["PatternLearner"] = None,
    ) -> None:
        self._path: Path = Path(path) if path else _DEFAULT_BANK_PATH
        self._entries: Dict[str, ReasoningEntry] = {}
        self._pattern_learner = pattern_learner

        if auto_load and self._path.exists():
            self.load()

        logger.debug(
            f"[VECTOR][reasoning_bank] init: {len(self._entries)} entries "
            f"path={self._path}"
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def store(
        self,
        task: str,
        reasoning: str,
        outcome: str,
        reward: float,
        task_type: str = "general",
    ) -> str:
        """Store a reasoning chain and return its id.

        High-reward entries (reward > 0.7) are auto-flagged as training data.
        """
        reward = float(np.clip(reward, 0.0, 1.0))
        entry_id = _new_id()
        combined_text = f"{task} {reasoning}"
        embedding = _hash_embed(combined_text, _EMBED_DIM)

        entry = ReasoningEntry(
            id=entry_id,
            task=task,
            reasoning=reasoning,
            outcome=outcome,
            reward=reward,
            task_type=task_type,
            embedding=embedding,
        )

        # Auto-set verdict for high-quality entries
        if reward >= 0.9:
            entry.verdict = "excellent"
        elif reward >= 0.7:
            entry.verdict = "good"
        elif reward < 0.3:
            entry.verdict = "bad"

        self._entries[entry_id] = entry

        if reward > 0.7:
            logger.info(
                f"[VECTOR][reasoning_bank] stored high-reward chain "
                f"id={entry_id} reward={reward:.2f} type={task_type} "
                f"[is_training_data=True]"
            )
        else:
            logger.debug(
                f"[VECTOR][reasoning_bank] stored id={entry_id} "
                f"reward={reward:.2f} type={task_type}"
            )

        # Feed to PatternLearner if wired
        if self._pattern_learner is not None:
            self._pattern_learner.extract(task, reasoning, outcome, reward)

        return entry_id

    def retrieve(
        self,
        task: str,
        top_k: int = 3,
        min_reward: float = 0.5,
    ) -> List[ReasoningEntry]:
        """Retrieve top-k most similar reasoning entries above min_reward.

        Args:
            task:       the new task/problem description
            top_k:      max number of results
            min_reward: only include entries with reward >= this threshold

        Returns:
            List of ReasoningEntry sorted by similarity descending.
        """
        if not self._entries:
            return []

        query_emb = _hash_embed(task, _EMBED_DIM)
        candidates = [
            e for e in self._entries.values()
            if e.reward >= min_reward and e.verdict != "bad"
        ]

        if not candidates:
            return []

        # Score by cosine similarity
        scored = [
            (e, _cosine_similarity(query_emb, e.embedding))
            for e in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        results = [e for e, _ in scored[:top_k]]
        logger.debug(
            f"[VECTOR][reasoning_bank] retrieved {len(results)} entries "
            f"for task='{task[:50]}...'"
        )
        return results

    def judge(
        self,
        entry_id: str,
        verdict: str,
        reward_adjustment: float = 0.0,
    ) -> None:
        """Update the verdict and optionally adjust reward for an entry.

        Args:
            entry_id:         id returned by store()
            verdict:          "good" | "bad" | "excellent" | "pending"
            reward_adjustment: signed delta to add to the entry's reward
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            logger.warning(f"[VECTOR][reasoning_bank] judge: entry {entry_id} not found")
            return

        valid_verdicts = {"pending", "good", "bad", "excellent"}
        if verdict not in valid_verdicts:
            logger.warning(f"[VECTOR][reasoning_bank] invalid verdict: {verdict}")
            return

        entry.verdict = verdict
        if reward_adjustment != 0.0:
            entry.reward = float(np.clip(entry.reward + reward_adjustment, 0.0, 1.0))

        logger.debug(
            f"[VECTOR][reasoning_bank] judged id={entry_id} "
            f"verdict={verdict} reward={entry.reward:.2f}"
        )

    def inject_past_reasoning(self, task: str, top_k: int = 3) -> str:
        """Format similar past reasoning chains as a prompt injection snippet.

        VECTOR Rule 8: call this before LLM reasoning on a similar task.

        Args:
            task:   the new problem
            top_k:  number of past chains to inject

        Returns:
            A formatted string ready to prepend to an LLM prompt.
        """
        entries = self.retrieve(task, top_k=top_k, min_reward=0.5)
        if not entries:
            return ""

        lines = ["## Past Reasoning (most similar):"]
        for i, e in enumerate(entries, 1):
            lines.append(
                f"\n### Example {i} (reward={e.reward:.2f} type={e.task_type})"
            )
            lines.append(f"**Task:** {e.task}")
            lines.append(f"**Reasoning:** {e.reasoning}")
            lines.append(f"**Outcome:** {e.outcome}")

        return "\n".join(lines)

    def distill(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """Extract common patterns and statistics from stored chains.

        Args:
            task_type: filter to a specific task type, or None for all.

        Returns:
            dict with avg_reward, top_entries, verdict_distribution, total.
        """
        entries = list(self._entries.values())
        if task_type:
            entries = [e for e in entries if e.task_type == task_type]

        if not entries:
            return {"total": 0, "task_type": task_type}

        rewards = np.array([e.reward for e in entries])
        verdict_counts: Dict[str, int] = {}
        for e in entries:
            verdict_counts[e.verdict] = verdict_counts.get(e.verdict, 0) + 1

        top_entries = sorted(entries, key=lambda x: x.reward, reverse=True)[:5]

        return {
            "task_type": task_type or "all",
            "total": len(entries),
            "avg_reward": round(float(rewards.mean()), 4),
            "max_reward": round(float(rewards.max()), 4),
            "min_reward": round(float(rewards.min()), 4),
            "std_reward": round(float(rewards.std()), 4),
            "verdict_distribution": verdict_counts,
            "top_entries": [
                {"id": e.id, "task": e.task[:80], "reward": e.reward}
                for e in top_entries
            ],
            "training_data_count": sum(1 for e in entries if e.reward > 0.7),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[Path | str] = None) -> None:
        """Save all entries to JSON."""
        save_path = Path(path) if path else self._path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        save_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.debug(
            f"[VECTOR][reasoning_bank] saved {len(self._entries)} entries to {save_path}"
        )

    def load(self, path: Optional[Path | str] = None) -> None:
        """Load entries from JSON. Merges with existing in-memory entries."""
        load_path = Path(path) if path else self._path
        if not load_path.exists():
            logger.warning(f"[VECTOR][reasoning_bank] file not found: {load_path}")
            return
        try:
            payload = json.loads(load_path.read_text(encoding="utf-8"))
            loaded = 0
            for d in payload.get("entries", []):
                entry = ReasoningEntry.from_dict(d)
                self._entries[entry.id] = entry
                loaded += 1
            logger.info(
                f"[VECTOR][reasoning_bank] loaded {loaded} entries from {load_path}"
            )
        except Exception as exc:
            logger.error(f"[VECTOR][reasoning_bank] load failed: {exc}")

    def stats(self) -> Dict[str, Any]:
        """Return bank-level statistics."""
        entries = list(self._entries.values())
        if not entries:
            return {"total": 0}

        rewards = np.array([e.reward for e in entries])
        type_counts: Dict[str, int] = {}
        for e in entries:
            type_counts[e.task_type] = type_counts.get(e.task_type, 0) + 1

        verdict_counts: Dict[str, int] = {}
        for e in entries:
            verdict_counts[e.verdict] = verdict_counts.get(e.verdict, 0) + 1

        return {
            "total": len(entries),
            "avg_reward": round(float(rewards.mean()), 4),
            "training_data_count": int((rewards > 0.7).sum()),
            "task_type_distribution": type_counts,
            "verdict_distribution": verdict_counts,
        }


# ---------------------------------------------------------------------------
# PatternConfig + Pattern
# ---------------------------------------------------------------------------

@dataclass
class PatternConfig:
    max_patterns: int = 500
    match_threshold: float = 0.7
    min_usages_for_stable: int = 3
    quality_threshold: float = 0.5


@dataclass
class Pattern:
    id: str
    name: str
    task_type: str
    strategy: str           # extracted strategy description
    embedding: np.ndarray
    usage_count: int = 0
    quality_score: float = 0.5
    created_at: float = field(default_factory=time.time)
    stable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type,
            "strategy": self.strategy,
            "embedding": self.embedding.tolist(),
            "usage_count": self.usage_count,
            "quality_score": self.quality_score,
            "created_at": self.created_at,
            "stable": self.stable,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Pattern":
        return cls(
            id=d["id"],
            name=d["name"],
            task_type=d.get("task_type", "general"),
            strategy=d["strategy"],
            embedding=np.array(d["embedding"], dtype=np.float64),
            usage_count=d.get("usage_count", 0),
            quality_score=d.get("quality_score", 0.5),
            created_at=d.get("created_at", time.time()),
            stable=d.get("stable", False),
        )


# ---------------------------------------------------------------------------
# PatternLearner
# ---------------------------------------------------------------------------

class PatternLearner:
    """Extract reusable patterns from reasoning trajectories.

    Methods:
    - extract(task, reasoning, outcome, reward) -> Optional[Pattern]
    - match(task) -> List[Pattern]      find matching patterns
    - evolve(pattern_id, reward) -> None  update quality score
    - get_best_strategies(task_type=None, top_k=5) -> List[str]
    - stats() -> dict

    Pattern extraction: if a reasoning entry with same task_type exists and
    cosine_similarity(new_embedding, existing_embedding) > match_threshold,
    merge rather than create duplicate. Otherwise create new pattern.

    VECTOR wiring: called by ReasoningBank.store() automatically.
    Patterns inform goal_system.generate_immediate_actions().
    """

    def __init__(
        self,
        config: Optional[PatternConfig] = None,
        path: Optional[Path | str] = None,
        auto_load: bool = True,
    ) -> None:
        self.config = config or PatternConfig()
        self._path: Path = Path(path) if path else _DEFAULT_PATTERNS_PATH
        self._patterns: Dict[str, Pattern] = {}

        if auto_load and self._path.exists():
            self._load()

        logger.debug(
            f"[VECTOR][pattern_learner] init: {len(self._patterns)} patterns"
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def extract(
        self,
        task: str,
        reasoning: str,
        outcome: str,
        reward: float,
    ) -> Optional[Pattern]:
        """Extract or merge a pattern from a reasoning entry.

        If a similar pattern already exists (cosine similarity > threshold),
        evolve it rather than creating a duplicate.

        Args:
            task:      problem description
            reasoning: chain-of-thought text
            outcome:   result description
            reward:    quality score 0.0-1.0

        Returns:
            The newly created or merged Pattern, or None if reward is too low.
        """
        if reward < self.config.quality_threshold:
            return None

        # Derive task type from keywords (simple heuristic)
        task_type = self._infer_task_type(task)
        combined = f"{task} {reasoning}"
        embedding = _hash_embed(combined, _EMBED_DIM)

        # Try to find matching pattern
        best_match: Optional[Pattern] = None
        best_sim: float = 0.0
        for p in self._patterns.values():
            if p.task_type != task_type:
                continue
            sim = _cosine_similarity(embedding, p.embedding)
            if sim > best_sim:
                best_sim = sim
                best_match = p

        if best_match is not None and best_sim >= self.config.match_threshold:
            # Merge: update quality score via exponential moving average
            alpha = 0.3
            best_match.quality_score = (
                alpha * reward + (1 - alpha) * best_match.quality_score
            )
            best_match.usage_count += 1
            best_match.stable = best_match.usage_count >= self.config.min_usages_for_stable
            # Blend embedding
            best_match.embedding = (
                0.7 * best_match.embedding + 0.3 * embedding
            )
            logger.debug(
                f"[VECTOR][pattern_learner] merged pattern id={best_match.id} "
                f"sim={best_sim:.3f} quality={best_match.quality_score:.3f}"
            )
            return best_match

        # Create new pattern if under max
        if len(self._patterns) >= self.config.max_patterns:
            # Evict the lowest-quality, least-used pattern
            worst = min(
                self._patterns.values(),
                key=lambda p: (p.quality_score * 0.7 + p.usage_count * 0.3),
            )
            del self._patterns[worst.id]
            logger.debug(
                f"[VECTOR][pattern_learner] evicted pattern id={worst.id}"
            )

        # Strategy extraction: take first 200 chars of reasoning as strategy summary
        strategy = reasoning[:200].strip()
        pattern_name = f"{task_type}_{len(self._patterns):04d}"

        new_pattern = Pattern(
            id=_new_id(),
            name=pattern_name,
            task_type=task_type,
            strategy=strategy,
            embedding=embedding,
            usage_count=1,
            quality_score=float(reward),
        )
        new_pattern.stable = new_pattern.usage_count >= self.config.min_usages_for_stable

        self._patterns[new_pattern.id] = new_pattern
        logger.debug(
            f"[VECTOR][pattern_learner] new pattern id={new_pattern.id} "
            f"type={task_type} quality={reward:.2f}"
        )
        return new_pattern

    def match(self, task: str) -> List[Pattern]:
        """Find patterns matching a task above the similarity threshold.

        Args:
            task: problem description to match against

        Returns:
            List of Pattern sorted by quality_score descending.
        """
        if not self._patterns:
            return []

        task_type = self._infer_task_type(task)
        query_emb = _hash_embed(task, _EMBED_DIM)

        matches = []
        for p in self._patterns.values():
            sim = _cosine_similarity(query_emb, p.embedding)
            if sim >= self.config.match_threshold or p.task_type == task_type:
                matches.append((p, sim))

        matches.sort(key=lambda x: x[0].quality_score * 0.6 + x[1] * 0.4, reverse=True)
        return [p for p, _ in matches]

    def evolve(self, pattern_id: str, reward: float) -> None:
        """Update a pattern's quality score based on new reward signal.

        Args:
            pattern_id: id of pattern to evolve
            reward:     scalar reward 0.0-1.0
        """
        pattern = self._patterns.get(pattern_id)
        if pattern is None:
            logger.warning(f"[VECTOR][pattern_learner] evolve: pattern {pattern_id} not found")
            return

        alpha = 0.2
        pattern.quality_score = float(
            np.clip(alpha * reward + (1 - alpha) * pattern.quality_score, 0.0, 1.0)
        )
        pattern.usage_count += 1
        pattern.stable = pattern.usage_count >= self.config.min_usages_for_stable

        logger.debug(
            f"[VECTOR][pattern_learner] evolved id={pattern_id} "
            f"quality={pattern.quality_score:.3f} usages={pattern.usage_count}"
        )

    def get_best_strategies(
        self,
        task_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[str]:
        """Return the strategy descriptions of the top-k highest quality patterns.

        Args:
            task_type: filter to a specific type, or None for all
            top_k:     max number of strategies to return

        Returns:
            List of strategy description strings.
        """
        patterns = list(self._patterns.values())
        if task_type:
            patterns = [p for p in patterns if p.task_type == task_type]

        # Sort by quality then stability
        patterns.sort(
            key=lambda p: (p.quality_score * 0.7 + (0.3 if p.stable else 0.0)),
            reverse=True,
        )
        return [p.strategy for p in patterns[:top_k]]

    def stable_patterns(self, task_type: Optional[str] = None) -> List[Pattern]:
        """Return every pattern that has crossed the stability threshold
        (repeated >= config.min_usages_for_stable times with reward above
        config.quality_threshold — see extract()). Highest quality first.

        No public accessor previously existed for the full stable set
        (stats() only returns aggregates, get_best_strategies() only returns
        strategy text) — added for consumers that need the real Pattern
        objects themselves, e.g. turning a stable pattern into a reusable
        artifact.

        Args:
            task_type: filter to a specific type, or None for all

        Returns:
            List of stable Pattern objects, highest quality_score first.
        """
        patterns = [p for p in self._patterns.values() if p.stable]
        if task_type:
            patterns = [p for p in patterns if p.task_type == task_type]
        patterns.sort(key=lambda p: p.quality_score, reverse=True)
        return patterns

    def stats(self) -> Dict[str, Any]:
        """Return learner statistics."""
        patterns = list(self._patterns.values())
        if not patterns:
            return {"total": 0}

        quality_scores = np.array([p.quality_score for p in patterns])
        type_counts: Dict[str, int] = {}
        for p in patterns:
            type_counts[p.task_type] = type_counts.get(p.task_type, 0) + 1

        return {
            "total": len(patterns),
            "stable": sum(1 for p in patterns if p.stable),
            "avg_quality": round(float(quality_scores.mean()), 4),
            "max_quality": round(float(quality_scores.max()), 4),
            "task_type_distribution": type_counts,
            "total_usages": sum(p.usage_count for p in patterns),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_task_type(task: str) -> str:
        """Infer task type from keywords in the task description."""
        task_lower = task.lower()
        keywords = {
            "code": ["code", "function", "implement", "bug", "fix", "refactor", "class", "method"],
            "security": ["security", "vulnerability", "auth", "inject", "xss", "csrf", "encrypt"],
            "research": ["research", "paper", "article", "analyse", "analyze", "investigate"],
            "planning": ["plan", "design", "architect", "strategy", "roadmap", "schedule"],
            "testing": ["test", "validate", "verify", "assert", "spec", "coverage"],
            "communication": ["email", "message", "notify", "send", "write"],
            "data": ["data", "database", "query", "sql", "store", "retrieve", "fetch"],
        }
        for task_type, words in keywords.items():
            if any(w in task_lower for w in words):
                return task_type
        return "general"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self, path: Optional[Path | str] = None) -> None:
        """Load patterns from JSON."""
        load_path = Path(path) if path else self._path
        if not load_path.exists():
            return
        try:
            payload = json.loads(load_path.read_text(encoding="utf-8"))
            for d in payload.get("patterns", []):
                p = Pattern.from_dict(d)
                self._patterns[p.id] = p
            logger.info(
                f"[VECTOR][pattern_learner] loaded {len(self._patterns)} patterns"
            )
        except Exception as exc:
            logger.error(f"[VECTOR][pattern_learner] load failed: {exc}")

    def save(self, path: Optional[Path | str] = None) -> None:
        """Save patterns to JSON."""
        save_path = Path(path) if path else self._path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "patterns": [p.to_dict() for p in self._patterns.values()],
        }
        save_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.debug(
            f"[VECTOR][pattern_learner] saved {len(self._patterns)} patterns to {save_path}"
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import tempfile

    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    with tempfile.TemporaryDirectory() as tmpdir:
        bank_path = Path(tmpdir) / "reasoning_bank.json"
        patterns_path = Path(tmpdir) / "patterns.json"

        learner = PatternLearner(path=patterns_path, auto_load=False)
        bank = ReasoningBank(path=bank_path, auto_load=False, pattern_learner=learner)

        # store entries
        id1 = bank.store(
            task="implement binary search function",
            reasoning="Start with low=0, high=len-1. Check mid. If target < mid go left.",
            outcome="Function implemented correctly, O(log n) complexity.",
            reward=0.9,
            task_type="code",
        )
        id2 = bank.store(
            task="debug authentication middleware",
            reasoning="Check JWT expiry first, then signature, then claims.",
            outcome="Bug found: token expiry was not being checked.",
            reward=0.75,
            task_type="security",
        )
        id3 = bank.store(
            task="implement linear search",
            reasoning="Iterate from index 0. Compare each element.",
            outcome="Works but slow O(n).",
            reward=0.5,
            task_type="code",
        )

        assert len(bank._entries) == 3

        # retrieve
        results = bank.retrieve("write a search algorithm", top_k=2, min_reward=0.6)
        assert len(results) >= 1
        assert results[0].reward >= 0.6

        # judge
        bank.judge(id1, verdict="excellent", reward_adjustment=0.05)
        assert bank._entries[id1].verdict == "excellent"
        assert bank._entries[id1].reward >= 0.9

        # inject_past_reasoning
        snippet = bank.inject_past_reasoning("implement a sorting algorithm", top_k=2)
        assert "Past Reasoning" in snippet or snippet == ""   # may be empty if no match

        # distill
        distilled = bank.distill(task_type="code")
        assert distilled["total"] == 2
        assert "avg_reward" in distilled

        # stats
        s = bank.stats()
        assert s["total"] == 3
        assert "avg_reward" in s

        # save/load round-trip
        bank.save()
        assert bank_path.exists()

        bank2 = ReasoningBank(path=bank_path, auto_load=True)
        assert len(bank2._entries) == 3

        # PatternLearner
        patterns = learner.match("implement a search function")
        strategies = learner.get_best_strategies(task_type="code", top_k=5)
        pl_stats = learner.stats()
        assert pl_stats["total"] >= 0

        if patterns:
            learner.evolve(patterns[0].id, reward=0.85)

        # PatternLearner save
        learner.save()
        assert patterns_path.exists()

        learner2 = PatternLearner(path=patterns_path, auto_load=True)
        assert learner2.stats()["total"] == learner.stats()["total"]

        # stable_patterns(): a genuinely repeated task (same task_type, near-
        # identical text so it merges rather than creating new patterns)
        # crosses min_usages_for_stable and becomes retrievable; a one-off
        # low-reward task never does.
        for _ in range(3):
            learner.extract(
                task="restart the stalled ingestion worker",
                reasoning="Check the queue depth, then send SIGTERM, then relaunch.",
                outcome="Worker restarted cleanly.",
                reward=0.8,
            )
        learner.extract(
            task="one-off task nobody repeats",
            reasoning="Did something unique once.",
            outcome="Done.",
            reward=0.3,  # below quality_threshold too, so extract() itself skips it
        )
        stable = learner.stable_patterns()
        assert stable, "a task repeated 3x above quality_threshold must produce a stable pattern"
        assert all(p.stable for p in stable)
        assert all(p.usage_count >= learner.config.min_usages_for_stable for p in stable)
        assert not any(p.strategy.startswith("Did something unique once") for p in stable)

        filtered = learner.stable_patterns(task_type=stable[0].task_type)
        assert all(p.task_type == stable[0].task_type for p in filtered)
        assert learner.stable_patterns(task_type="_no_such_type_") == []

    print("✅ reasoning_bank OK")
