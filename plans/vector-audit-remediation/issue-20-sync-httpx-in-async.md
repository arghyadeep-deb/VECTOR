# Issue 20 — Sync httpx.Client in async stream()

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `_openai_compat.py:119`, `ollama.py:181` — blocks the event loop
- **Status:** ✅ RESOLVED

## Issue (as reported)
Synchronous `httpx.Client` used inside an `async def stream()` blocks the event
loop, stalling every other coroutine during LLM streaming.

## Resolution
- Added dedicated `httpx.AsyncClient` instances to `_openai_compat.py` and `ollama.py`.
- Async stream paths now use `async with self._async_client.stream(...)` and `async for line in resp.aiter_lines()`.
- `close()` now closes both sync and async clients.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
