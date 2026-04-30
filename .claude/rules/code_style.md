# Code Style

## Language
Python 3.11+ for all backend. TypeScript for Cloudflare Workers only.

## Naming
```
files:      snake_case          (context_engine.py)
classes:    PascalCase          (ContextEngine, DecisionEngine)
functions:  snake_case          (get_full_context, update_from_outcome)
constants:  UPPER_SNAKE_CASE    (VECTOR_VERSION, OWNER_NAME)
db tables:  snake_case          (episodic_memory, policy_memory)
models:     hyphen-separated    (vector-focus, vector-coder)
```

## Every File Must Have
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG

# At bottom — every file, every time:
if __name__ == "__main__":
    # real test, no mocks
    result = main_function()
    print("✅ filename OK" if result else "❌ FAILED")
```

## Logging — loguru everywhere, never print() in production
```python
from loguru import logger
logger.info("[VECTOR][module] message")
logger.warning("[VECTOR][tts] Kokoro unavailable, using fallback")
logger.error("[VECTOR][db] Supabase failed, using local SQLite")
logger.critical("[VECTOR][security] Malware detected")
```

## Error Handling — resilience first
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

## Fallback Chain (every component)
```
Claude API → Ollama local → cached response → notify owner
Kokoro TTS → pyttsx3 → text-only mode (never crash)
Whisper    → text input mode (never crash)
Supabase   → Turso → local SQLite (always works)
```

## Config Convention
```
ALL configurable values → core/config.py CONFIG dict
NEVER hardcode paths, API keys, or magic numbers in business logic
If you type a string path in any file other than config.py: stop and add to CONFIG
```

## Git Convention
```
Auto-commits by VECTOR: "auto: [module] [what changed]"
Manual commits:         "[T1.5] episodic.py: FTS5 + 5 tables done"
Never commit: .env, *.db, models/*.lgb, google_credentials.json
Commit every day — minimum 1 commit before sleep
```