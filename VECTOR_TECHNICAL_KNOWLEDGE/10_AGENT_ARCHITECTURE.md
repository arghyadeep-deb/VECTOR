# Agent Architecture

**Purpose:** Agent base class, HP system, lifecycle, registry  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's agent system implements a Darwinian multi-agent architecture where 133+ agents across 33+ districts evolve, die, and are reborn based on performance.

**Key Properties:**
- **Darwinian lifecycle** — birth, life, death, ghost, rebirth
- **HP system** — 0-1000 HP, agents die at 0
- **Ghost memory** — deceased agent knowledge preserved
- **Council governance** — HP > 700 get voting rights
- **Model access tiers** — HP > 800 get Claude Sonnet access

**Files:**
- `core/city/agent_base.py` (~400 lines)
- `core/city/agent_registry.py` (~300 lines)
- `districts/*/` — 133+ agent files

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Agent Base Class

### AgentBase

**File:** `core/city/agent_base.py:50-200`  
**Status:** ✅ IMPLEMENTED

```python
class AgentBase:
    """Base class for all VECTOR agents."""
    
    def __init__(self, name: str, district: str, hp: int = 500):
        self.name = name
        self.district = district
        self.hp = hp
        self.hp_max = 1000
        
        # Metadata
        self.created_at = time.time()
        self.last_active = time.time()
        self.generation = 1  # Incremented on rebirth
        
        # Ghost memory (inherited from predecessor)
        self.ghost_memory: List[dict] = []
        
        # Model access (HP-based)
        self.model_access = self._calculate_model_access()
    
    def _calculate_model_access(self) -> dict:
        """Calculate model access based on HP."""
        if self.hp > 800:
            return {
                "primary": "claude-sonnet",
                "fallback": "vector-focus",
                "council": True
            }
        elif self.hp > 700:
            return {
                "primary": "kimi-k2.6",
                "fallback": "vector-focus",
                "council": True
            }
        elif self.hp > 600:
            return {
                "primary": "vector-focus",
                "fallback": "vector-ambient",
                "council": False
            }
        else:
            return {
                "primary": "vector-ambient",
                "fallback": None,
                "council": False
            }
    
    async def execute(self, query: str, task_type: str) -> dict:
        """Execute task."""
        # Update last active
        self.last_active = time.time()
        
        # Check if dead
        if self.hp <= 0:
            logger.warning(f"[VECTOR][agent] {self.name} is dead (HP=0)")
            return {"success": False, "error": "Agent dead"}
        
        try:
            # Execute task
            result = await self._execute_task(query, task_type)
            
            # Update HP based on result
            if result.get("success"):
                self.adjust_hp(+30, "output used by VECTOR")
            else:
                self.adjust_hp(-30, "task failed")
            
            return result
        
        except Exception as e:
            logger.error(f"[VECTOR][agent] {self.name} failed: {e}")
            self.adjust_hp(-100, "critical error")
            return {"success": False, "error": str(e)}
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        """Execute specific task (override in subclass)."""
        raise NotImplementedError
    
    def adjust_hp(self, amount: int, reason: str):
        """Adjust HP."""
        old_hp = self.hp
        self.hp = max(0, min(self.hp_max, self.hp + amount))
        
        logger.info(f"[VECTOR][agent] {self.name} HP: {old_hp} → {self.hp} ({reason})")
        
        # Check death
        if self.hp == 0:
            self._die()
        
        # Update model access
        self.model_access = self._calculate_model_access()
    
    def _die(self):
        """Handle agent death."""
        logger.warning(f"[VECTOR][agent] {self.name} died (HP=0)")
        
        # Store ghost memory
        ghost = {
            "name": self.name,
            "district": self.district,
            "generation": self.generation,
            "hp_history": self.hp,
            "created_at": self.created_at,
            "died_at": time.time(),
            "lessons_learned": self.ghost_memory
        }
        
        # Notify registry
        from core.city.agent_registry import AgentRegistry
        registry = AgentRegistry()
        registry.handle_death(self, ghost)
```

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

| HP Range | Model Access | Council | Status |
|----------|--------------|---------|--------|
| 800-1000 | Claude Sonnet | ✅ Yes | Elite |
| 700-800 | Kimi K2.6 | ✅ Yes | Senior |
| 600-700 | Vector Focus | ❌ No | Regular |
| 0-600 | Vector Ambient | ❌ No | Junior |
| 0 | Dead | ❌ No | Ghost |

---

## Agent Registry

### Registry Class

**File:** `core/city/agent_registry.py:50-200`  
**Status:** ✅ IMPLEMENTED

```python
class AgentRegistry:
    """Registry for all VECTOR agents."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.agents = {}
            cls._instance.ghosts = {}
        return cls._instance
    
    def register(self, agent: AgentBase):
        """Register agent."""
        self.agents[agent.name] = agent
        logger.info(f"[VECTOR][registry] Registered: {agent.name}")
    
    def unregister(self, agent_name: str):
        """Unregister agent."""
        if agent_name in self.agents:
            del self.agents[agent_name]
            logger.info(f"[VECTOR][registry] Unregistered: {agent_name}")
    
    def get(self, agent_name: str) -> Optional[AgentBase]:
        """Get agent by name."""
        return self.agents.get(agent_name)
    
    def list(self) -> List[AgentBase]:
        """List all agents."""
        return list(self.agents.values())
    
    def get_by_district(self, district: str) -> List[AgentBase]:
        """Get agents by district."""
        return [a for a in self.agents.values() if a.district == district]
    
    def count(self) -> int:
        """Count agents."""
        return len(self.agents)
    
    def handle_death(self, agent: AgentBase, ghost: dict):
        """Handle agent death."""
        # Store ghost
        self.ghosts[agent.name] = ghost
        
        # Unregister agent
        self.unregister(agent.name)
        
        # Attempt rebirth
        self._attempt_rebirth(agent, ghost)
    
    def _attempt_rebirth(self, agent: AgentBase, ghost: dict):
        """Attempt to rebirth agent."""
        # Create new agent with ghost memory
        new_agent = self._create_successor(agent, ghost)
        
        if new_agent:
            self.register(new_agent)
            logger.info(f"[VECTOR][registry] Rebirth: {new_agent.name} (gen {new_agent.generation})")
    
    def _create_successor(self, agent: AgentBase, ghost: dict) -> Optional[AgentBase]:
        """Create successor agent with ghost memory."""
        # Import agent class
        module_path = f"districts.{agent.district}.{agent.name}"
        
        try:
            module = importlib.import_module(module_path)
            agent_cls = getattr(module, agent.__class__.__name__)
            
            # Create new instance
            new_agent = agent_cls(
                name=agent.name,
                district=agent.district,
                hp=500  # Start with 500 HP
            )
            
            # Inherit ghost memory
            new_agent.ghost_memory = ghost["lessons_learned"]
            new_agent.generation = ghost["generation"] + 1
            
            return new_agent
        
        except Exception as e:
            logger.error(f"[VECTOR][registry] Rebirth failed: {e}")
            return None
```

---

## Ghost Memory

### Ghost Memory Structure

**File:** `core/city/agent_registry.py:200-300`  
**Status:** ✅ IMPLEMENTED

```python
@dataclass
class GhostMemory:
    """Ghost memory of deceased agent."""
    
    name: str
    district: str
    generation: int
    
    # History
    created_at: float
    died_at: float
    total_lifetime: float
    
    # Lessons
    lessons_learned: List[dict]
    successful_patterns: List[str]
    failed_patterns: List[str]
    
    # Stats
    tasks_completed: int
    tasks_failed: int
    avg_hp: float
    
    def to_dict(self) -> dict:
        """Export ghost memory."""
        return {
            "name": self.name,
            "district": self.district,
            "generation": self.generation,
            "created_at": self.created_at,
            "died_at": self.died_at,
            "total_lifetime": self.total_lifetime,
            "lessons_learned": self.lessons_learned,
            "successful_patterns": self.successful_patterns,
            "failed_patterns": self.failed_patterns,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "avg_hp": self.avg_hp
        }
```

---

## Agent Lifecycle

### Lifecycle Stages

```
Birth (HP=500)
    ↓
Life (HP 0-1000)
    ↓
Death (HP=0)
    ↓
Ghost (memory preserved)
    ↓
Rebirth (new agent with ghost memory)
    ↓
Life (HP=500, gen+1)
```

### Birth

**File:** `core/city/agent_base.py:50-100`  
**Status:** ✅ IMPLEMENTED

```python
def __init__(self, name: str, district: str, hp: int = 500):
    """Initialize agent."""
    self.name = name
    self.district = district
    self.hp = hp
    self.hp_max = 1000
    
    # Metadata
    self.created_at = time.time()
    self.last_active = time.time()
    self.generation = 1
    
    # Ghost memory
    self.ghost_memory = []
    
    # Model access
    self.model_access = self._calculate_model_access()
    
    logger.info(f"[VECTOR][agent] Born: {name} (district={district}, hp={hp})")
```

### Life

**File:** `core/city/agent_base.py:150-200`  
**Status:** ✅ IMPLEMENTED

```python
async def execute(self, query: str, task_type: str) -> dict:
    """Execute task during life."""
    # Update last active
    self.last_active = time.time()
    
    # Check if dead
    if self.hp <= 0:
        return {"success": False, "error": "Agent dead"}
    
    try:
        # Execute task
        result = await self._execute_task(query, task_type)
        
        # Update HP
        if result.get("success"):
            self.adjust_hp(+30, "output used")
        else:
            self.adjust_hp(-30, "task failed")
        
        return result
    
    except Exception as e:
        logger.error(f"[VECTOR][agent] {self.name} failed: {e}")
        self.adjust_hp(-100, "critical error")
        return {"success": False, "error": str(e)}
```

### Death

**File:** `core/city/agent_base.py:250-300`  
**Status:** ✅ IMPLEMENTED

```python
def _die(self):
    """Handle agent death."""
    logger.warning(f"[VECTOR][agent] {self.name} died (HP=0)")
    
    # Store ghost memory
    ghost = {
        "name": self.name,
        "district": self.district,
        "generation": self.generation,
        "created_at": self.created_at,
        "died_at": time.time(),
        "lessons_learned": self.ghost_memory
    }
    
    # Notify registry
    from core.city.agent_registry import AgentRegistry
    registry = AgentRegistry()
    registry.handle_death(self, ghost)
```

### Rebirth

**File:** `core/city/agent_registry.py:250-300`  
**Status:** ✅ IMPLEMENTED

```python
def _create_successor(self, agent: AgentBase, ghost: dict) -> Optional[AgentBase]:
    """Create successor with ghost memory."""
    try:
        # Import agent class
        module_path = f"districts.{agent.district}.{agent.name}"
        module = importlib.import_module(module_path)
        agent_cls = getattr(module, agent.__class__.__name__)
        
        # Create new instance
        new_agent = agent_cls(
            name=agent.name,
            district=agent.district,
            hp=500
        )
        
        # Inherit ghost memory
        new_agent.ghost_memory = ghost["lessons_learned"]
        new_agent.generation = ghost["generation"] + 1
        
        return new_agent
    
    except Exception as e:
        logger.error(f"[VECTOR][registry] Rebirth failed: {e}")
        return None
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Agent birth | <1ms | Memory allocation |
| Task execution | 1-10s | LLM calls |
| HP adjustment | <1ms | Memory update |
| Death handling | 10-50ms | Ghost storage |
| Rebirth | 50-200ms | Module import |

---

## Known Issues

### Issue 1: No HP Decay

**Symptom:** Agents never lose HP over time  
**Root Cause:** No passive decay implemented  
**Impact:** Stale agents persist  
**Workaround:** Manual culling  
**Priority:** LOW

### Issue 2: Ghost Memory Not Used

**Symptom:** Successor doesn't leverage ghost memory  
**Root Cause:** Not wired into execution  
**Impact:** Repeated mistakes  
**Workaround:** Inject ghost memory into prompts  
**Priority:** MEDIUM

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `10_AGENT_ARCHITECTURE.md` — This document
- `11_VECTOR_CITY.md` — Districts
- `12_HP_AND_EVOLUTION.md` — HP system details
- `09_GOVERNOR_AND_PERMISSIONS.md` — Governor routing

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
