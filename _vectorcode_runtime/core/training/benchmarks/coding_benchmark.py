"""Coding benchmark: 20 prompts covering function writing, bug fixing, code review, refactoring, API design."""


__all__ = [
    "CODING_PROMPTS",
    "CodingBenchmark",
]

from typing import Callable

from loguru import logger


CODING_PROMPTS = [
    {"id": "write_fibonacci", "prompt": "Write a Python function that returns the nth Fibonacci number using iteration. Include type hints.", "expected": "def", "type": "exact"},
    {"id": "fix_off_by_one", "prompt": "Fix the bug: def sum_list(lst): total = 0; for i in range(len(lst)): total += lst[i+1]; return total", "expected": "lst[i]", "type": "exact"},
    {"id": "review_sql_injection", "prompt": "Review this code for security issues: def get_user(name): cursor.execute(f'SELECT * FROM users WHERE name = {name}')", "expected": "parameterized", "type": "rubric"},
    {"id": "refactor_nested_loops", "prompt": "Refactor to reduce complexity: def find_duplicates(a, b): result = []; for x in a: for y in b: if x == y: result.append(x); return result", "expected": "set", "type": "rubric"},
    {"id": "design_rate_limiter", "prompt": "Design a simple rate limiter API. Show the interface and explain the algorithm.", "expected": "token_bucket|sliding_window|leaky_bucket", "type": "rubric"},
    {"id": "write_binary_search", "prompt": "Write a binary search function in Python with type hints and edge case handling.", "expected": "def binary_search", "type": "exact"},
    {"id": "fix_memory_leak", "prompt": "Fix the memory issue in this class: class Logger: def __init__(self): self.handlers = []\ndef add_handler(self, h): self.handlers.append(h)", "expected": "remove|cleanup|close", "type": "rubric"},
    {"id": "review_thread_safety", "prompt": "Review this concurrent code for race conditions and deadlocks.", "expected": "lock|mutex|thread_safe|atomic", "type": "rubric"},
    {"id": "refactor_global_state", "prompt": "Refactor this module to eliminate global state: config = {}; def set(key, val): global config; config[key] = val", "expected": "class|Config|dependency_injection", "type": "rubric"},
    {"id": "design_event_system", "prompt": "Design an event emission and subscription system. Show the key interfaces.", "expected": "subscribe|emit|listener|observer", "type": "rubric"},
    {"id": "write_quicksort", "prompt": "Write an in-place quicksort implementation in Python with type hints.", "expected": "def quicksort", "type": "exact"},
    {"id": "fix_deadlock", "prompt": "Fix the deadlock: lock_a.acquire(); lock_b.acquire(); # work; lock_b.release(); lock_a.release()", "expected": "ordering|try_finally|with|acquire", "type": "rubric"},
    {"id": "review_error_handling", "prompt": "Review error handling: def divide(a, b): return a / b", "expected": "except|try|ZeroDivisionError", "type": "exact"},
    {"id": "refactor_validation", "prompt": "Refactor this validation into reusable components: if x > 0 and x < 100 and y > 0 and y < 100:", "expected": "validator|function|class|dataclass", "type": "rubric"},
    {"id": "design_cache_api", "prompt": "Design a cache API with TTL support. Show the interface and expected behavior.", "expected": "ttl|expire|get|set|Cache", "type": "rubric"},
    {"id": "write_merge_sort", "prompt": "Write a merge sort implementation in Python with type hints.", "expected": "def merge_sort", "type": "exact"},
    {"id": "fix_null_pointer", "prompt": "Fix: user = get_user(id); print(user.name) where get_user may return None.", "expected": "if user|is None|Optional|check", "type": "exact"},
    {"id": "review_performance", "prompt": "Review performance: [x for x in range(1000000) if x in [i*2 for i in range(1000000)]]", "expected": "set|O(1)|hash|complexity", "type": "rubric"},
    {"id": "refactor_callback_hell", "prompt": "Refactor this callback chain: get_data(callback1); def callback1(d): process(d, callback2); def callback2(r): save(r)", "expected": "async|await|coroutine|Promise", "type": "rubric"},
    {"id": "design_plugin_arch", "prompt": "Design a plugin architecture for a CLI tool. Show the plugin interface and discovery mechanism.", "expected": "register|discover|plugin|interface|entry_point", "type": "rubric"},
]


class CodingBenchmark:
    def __init__(self):
        self.prompts = CODING_PROMPTS
        logger.info("[Benchmark] CodingBenchmark initialized with {} prompts", len(self.prompts))

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores = {}
        for p in self.prompts:
            try:
                response = model_fn(p["prompt"])
                score = self._score_response(p, response)
                scores[p["id"]] = score
                logger.debug("[Benchmark] {} scored {:.2f}", p["id"], score)
            except Exception as e:
                logger.warning("[Benchmark] {} failed: {}", p["id"], e)
                scores[p["id"]] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Benchmark] Coding average: {:.2f}/1.00", avg)
        return scores

    def _score_response(self, prompt: dict, response: str) -> float:
        if not response:
            return 0.0
        response_lower = response.lower()
        if prompt["type"] == "exact":
            checks = prompt["expected"].lower().split("|")
            for c in checks:
                if c in response_lower:
                    return 1.0
            return 0.0
        keywords = prompt["expected"].lower().split("|")
        matches = sum(1 for k in keywords if k in response_lower)
        return matches / max(len(keywords), 1)
