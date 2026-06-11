# Issue 20 — Sync httpx.Client in async stream()

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `_openai_compat.py:119`, `ollama.py:181` — blocks the event loop
- **Status:** ⬜ TODO

## Issue (as reported)
Synchronous `httpx.Client` used inside an `async def stream()` blocks the event
loop, stalling every other coroutine during LLM streaming.

## Analysis (to complete during analysis pass)
- Affected files: `core/inference/.../_openai_compat.py`, `.../ollama.py` (confirm exact paths)
- Fix approach: _pending_ (use `httpx.AsyncClient` + `async for` streaming, or `asyncio.to_thread`)
- Tests / Acceptance: _pending_
