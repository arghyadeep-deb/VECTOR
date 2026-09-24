# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by core/inference/provider_client.py + model_pool. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""Model router: classifies tasks into domains and routes to the best adapter-aware model via Ollama."""


__all__ = [
    "ClassificationResult",
    "DEFAULT_DOMAIN",
    "ModelRouter",
    "RoutingResult",
    "TaskClassifier",
]

import json
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "coding": ["write", "code", "function", "debug", "refactor", "implement", "fix", "bug",
                "algorithm", "class", "api", "endpoint", "test", "script", "syntax", "compile",
                "pull request", "commit", "review", "optimize", "performance", "memory leak"],
    "research": ["research", "paper", "arxiv", "publication", "compare", "survey", "literature",
                  "state of the art", "explain", "analysis", "summarize", "summarise",
                  "attention", "transformer", "diffusion", "rag", "llm", "fine.tune"],
    "voice": ["say", "speak", "pronounce", "voice", "listen", "audio", "speech",
               "narrate", "read aloud", "talk", "tell me", "wake word", "hey vector"],
    "personality": ["sir", "your name", "who are you", "what are you", "joke", "humor",
                     "personality", "character", "behavior", "mannerism", "greeting",
                     "tone", "style", "funny", "mood"],
}

DEFAULT_DOMAIN = "general"


@dataclass
class ClassificationResult:
    domain: str
    confidence: float
    method: str = "keyword"


@dataclass
class RoutingResult:
    model_name: str
    adapter_name: str
    domain: str
    confidence: float
    available_adapters: list[str] = field(default_factory=list)


class TaskClassifier:
    def __init__(self, llm_fallback: bool = False):
        self.llm_fallback = llm_fallback
        self._keyword_map = DOMAIN_KEYWORDS
        logger.info("[ModelRouter] TaskClassifier initialized (llm_fallback={})", llm_fallback)

    def classify(self, task_text: str) -> ClassificationResult:
        if not task_text or not task_text.strip():
            return ClassificationResult(domain=DEFAULT_DOMAIN, confidence=0.0, method="keyword")
        task_lower = task_text.lower()
        domain_scores: dict[str, float] = {}
        for domain, keywords in self._keyword_map.items():
            score = 0.0
            for kw in keywords:
                if kw in task_lower:
                    score += 1.0
            if keywords:
                score = score / max(len(keywords), 1)
                domain_scores[domain] = score
        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            best_score = domain_scores[best_domain]
            if best_score >= 0.05:
                if self.llm_fallback and best_score < 0.15:
                    llm_result = self._classify_with_llm(task_text)
                    if llm_result and llm_result.domain != DEFAULT_DOMAIN:
                        return llm_result
                return ClassificationResult(domain=best_domain, confidence=min(best_score * 3.0, 1.0), method="keyword")
        if self.llm_fallback:
            llm_result = self._classify_with_llm(task_text)
            if llm_result:
                return llm_result
        return ClassificationResult(domain=DEFAULT_DOMAIN, confidence=0.3, method="keyword")

    def _classify_with_llm(self, task_text: str) -> ClassificationResult | None:
        try:
            from core.inference.ollama_safe import chat
            prompt = (
                f"Classify this task into one domain: coding, research, voice, personality, or general. "
                f"Respond with only the domain word.\n\nTask: {task_text}"
            )
            response = chat(model="vector-fast", messages=[{"role": "user", "content": prompt}], timeout=15.0,
                            caller_id="model_router_classify")
            domain = response.strip().lower()
            if domain in self._keyword_map:
                return ClassificationResult(domain=domain, confidence=0.85, method="llm")
            return None
        except Exception as e:
            logger.warning("[ModelRouter] LLM classification fallback failed: {}", e)
            return None


class ModelRouter:
    def __init__(self, adapter_dir: str = "models/adapters", base_model: str = "vector-focus"):
        self.adapter_dir = Path(adapter_dir)
        self.base_model = base_model
        self.classifier = TaskClassifier()
        self._stats: dict[str, Any] = {
            "total_routes": 0,
            "domain_counts": {},
            "adapter_swaps": 0,
            "last_route": "",
            "started_at": datetime.now().isoformat(),
        }
        self._domain_adapter_map: dict[str, str] = {}
        self._load_adapter_map()
        logger.info("[ModelRouter] ModelRouter initialized (base={}, adapters={})", base_model, self.adapter_dir)

    def route(self, task: str, context: dict | None = None) -> RoutingResult:
        self._stats["total_routes"] += 1
        self._stats["last_route"] = task[:100]
        classification = self.classifier.classify(task)
        domain = classification.domain
        self._stats["domain_counts"][domain] = self._stats["domain_counts"].get(domain, 0) + 1
        adapter_name = self._domain_adapter_map.get(domain, "")
        model_name = self.base_model
        available = self.list_adapters()
        logger.info("[ModelRouter] Routed '{}' → domain={} (conf={:.2f}) adapter={}",
                     task[:60], domain, classification.confidence, adapter_name or "none")
        return RoutingResult(
            model_name=model_name,
            adapter_name=adapter_name,
            domain=domain,
            confidence=classification.confidence,
            available_adapters=[a.get("name", "") for a in available],
        )

    def hot_swap(self, adapter_name: str) -> bool:
        try:
            available = self.list_adapters()
            match = next((a for a in available if a.get("name") == adapter_name), None)
            if not match:
                logger.warning("[ModelRouter] Adapter '{}' not found for hot-swap", adapter_name)
                return False
            base = match.get("base_model", self.base_model)
            modelfile = f"FROM {base}\nADAPTER {self.adapter_dir / adapter_name}\nPARAMETER temperature 0.7\n"
            import subprocess
            modelfile_path = self.adapter_dir / f"{adapter_name}_swap.Modelfile"
            modelfile_path.write_text(modelfile, encoding="utf-8")
            result = subprocess.run(
                ["ollama", "create", f"vector-{adapter_name}", "-f", str(modelfile_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                self._stats["adapter_swaps"] += 1
                logger.info("[ModelRouter] Hot-swapped to adapter '{}'", adapter_name)
                return True
            logger.warning("[ModelRouter] Hot-swap failed: {}", result.stderr)
            return False
        except FileNotFoundError:
            logger.warning("[ModelRouter] Ollama CLI not found, cannot hot-swap")
            return False
        except Exception as e:
            logger.warning("[ModelRouter] Hot-swap error: {}", e)
            return False

    def get_domain_for_task(self, task_text: str) -> str:
        return self.classifier.classify(task_text).domain

    def list_adapters(self) -> list[dict]:
        adapters = []
        if not self.adapter_dir.exists():
            self.adapter_dir.mkdir(parents=True, exist_ok=True)
            return adapters
        for d in self.adapter_dir.iterdir():
            if d.is_dir():
                manifest = d / "manifest.json"
                if manifest.exists():
                    try:
                        data = json.loads(manifest.read_text(encoding="utf-8"))
                        adapters.append(data)
                    except Exception as e:
                        logger.warning("[ModelRouter] Failed to read {}: {}", manifest, e)
        try:
            import ollama
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed.
            with ollama.Client(host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")) as client:
                local_models = client.list()
            for model in local_models.get("models", []):
                name = model.get("name", "")
                if name not in [a.get("name", "") for a in adapters]:
                    adapters.append({"name": name, "base_model": name, "source": "ollama"})
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return adapters

    def get_stats(self) -> dict:
        stats = dict(self._stats)
        stats["adapter_count"] = len(self.list_adapters())
        stats["domains_mapped"] = dict(self._domain_adapter_map)
        return stats

    def register_adapter_for_domain(self, domain: str, adapter_name: str) -> None:
        self._domain_adapter_map[domain] = adapter_name
        logger.info("[ModelRouter] Mapped domain '{}' → adapter '{}'", domain, adapter_name)

    def _load_adapter_map(self) -> None:
        map_path = self.adapter_dir / "domain_map.json"
        if map_path.exists():
            try:
                data = json.loads(map_path.read_text(encoding="utf-8"))
                self._domain_adapter_map = data.get("mappings", {})
                logger.info("[ModelRouter] Loaded {} domain→adapter mappings", len(self._domain_adapter_map))
            except Exception as e:
                logger.warning("[ModelRouter] Failed to load domain map: {}", e)
