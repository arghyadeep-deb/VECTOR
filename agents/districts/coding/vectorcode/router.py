import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from core.config import CONFIG

import re
from loguru import logger

# Routing table: (compiled pattern, model name) — checked in order, first match wins
_ROUTES = [
    # Council/high-stakes first (most specific)
    (re.compile(r"\b(council|vote|chairman|critical)\b", re.IGNORECASE), "vector-chairman"),
    # Deep analysis
    (re.compile(r"\b(deep|overnight|comprehensive|entire)\b", re.IGNORECASE), "vector-deep"),
    # Planning / reasoning
    (re.compile(r"\b(plan|design|architect|think|how|approach|strategy|decide)\b", re.IGNORECASE), "vector-reasoning"),
    # Review / audit
    (re.compile(r"\b(review|check|audit|verify|test|inspect|analyse|analyze)\b", re.IGNORECASE), "vector-dev"),
    # Code writing
    (re.compile(r"\b(write|implement|create|generate|code|function|class|method)\b", re.IGNORECASE), "vector-coder"),
    # Important (broad) — after specifics
    (re.compile(r"\b(important)\b", re.IGNORECASE), "vector-chairman"),
    # Full (after deep/comprehensive covered above)
    (re.compile(r"\b(full)\b", re.IGNORECASE), "vector-deep"),
]

_DEFAULT_MODEL = "vector-fast"


class SemanticRouter:
    """
    Keyword-based deterministic router — no LLM call, O(n) regex scan.
    Maps a task string to an Ollama model name (RULE 4 compliant).
    """

    def route(self, task: str) -> str:
        """Return the best-fit Ollama model name for the given task."""
        for pattern, model in _ROUTES:
            if pattern.search(task):
                logger.debug(f"[VECTOR][router] '{task[:60]}' → {model}")
                return model
        logger.debug(f"[VECTOR][router] '{task[:60]}' → {_DEFAULT_MODEL} (default)")
        return _DEFAULT_MODEL

    def route_sequence(self, tasks: list) -> list:
        """
        Route a list of tasks and return the list of models.
        The returned list has the same length as tasks.
        """
        return [self.route(t) for t in tasks]

    def count_switches(self, tasks: list) -> int:
        """Count model switches across a sequence of tasks."""
        models = self.route_sequence(tasks)
        return sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])


if __name__ == "__main__":
    r = SemanticRouter()
    assert r.route("write a function") == "vector-coder", f"Got {r.route('write a function')}"
    assert r.route("review this code") == "vector-dev", f"Got {r.route('review this code')}"
    assert r.route("plan how to refactor") == "vector-reasoning", f"Got {r.route('plan how to refactor')}"
    assert r.route("what is the status") == "vector-fast", f"Got {r.route('what is the status')}"
    models = [r.route(t) for t in ["plan the task", "write the code", "review it"]]
    switches = sum(1 for i in range(1, len(models)) if models[i] != models[i - 1])
    assert switches <= 3
    print("router.py OK")
