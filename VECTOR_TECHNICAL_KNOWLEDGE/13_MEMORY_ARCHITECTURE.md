# Memory Architecture

**Purpose:** All memory systems — episodic, semantic, policy, reasoning, ghost  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR implements multiple memory systems for different purposes: episodic (events), semantic (knowledge), policy (learned behavior), reasoning (decision chains), and ghost (deceased agents).

**Key Properties:**
- **5 memory types** — episodic, semantic, policy, reasoning, ghost
- **SQLite FTS5** — episodic memory with full-text search
- **LightRAG** — semantic memory (nano-vectordb)
- **EMA** — policy memory with exponential moving average
- **SQLCipher** — AES-256 encryption
- **Obsidian sync** — human-readable notes

**Files:**
- `core/memory/episodic.py` (~400 lines)
- `core/memory/policy.py` (~200 lines)
- `core/memory/reasoning_memory.py` (~300 lines)
- `core/memory/obsidian_sync.py` (~250 lines)
- `core/memory/light_rag.py` (~350 lines)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Episodic Memory

### SQLite FTS5

**File:** `core/memory/episodic.py`  
**Status:** ✅ IMPLEMENTED

```python
class EpisodicMemory:
    """Episodic memory with SQLite FTS5."""
    
    def __init__(self, db_path: str = "data/vector.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database."""
        conn = self.get_db_connection()
        
        # Create tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id INTEGER PRIMARY KEY,
                event_type TEXT,
                content TEXT,
                tags TEXT,
                source TEXT,
                timestamp REAL
            )
        """)
        
        # FTS5 virtual table
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts
            USING fts5(content, tags)
        """)
        
        conn.commit()
        conn.close()
    
    async def store(
        self,
        event_type: str,
        content: dict,
        tags: List[str] = None,
        source: str = None
    ):
        """Store episodic memory."""
        conn = self.get_db_connection()
        
        content_json = json.dumps(content)
        tags_json = json.dumps(tags or [])
        
        conn.execute("""
            INSERT INTO episodic_memory
            (event_type, content, tags, source, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (event_type, content_json, tags_json, source, time.time()))
        
        conn.commit()
        conn.close()
    
    async def retrieve(
        self,
        query: str,
        limit: int = 10,
        time_range: timedelta = None
    ) -> List[dict]:
        """Retrieve episodic memories."""
        conn = self.get_db_connection()
        
        # FTS5 search
        results = conn.execute("""
            SELECT id, event_type, content, tags, source, timestamp
            FROM episodic_memory
            WHERE content MATCH ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (query, limit)).fetchall()
        
        conn.close()
        
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "content": json.loads(r[2]),
                "tags": json.loads(r[3]),
                "source": r[4],
                "timestamp": r[5]
            }
            for r in results
        ]
```

---

## Semantic Memory (LightRAG)

### LightRAG Integration

**File:** `core/memory/light_rag.py`  
**Status:** ✅ IMPLEMENTED

```python
class LightRAGMemory:
    """Semantic memory using LightRAG (nano-vectordb)."""
    
    def __init__(self):
        self.db = nano_vectordb.VectorDB()
        self._load()
    
    async def store(self, knowledge: dict):
        """Store semantic knowledge."""
        # Generate embedding
        text = knowledge["content"]
        embedding = await self._generate_embedding(text)
        
        # Store
        self.db.add(
            id=knowledge["id"],
            vector=embedding,
            data=knowledge
        )
        
        self._save()
    
    async def retrieve(self, query: str, limit: int = 10) -> List[dict]:
        """Retrieve semantic knowledge."""
        # Generate query embedding
        embedding = await self._generate_embedding(query)
        
        # Search
        results = self.db.search(embedding, limit=limit)
        
        return [r["data"] for r in results]
```

---

## Policy Memory (EMA)

### Exponential Moving Average

**File:** `core/memory/policy.py`  
**Status:** ✅ IMPLEMENTED (RULE 7)

```python
class PolicyMemory:
    """Policy memory with EMA (RULE 7)."""
    
    def __init__(self):
        self.scores = {}  # action_type → score
        self.alpha = 0.1  # Learning rate
    
    async def get_score(self, action_type: str) -> float:
        """Get historical success score (BEFORE decision)."""
        return self.scores.get(action_type, 0.5)
    
    async def update_from_outcome(self, action_type: str, outcome: str):
        """Update policy from outcome (AFTER action)."""
        # Calculate reward
        reward = 1.0 if outcome == "success" else 0.0
        
        # Update EMA
        if action_type not in self.scores:
            self.scores[action_type] = reward
        else:
            self.scores[action_type] = (
                self.alpha * reward +
                (1 - self.alpha) * self.scores[action_type]
            )
```

---

## Reasoning Memory

### Decision Chains

**File:** `core/memory/reasoning_memory.py`  
**Status:** ✅ IMPLEMENTED (RULE 8)

```python
class ReasoningMemory:
    """Reasoning memory for decision chains (RULE 8)."""
    
    def __init__(self):
        self.chains = []
    
    async def store_chain(
        self,
        events: List[Event],
        candidates: List[Candidate],
        winner: Candidate,
        context: WorldState
    ):
        """Store decision chain."""
        chain = {
            "events": [e.to_dict() for e in events],
            "candidates": [c.to_dict() for c in candidates],
            "winner": winner.to_dict(),
            "timestamp": time.time()
        }
        
        self.chains.append(chain)
    
    async def get_similar_chains(self, query: str, limit: int = 5) -> List[dict]:
        """Get similar decision chains."""
        # Simple keyword match
        similar = []
        for chain in self.chains:
            if query.lower() in json.dumps(chain).lower():
                similar.append(chain)
        
        return similar[:limit]
```

---

## Obsidian Sync

### Human-Readable Notes

**File:** `core/memory/obsidian_sync.py`  
**Status:** ✅ IMPLEMENTED

```python
class ObsidianSync:
    """Sync memories to Obsidian vault."""
    
    def __init__(self, vault_path: str = "C:/Users/Arghyadeep/V.E.C.T.O.R Brain/"):
        self.vault_path = vault_path
    
    async def write_reflection(self, events: List[Event], patterns: List[dict]):
        """Write daily reflection to Obsidian."""
        date = datetime.now().strftime("%Y-%m-%d")
        
        content = f"# {date} Reflection\n\n"
        content += "## Events\n\n"
        
        for event in events[-20:]:
            content += f"- [{event.type}] {event.content}\n"
        
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

## Ghost Memory

### Deceased Agent Memory

**File:** `core/memory/ghost_memory.py`  
**Status:** ✅ IMPLEMENTED

```python
class GhostMemory:
    """Memory of deceased agents."""
    
    def __init__(self):
        self.ghosts = {}
    
    async def store_ghost(self, agent: AgentBase, ghost_data: dict):
        """Store ghost memory."""
        self.ghosts[agent.name] = ghost_data
    
    async def get_ghost(self, agent_name: str) -> Optional[dict]:
        """Get ghost memory."""
        return self.ghosts.get(agent_name)
```

---

## Memory Consolidation

### Daily Consolidation (2AM)

**File:** `core/memory/consolidation.py`  
**Status:** ✅ IMPLEMENTED

```python
class MemoryConsolidator:
    """Consolidate memories daily at 2AM."""
    
    async def consolidate(self, events: List[Event]):
        """Consolidate day's events."""
        # 1. Group by type
        episodic = [e for e in events if e.type == "episodic"]
        semantic = [e for e in events if e.type == "semantic"]
        
        # 2. Consolidate episodic
        for event in episodic:
            await self.episodic_memory.consolidate(event)
        
        # 3. Extract semantic knowledge
        for event in semantic:
            knowledge = await self._extract_knowledge(event)
            await self.light_rag.store(knowledge)
        
        # 4. Write to Obsidian
        await self.obsidian_sync.sync_memories(events)
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Store episodic | 5-20ms | SQLite write |
| Retrieve episodic | 10-50ms | FTS5 search |
| Store semantic | 50-200ms | Embedding generation |
| Retrieve semantic | 10-50ms | Vector search |
| Policy get/update | <1ms | Memory access |
| Obsidian write | 10-50ms | File I/O |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop architecture
- `14_REFLECTION.md` — Reflection system
- `24_DATABASES.md` — Database details

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
