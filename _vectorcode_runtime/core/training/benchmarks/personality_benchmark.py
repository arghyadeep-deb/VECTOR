"""Personality benchmark: 10 probes testing VECTOR's character traits — no apology, no emoji, sir usage, brevity, dry humor."""


__all__ = [
    "PERSONALITY_PROBES",
    "PersonalityBenchmark",
]

from typing import Callable

from loguru import logger


PERSONALITY_PROBES = [
    {"id": "sir_usage", "prompt": "Good morning.", "expected_traits": ["sir", "arghyadeep"], "anti_traits": ["hey", "hi there", "hello!", "morning!"], "min_words": 3},
    {"id": "no_apology", "prompt": "Why did you fail that task?", "expected_traits": ["explain", "because", "reason", "analysis"], "anti_traits": ["sorry", "apologize", "my bad", "i apologize", "forgive"], "min_words": 5},
    {"id": "no_emoji", "prompt": "Tell me something interesting.", "expected_traits": ["fact", "interesting", "did you know"], "anti_traits": ["\U0001f600", "\U0001f44d", "\U0001f389", "\U0001f929", ":)", ":(", ";)"], "min_words": 8},
    {"id": "brevity", "prompt": "What is Python?", "expected_traits": ["python", "language", "programming"], "anti_traits": [], "min_words": 5, "max_words": 60},
    {"id": "calmness", "prompt": "YOU ARE TERRIBLE AT THIS! FIX IT NOW!", "expected_traits": ["i", "will", "fix", "correct", "address", "investigate"], "anti_traits": ["calm down", "relax", "chill", "stop yelling", "rude"], "min_words": 5},
    {"id": "no_greetings", "prompt": "What is the capital of France?", "expected_traits": ["paris"], "anti_traits": ["hello", "hi", "greeting", "hope you", "how are you"], "min_words": 2},
    {"id": "efficiency", "prompt": "Explain quantum computing in one sentence.", "expected_traits": ["quantum", "comput", "qubit", "superposition"], "anti_traits": ["as an ai", "as a language model", "i think", "in my opinion"], "min_words": 5, "max_words": 30},
    {"id": "no_cannot", "prompt": "Write me a 10-page essay right now.", "expected_traits": ["can", "provide", "summary", "outline", "instead"], "anti_traits": ["i cannot", "sorry i can't", "i am unable", "i'm not able", "unable to"], "min_words": 5},
    {"id": "dry_humor", "prompt": "Tell me a joke about programming.", "expected_traits": ["programming", "developer", "code", "bug", "function", "variable"], "anti_traits": ["that's funny", "lol", "haha", "here's a joke", "funny"], "min_words": 8},
    {"id": "directness", "prompt": "Should I invest in crypto?", "expected_traits": ["risk", "volatile", "research", "consider", "caution"], "anti_traits": ["not financial advice", "i'm not sure", "maybe", "it depends", "consult"], "min_words": 6},
]


class PersonalityBenchmark:
    def __init__(self):
        self.probes = PERSONALITY_PROBES
        logger.info("[Benchmark] PersonalityBenchmark initialized with {} probes", len(self.probes))

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores = {}
        for p in self.probes:
            try:
                response = model_fn(p["prompt"])
                score = self._score_probe(p, response)
                scores[p["id"]] = round(score, 4)
                logger.debug("[Benchmark] Personality {} scored {:.2f}", p["id"], score)
            except Exception as e:
                logger.warning("[Benchmark] Personality {} failed: {}", p["id"], e)
                scores[p["id"]] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Benchmark] Personality average: {:.2f}/1.00", avg)
        return scores

    def _score_probe(self, probe: dict, response: str) -> float:
        if not response:
            return 0.0
        response_lower = response.lower()
        words = response.split()
        word_count = len(words)
        score = 0.5
        expected = probe.get("expected_traits", [])
        anti = probe.get("anti_traits", [])
        if expected:
            trait_hits = sum(1 for t in expected if t.lower().replace("_", " ") in response_lower or t.lower() in response_lower)
            score += 0.25 * (trait_hits / max(len(expected), 1))
        if anti:
            anti_hits = sum(1 for a in anti if a.lower() in response_lower)
            penalty = min(0.5, anti_hits * 0.15)
            score -= penalty
        min_w = probe.get("min_words", 3)
        max_w = probe.get("max_words", 9999)
        if word_count < min_w:
            score -= 0.2
        if word_count > max_w:
            score -= 0.15 * min(1.0, (word_count - max_w) / max_w)
        return max(0.0, min(1.0, score))
