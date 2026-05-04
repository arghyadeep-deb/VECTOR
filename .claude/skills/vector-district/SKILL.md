---
name: vector-district
description: Scaffold a new district agent for VECTOR City. Creates a properly structured agent file inheriting AgentBase with loguru, fallback chains, and __main__ test.
---

The user wants to create a new district agent. Scaffold it from the VECTOR template.

## Usage
`/vector-district <district>/<agent_name>`

Example: `/vector-district coding/git_bot`

## Template Structure

Every district agent must follow this pattern:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class <AgentName>(AgentBase):
    """<One-line description of what this agent does>"""

    def __init__(self):
        super().__init__(
            agent_id="<district>_<agent_name>_v1",
            name="<AgentName>",
            district="<district>",
        )
        logger.info(f"[VECTOR][<agent_name>] initialized — HP: {self.health_points}")

    async def run(self, task: dict) -> dict:
        """Execute the agent's primary task."""
        try:
            result = await self._do_task(task)
            self.award_points(50, "task_completed")
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.error(f"[VECTOR][<agent_name>] {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

    async def _do_task(self, task: dict) -> dict:
        # TODO: implement
        return {"stub": True}


if __name__ == "__main__":
    import asyncio
    agent = <AgentName>()
    result = asyncio.run(agent.run({"type": "test"}))
    status = agent.get_status()
    print(f"✅ <agent_name> OK — HP: {status['hp']}, model: {status['model']}" if result else "❌ FAILED")
```

## Steps

1. Parse the argument to get district name and agent name
2. Generate the agent file at `agents/districts/<district>/<agent_name>.py`
3. Replace all `<placeholders>` with actual names using PascalCase for class, snake_case for files
4. Ensure the `sys.path.insert` depth is correct (count parent directories to project root)
5. Add the agent to the district's `__init__.py`
6. Run the new file to verify it prints ✅

## Rules
- Never use `print()` — use `loguru logger`
- Never use `requests` — use `httpx`
- Every task outcome must call `award_points()` or `deduct_points()`
- Fallback chain: primary → fallback → cached result → notify owner
