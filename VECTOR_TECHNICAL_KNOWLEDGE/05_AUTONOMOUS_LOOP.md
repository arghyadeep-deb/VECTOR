# Autonomous Loop Architecture

**Purpose:** Core autonomous loop — the heartbeat of VECTOR  
**Level:** Subsystem Level (Level 2)

---

## Overview

The autonomous loop is the **heartbeat of VECTOR**. It never stops, never crashes, and runs 24/7 on local hardware. The loop implements the observe→think→act→reflect cycle that drives all autonomous behavior.

**Key Properties:**
- **Never stops** — all exceptions caught, graceful degradation
- **Never crashes** — every coroutine has exception handling
- **Observable** — extensive logging, metrics, monitoring
- **Recoverable** — restart recovery, checkpoint support
- **Permission-gated** — all actions go through PermissionGateway

**File:** `core/loop/autonomous_loop.py`  
**Lines:** ~1600  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Loop Architecture

### Four Coroutines

```python
async def run_forever(self):
    """Main entry point — never returns."""
    # Start all coroutines concurrently
    await asyncio.gather(
        self.observe_loop(),    # 0.5s cadence
        self.think_loop(),      # event-driven
        self.act_loop(),        # permission-gated
        self.reflect_loop()     # 2AM daily
    )
```

**Coroutine Purposes:**

| Coroutine | Cadence | Purpose | Status |
|-----------|---------|---------|--------|
| `observe_loop()` | 0.5s | Sense environment, detect changes | ✅ |
| `think_loop()` | Event-driven | Make decisions, generate candidates | ✅ |
| `act_loop()` | On-demand | Execute actions (permission-gated) | ✅ |
| `reflect_loop()` | 2AM daily | Review, consolidate, learn | ✅ |

---

## Observe Loop (0.5s Cadence)

### Function: `observe_loop()`

**File:** `core/loop/autonomous_loop.py:450-550`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Sense environment, detect changes, trigger events

**Process:**

```python
async def observe_loop(self):
    """Sense environment every 0.5s."""
    while True:
        try:
            async with asyncio.timeout(15):  # 15s timeout
                await self._observe_tick()
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            logger.warning("[VECTOR][observe] Tick timeout (>15s)")
            await asyncio.sleep(5)  # back off
        except Exception as e:
            logger.error(f"[VECTOR][observe] {e}")
            await asyncio.sleep(5)  # back off, then retry
            # NEVER propagate — loop must not die

async def _observe_tick(self):
    """Single observe tick."""
    # 1. Sense environment
    events = []
    
    # Device state
    device_state = await self._sense_device()
    events.append(device_state)
    
    # Screen content
    screen_content = await self._sense_screen()
    if screen_content.changed:
        events.append(screen_content)
    
    # Face detection
    face = await self._sense_face()
    if face.detected:
        events.append(face)
    
    # Sound classification
    sound = await self._sense_sound()
    if sound.classified:
        events.append(sound)
    
    # File system changes (Obsidian)
    file_changes = await self._sense_files()
    events.extend(file_changes)
    
    # Network events (API calls, webhooks)
    network_events = await self._sense_network()
    events.extend(network_events)
    
    # 2. Store events
    for event in events:
        await self.event_queue.put(event)
    
    # 3. Update world state
    await self.context_engine.update(events)
    
    # 4. Log metrics
    self.metrics.observe_ticks += 1
    self.metrics.last_observe_time = time.time()
```

**Sensing Methods:**

```python
async def _sense_device(self) -> DeviceState:
    """Sense device state (battery, CPU, GPU, memory)."""
    try:
        import psutil
        
        battery = psutil.sensors_battery()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        gpu = await self._get_gpu_info()
        
        return DeviceState(
            battery_percent=battery.percent if battery else None,
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            gpu_memory_used=gpu.memory_used,
            gpu_memory_total=gpu.memory_total,
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][observe] Device sense failed: {e}")
        return DeviceState.error()

async def _sense_screen(self) -> ScreenContent:
    """Sense screen content (OCR, changes)."""
    try:
        # Non-blocking (run in thread)
        screenshot = await asyncio.to_thread(self.screen_observer.observe)
        
        # Detect changes
        changed = self.screen_observer.has_changed(screenshot)
        
        # OCR (if enabled)
        text = None
        if self.config.ocr_enabled:
            text = await asyncio.to_thread(
                self.ocr_engine.extract_text,
                screenshot
            )
        
        return ScreenContent(
            screenshot=screenshot,
            changed=changed,
            text=text,
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][observe] Screen sense failed: {e}")
        return ScreenContent.error()

async def _sense_face(self) -> FaceDetection:
    """Sense face (detection, recognition)."""
    try:
        # Non-blocking (run in thread)
        result = await asyncio.to_thread(
            self.face_detector.capture_and_scan
        )
        
        return FaceDetection(
            detected=result.face_detected,
            name=result.recognized_name,
            confidence=result.confidence,
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][observe] Face sense failed: {e}")
        return FaceDetection.error()

async def _sense_sound(self) -> SoundClassification:
    """Sense sound (classification, volume)."""
    try:
        audio = self.sound_classifier.capture()
        classification = self.sound_classifier.classify(audio)
        
        return SoundClassification(
            classification=classification.label,
            confidence=classification.confidence,
            volume_rms=audio.rms,
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][observe] Sound sense failed: {e}")
        return SoundClassification.error()

async def _sense_files(self) -> List[FileChange]:
    """Sense file system changes (Obsidian vault)."""
    try:
        changes = self.file_watcher.get_changes()
        return changes
    except Exception as e:
        logger.error(f"[VECTOR][observe] File sense failed: {e}")
        return []

async def _sense_network(self) -> List[NetworkEvent]:
    """Sense network events (API calls, webhooks)."""
    try:
        events = self.network_monitor.get_events()
        return events
    except Exception as e:
        logger.error(f"[VECTOR][observe] Network sense failed: {e}")
        return []
```

**Dependencies:** `core/sensing/`, `psutil`, `asyncio`  
**Callers:** `run_forever()`  
**Production Status:** ✅ Production-reachable

---

## Think Loop (Event-Driven)

### Function: `think_loop()`

**File:** `core/loop/autonomous_loop.py:550-700`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Process events, make decisions, generate candidates

**Process:**

```python
async def think_loop(self):
    """Process events and make decisions."""
    while True:
        try:
            async with asyncio.timeout(60):  # 60s timeout
                await self._think_tick()
            await asyncio.sleep(0.1)  # Small delay
        except asyncio.TimeoutError:
            logger.warning("[VECTOR][think] Tick timeout (>60s)")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"[VECTOR][think] {e}")
            await asyncio.sleep(5)

async def _think_tick(self):
    """Single think tick."""
    # 1. Get events from queue
    if self.event_queue.empty():
        return
    
    events = []
    while not self.event_queue.empty():
        event = await self.event_queue.get()
        events.append(event)
    
    # 2. Get current context
    context = await self.context_engine.get_full_context()
    
    # 3. Get active goals
    goals = self.goal_system.get_active_goals()
    
    # 4. Generate candidates
    candidates = await self.decision_engine.generate_candidates(
        events=events,
        context=context,
        goals=goals
    )
    
    # 5. Score candidates
    scored_candidates = await self.decision_engine.evaluate(candidates)
    
    # 6. Select winner
    if scored_candidates:
        winner = max(scored_candidates, key=lambda c: c.total_score)
        
        # 7. Queue for action
        await self.action_queue.put(winner)
        
        # 8. Log decision
        logger.info(f"[VECTOR][think] Decision: {winner.action_type} "
                   f"(score={winner.total_score:.2f})")
        
        # 9. Store in reasoning memory
        await self.reasoning_memory.store_chain(
            events=events,
            candidates=scored_candidates,
            winner=winner,
            context=context
        )
    
    # 10. Log metrics
    self.metrics.think_ticks += 1
    self.metrics.candidates_generated += len(candidates)
```

**Decision Engine Integration:**

```python
# From core/loop/decision_engine.py
async def generate_candidates(
    self,
    events: List[Event],
    context: WorldState,
    goals: List[Goal]
) -> List[Candidate]:
    """Generate action candidates from events and goals."""
    candidates = []
    
    # 1. Goal-aligned candidates
    for goal in goals:
        candidate = await self._generate_from_goal(goal, context)
        if candidate:
            candidates.append(candidate)
    
    # 2. Event-driven candidates
    for event in events:
        candidate = await self._generate_from_event(event, context)
        if candidate:
            candidates.append(candidate)
    
    # 3. Opportunistic candidates (from ReasoningBank)
    bank_candidates = await self._generate_from_reasoning_bank(context)
    candidates.extend(bank_candidates)
    
    return candidates

async def evaluate(self, candidates: List[Candidate]) -> List[Candidate]:
    """Score candidates using 5-factor formula."""
    for candidate in candidates:
        # 1. Get policy score (BEFORE decision)
        policy_score = await self.policy_memory.get_score(candidate.action_type)
        
        # 2. Calculate factors
        goal_alignment = self._calculate_goal_alignment(candidate)
        confidence = self._calculate_confidence(candidate)
        urgency = self._calculate_urgency(candidate)
        timing = self._calculate_timing(candidate)
        cost = self._calculate_cost(candidate)
        
        # 3. Apply formula
        candidate.total_score = (
            goal_alignment * 0.30 +
            confidence * 0.25 +
            policy_score * 0.20 +
            urgency * 0.15 +
            timing * 0.10 -
            cost * 0.05
        )
        
        # 4. Store factor breakdown
        candidate.factors = {
            "goal_alignment": goal_alignment,
            "confidence": confidence,
            "policy": policy_score,
            "urgency": urgency,
            "timing": timing,
            "cost": cost
        }
    
    return candidates
```

**Dependencies:** `core/brain/goal_system.py`, `core/loop/decision_engine.py`, `core/memory/policy.py`  
**Callers:** `run_forever()`  
**Production Status:** ✅ Production-reachable

---

## Act Loop (Permission-Gated)

### Function: `act_loop()`

**File:** `core/loop/autonomous_loop.py:700-850`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Execute actions (permission-gated)

**Process:**

```python
async def act_loop(self):
    """Execute actions from queue."""
    while True:
        try:
            # Wait for action
            action = await self.action_queue.get()
            
            # Execute
            await self._execute_action(action)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"[VECTOR][act] {e}")
            await asyncio.sleep(5)

async def _execute_action(self, action: Candidate):
    """Execute single action with permission gate."""
    # 1. Check permission
    permission = await self.permission_gateway.check(action)
    
    if permission == PermissionLevel.FORBIDDEN:
        logger.warning(f"[VECTOR][act] Action forbidden: {action.action_type}")
        return
    
    if permission == PermissionLevel.RED:
        # Require owner approval
        approved = await self._request_owner_approval(action)
        if not approved:
            logger.info(f"[VECTOR][act] Action rejected by owner: {action.action_type}")
            return
    
    # 2. Execute action
    try:
        result = await self._dispatch_action(action)
        
        # 3. Update policy (AFTER action)
        await self.policy_memory.update_from_outcome(
            action_type=action.action_type,
            outcome=result.outcome
        )
        
        # 4. Store result
        await self.episodic_memory.store(
            event_type="action_executed",
            content={
                "action_type": action.action_type,
                "result": result.to_dict(),
                "permission": permission.value
            },
            tags=[action.district, action.action_type]
        )
        
        # 5. Update agent HP
        if action.agent_id:
            hp_change = self._calculate_hp_change(result)
            await self.agent_registry.update_hp(action.agent_id, hp_change)
        
        # 6. Log success
        logger.info(f"[VECTOR][act] Action executed: {action.action_type}")
        
        # 7. Notify owner (YELLOW/RED)
        if permission in (PermissionLevel.YELLOW, PermissionLevel.RED):
            await self._notify_owner(action, result)
        
    except Exception as e:
        logger.error(f"[VECTOR][act] Action failed: {e}")
        
        # Update policy with failure
        await self.policy_memory.update_from_outcome(
            action_type=action.action_type,
            outcome="failure"
        )

async def _dispatch_action(self, action: Candidate) -> ActionResult:
    """Dispatch action to appropriate handler."""
    # Route to district
    district = action.district
    
    if district == "coding":
        return await self._execute_coding_action(action)
    elif district == "research":
        return await self._execute_research_action(action)
    elif district == "communications":
        return await self._execute_communication_action(action)
    elif district == "finance":
        return await self._execute_finance_action(action)
    # ... (33+ districts)
    else:
        raise ValueError(f"Unknown district: {district}")

async def _execute_coding_action(self, action: Candidate) -> ActionResult:
    """Execute coding action."""
    # Route to agent
    agent = self.agent_registry.get(action.agent_id)
    
    # Execute
    result = await agent.execute(action)
    
    return ActionResult(
        success=result.success,
        output=result.output,
        outcome="success" if result.success else "failure"
    )
```

**Permission Gateway Integration:**

```python
# From core/loop/permission_gateway.py
async def check(self, action: Candidate) -> PermissionLevel:
    """Check permission for action."""
    # 1. Check forbidden list
    if action.action_type in self.forbidden_actions:
        return PermissionLevel.FORBIDDEN
    
    # 2. Determine tier
    tier = self._determine_tier(action)
    
    if tier == "GREEN":
        return PermissionLevel.GREEN
    elif tier == "YELLOW":
        return PermissionLevel.YELLOW
    elif tier == "RED":
        return PermissionLevel.RED
    else:
        return PermissionLevel.FORBIDDEN

def _determine_tier(self, action: Candidate) -> str:
    """Determine permission tier."""
    # GREEN: Low-risk, reversible
    if action.reversible and action.scope == "local":
        return "GREEN"
    
    # RED: High-risk, irreversible, external
    if not action.reversible or action.scope == "external":
        return "RED"
    
    # YELLOW: Medium-risk
    return "YELLOW"

async def _request_owner_approval(self, action: Candidate) -> bool:
    """Request owner approval via Pushover."""
    from pushover import Pushover
    
    push = Pushover(
        app_token=os.getenv("PUSHOVER_APP_TOKEN"),
        user_key=os.getenv("PUSHOVER_USER_KEY")
    )
    
    message = f"VECTOR needs approval for: {action.action_type}\n\n{action.description}"
    
    # Send notification
    push.send_message(message, title="VECTOR Approval Required")
    
    # Wait for response (timeout 5min)
    try:
        response = await asyncio.wait_for(
            self._wait_for_approval(),
            timeout=300
        )
        return response.approved
    except asyncio.TimeoutError:
        logger.warning("[VECTOR][permission] Approval timeout → REJECT")
        return False
```

**Dependencies:** `core/loop/permission_gateway.py`, `districts/*/`  
**Callers:** `run_forever()`  
**Production Status:** ✅ Production-reachable

---

## Reflect Loop (2AM Daily)

### Function: `reflect_loop()`

**File:** `core/loop/autonomous_loop.py:850-1000`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Daily reflection, memory consolidation, learning

**Process:**

```python
async def reflect_loop(self):
    """Daily reflection at 2AM."""
    while True:
        try:
            # Wait until 2AM
            now = datetime.now()
            next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now > next_2am:
                next_2am += timedelta(days=1)
            
            wait_seconds = (next_2am - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            # Run reflection
            await self._reflect()
            
            # Wait 1 hour before next check
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"[VECTOR][reflect] {e}")
            await asyncio.sleep(3600)

async def _reflect(self):
    """Single reflection cycle."""
    logger.info("[VECTOR][reflect] Starting daily reflection...")
    
    try:
        # 1. Review day's events
        events = await self.episodic_memory.retrieve(
            query="*",
            limit=1000,
            time_range=timedelta(days=1)
        )
        
        # 2. Consolidate memories
        await self.memory_consolidator.consolidate(events)
        
        # 3. Extract patterns
        patterns = await self.pattern_finder.find_patterns(events)
        
        # 4. Update policy
        await self.policy_memory.update_from_reflection(patterns)
        
        # 5. Write to Obsidian
        await self.obsidian_sync.write_reflection(events, patterns)
        
        # 6. Update goals
        await self.goal_system.update_progress(events)
        
        # 7. Prune expired goals
        self.goal_system._prune_expired()
        
        # 8. Log completion
        logger.info("[VECTOR][reflect] Reflection complete")
        
    except Exception as e:
        logger.error(f"[VECTOR][reflect] Reflection failed: {e}")
```

**Memory Consolidation:**

```python
# From core/memory/consolidation.py
async def consolidate(self, events: List[Event]):
    """Consolidate memories."""
    # 1. Group by type
    episodic_events = [e for e in events if e.type == "episodic"]
    semantic_events = [e for e in events if e.type == "semantic"]
    
    # 2. Consolidate episodic
    for event in episodic_events:
        await self.episodic_memory.consolidate(event)
    
    # 3. Extract semantic knowledge
    for event in semantic_events:
        knowledge = await self._extract_knowledge(event)
        await self.light_rag.store(knowledge)
    
    # 4. Update reasoning chains
    await self.reasoning_memory.consolidate(events)
    
    # 5. Write to Obsidian
    await self.obsidian_sync.sync_memories(events)
```

**Dependencies:** `core/memory/`, `districts/reflection/`  
**Callers:** `run_forever()`  
**Production Status:** ✅ Production-reachable

---

## Exception Handling Strategy

### Never Crash Principle

**File:** `core/loop/autonomous_loop.py`  
**Status:** ✅ IMPLEMENTED

**Strategy:** Every coroutine catches all exceptions, logs, and continues

```python
# Pattern used in all loops:
async def observe_loop(self):
    while True:
        try:
            async with asyncio.timeout(15):
                await self._observe_tick()
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            logger.warning("[VECTOR][observe] Tick timeout (>15s)")
            await asyncio.sleep(5)  # back off
        except Exception as e:
            logger.error(f"[VECTOR][observe] {e}")
            await asyncio.sleep(5)  # back off, then retry
            # NEVER propagate — loop must not die
```

**Timeout Protection:**

```python
# Observe loop: 15s timeout
async with asyncio.timeout(15):
    await self._observe_tick()

# Think loop: 60s timeout
async with asyncio.timeout(60):
    await self._think_tick()
```

**Non-Blocking Operations:**

```python
# Screen observation (potentially slow)
screenshot = await asyncio.to_thread(self.screen_observer.observe)

# Face detection (potentially slow)
result = await asyncio.to_thread(self.face_detector.capture_and_scan)
```

---

## Metrics and Observability

### Metrics Collection

**File:** `core/loop/autonomous_loop.py`  
**Status:** ✅ IMPLEMENTED

```python
class LoopMetrics:
    """Autonomous loop metrics."""
    
    def __init__(self):
        self.observe_ticks = 0
        self.think_ticks = 0
        self.act_ticks = 0
        self.reflect_ticks = 0
        
        self.candidates_generated = 0
        self.actions_executed = 0
        self.actions_failed = 0
        
        self.last_observe_time = 0
        self.last_think_time = 0
        self.last_act_time = 0
        self.last_reflect_time = 0
        
        self.start_time = time.time()
    
    def to_dict(self) -> dict:
        """Export metrics."""
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": uptime,
            "observe_ticks": self.observe_ticks,
            "think_ticks": self.think_ticks,
            "act_ticks": self.act_ticks,
            "reflect_ticks": self.reflect_ticks,
            "candidates_generated": self.candidates_generated,
            "actions_executed": self.actions_executed,
            "actions_failed": self.actions_failed,
            "observe_rate": self.observe_ticks / uptime if uptime > 0 else 0,
            "think_rate": self.think_ticks / uptime if uptime > 0 else 0,
            "act_rate": self.act_ticks / uptime if uptime > 0 else 0,
        }
```

**Exposure:**

```python
# API endpoint
@app.get("/status")
async def get_status():
    return {
        "loop": autonomous_loop.metrics.to_dict(),
        "agents": agent_registry.count(),
        "memory": episodic_memory.count()
    }
```

---

## Lifecycle Management

### Start/Stop

**File:** `core/loop/autonomous_loop.py`  
**Status:** ✅ IMPLEMENTED

```python
async def start(self):
    """Start autonomous loop."""
    logger.info("[VECTOR][loop] Starting autonomous loop...")
    
    # Initialize components
    await self._initialize()
    
    # Start coroutines
    self.running = True
    await self.run_forever()

async def stop(self):
    """Stop autonomous loop."""
    logger.info("[VECTOR][loop] Stopping autonomous loop...")
    
    self.running = False
    
    # Cancel tasks
    for task in self.tasks:
        task.cancel()
    
    # Wait for cleanup
    await asyncio.gather(*self.tasks, return_exceptions=True)
    
    logger.info("[VECTOR][loop] Autonomous loop stopped")

async def _initialize(self):
    """Initialize all components."""
    # Context engine
    await self.context_engine.initialize()
    
    # Goal system
    await self.goal_system.initialize()
    
    # Decision engine
    await self.decision_engine.initialize()
    
    # Memory systems
    await self.episodic_memory.initialize()
    await self.policy_memory.initialize()
    await self.reasoning_memory.initialize()
    
    # Agent registry
    await self.agent_registry.initialize()
    
    # Permission gateway
    await self.permission_gateway.initialize()
    
    logger.info("[VECTOR][loop] All components initialized")
```

---

## Performance Characteristics

| Metric | Value | Bottleneck |
|--------|-------|------------|
| Observe tick duration | 10-50ms | Screen OCR |
| Think tick duration | 100-500ms | LLM calls |
| Act tick duration | 1-10s | External APIs |
| Reflect duration | 30-120s | Memory consolidation |
| Memory usage | 2-4GB | Model loading |
| CPU usage | 5-20% | Observe loop |
| GPU usage | 0-50% | Model inference |

---

## Known Issues

### Issue 1: Observe Loop Blocking

**Symptom:** Observe tick takes >15s  
**Root Cause:** Synchronous screen OCR  
**Impact:** Delayed event detection  
**Workaround:** Non-blocking `asyncio.to_thread()` (implemented)  
**Priority:** FIXED

### Issue 2: Think Loop Timeout

**Symptom:** Think tick takes >60s  
**Root Cause:** Slow LLM provider  
**Impact:** Delayed decisions  
**Workaround:** Timeout + fallback to local model  
**Priority:** MEDIUM

### Issue 3: Action Queue Overflow

**Symptom:** Action queue grows unbounded  
**Root Cause:** Actions generated faster than executed  
**Impact:** Memory growth  
**Workaround:** Queue size limit (not yet implemented)  
**Priority:** LOW

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `04_RUNTIME_AND_BOOT.md` — Startup sequence
- `06_CONTEXT_ENGINE.md` — World state assembly
- `07_GOALS_AND_PLANNING.md` — Goal hierarchy
- `08_DECISION_ENGINE.md` — Decision making
- `09_GOVERNOR_AND_PERMISSIONS.md` — Permission gates
- `27_OBSERVABILITY.md` — Metrics and monitoring

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
