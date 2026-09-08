# Decision Engine — Candidate Generation and Scoring

**Purpose:** 5-factor candidate scoring, action selection  
**Level:** Subsystem Level (Level 2)

---

## Overview

The Decision Engine generates action candidates from goals and events, scores them using a 5-factor formula, and selects the best action for execution.

**Key Properties:**
- **5-factor scoring** — goal alignment, confidence, policy, urgency, timing, cost
- **Candidate generation** — from goals, events, and reasoning bank
- **Policy integration** — `get_score()` BEFORE, `update_from_outcome()` AFTER
- **ReasoningBank** — RULE 8 compliance, stores all decision chains
- **Observable** — all decisions logged and stored

**File:** `core/loop/decision_engine.py`  
**Lines:** ~700  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## 5-Factor Scoring Formula

### Scoring Formula

**File:** `core/loop/decision_engine.py:100-150`  
**Status:** ✅ IMPLEMENTED

```python
total_score = (
    goal_alignment * 0.30 +    # How well action aligns with active goals
    confidence * 0.25 +         # Confidence in success
    policy_score * 0.20 +       # Historical success rate (RULE 7)
    urgency * 0.15 +            # Time sensitivity
    timing * 0.10 -             # Current timing appropriateness
    cost * 0.05                 # Resource cost (negative factor)
)
```

**Factor Weights:**

| Factor | Weight | Purpose | Status |
|--------|--------|---------|--------|
| goal_alignment | 30% | Align with strategic objectives | ✅ |
| confidence | 25% | Likelihood of success | ✅ |
| policy_score | 20% | Historical performance (RULE 7) | ✅ |
| urgency | 15% | Time sensitivity | ✅ |
| timing | 10% | Current timing | ✅ |
| cost | -5% | Resource expenditure | ✅ |

---

## Candidate Structure

### Candidate Class

**File:** `core/loop/decision_engine.py:50-100`  
**Status:** ✅ IMPLEMENTED

```python
@dataclass
class Candidate:
    """Action candidate."""
    
    action_type: str
    district: str
    description: str
    
    # Source
    source_goal_id: Optional[str] = None
    source_event_id: Optional[str] = None
    
    # Scoring
    total_score: float = 0.0
    factors: dict = field(default_factory=dict)
    
    # Metadata
    generated_at: float = field(default_factory=time.time)
    agent_id: Optional[str] = None
    
    # Execution
    reversible: bool = True
    scope: str = "local"  # "local", "external"
    
    def to_dict(self) -> dict:
        """Export candidate."""
        return {
            "action_type": self.action_type,
            "district": self.district,
            "description": self.description,
            "source_goal_id": self.source_goal_id,
            "source_event_id": self.source_event_id,
            "total_score": self.total_score,
            "factors": self.factors,
            "generated_at": self.generated_at,
            "agent_id": self.agent_id,
            "reversible": self.reversible,
            "scope": self.scope
        }
```

---

## Candidate Generation

### Generate Candidates

**File:** `core/loop/decision_engine.py:200-350`  
**Status:** ✅ IMPLEMENTED

```python
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
    
    logger.info(f"[VECTOR][decision] Generated {len(candidates)} candidates")
    
    return candidates

async def _generate_from_goal(self, goal: Goal, context: WorldState) -> Optional[Candidate]:
    """Generate action candidate from goal."""
    
    # Use LLM to generate action
    from core.inference.provider_client import chat
    
    # Inject context (RULE 1)
    hydration = await context_engine.session_hydration_prompt()
    
    prompt = f"""Given this goal:
{goal.description}

Current progress: {goal.progress:.0%}
Actions taken so far: {', '.join(goal.actions_taken[-5:]) if goal.actions_taken else 'None'}

What is the SINGLE BEST next action to make progress on this goal?
Return JSON: {{"action_type": "...", "district": "...", "description": "..."}}
"""
    
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

async def _generate_from_event(self, event: Event, context: WorldState) -> Optional[Candidate]:
    """Generate action candidate from event."""
    
    # Check if event requires action
    if event.type not in ["alert", "request", "anomaly"]:
        return None
    
    # Use LLM to generate action
    from core.inference.provider_client import chat
    
    hydration = await context_engine.session_hydration_prompt()
    
    prompt = f"""Event detected:
Type: {event.type}
Content: {event.content}

What action should VECTOR take in response?
Return JSON: {{"action_type": "...", "district": "...", "description": "..."}}
"""
    
    messages = [
        {"role": "system", "content": hydration},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat(messages, model="vector-focus")
    
    try:
        action_data = json.loads(response.content)
        
        return Candidate(
            action_type=action_data["action_type"],
            district=action_data["district"],
            description=action_data["description"],
            source_event_id=event.id,
            generated_at=time.time()
        )
    except Exception as e:
        logger.error(f"[VECTOR][decision] Failed to parse event action: {e}")
        return None

async def _generate_from_reasoning_bank(self, context: WorldState) -> List[Candidate]:
    """Generate candidates from ReasoningBank (RULE 8)."""
    candidates = []
    
    try:
        # Get similar past decisions
        similar = await self.reasoning_bank.get_similar(
            context=context,
            limit=5
        )
        
        for past_decision in similar:
            if past_decision.reward > 0.7:  # Only high-reward decisions
                candidate = Candidate(
                    action_type=past_decision.action_type,
                    district=past_decision.district,
                    description=f"Repeat successful action: {past_decision.description}",
                    generated_at=time.time()
                )
                candidates.append(candidate)
        
    except Exception as e:
        logger.warning(f"[VECTOR][decision] ReasoningBank failed: {e}")
    
    return candidates
```

---

## Candidate Evaluation

### Evaluate Candidates

**File:** `core/loop/decision_engine.py:350-500`  
**Status:** ✅ IMPLEMENTED

```python
async def evaluate(self, candidates: List[Candidate]) -> List[Candidate]:
    """Score candidates using 5-factor formula."""
    
    for candidate in candidates:
        # 1. Get policy score (BEFORE decision — RULE 7)
        policy_score = await self.policy_memory.get_score(candidate.action_type)
        
        # 2. Calculate factors
        goal_alignment = self._calculate_goal_alignment(candidate)
        confidence = await self._calculate_confidence(candidate)
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
        
        logger.debug(f"[VECTOR][decision] Candidate: {candidate.action_type} "
                    f"(score={candidate.total_score:.2f})")
    
    # Sort by score
    candidates.sort(key=lambda c: c.total_score, reverse=True)
    
    return candidates

def _calculate_goal_alignment(self, candidate: Candidate) -> float:
    """Calculate how well candidate aligns with active goals."""
    
    if not candidate.source_goal_id:
        return self._estimate_goal_match(candidate)
    
    goal = self.goal_system.get_goal(candidate.source_goal_id)
    if not goal:
        return 0.0
    
    # Higher alignment if goal is stalled
    urgency_factor = 1.0 - goal.progress
    
    # Weight by goal priority
    alignment = goal.priority * goal.importance * urgency_factor
    
    return alignment

async def _calculate_confidence(self, candidate: Candidate) -> float:
    """Calculate confidence in success."""
    
    # Check historical success rate
    history = await self.episodic_memory.retrieve(
        query=candidate.action_type,
        limit=50
    )
    
    successes = sum(1 for h in history if h.content.get("success", False))
    total = len(history)
    
    if total == 0:
        return 0.5  # Default confidence
    
    return successes / total

def _calculate_urgency(self, candidate: Candidate) -> float:
    """Calculate time sensitivity."""
    
    # Check if source goal has deadline
    if candidate.source_goal_id:
        goal = self.goal_system.get_goal(candidate.source_goal_id)
        if goal and goal.due_date:
            days_left = (goal.due_date - time.time()) / (24 * 3600)
            
            if days_left < 1:
                return 1.0  # Critical
            elif days_left < 3:
                return 0.8  # High
            elif days_left < 7:
                return 0.6  # Medium
            else:
                return 0.4  # Low
    
    # Check event urgency
    if candidate.source_event_id:
        return 0.7  # Events are usually urgent
    
    return 0.5  # Default

def _calculate_timing(self, candidate: Candidate) -> float:
    """Calculate current timing appropriateness."""
    
    # Check time of day
    now = datetime.now()
    hour = now.hour
    
    # Some actions are time-sensitive
    if "morning" in candidate.description.lower() and 6 <= hour <= 10:
        return 1.0
    elif "nightly" in candidate.description.lower() and 20 <= hour <= 23:
        return 1.0
    elif "2am" in candidate.description.lower() and hour == 2:
        return 1.0
    
    # Check device state
    # (skip if battery low, etc.)
    
    return 0.7  # Default good timing

def _calculate_cost(self, candidate: Candidate) -> float:
    """Calculate resource cost."""
    
    cost = 0.0
    
    # LLM call cost
    cost += 0.1  # Base cost
    
    # External API cost
    if candidate.scope == "external":
        cost += 0.3
    
    # Long-running task cost
    if "long" in candidate.description.lower():
        cost += 0.2
    
    return min(cost, 1.0)  # Cap at 1.0
```

---

## ReasoningBank Integration (RULE 8)

### Store Decision Chain

**File:** `core/loop/decision_engine.py:500-550`  
**Status:** ✅ IMPLEMENTED

```python
async def store_decision_chain(
    self,
    events: List[Event],
    candidates: List[Candidate],
    winner: Candidate,
    context: WorldState
):
    """Store decision chain in ReasoningBank (RULE 8)."""
    
    try:
        chain = {
            "events": [e.to_dict() for e in events],
            "candidates": [c.to_dict() for c in candidates],
            "winner": winner.to_dict(),
            "context_summary": {
                "time": context.environment.timestamp,
                "active_goals": len(context.goals.active_goals),
                "device_state": context.device.cpu_percent
            },
            "timestamp": time.time()
        }
        
        await self.reasoning_bank.store(chain)
        
        logger.debug(f"[VECTOR][decision] Stored decision chain")
        
    except Exception as e:
        logger.warning(f"[VECTOR][decision] Failed to store chain: {e}")
```

---

## Policy Memory Integration (RULE 7)

### Before and After

**File:** `core/memory/policy.py`  
**Status:** ✅ IMPLEMENTED (RULE 7)

```python
# BEFORE decision
async def get_score(self, action_type: str) -> float:
    """Get historical success score for action type."""
    
    # Exponential Moving Average (EMA)
    if action_type not in self.scores:
        return 0.5  # Default
    
    return self.scores[action_type]

# AFTER action
async def update_from_outcome(self, action_type: str, outcome: str):
    """Update policy from action outcome."""
    
    # Calculate reward
    if outcome == "success":
        reward = 1.0
    elif outcome == "partial":
        reward = 0.5
    else:  # failure
        reward = 0.0
    
    # Update EMA
    alpha = 0.1  # Learning rate
    
    if action_type not in self.scores:
        self.scores[action_type] = reward
    else:
        self.scores[action_type] = (
            alpha * reward +
            (1 - alpha) * self.scores[action_type]
        )
    
    logger.debug(f"[VECTOR][policy] Updated {action_type}: {self.scores[action_type]:.2f}")
```

---

## Decision Selection

### Select Winner

**File:** `core/loop/decision_engine.py:150-200`  
**Status:** ✅ IMPLEMENTED

```python
def select_winner(self, scored_candidates: List[Candidate]) -> Optional[Candidate]:
    """Select best candidate."""
    
    if not scored_candidates:
        return None
    
    # Already sorted by evaluate()
    winner = scored_candidates[0]
    
    # Check minimum threshold
    if winner.total_score < 0.3:
        logger.info(f"[VECTOR][decision] No candidate above threshold "
                   f"(best={winner.total_score:.2f})")
        return None
    
    logger.info(f"[VECTOR][decision] Selected: {winner.action_type} "
               f"(score={winner.total_score:.2f})")
    
    return winner
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Generate candidates | 1-5s | LLM calls |
| Evaluate candidates | 100-500ms | Policy lookups |
| Select winner | <1ms | Memory access |
| Store chain | 10-50ms | ReasoningBank write |

---

## Known Issues

### Issue 1: Candidate Generation Slow

**Symptom:** Think loop takes >5s  
**Root Cause:** LLM calls for each goal  
**Impact:** Delayed decisions  
**Workaround:** Batch generation, caching  
**Priority:** MEDIUM

### Issue 2: Policy Scores Unstable

**Symptom:** Policy scores fluctuate wildly  
**Root Cause:** EMA alpha too high  
**Impact:** Unreliable scoring  
**Workaround:** Reduce alpha to 0.05  
**Priority:** LOW

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop architecture
- `07_GOALS_AND_PLANNING.md` — Goal hierarchy
- `13_MEMORY_ARCHITECTURE.md` — Policy memory
- `09_GOVERNOR_AND_PERMISSIONS.md` — Permission gates

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
