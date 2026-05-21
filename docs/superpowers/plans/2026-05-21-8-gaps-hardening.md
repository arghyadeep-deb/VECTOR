# 8 Gaps Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seal 8 identified gaps in the VECTOR autonomous loop: activate dead loops, fix unguarded imports, fix event wiring, remove phantom references, secure OFP secret, merge entry points, fix sync HTTP calls, complete work-stealing.

**Architecture:** Each gap is an independent, surgical patch (5–60 lines). Execute in order 1→8. Each patch is verified with the existing smoke test before moving to the next.

**Tech Stack:** Python 3.12+, asyncio, httpx, FastAPI, loguru

---

### Task 1: Activate 4 dead autonomous loops

**Files:**
- Modify: `core/loop/autonomous_loop.py:1224-1238`

- [ ] **Step 1: Add 4 missing coroutines to run_forever() gather**

Change lines 1224-1238 from:
```python
        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.reflect_loop(),
            self.sync_loop(),
            self.obsidian_loop(),
            self.phone_loop(),
            self.vectorcode_loop(),
            self.scheduler_loop(),
            self.ambient_scheduler_loop(),
            self.hypothesis_loop(),
            self.predict_cycle(),
            self.degradation_monitor(),
            return_exceptions=True,
        )
```
to:
```python
        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.reflect_loop(),
            self.sync_loop(),
            self.obsidian_loop(),
            self.phone_loop(),
            self.vectorcode_loop(),
            self.scheduler_loop(),
            self.ambient_scheduler_loop(),
            self.hypothesis_loop(),
            self.predict_cycle(),
            self.degradation_monitor(),
            self.wearable_poll_cycle(),
            self.health_analysis_cycle(),
            self.emergency_detection_cycle(),
            self.research_loop(),
            return_exceptions=True,
        )
```

- [ ] **Step 2: Verify with smoke test**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Commit**

```bash
git add core/loop/autonomous_loop.py
git commit -m "fix: activate 4 dead autonomous loops in run_forever gather"
```

---

### Task 2: Fix unguarded top-level imports in core/sandbox/runner.py

**Files:**
- Modify: `core/sandbox/runner.py:22-25`

- [ ] **Step 1: Wrap unguarded vectorcode imports with try/except**

Change lines 22-25 from:
```python
from vectorcode.src.vc_districts._stubs import AgentContext, AgentResult, BaseAgent
from vectorcode.src.vc_core.events import EventBus
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_engine._stubs import InferenceEngine
```
to:
```python
try:
    from vectorcode.src.vc_districts._stubs import AgentContext, AgentResult, BaseAgent
except ImportError:
    AgentContext = AgentResult = BaseAgent = None
try:
    from vectorcode.src.vc_core.events import EventBus
except ImportError:
    EventBus = None
try:
    from vectorcode.src.vc_core.types import ToolResult
except ImportError:
    ToolResult = None
try:
    from vectorcode.src.vc_engine._stubs import InferenceEngine
except ImportError:
    InferenceEngine = None
```

- [ ] **Step 2: Verify module loads without crash**

Run: `python -c "from core.sandbox.runner import ContainerRunner, SandboxedAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run smoke test**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 4: Commit**

```bash
git add core/sandbox/runner.py
git commit -m "fix: guard top-level vectorcode imports in core/sandbox/runner.py"
```

---

### Task 3: Fix auto_subscribe_all() to use singleton registry

**Files:**
- Modify: `core/event_bus/wiring.py:179-190`

- [ ] **Step 1: Replace AgentRegistry() with get_registry()**

Change lines 179-190 from:
```python
def auto_subscribe_all() -> int:
    from core.city.agent_registry import AgentRegistry
    registry = AgentRegistry()
    count = 0
    for agent in registry.get_all_agents():
        events = get_subscriptions_for(agent.district)
        for et in events:
            agent.subscribe_to(et.value)
            count += 1
    if count:
        logger.info("[VECTOR][event_wiring] auto-subscribed {} agent-event pairs", count)
    return count
```
to:
```python
def auto_subscribe_all() -> int:
    from core.city.agent_registry import get_registry
    registry = get_registry()
    count = 0
    for agent in registry.get_all_agents():
        events = get_subscriptions_for(agent.district)
        for et in events:
            agent.subscribe_to(et.value)
            count += 1
    if count:
        logger.info("[VECTOR][event_wiring] auto-subscribed {} agent-event pairs", count)
    return count
```

- [ ] **Step 2: Run smoke test to verify no regression**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Commit**

```bash
git add core/event_bus/wiring.py
git commit -m "fix: auto_subscribe_all uses singleton registry instead of empty instance"
```

---

### Task 4: Remove phantom vc_districts references

**Files:**
- Modify: `core/loop/cron_jobs.py:168-183`
- Modify: `core/sandbox/runner.py:22` (already guarded in Task 2, now remove the import)

- [ ] **Step 1: Replace vc_districts import in cron_jobs.py with graceful fallback**

The function `_run_morning_digest_fn` at line 168 imports `MorningDigestAgent` from the phantom `vc_districts` module. Replace the entire function with a no-op fallback since the module doesn't exist:

Replace lines 168-183:
```python
async def _run_morning_digest_fn(**kwargs: Any) -> dict:
    """Run the MorningDigestAgent and return a digest dict."""
    try:
        from vectorcode.src.vc_districts.morning_digest import MorningDigestAgent
        agent = MorningDigestAgent()
        if hasattr(agent, "run"):
            result = agent.run()
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return result
            return {"status": "ok", "output": str(result)[:500]}
        return {"status": "skipped", "reason": "MorningDigestAgent has no run()"}
    except Exception as e:
        logger.warning(f"[VECTOR][cron] morning_digest failed: {e}")
        return {"status": "failed", "reason": str(e)}
```
to:
```python
async def _run_morning_digest_fn(**kwargs: Any) -> dict:
    """Morning digest — unavailable (vc_districts module does not exist)."""
    return {"status": "skipped", "reason": "vc_districts module not available"}
```

- [ ] **Step 2: Remove phantom vc_districts import from sandbox/runner.py**

The import was already guarded in Task 2, but now remove it entirely since the module doesn't exist. Replace the guarded block:
```python
try:
    from vectorcode.src.vc_districts._stubs import AgentContext, AgentResult, BaseAgent
except ImportError:
    AgentContext = AgentResult = BaseAgent = None
```
with just the fallback:
```python
AgentContext = AgentResult = BaseAgent = None
```

Then shift lines 31+ to remove the try/except block, keeping all subsequent imports unchanged.

- [ ] **Step 3: Run smoke test**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 4: Commit**

```bash
git add core/loop/cron_jobs.py core/sandbox/runner.py
git commit -m "fix: remove phantom vc_districts module references"
```

---

### Task 5: Add startup warning for default OFP secret

**Files:**
- Modify: `core/network/ofp_protocol.py:198-199`

- [ ] **Step 1: Add warning when using default secret**

Change lines 198-199 from:
```python
self._secret = secret or os.getenv("VECTOR_OFP_SECRET", "vector-default-secret").encode()
```
to:
```python
_secret_env = os.getenv("VECTOR_OFP_SECRET")
if secret:
    self._secret = secret
elif _secret_env:
    self._secret = _secret_env.encode()
else:
    logger.warning(
        "[VECTOR][ofp] Using DEFAULT shared secret — "
        "set VECTOR_OFP_SECRET env var for production"
    )
    self._secret = b"vector-default-secret"
```

Import `logger` is already imported at line 42.

- [ ] **Step 2: Verify module loads and warning fires**

Run: `python -c "from core.network.ofp_protocol import OFPNode; n = OFPNode(port=17790); print('OK:', n.node_id)"`
Expected: Warning about default secret, then `OK: vector-...`

- [ ] **Step 3: Commit**

```bash
git add core/network/ofp_protocol.py
git commit -m "fix: add startup warning for default OFP secret"
```

---

### Task 6: Merge dual entry points — make run_vector delegate to core/api/app.py

**Files:**
- Modify: `run_vector.py:838-845`, `run_vector.py:848-863`, `run_vector.py:970-995`
- No change: `core/api/app.py`

- [ ] **Step 1: Refactor run_vector.py's run_api() to delegate through core.api.create_app()**

The existing `run_api()` at line 848 already calls `create_app()`. The issue is that `run_vector.py` and `core/api/app.py` have independent bootstrap logic. The fix is to make `run_loop()` in `run_vector.py` also call `bootstrap_agents()` which is already handled there, and add the `auto_subscribe_all()` wiring.

Add `auto_subscribe_all()` call to `bootstrap_agents()` in `run_vector.py` (it's already there at line 572-577):

```python
    # ── Agent-to-Agent event wiring — auto-subscribe by district name ─────
    try:
        from core.event_bus.wiring import auto_subscribe_all as _wire_events
        _wire_events()
    except Exception as e:
        logger.warning(f"[bootstrap] event wiring skipped: {e}")
```

This code is already present at line 572-577. The real merge is to ensure `run_api()` also calls `bootstrap_agents()`. Looking at `core/api/app.py` lifespan (line 30), it already calls `bootstrap_agents()`.

The actual gap is: when running in API mode via `run_vector.py`, the `bootstrap_agents()` is called inside `run_api()` → `create_app()` → lifespan. When running in loop mode, `bootstrap_agents()` is called in `run_loop()`. So the entry points are already dual.

The minimal fix is to unify by making `run_vector.py` the single entry point that always calls `bootstrap_agents()` upfront, and then decides whether to start loop or API. This avoids the situation where `core/api/app.py` would try to bootstrap agents if imported independently.

Actually, the simplest merge: **Make `run_vector.py` always bootstrap agents before mode dispatch, and have `core/api/app.py`'s lifespan NOT bootstrap (since run_vector already did).**

Change the `main()` function to bootstrap agents before dispatching:

Replace lines 970-995:
```python
def main() -> int:
    args = parse_args()
    logger.info(f"[VECTOR][launcher] mode={args.mode}")

    if args.ha:
        ha_startup()

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result["status"] == "ok" else 1

    try:
        asyncio.run(run_loop())
        return 0
    except KeyboardInterrupt:
        logger.info("[VECTOR][launcher] stopped by owner")
        return 0
```
to:
```python
def main() -> int:
    args = parse_args()
    logger.info(f"[VECTOR][launcher] mode={args.mode}")

    # Always bootstrap agents upfront, before mode dispatch
    bootstrap_agents()

    if args.ha:
        ha_startup()

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result["status"] == "ok" else 1

    try:
        asyncio.run(run_loop())
        return 0
    except KeyboardInterrupt:
        logger.info("[VECTOR][launcher] stopped by owner")
        return 0
```

Also remove the `bootstrap_agents()` call from `run_loop()` (line 841) since it's now called in `main()`:

```python
async def run_loop() -> None:
    """Start the autonomous loop. This is intended to run until interrupted."""
    preflight_checks()
    # bootstrap_agents() is now called in main() before dispatch
    await _start_background_services()
    from core.loop.autonomous_loop import AutonomousLoop

    await AutonomousLoop().run_forever()
```

- [ ] **Step 2: Run smoke test to verify**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Commit**

```bash
git add run_vector.py
git commit -m "fix: unify entry points — bootstrap agents once in main()"
```

---

### Task 7: Fix sync httpx.Client() calls in browser MCP tools

**Files:**
- Modify: `core/mcp_server.py:2217-2419`

- [ ] **Step 1: Replace sync httpx.Client with async httpx.AsyncClient in browser MCP stubs**

The browser tools (test_browser_navigate, test_browser_click, etc.) use `with _httpx.Client(timeout=10) as client:` which blocks the asyncio event loop. Replace each with `async with _httpx.AsyncClient(timeout=10) as client:`.

There are 15+ occurrences. The pattern is:
```python
with _httpx.Client(timeout=10) as client:
    response = client.get(url)
```
Replace with:
```python
async with _httpx.AsyncClient(timeout=10) as client:
    response = await client.get(url)
```

Locations (all in core/mcp_server.py):
- Line 2217: `test_browser_navigate` — `_httpx.Client` → `_httpx.AsyncClient`
- Line 2230: `test_browser_click` — same pattern
- Line 2248: `test_browser_type` — same
- Line 2261: `test_browser_screenshot` — same
- Line 2274: `test_browser_evaluate` — same
- Line 2287: `test_browser_get_info` — same
- Line 2305: `test_browser_obsidian_write` — same
- Line 2318: `test_browser_obsidian_query` — same
- Line 2331: `test_browser_scroll` — same
- Line 2344: `test_browser_back` — same
- Line 2357: `test_browser_forward` — same
- Line 2370: `test_browser_refresh` — same
- Line 2388: `test_browser_set_viewport` — same
- Line 2401: `test_browser_get_html` — same
- Line 2419: `test_browser_inject_css` — same

Also, the function signatures must be changed from `def` to `async def`, and the `_safe_json` calls need to be awaited.

- [ ] **Step 2: Verify with smoke test**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Commit**

```bash
git add core/mcp_server.py
git commit -m "fix: replace sync httpx.Client with async AsyncClient in browser MCP tools"
```

---

### Task 8: Complete work-stealing loop — call steal() after register_claimant()

**Files:**
- Modify: `core/loop/autonomous_loop.py:301-326`

- [ ] **Step 1: Add steal() call after registering claimants**

In the work-stealing block (lines 301-326), after registering claimants, add a call to actually steal tasks.

Replace lines 301-326:
```python
            # Phase 3E: Claims work-stealing — distribute tasks when queue > 5
            try:
                from core.loop.task_queue import TaskQueue
                tq = TaskQueue.get()
                summary = tq.summary() if hasattr(tq, 'summary') else {}
                queued = summary.get("queued", 0) if isinstance(summary, dict) else 0
                if queued > 5:
                    from vectorcode.src.claims import ClaimService
                    from core.city.agent_registry import get_registry
                    cs = ClaimService()
                    reg = get_registry()
                    alive = reg.list_alive()
                    if alive:
                        # Register alive agents as claimants
                        for agent in alive[:10]:
                            try:
                                cs.register_claimant(
                                    agent_id=agent.id,
                                    agent_type=agent.district,
                                    capacity=1,
                                )
                            except Exception:
                                logger.debug("[VECTOR] suppressed exception", exc_info=True)
                        logger.info(f"[VECTOR][claims] {queued} pending tasks → distributing to {len(alive)} agents")
            except Exception as _cl_err:
                logger.debug(f"[VECTOR][scheduler_loop] claims work-stealing skipped: {_cl_err}")
```
to:
```python
            # Phase 3E: Claims work-stealing — distribute tasks when queue > 5
            try:
                from core.loop.task_queue import TaskQueue
                tq = TaskQueue.get()
                summary = tq.summary() if hasattr(tq, 'summary') else {}
                queued = summary.get("queued", 0) if isinstance(summary, dict) else 0
                if queued > 5:
                    from vectorcode.src.claims import ClaimService
                    from core.city.agent_registry import get_registry
                    cs = ClaimService()
                    reg = get_registry()
                    alive = reg.list_alive()
                    if alive:
                        # Register alive agents as claimants
                        for agent in alive[:10]:
                            try:
                                cs.register_claimant(
                                    agent_id=agent.id,
                                    agent_type=agent.district,
                                    capacity=1,
                                )
                            except Exception:
                                logger.debug("[VECTOR] suppressed exception", exc_info=True)
                        # Actually steal pending tasks and assign them
                        stolen = cs.steal_work(max_tasks=queued)
                        if stolen:
                            for task in stolen:
                                try:
                                    tq.assign(task)
                                except Exception:
                                    logger.debug("[VECTOR] suppressed exception", exc_info=True)
                            logger.info(f"[VECTOR][claims] stole {len(stolen)} tasks → assigned to agents")
                        else:
                            logger.info(f"[VECTOR][claims] {queued} pending tasks, registering {len(alive)} claimants (no tasks stolen yet)")
            except Exception as _cl_err:
                logger.debug(f"[VECTOR][scheduler_loop] claims work-stealing skipped: {_cl_err}")
```

- [ ] **Step 2: Run smoke test to verify no regression**

Run: `python run_vector.py smoke`
Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Commit**

```bash
git add core/loop/autonomous_loop.py
git commit -m "fix: complete work-stealing loop with steal() call after register_claimant"
```
