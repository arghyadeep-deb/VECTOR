<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: async-python-patterns
description: Comprehensive asyncio guidance for Python. Use when building VECTOR's autonomous loop, voice pipeline, or any concurrent I/O in core/. VECTOR is async-first — this skill covers all the patterns.
risk: safe
source: sickn33/antigravity-awesome-skills (community)
---

# Async Python Patterns

Comprehensive guidance for implementing asynchronous Python using asyncio, concurrent programming patterns, and async/await for high-performance non-blocking systems.

## Use this skill when

- Building or debugging VECTOR's autonomous_loop.py coroutines
- Implementing voice pipeline (STT + TTS must be non-blocking)
- Writing any new `async def` in core/ or agents/
- Fixing a coroutine that blocks the event loop
- Setting up asyncio.gather() with return_exceptions=True

## VECTOR Asyncio Rules

- **Every coroutine catches ALL exceptions** — never let exceptions propagate up
- **Never use `asyncio.sleep()` for long durations without chunking** — use 1s chunks so stop() works
- **`asyncio.gather(return_exceptions=True)`** in run_forever() so one crash doesn't kill others
- **Never use `threading`** — use asyncio (libraries.md)
- **Never block the event loop** — database calls use run_in_executor if not async-native

## Key Patterns

### Chunked Sleep (VECTOR standard)
```python
# WRONG — stop() can't interrupt this
await asyncio.sleep(3600)

# RIGHT — stop() works within 1s
remaining = 3600
while self._running and remaining > 0:
    await asyncio.sleep(min(1.0, remaining))
    remaining -= 1.0
```

### Exception-safe coroutine
```python
async def observe_loop(self):
    while self._running:
        try:
            await self._observe_tick()
        except Exception as e:
            logger.error(f"[VECTOR][observe] {e}")
        await asyncio.sleep(0.5)
```

### Parallel coroutines
```python
await asyncio.gather(
    self.observe_loop(),
    self.think_loop(),
    self.act_loop(),
    self.reflect_loop(),
    self.sync_loop(),
    return_exceptions=True,  # REQUIRED — one crash doesn't kill others
)
```

### run_in_executor for blocking calls
```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, blocking_function, arg1, arg2)
```

### Async queue between coroutines
```python
queue = asyncio.Queue()

async def producer():
    await queue.put(item)

async def consumer():
    item = await queue.get()
    queue.task_done()
```

## Common Pitfalls

- `time.sleep()` in async code — blocks entire event loop. Use `await asyncio.sleep()`
- Synchronous DB calls in async context — use run_in_executor or async driver
- No timeout on external calls — always `asyncio.wait_for(coro, timeout=10)`
- Creating tasks without awaiting — use `asyncio.create_task()` and track them
