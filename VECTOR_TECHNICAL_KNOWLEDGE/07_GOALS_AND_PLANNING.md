# Goals and Planning System

**Purpose:** 3-horizon goal hierarchy, planning, progress tracking  
**Level:** Subsystem Level (Level 2)

---

## Overview

The Goal System implements VECTOR's 3-horizon goal hierarchy: LONG (90 days), MID (30 days), and SHORT (7 days). Goals drive all decision-making and action generation.

**Key Properties:**
- **3 horizons** — LONG/MID/SHORT term goals
- **Pre-seeded** — 5 initial goals from owner
- **Auto-expiry** — stale goals pruned automatically
- **Progress tracking** — automatic progress updates
- **Action generation** — goals drive candidate generation

**File:** `core/brain/goal_system.py`  
**Lines:** ~600  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Goal Hierarchy

### Three Horizons

```python
class GoalHorizon(Enum):
    LONG = "LONG"    # 90 days — strategic objectives
    MID = "MID"      # 30 days — tactical objectives
    SHORT = "SHORT"  # 7 days — immediate actions
```

**Horizon Details:**

| Horizon | Duration | Purpose | Example | Status |
|---------|----------|---------|---------|--------|
| LONG | 90 days | Strategic objectives | "Launch first SaaS product" | ✅ |
| MID | 30 days | Tactical objectives | "Complete VECTOR Phase 2" | ✅ |
| SHORT | 7 days | Immediate actions | "Fix intent classification" | ✅ |

---

## Goal Structure

### Goal Class

**File:** `core/brain/goal_system.py:50-150`  
**Status:** ✅ IMPLEMENTED

```python
@dataclass
class Goal:
    """Goal representation."""
    
    id: str
    description: str
    horizon: GoalHorizon
    progress: float  # 0.0 to 1.0
    status: str  # "active", "completed", "expired"
    
    # Metadata
    created_at: float
    updated_at: float
    due_date: Optional[float] = None
    
    # Progress tracking
    actions_taken: List[str] = field(default_factory=list)
    milestones: List[dict] = field(default_factory=list)
    
    # Parent/child relationships
    parent_goal_id: Optional[str] = None
    child_goal_ids: List[str] = field(default_factory=list)
    
    # Scoring
    priority: float = 0.5  # 0.0 to 1.0
    importance: float = 0.5  # 0.0 to 1.0
    
    def to_dict(self) -> dict:
        """Export goal."""
        return {
            "id": self.id,
            "description": self.description,
            "horizon": self.horizon.value,
            "progress": self.progress,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "due_date": self.due_date,
            "actions_taken": self.actions_taken,
            "milestones": self.milestones,
            "parent_goal_id": self.parent_goal_id,
            "child_goal_ids": self.child_goal_ids,
            "priority": self.priority,
            "importance": self.importance
        }
```

---

## Pre-Seeded Goals

### Initial Goals

**File:** `core/brain/goal_system.py:200-300`  
**Status:** ✅ IMPLEMENTED

**5 Initial Goals (from owner):**

```python
def _preseed_goals(self):
    """Pre-seed initial goals from owner."""
    
    # LONG: Launch first SaaS product (90 days)
    self.add_goal(
        description="Launch first SaaS product and achieve first ₹1L revenue",
        horizon=GoalHorizon.LONG,
        priority=0.9,
        importance=0.95,
        due_date=time.time() + (90 * 24 * 3600)
    )
    
    # MID: Complete VECTOR Phase 2 (30 days)
    self.add_goal(
        description="Complete VECTOR Phase 2: all districts built, 95% intent accuracy",
        horizon=GoalHorizon.MID,
        priority=0.8,
        importance=0.85,
        due_date=time.time() + (30 * 24 * 3600)
    )
    
    # MID: Build audience (30 days)
    self.add_goal(
        description="Build technical audience to 5K followers across platforms",
        horizon=GoalHorizon.MID,
        priority=0.7,
        importance=0.75,
        due_date=time.time() + (30 * 24 * 3600)
    )
    
    # SHORT: Fix intent classification (7 days)
    self.add_goal(
        description="Improve intent classification accuracy to 95%+",
        horizon=GoalHorizon.SHORT,
        priority=0.85,
        importance=0.8,
        due_date=time.time() + (7 * 24 * 3600)
    )
    
    # SHORT: Deploy Cloudflare API (7 days)
    self.add_goal(
        description="Deploy Cloudflare Worker API to production",
        horizon=GoalHorizon.SHORT,
        priority=0.75,
        importance=0.7,
        due_date=time.time() + (7 * 24 * 3600)
    )
```

---

## Goal Management

### Add Goal

**File:** `core/brain/goal_system.py:150-200`  
**Status:** ✅ IMPLEMENTED

```python
def add_goal(
    self,
    description: str,
    horizon: GoalHorizon,
    priority: float = 0.5,
    importance: float = 0.5,
    due_date: Optional[float] = None,
    parent_goal_id: Optional[str] = None
) -> Goal:
    """Add new goal."""
    
    # Generate ID
    goal_id = f"goal_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    # Create goal
    goal = Goal(
        id=goal_id,
        description=description,
        horizon=horizon,
        progress=0.0,
        status="active",
        created_at=time.time(),
        updated_at=time.time(),
        due_date=due_date,
        priority=priority,
        importance=importance,
        parent_goal_id=parent_goal_id
    )
    
    # Store
    self.goals[goal_id] = goal
    
    # Link to parent
    if parent_goal_id and parent_goal_id in self.goals:
        parent = self.goals[parent_goal_id]
        parent.child_goal_ids.append(goal_id)
    
    # Log
    logger.info(f"[VECTOR][goals] Added goal: {description[:50]}... (horizon={horizon.value})")
    
    # Store in episodic memory
    asyncio.create_task(self.episodic_memory.store(
        event_type="goal_added",
        content={
            "goal_id": goal_id,
            "description": description,
            "horizon": horizon.value,
            "priority": priority,
            "importance": importance
        },
        tags=["goal", horizon.value]
    ))
    
    return goal
```

### Update Progress

**File:** `core/brain/goal_system.py:300-400`  
**Status:** ✅ IMPLEMENTED

```python
def update_progress(self, goal_id: str, progress: float, action: str = None):
    """Update goal progress."""
    if goal_id not in self.goals:
        logger.warning(f"[VECTOR][goals] Goal not found: {goal_id}")
        return
    
    goal = self.goals[goal_id]
    
    # Update progress
    goal.progress = max(0.0, min(1.0, progress))
    goal.updated_at = time.time()
    
    # Track action
    if action:
        goal.actions_taken.append(action)
    
    # Check completion
    if goal.progress >= 1.0:
        goal.status = "completed"
        logger.info(f"[VECTOR][goals] Goal completed: {goal.description[:50]}...")
        
        # Store in episodic memory
        asyncio.create_task(self.episodic_memory.store(
            event_type="goal_completed",
            content={
                "goal_id": goal_id,
                "description": goal.description,
                "progress": goal.progress
            },
            tags=["goal", "completed"]
        ))
    
    # Update parent progress
    if goal.parent_goal_id:
        self._update_parent_progress(goal.parent_goal_id)

def _update_parent_progress(self, parent_id: str):
    """Update parent goal progress from children."""
    if parent_id not in self.goals:
        return
    
    parent = self.goals[parent_id]
    
    # Calculate average child progress
    child_progress = []
    for child_id in parent.child_goal_ids:
        if child_id in self.goals:
            child_progress.append(self.goals[child_id].progress)
    
    if child_progress:
        parent.progress = sum(child_progress) / len(child_progress)
        parent.updated_at = time.time()
```

### Prune Expired Goals

**File:** `core/brain/goal_system.py:400-450`  
**Status:** ✅ IMPLEMENTED

```python
def _prune_expired(self):
    """Prune expired or stale goals."""
    now = time.time()
    
    for goal_id, goal in list(self.goals.items()):
        # Check due date
        if goal.due_date and now > goal.due_date:
            goal.status = "expired"
            logger.info(f"[VECTOR][goals] Goal expired: {goal.description[:50]}...")
            continue
        
        # Check staleness (no progress for X days)
        days_since_update = (now - goal.updated_at) / (24 * 3600)
        
        if goal.horizon == GoalHorizon.SHORT and days_since_update > 7:
            goal.status = "expired"
            logger.info(f"[VECTOR][goals] SHORT goal stale: {goal.description[:50]}...")
        
        elif goal.horizon == GoalHorizon.MID and days_since_update > 30:
            goal.status = "expired"
            logger.info(f"[VECTOR][goals] MID goal stale: {goal.description[:50]}...")
        
        elif goal.horizon == GoalHorizon.LONG and days_since_update > 90:
            goal.status = "expired"
            logger.info(f"[VECTOR][goals] LONG goal stale: {goal.description[:50]}...")
```

---

## Goal Retrieval

### Get Active Goals

**File:** `core/brain/goal_system.py:200-250`  
**Status:** ✅ IMPLEMENTED

```python
def get_active_goals(self, horizon: Optional[GoalHorizon] = None) -> List[Goal]:
    """Get active goals, optionally filtered by horizon."""
    # Prune expired first
    self._prune_expired()
    
    # Filter
    active = [g for g in self.goals.values() if g.status == "active"]
    
    if horizon:
        active = [g for g in active if g.horizon == horizon]
    
    # Sort by priority * importance
    active.sort(key=lambda g: g.priority * g.importance, reverse=True)
    
    return active

def get_goals(self, horizon: Optional[GoalHorizon] = None) -> List[Goal]:
    """Get all goals, optionally filtered by horizon."""
    goals = list(self.goals.values())
    
    if horizon:
        goals = [g for g in goals if g.horizon == horizon]
    
    return goals

def get_goal(self, goal_id: str) -> Optional[Goal]:
    """Get single goal by ID."""
    return self.goals.get(goal_id)
```

---

## Action Generation from Goals

### Generate Candidates

**File:** `core/loop/decision_engine.py:200-300`  
**Status:** ✅ IMPLEMENTED

```python
async def _generate_from_goal(self, goal: Goal, context: WorldState) -> Optional[Candidate]:
    """Generate action candidate from goal."""
    
    # Use LLM to generate action
    from core.inference.provider_client import chat
    
    prompt = f"""Given this goal:
{goal.description}

Current progress: {goal.progress:.0%}
Actions taken so far: {', '.join(goal.actions_taken[-5:]) if goal.actions_taken else 'None'}

Current context:
- Time: {context.environment.time_of_day}
- Active agents: {context.agents.active_agents}
- Device: {context.device.gpu_name} GPU, {context.device.memory_available_gb:.1f}GB RAM available

What is the SINGLE BEST next action to make progress on this goal?
Return JSON: {{"action_type": "...", "district": "...", "description": "..."}}
"""
    
    # Inject context (RULE 1)
    hydration = await context_engine.session_hydration_prompt()
    messages = [
        {"role": "system", "content": hydration},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat(messages, model="vector-focus")
    
    # Parse response
    try:
        action_data = json.loads(response.content)
        
        return Candidate(
            action_type=action_data["action_type"],
            district=action_data["district"],
            description=action_data["description"],
            source_goal_id=goal.id,
            generated_at=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][decision] Failed to parse goal action: {e}")
        return None
```

---

## Progress Summary

### Get Progress Summary

**File:** `core/brain/goal_system.py:450-500`  
**Status:** ✅ IMPLEMENTED

```python
def get_progress_summary(self) -> dict:
    """Get progress summary across all horizons."""
    
    # Prune expired
    self._prune_expired()
    
    # Count by status
    active = len([g for g in self.goals.values() if g.status == "active"])
    completed = len([g for g in self.goals.values() if g.status == "completed"])
    expired = len([g for g in self.goals.values() if g.status == "expired"])
    
    # Average progress by horizon
    long_active = [g for g in self.goals.values() 
                   if g.horizon == GoalHorizon.LONG and g.status == "active"]
    mid_active = [g for g in self.goals.values() 
                  if g.horizon == GoalHorizon.MID and g.status == "active"]
    short_active = [g for g in self.goals.values() 
                    if g.horizon == GoalHorizon.SHORT and g.status == "active"]
    
    long_progress = sum(g.progress for g in long_active) / len(long_active) if long_active else 0
    mid_progress = sum(g.progress for g in mid_active) / len(mid_active) if mid_active else 0
    short_progress = sum(g.progress for g in short_active) / len(short_active) if short_active else 0
    
    return {
        "total_goals": len(self.goals),
        "active_goals": active,
        "completed_goals": completed,
        "expired_goals": expired,
        "long_term_progress": long_progress,
        "mid_term_progress": mid_progress,
        "short_term_progress": short_progress,
        "overall_progress": (long_progress + mid_progress + short_progress) / 3
    }
```

---

## Integration with Decision Engine

### Goal Alignment Scoring

**File:** `core/loop/decision_engine.py:150-200`  
**Status:** ✅ IMPLEMENTED

```python
def _calculate_goal_alignment(self, candidate: Candidate) -> float:
    """Calculate how well candidate aligns with active goals."""
    
    if not candidate.source_goal_id:
        # No source goal — check if action matches any goal
        return self._estimate_goal_match(candidate)
    
    # Has source goal — use its progress
    goal = self.goal_system.get_goal(candidate.source_goal_id)
    if not goal:
        return 0.0
    
    # Higher alignment if goal is stalled (low progress)
    # This prioritizes making progress on stuck goals
    urgency_factor = 1.0 - goal.progress
    
    # Weight by goal priority
    alignment = goal.priority * goal.importance * urgency_factor
    
    return alignment

def _estimate_goal_match(self, candidate: Candidate) -> float:
    """Estimate goal match for candidate without source goal."""
    
    # Check if action description matches any goal
    active_goals = self.goal_system.get_active_goals()
    
    best_match = 0.0
    for goal in active_goals:
        # Simple keyword match
        goal_words = set(goal.description.lower().split())
        action_words = set(candidate.description.lower().split())
        
        overlap = len(goal_words & action_words) / max(len(goal_words), 1)
        match_score = overlap * goal.priority * goal.importance
        
        best_match = max(best_match, match_score)
    
    return best_match
```

---

## Persistence

### Save/Load Goals

**File:** `core/brain/goal_system.py:500-600`  
**Status:** ✅ IMPLEMENTED

```python
def save(self, path: str = "data/goals.json"):
    """Save goals to disk."""
    data = {
        "goals": {
            goal_id: goal.to_dict()
            for goal_id, goal in self.goals.items()
        },
        "saved_at": time.time()
    }
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"[VECTOR][goals] Saved {len(self.goals)} goals to {path}")

def load(self, path: str = "data/goals.json"):
    """Load goals from disk."""
    if not os.path.exists(path):
        logger.warning(f"[VECTOR][goals] No saved goals at {path}")
        self._preseed_goals()
        return
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    # Reconstruct goals
    for goal_id, goal_data in data["goals"].items():
        goal = Goal(
            id=goal_data["id"],
            description=goal_data["description"],
            horizon=GoalHorizon(goal_data["horizon"]),
            progress=goal_data["progress"],
            status=goal_data["status"],
            created_at=goal_data["created_at"],
            updated_at=goal_data["updated_at"],
            due_date=goal_data.get("due_date"),
            actions_taken=goal_data.get("actions_taken", []),
            milestones=goal_data.get("milestones", []),
            parent_goal_id=goal_data.get("parent_goal_id"),
            child_goal_ids=goal_data.get("child_goal_ids", []),
            priority=goal_data.get("priority", 0.5),
            importance=goal_data.get("importance", 0.5)
        )
        self.goals[goal_id] = goal
    
    logger.info(f"[VECTOR][goals] Loaded {len(self.goals)} goals from {path}")
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Add goal | <1ms | Memory allocation |
| Update progress | <1ms | Memory update |
| Get active goals | 1-5ms | Filtering, sorting |
| Prune expired | 1-10ms | Date comparisons |
| Save/Load | 5-20ms | Disk I/O |

---

## Known Issues

### Issue 1: Goal Expiry Too Aggressive

**Symptom:** Goals expire before completion  
**Root Cause:** Staleness check too strict  
**Impact:** Lost progress  
**Workaround:** Increase staleness thresholds  
**Priority:** LOW

### Issue 2: No Goal Prioritization UI

**Symptom:** Hard to see which goals are most important  
**Root Cause:** No dashboard  
**Impact:** Manual tracking needed  
**Workaround:** Use API endpoint  
**Priority:** LOW

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `06_CONTEXT_ENGINE.md` — World state
- `08_DECISION_ENGINE.md` — Decision making
- `05_AUTONOMOUS_LOOP.md` — Loop architecture

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
