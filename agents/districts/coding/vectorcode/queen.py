"""QueenCoordinator — VectorCode VC-3. Decomposes tasks into domain-routed subtasks."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger


def chat(model: str, prompt: str) -> str:
    """Thin Ollama wrapper. Returns raw string or empty subtasks JSON on failure."""
    import ollama
    try:
        resp = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return resp["message"]["content"]
    except Exception as e:
        logger.warning(f"[VECTOR][queen] ollama unavailable: {e}")
        return '{"subtasks": []}'


_DECOMPOSE_PROMPT = """\
Decompose the following task into concrete subtasks. Return ONLY valid JSON.

Format:
{{"subtasks": [{{"task": "...", "domain": "core|security|devops|research|support"}}]}}

Task: {task}"""


class QueenCoordinator:
    """Decomposes a high-level task into subtasks using vector-reasoning."""

    def decompose(self, task: str) -> list:
        prompt = _DECOMPOSE_PROMPT.format(task=task)
        raw = chat("vector-reasoning", prompt)
        try:
            data = json.loads(raw)
            subtasks = data.get("subtasks", [])
            if subtasks and all("task" in s and "domain" in s for s in subtasks):
                return subtasks
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning(f"[VECTOR][queen] bad JSON from LLM, using fallback")
        # Fallback: wrap the original task as a single core subtask
        return [{"task": task, "domain": "core"}]


if __name__ == "__main__":
    q = QueenCoordinator()
    result = q.decompose("build a login endpoint with JWT auth")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "task" in result[0]
    print(f"queen.py OK — {len(result)} subtask(s)")
