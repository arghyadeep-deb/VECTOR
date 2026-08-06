# VECTOR Style Guide

> Project-specific conventions for the VECTOR codebase.
> Full rules with examples live in `.claude/rules/code_style.md` and `.claude/rules/libraries.md`.
> This file is the consolidated quick reference.

---

## Language & Runtime

- **Python 3.12+** for all backend (PEP 695 generics in use)
- **TypeScript** for Cloudflare Workers only
- `requires-python = ">=3.12"` in `pyproject.toml`

---

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `context_engine.py` |
| Classes | `PascalCase` | `ContextEngine`, `DecisionEngine` |
| Functions | `snake_case` | `get_full_context`, `update_from_outcome` |
| Constants | `UPPER_SNAKE_CASE` | `VECTOR_VERSION`, `OWNER_NAME` |
| DB tables | `snake_case` | `episodic_memory`, `policy_memory` |
| Ollama models | `hyphen-separated` | `vector-focus`, `vector-coder` |
| Districts | `snake_case/` | `governance/`, `coding/` |

---

## File Structure

Every Python file must have:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG

def main():
    # real implementation
    pass

# At bottom — every file, every time:
if __name__ == "__main__":
    # real test, no mocks
    result = main()
    print("✅ filename OK" if result else "❌ FAILED")
```

---

## Logging

**loguru everywhere, never `print()` in production:**

```python
from loguru import logger

logger.info("[VECTOR][module] message")
logger.warning("[VECTOR][tts] Kokoro unavailable, using fallback")
logger.error("[VECTOR][db] Supabase failed, using local SQLite")
logger.critical("[VECTOR][security] Malware detected")
```

Format: `[VECTOR][<module>] <message>`

Log levels:

| Level | Use |
|-------|-----|
| `DEBUG` | Development-only details |
| `INFO` | Significant events (request completed, evaluation run) |
| `WARNING` | Recoverable issues (retry succeeded, fallback used) |
| `ERROR` | Failures that need attention |
| `CRITICAL` | System-level failures |

Never log: secrets, API keys, full PII, raw prompts with sensitive content.

---

## Error Handling

**Resilience first — the loop must never die:**

```python
# Every coroutine in autonomous_loop:
async def observe_loop():
    while True:
        try:
            await observe_tick()
        except Exception as e:
            logger.error(f"[VECTOR][observe] {e}")
            await asyncio.sleep(5)  # back off, then retry
            # NEVER propagate — loop must not die
```

Rules:

- Catch specific exceptions where possible
- Every autonomous coroutine catches ALL exceptions
- Always log the error before retrying
- Return structured error responses
- Never swallow errors silently

---

## Fallback Chains

Every component must degrade gracefully:

```
Claude API → Ollama local → cached response → notify owner
Kokoro TTS → pyttsx3 → text-only mode (never crash)
Whisper    → text input mode (never crash)
Supabase   → Turso → local SQLite (always works)
```

---

## Configuration

```python
# ALL configurable values → core/config.py CONFIG dict
# NEVER hardcode paths, API keys, or magic numbers in business logic

# Good:
from core.config import CONFIG
db_path = CONFIG["database"]["path"]

# Bad:
db_path = "vector_memory.db"  # hardcoded in business logic
```

If you type a string path in any file other than `config.py`: stop and add to CONFIG.

---

## Dependency Injection

Prefer constructor injection over global state:

```python
# Good — explicit dependencies
class EvaluationService:
    def __init__(self, llm_client: LLMClient, db: Database, config: EvalConfig):
        self.llm_client = llm_client
        self.db = db
        self.config = config

# Bad — hidden dependencies
class EvaluationService:
    def __init__(self):
        self.llm_client = get_global_llm()  # hidden
```

---

## Async Patterns

- Use `async/await` for all I/O operations
- Never mix sync and async in the same call chain
- Use `asyncio.gather` for concurrent independent operations
- Always set timeouts on async calls
- Move blocking calls to `asyncio.to_thread()`

```python
# Good — blocking call offloaded
async def sense_tick():
    result = await asyncio.to_thread(ScreenObserver().observe)
    return result
```

---

## Type Hints

Always use type hints on public functions:

```python
def run_evaluation(
    prompt: str,
    model: str,
    *,
    max_tokens: int = 4096,
    timeout: float = 30.0,
) -> EvalResult:
```

---

## Libraries

**Always use these (never substitute):**

| Need | Use | Never |
|------|-----|-------|
| API server | `fastapi + uvicorn` | `flask` |
| HTTP client | `httpx` | `requests` |
| Logging | `loguru` | `print()` |
| Concurrency | `asyncio` | `threading` |
| Serialization | `json/msgpack` | `pickle` |
| Validation | `pydantic` | manual checks |
| DB | `sqlcipher3` (local) | raw `sqlite3` for main DB |

See `.claude/rules/libraries.md` for the full approved list.

---

## Folder Structure

```
VECTOR Codebase/
├── core/              # Core platform logic
│   ├── loop/          # Autonomous loop, context/decision/permission engines
│   ├── memory/        # Episodic, policy, reasoning, RAG
│   ├── brain/         # Goals, epistemic tracker, red team, hypothesis
│   ├── city/          # Agent base, registry, governor, evolution
│   ├── inference/     # 27 LLM providers, model routing, quota
│   ├── voice/         # STT, TTS, wake word
│   ├── sensing/       # Camera, screen, health
│   ├── control/       # PC, phone, security
│   ├── security/      # Prompt injection, SSRF, taint tracking
│   └── config.py      # ALL configuration
├── districts/         # 33 domain districts with agent files
├── vectorcode/        # Communications layer (30+ platform adapters)
├── api/               # Cloudflare Worker API
├── cloud/             # Cloud deployment configs
├── frontend/          # HUD (6.3k LOC, served at /hud/)
├── tests/             # Test suite
├── docs/              # Architecture docs, ADRs
├── scripts/           # Utility scripts
├── .claude/           # Rules, commands, hooks, skills, agents
└── brain/             # Junction → Obsidian vault
```

---

## Git Convention

```
Auto-commits by VECTOR: "auto: [module] [what changed]"
Manual commits:         "[T1.5] episodic.py: FTS5 + 5 tables done"
Never commit: .env, *.db, models/*.lgb, google_credentials.json
Commit every day — minimum 1 commit before sleep
```
