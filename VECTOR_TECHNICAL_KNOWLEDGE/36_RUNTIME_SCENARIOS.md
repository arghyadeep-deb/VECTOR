# Runtime Scenarios

**Purpose:** End-to-end execution traces
**Level:** System Level (Level 1)

---

## Overview

This document traces complete execution paths through VECTOR for common scenarios.

**Key Properties:**
- **Scenario-based** — real use cases
- **Full trace** — observe→think→act→reflect
- **Permission-gated** — all actions through gateway
- **Observable** — every step logged

---

## Scenario 1: User Query via Telegram

### Flow

```
1. User sends "What are my goals?" via Telegram
2. Telegram adapter receives message
3. Governor classifies intent → district: governance, task_type: query
4. Context engine assembles 14-domain world state
5. Decision engine generates candidates:
   - Candidate 1: query goal_system.get_active_goals()
   - Score: 0.85 (high goal_alignment, high confidence)
6. Policy check: get_score() → 0.9 (safe action)
7. Permission gateway: GREEN tier (read-only)
8. Execute: goal_system.get_active_goals()
9. Format response via LLM
10. Send via Telegram adapter
11. Policy update: update_from_outcome(0.8)
12. Episodic memory: store interaction
```

### Code Trace

```python
# 1. Telegram adapter
# vectorcode/src/channels/telegram.py
async def receive(self) -> List[Message]:
    updates = await self._api_call("getUpdates")
    return [Message(...) for update in updates]

# 2. Governor routing
# core/city/governor.py
async def route(self, query: str) -> dict:
    # Intent classification (4-stage)
    intent = await self._classify_intent(query)
    
    # Route to district
    district = self.DISTRICT_TASK_MAP[intent["district"]]
    task_type = intent["task_type"]
    
    return {"district": district, "task_type": task_type}

# 3. Context engine
# core/loop/context_engine.py
async def session_hydration_prompt(self, domain: str = None) -> str:
    context = await self.get_full_context()
    return f"Current state:\n{json.dumps(context, indent=2)}"

# 4. Decision engine
# core/loop/decision_engine.py
async def evaluate(self) -> dict:
    candidates = self._generate_candidates()
    
    for candidate in candidates:
        score = self._calculate_score(
            goal_alignment=0.8,
            confidence=0.9,
            policy_score=0.9,
            urgency=0.5,
            timing=0.5,
            cost=0.0
        )
        candidate["score"] = score
    
    best = max(candidates, key=lambda c: c["score"])
    return best

# 5. Permission gateway
# core/loop/permission_gateway.py
async def check_permission(self, action: dict) -> bool:
    tier = self._determine_tier(action)
    
    if tier == "GREEN":
        return True
    elif tier == "YELLOW":
        return await self._log_and_approve(action)
    elif tier == "RED":
        return await self._pushover_approval(action)
    else:  # FORBIDDEN
        return False

# 6. Execute
# core/brain/goal_system.py
def get_active_goals(self) -> list:
    self._prune_expired()
    return [g for g in self.goals if g["status"] == "active"]

# 7. Send response
# vectorcode/src/channels/telegram.py
async def send(self, message: str, recipient: str):
    await self._api_call("sendMessage", {
        "chat_id": recipient,
        "text": message
    })

# 8. Policy update
# core/memory/policy.py
def update_from_outcome(self, action: str, outcome: float):
    current = self.get_score(action)
    self.scores[action] = current * (1 - self.alpha) + outcome * self.alpha

# 9. Episodic memory
# core/memory/episodic.py
async def store(self, content: str, metadata: dict = None):
    self.conn.execute(
        "INSERT INTO episodic_memory (content, metadata, timestamp) VALUES (?, ?, ?)",
        (content, json.dumps(metadata), time.time())
    )
```

---

## Scenario 2: High-Stakes Decision (LLM Council)

### Flow

```
1. Decision engine identifies high-stakes decision (stakes="high")
2. Trigger LLM Council
3. Collect votes from council members (HP >700):
   - vector-reasoning
   - vector-r1
   - qwen3:30b-a3b
   - vector-chairman (chairman)
4. Each member analyzes independently
5. Chairman synthesizes discussion
6. Final vote
7. Execute decision
8. Store reasoning chain
```

### Code Trace

```python
# 1. Detect high stakes
# core/loop/decision_engine.py
async def evaluate(self) -> dict:
    best = self._select_best_candidate()
    
    if best["stakes"] == "high":
        # Trigger council
        council_result = await self._trigger_council(best)
        best["council_result"] = council_result
    
    return best

# 2. Trigger council
# districts/governance/llm_council.py
async def deliberate(self, decision: dict) -> dict:
    # Stage 1: Individual votes
    votes = []
    for member in self.members:  # HP >700 agents
        vote = await member.analyze(decision)
        votes.append(vote)
    
    # Stage 2: Discussion
    discussion = await self.chairman.synthesize(votes)
    
    # Stage 3: Final vote
    final = await self._vote(discussion)
    
    return {
        "decision": decision,
        "votes": votes,
        "discussion": discussion,
        "final": final
    }

# 3. Store reasoning chain
# core/memory/reasoning_memory.py
async def store_chain(self, chain: dict):
    self.conn.execute(
        "INSERT INTO reasoning_chains (chain, reward, timestamp) VALUES (?, ?, ?)",
        (json.dumps(chain), chain.get("reward", 0.0), time.time())
    )
```

---

## Scenario 3: RED Tier Action (Owner Approval)

### Flow

```
1. Decision engine selects action: git push
2. Permission gateway: RED tier (write operation)
3. Send Pushover notification to owner
4. Wait for approval (timeout 5min)
5. If approved: execute
6. If rejected: skip, log outcome
7. Policy update: update_from_outcome()
```

### Code Trace

```python
# 1. Detect RED tier
# core/loop/permission_gateway.py
async def check_permission(self, action: dict) -> bool:
    tier = self._determine_tier(action)
    
    if tier == "RED":
        return await self._pushover_approval(action)

# 2. Send Pushover
# core/notifications/pushover.py
async def send_approval_request(self, action: dict) -> bool:
    await send_notification(
        title="VECTOR Approval Required",
        message=f"Action: {action['description']}",
        priority=1
    )
    
    # Wait for response
    try:
        approved = await asyncio.wait_for(
            self._wait_for_response(),
            timeout=300  # 5 minutes
        )
        return approved
    except asyncio.TimeoutError:
        return False  # Timeout = reject

# 3. Execute or skip
# core/loop/autonomous_loop.py
async def act_loop(self):
    while True:
        action = await self.decision_engine.evaluate()
        
        approved = await self.permission_gateway.check_permission(action)
        
        if approved:
            await self._execute(action)
            outcome = 1.0
        else:
            outcome = 0.0
        
        # Policy update
        self.policy.update_from_outcome(action["id"], outcome)
```

---

## Scenario 4: Daily Reflection (2AM)

### Flow

```
1. Scheduler triggers at 2AM
2. Load today's episodic memories
3. Consolidate: episodic → semantic
4. Extract patterns
5. Update policies
6. Write Obsidian journal
7. Update goal progress
```

### Code Trace

```python
# 1. Scheduler trigger
# core/scheduler/scheduler.py
self.scheduler.add_job(
    self._daily_reflection,
    CronTrigger(hour=2, minute=0)
)

# 2. Reflection
# core/loop/autonomous_loop.py
async def reflect_loop(self):
    # Load today's memories
    memories = await self.episodic.get_today()
    
    # Consolidate
    await self.memory_curator.consolidate(memories)
    
    # Extract patterns
    patterns = await self.pattern_finder.find(memories)
    
    # Update policies
    for pattern in patterns:
        self.policy.update_from_outcome(pattern["action"], pattern["outcome"])
    
    # Write journal
    await self.journal_writer.write(memories, patterns)
    
    # Update goals
    await self.goal_system.update_progress()

# 3. Journal writing
# districts/reflection/journal_writer.py
async def write(self, memories: list, patterns: list):
    from core.config import CONFIG
    
    journal_path = Path(CONFIG.obsidian_path) / "Journals" / f"{date.today()}.md"
    
    content = f"""# {date.today()}

## Memories Today
{len(memories)} interactions

## Patterns
{json.dumps(patterns, indent=2)}

## Insights
{await self._generate_insights(memories, patterns)}
"""
    
    journal_path.write_text(content)
```

---

## Scenario 5: Agent Death and Rebirth

### Flow

```
1. Agent HP reaches 0 (critical error)
2. Agent dies
3. Store ghost memory (lessons learned)
4. Remove from registry
5. After 24h: spawn successor
6. Successor inherits ghost memory
7. Successor starts with HP 500
```

### Code Trace

```python
# 1. HP check
# core/city/agent_base.py
def adjust_hp(self, delta: int):
    self.hp = max(0, min(1000, self.hp + delta))
    
    if self.hp == 0:
        self.die()

# 2. Death
async def die(self):
    logger.warning(f"[VECTOR][agent] {self.name} died (HP=0)")
    
    # Store ghost memory
    await self._store_ghost_memory()
    
    # Remove from registry
    self.registry.remove(self.agent_id)

# 3. Ghost memory
async def _store_ghost_memory(self):
    ghost = {
        "agent_id": self.agent_id,
        "name": self.name,
        "lessons": self.learned_lessons,
        "death_timestamp": time.time()
    }
    
    await self.episodic.store(
        content=json.dumps(ghost),
        metadata={"type": "ghost_memory"}
    )

# 4. Successor (after 24h)
# core/city/evolution_engine.py
async def spawn_successor(self, ghost: dict):
    # Load ghost memory
    lessons = ghost["lessons"]
    
    # Create new agent
    successor = AgentBase(
        name=f"{ghost['name']}_v2",
        district=ghost["district"]
    )
    
    # Inherit lessons
    successor.learned_lessons = lessons
    
    # Start with HP 500
    successor.hp = 500
    
    # Register
    self.registry.add(successor)
```

---

## Performance Characteristics

| Scenario | Duration | Bottleneck |
|----------|----------|------------|
| User query | 2-10s | LLM calls |
| Council deliberation | 10-30s | Multi-agent voting |
| RED approval | 0-5min | Owner response |
| Daily reflection | 30-120s | Consolidation |
| Agent death | 100-500ms | DB writes |
| Agent rebirth | 1-5s | Initialization |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop details
- `08_DECISION_ENGINE.md` — Decision making
- `09_GOVERNOR_AND_PERMISSIONS.md` — Permissions

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
