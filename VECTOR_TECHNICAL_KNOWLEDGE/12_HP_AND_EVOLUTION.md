# HP System and Agent Evolution

**Purpose:** HP system, agent evolution, ghost memory, Darwinian lifecycle  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR implements a Darwinian agent system where agents have HP (0-1000), die at 0, and are reborn with ghost memory. High-HP agents gain council voting rights and premium model access.

**Key Properties:**
- **HP range** — 0-1000
- **Death at 0** — ghost memory preserved
- **Rebirth** — successor inherits ghost memory
- **Council** — HP > 700 get voting rights
- **Model tiers** — HP-based model access

**Files:**
- `core/city/agent_base.py`
- `core/city/evolution_engine.py`

**Status:** ✅ IMPLEMENTED, production-reachable

---

## HP System

### HP Adjustments

**File:** `core/city/agent_base.py:200-250`  
**Status:** ✅ IMPLEMENTED

```python
# HP adjustments:
HP_USER_APPROVED = +100      # User approved output
HP_TASK_WELL = +50           # Task completed well
HP_OUTPUT_USED = +30         # Output used by VECTOR
HP_COUNCIL_VOTED = +40       # Council voted for them
HP_TASK_FAILED = -30         # Task failed
HP_OUTPUT_IGNORED = -50      # Output ignored 3x
HP_CRITICAL_ERROR = -100     # Critical error
```

### HP Thresholds

**File:** `core/city/agent_base.py:100-150`  
**Status:** ✅ IMPLEMENTED

| HP Range | Model Access | Council | Tier |
|----------|--------------|---------|------|
| 800-1000 | Claude Sonnet | ✅ Yes | Elite |
| 700-800 | Kimi K2.6 | ✅ Yes | Senior |
| 600-700 | Vector Focus | ❌ No | Regular |
| 0-600 | Vector Ambient | ❌ No | Junior |
| 0 | Dead | ❌ No | Ghost |

---

## Agent Lifecycle

### Birth → Life → Death → Ghost → Rebirth

```
Birth (HP=500, gen=1)
    ↓
Life (HP 0-1000)
    ↓
Death (HP=0)
    ↓
Ghost (memory preserved)
    ↓
Rebirth (HP=500, gen=2, inherits ghost)
    ↓
Life (HP 0-1000)
    ↓
[Cycle repeats]
```

### Birth

```python
def __init__(self, name: str, district: str, hp: int = 500):
    self.name = name
    self.district = district
    self.hp = hp
    self.generation = 1
    self.ghost_memory = []
```

### Death

```python
def _die(self):
    logger.warning(f"[VECTOR][agent] {self.name} died (HP=0)")
    
    ghost = {
        "name": self.name,
        "district": self.district,
        "generation": self.generation,
        "lessons_learned": self.ghost_memory
    }
    
    # Notify registry
    registry.handle_death(self, ghost)
```

### Rebirth

```python
def _create_successor(self, agent: AgentBase, ghost: dict):
    new_agent = agent_cls(
        name=agent.name,
        district=agent.district,
        hp=500
    )
    
    # Inherit ghost memory
    new_agent.ghost_memory = ghost["lessons_learned"]
    new_agent.generation = ghost["generation"] + 1
    
    return new_agent
```

---

## Evolution Engine

### Evolution Engine

**File:** `core/city/evolution_engine.py`  
**Status:** ✅ IMPLEMENTED

```python
class EvolutionEngine:
    """Agent evolution and cross-generation learning."""
    
    async def inherit_lessons(self, ghost: dict) -> List[dict]:
        """Extract lessons from ghost memory."""
        lessons = []
        
        for entry in ghost["lessons_learned"]:
            if entry["outcome"] == "success":
                lessons.append({
                    "pattern": entry["pattern"],
                    "confidence": entry["confidence"]
                })
        
        return lessons
    
    def cull_bottom(self, threshold: int = 200):
        """Cull agents below HP threshold."""
        from core.city.agent_registry import AgentRegistry
        registry = AgentRegistry()
        
        for agent in registry.list():
            if agent.hp < threshold:
                agent.adjust_hp(-agent.hp, "culling")
        
        logger.info(f"[VECTOR][evolution] Culled agents below {threshold} HP")
```

---

## Ghost Memory

### Ghost Memory Structure

```python
@dataclass
class GhostMemory:
    name: str
    district: str
    generation: int
    lessons_learned: List[dict]
    successful_patterns: List[str]
    failed_patterns: List[str]
    tasks_completed: int
    tasks_failed: int
```

### Ghost Memory Usage

```python
async def execute(self, query: str, task_type: str) -> dict:
    # Inject ghost memory into prompt
    if self.ghost_memory:
        ghost_context = "Lessons from previous generations:\n"
        for lesson in self.ghost_memory[-10:]:
            ghost_context += f"- {lesson['pattern']}\n"
        
        # Include in LLM call
        messages.append({"role": "system", "content": ghost_context})
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| HP adjustment | <1ms | Memory update |
| Death handling | 10-50ms | Ghost storage |
| Rebirth | 50-200ms | Module import |
| Lesson inheritance | 10-50ms | Memory retrieval |

---

## Cross-References

See:
- `10_AGENT_ARCHITECTURE.md` — Agent system
- `11_VECTOR_CITY.md` — Districts
- `09_GOVERNOR_AND_PERMISSIONS.md` — Council

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
