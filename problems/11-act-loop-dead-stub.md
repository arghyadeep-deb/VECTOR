# Problem 11 — act_loop Is a Dead Stub (Think/Act Separation Broken)

**Severity: HIGH**
**Status: FIXED 2026-05-11 — dead act_loop() removed from asyncio.gather() and deleted. _act_on() is called directly from think_loop via _think_tick().**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

`core/loop/autonomous_loop.py` advertises a clean observe→think→act
coroutine separation, but `act_loop()` does nothing:

```python
async def act_loop(self):
    """Execute approved actions through permission gateway."""
    while self._running:
        try:
            await asyncio.sleep(1)    # ← entire body
        except Exception as e:
            logger.error(...)
            await asyncio.sleep(5)
```

All actual action execution happens inside `_think_tick()` → `_act_on()`,
which is called from `think_loop`. The `act_loop` coroutine runs forever
alongside `think_loop`, consuming an event loop slot while doing nothing.

## Why It Matters

1. The spec's observe → think → act pipeline has no queue between think
   and act. Actions execute synchronously inside the think tick, blocking
   the next think cycle until the action completes (including RED-tier
   30-second confirmation waits).

2. If `_act_on()` raises an exception, the think tick's exception handler
   catches it, but no retry or queueing occurs. Actions are fire-and-forget.

3. The misleading comment ("Execute approved actions through permission
   gateway") makes future developers think `act_loop` handles this — it
   doesn't.

## Architectural Options

**Option A (Minimal fix — recommended now):** Remove `act_loop` from the
`asyncio.gather()` call and add a comment explaining that actions are
dispatched inline from `_think_tick`. Honest and simple.

**Option B (Proper queue):** Implement a real action queue:
```python
self._action_queue: asyncio.Queue = asyncio.Queue()

# think_loop puts winner into queue instead of calling _act_on directly
await self._action_queue.put(winner)

# act_loop consumes queue
async def act_loop(self):
    while self._running:
        winner = await self._action_queue.get()
        await self._act_on(winner)
        self._action_queue.task_done()
```
This decouples think latency from action latency and enables batching.

## Fix Required (Option A — immediate)

`core/loop/autonomous_loop.py` in `run_forever()`:

```python
# Remove act_loop from gather — it is a dead coroutine
await asyncio.gather(
    self.observe_loop(),
    self.think_loop(),
    # act_loop removed — actions dispatched inline from _think_tick
    self.reflect_loop(),
    self.sync_loop(),
    self.obsidian_loop(),
    self.phone_loop(),
    return_exceptions=True,
)
```

And delete the `act_loop` method entirely, or keep it empty and document
it as a placeholder for Option B.
