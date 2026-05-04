---
name: vector-district-builder
description: Use when scaffolding, building, or debugging any of the 8 VECTOR districts. Triggers on: "build District N", "scaffold district", "wire up district", any district name (Mayor's Office, LLM Council, Security, Coding, Time/Calendar, Comms, Memory Curator, Research)
---

# VECTOR District Builder

## District Registry
| # | Name | Key Dep | Status |
|---|------|---------|--------|
| 1 | Mayor's Office | humanlayer | Phase 1 |
| 2 | LLM Council | karpathy/llm-council, OpenRouter | Phase 1 |
| 3 | Security | custom | Phase 1 |
| 4 | Coding | GitBot | Phase 1 |
| 5 | Time/Calendar | KIIT scraper | Phase 1 |
| 6 | Comms | hermes-agent | Phase 1 |
| 7 | Memory Curator | LightRAG + mem0 | Phase 1 |
| 8 | Research | karpathy/autoresearch + OpenCLI | Phase 1 |

## Every District MUST Have

### 1. Base Agent Class
```python
class District_N_Agent:
    def __init__(self, name: str, initial_hp: int = 100):
        self.name = name
        self.hp = initial_hp
        self.memory = []          # ghost memory for successors
        self.session_id = uuid4()

    def earn_hp(self, points: int, reason: str):
        self.hp = min(200, self.hp + points)

    def lose_hp(self, points: int, reason: str):
        self.hp = max(0, self.hp - points)
        if self.hp == 0:
            self._die_and_spawn_successor()

    def _die_and_spawn_successor(self):
        # Pass ghost memory to new instance
        successor = self.__class__(self.name, initial_hp=50)
        successor.memory = self.memory[-100:]  # last 100 memories
        return successor

    def run_forever(self):
        """NEVER returns. The loop is the agent's life."""
        while True:
            try:
                self._tick()
            except Exception as e:
                self.lose_hp(10, f"error: {e}")
```

### 2. HumanLayer Gate on ALL write tools
```python
from humanlayer import HumanLayer

hl = HumanLayer()

@hl.require_approval()
def write_file(path: str, content: str):
    """Every file write needs approval."""
    ...

@hl.require_approval()
def git_commit(message: str):
    """Every commit needs approval."""
    ...
```

### 3. LightRAG Memory Hook
```python
from lightrag import LightRAG, QueryParam

rag = LightRAG(working_dir="./district_N_memory")

def remember(content: str):
    rag.insert(content)

def recall(query: str, mode="hybrid") -> str:
    return rag.query(query, param=QueryParam(mode=mode))
```

### 4. Session Hydration (BEFORE every LLM call)
```python
def hydrate_session() -> str:
    context = recall("recent decisions and current state")
    return f"[SESSION HYDRATION]\n{context}\n[END HYDRATION]"
```

### 5. Mayor's Office Registration
```python
# In mayor/registry.py
DISTRICTS = {
    "district_N": {
        "agent": District_N_Agent,
        "endpoint": "http://localhost:800N",
        "min_hp_for_council": 30,
    }
}
```

## Build Order Within a District
1. Write failing tests for base class
2. Implement HP system + `run_forever()`
3. Register tools with HumanLayer gates
4. Wire LightRAG read/write
5. Register with Mayor's Office
6. Run shipped test (three questions)

## Shipped Test (all 3 must pass before Phase 2)
1. "Did VECTOR do something useful you didn't ask?"
2. "Last week's mistake — still making it?"
3. "Laptop crashes — remembers last 3 days?"
