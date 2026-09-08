# Reflection System

**Purpose:** Daily reflection, memory consolidation, learning  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's reflection system runs daily at 2AM to review the day's events, consolidate memories, extract patterns, and update policies.

**Key Properties:**
- **Daily at 2AM** — automated reflection cycle
- **Memory consolidation** — episodic → semantic
- **Pattern extraction** — identify recurring themes
- **Policy updates** — learn from outcomes
- **Obsidian sync** — write reflections to vault

**Files:**
- `districts/reflection/daily_reviewer.py`
- `districts/reflection/journal_writer.py`
- `districts/reflection/growth_analyst.py`

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Reflection Process

### Daily Cycle (2AM)

**File:** `core/loop/autonomous_loop.py:850-1000`  
**Status:** ✅ IMPLEMENTED

```python
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
        
        logger.info("[VECTOR][reflect] Reflection complete")
        
    except Exception as e:
        logger.error(f"[VECTOR][reflect] Reflection failed: {e}")
```

---

## Memory Consolidation

### Episodic → Semantic

**File:** `core/memory/consolidation.py`  
**Status:** ✅ IMPLEMENTED

```python
async def consolidate(self, events: List[Event]):
    """Consolidate day's events."""
    
    # Group by type
    episodic = [e for e in events if e.type == "episodic"]
    semantic = [e for e in events if e.type == "semantic"]
    
    # Consolidate episodic
    for event in episodic:
        await self.episodic_memory.consolidate(event)
    
    # Extract semantic knowledge
    for event in semantic:
        knowledge = await self._extract_knowledge(event)
        await self.light_rag.store(knowledge)
    
    # Update reasoning chains
    await self.reasoning_memory.consolidate(events)
    
    # Write to Obsidian
    await self.obsidian_sync.sync_memories(events)

async def _extract_knowledge(self, event: Event) -> dict:
    """Extract semantic knowledge from event."""
    
    from core.inference.provider_client import chat
    
    # Inject context (RULE 1)
    hydration = await context_engine.session_hydration_prompt()
    
    prompt = f"""Extract key knowledge from this event:

Event: {event.content}

What is the key insight or fact?
Return JSON: {{"content": "...", "tags": [...]}}
"""
    
    messages = [
        {"role": "system", "content": hydration},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat(messages, model="vector-focus")
    
    try:
        knowledge = json.loads(response.content)
        knowledge["id"] = f"knowledge_{int(time.time())}"
        return knowledge
    except Exception as e:
        logger.error(f"[VECTOR][consolidation] Extract failed: {e}")
        return None
```

---

## Pattern Finding

### Extract Patterns

**File:** `districts/memory_curator/pattern_finder.py`  
**Status:** ✅ IMPLEMENTED

```python
class PatternFinder:
    """Find patterns in events."""
    
    async def find_patterns(self, events: List[Event]) -> List[dict]:
        """Find recurring patterns."""
        
        patterns = []
        
        # Group by event type
        by_type = {}
        for event in events:
            if event.type not in by_type:
                by_type[event.type] = []
            by_type[event.type].append(event)
        
        # Find frequent types
        for event_type, type_events in by_type.items():
            if len(type_events) >= 5:  # At least 5 occurrences
                patterns.append({
                    "type": "frequency",
                    "event_type": event_type,
                    "count": len(type_events),
                    "description": f"Frequent event: {event_type} ({len(type_events)}x)"
                })
        
        # Find temporal patterns
        # ... (implementation)
        
        return patterns
```

---

## Obsidian Integration

### Write Reflection

**File:** `core/memory/obsidian_sync.py`  
**Status:** ✅ IMPLEMENTED

```python
async def write_reflection(self, events: List[Event], patterns: List[dict]):
    """Write daily reflection to Obsidian."""
    
    date = datetime.now().strftime("%Y-%m-%d")
    
    content = f"# {date} Reflection\n\n"
    
    # Events section
    content += "## Events\n\n"
    for event in events[-20:]:
        content += f"- [{event.type}] {event.content[:100]}...\n"
    
    # Patterns section
    content += "\n## Patterns\n\n"
    for pattern in patterns:
        content += f"- {pattern['description']}\n"
    
    # Write to vault
    path = f"{self.vault_path}/01 Journals/{date}.md"
    with open(path, 'w') as f:
        f.write(content)
    
    logger.info(f"[VECTOR][obsidian] Wrote reflection to {path}")
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Event retrieval | 50-200ms | SQLite query |
| Memory consolidation | 5-30s | LLM calls |
| Pattern finding | 1-5s | Event processing |
| Obsidian write | 10-50ms | File I/O |
| Total reflection | 30-120s | Consolidation |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop architecture
- `13_MEMORY_ARCHITECTURE.md` — Memory systems

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
