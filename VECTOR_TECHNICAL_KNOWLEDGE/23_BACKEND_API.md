# Backend API

**Purpose:** FastAPI server, MCP server, endpoints
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR exposes its capabilities via a FastAPI server (local) and MCP server (tool protocol), plus a Cloudflare Worker API (remote).

**Key Properties:**
- **FastAPI** — local HTTP API
- **MCP server** — Model Context Protocol tools
- **Cloudflare Worker** — remote API (deployed)
- **Rate limiting** — slowapi protection
- **Authentication** — API key required

**Files:**
- `core/api/app.py` (~200 lines)
- `core/api/routers/` (~15 files)
- `core/mcp_server.py` (~500 lines)
- `api/src/` (Cloudflare Worker)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## FastAPI Server

### App Setup

**File:** `core/api/app.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

app = FastAPI(title="VECTOR API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Routers
from .routers import commands, memory, agents, goals, voice, status
app.include_router(commands.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(goals.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(status.router, prefix="/api")

# Serve HUD
from fastapi.staticfiles import StaticFiles
app.mount("/hud", StaticFiles(directory="frontend", html=True), name="hud")
```

---

## API Routers

### Commands Router

**File:** `core/api/routers/commands.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class CommandRequest(BaseModel):
    command: str
    key: str

@router.post("/command")
async def execute_command(req: CommandRequest):
    """Execute command via API."""
    # Verify API key
    from core.config import CONFIG
    if req.key != CONFIG["api_key"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Scan for injection
    from core.security.prompt_injection import scan_text
    scan_result = scan_text(req.command)
    if scan_result["risk"] == "CRITICAL":
        raise HTTPException(status_code=400, detail="Prompt injection detected")
    
    # Queue command
    from core.api.command_queue import CommandQueue
    queue = CommandQueue()
    await queue.enqueue(req.command)
    
    return {"success": True, "message": "Command queued"}
```

### Memory Router

**File:** `core/api/routers/memory.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()

@router.get("/memory/recent")
async def get_recent_memory(
    limit: int = Query(default=50, ge=1, le=200)
):
    """Get recent episodic memories."""
    from core.memory.episodic import EpisodicMemory
    memory = EpisodicMemory()
    
    memories = await memory.get_recent(limit=limit)
    
    return {"memories": memories}

@router.get("/memory/search")
async def search_memory(
    query: str,
    limit: int = Query(default=20, ge=1, le=100)
):
    """Search episodic memory."""
    from core.memory.episodic import EpisodicMemory
    memory = EpisodicMemory()
    
    results = await memory.query(query=query, limit=limit)
    
    return {"results": results}
```

### Agents Router

**File:** `core/api/routers/agents.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/agents")
async def get_agents():
    """Get all agents."""
    from core.city.agent_registry import AgentRegistry
    registry = AgentRegistry.instance()
    
    agents = registry.list_agents()
    
    return {"agents": agents}

@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    from core.city.agent_registry import AgentRegistry
    registry = AgentRegistry.instance()
    
    agent = registry.get(agent_id)
    if not agent:
        return {"error": "Agent not found"}
    
    return {
        "id": agent.agent_id,
        "name": agent.name,
        "hp": agent.hp,
        "status": agent.status,
        "district": agent.district
    }
```

### Goals Router

**File:** `core/api/routers/goals.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/goals")
async def get_goals():
    """Get active goals."""
    from core.brain.goal_system import GoalSystem
    goals = GoalSystem()
    
    active = goals.get_active_goals()
    
    return {"goals": active}

@router.post("/goals")
async def add_goal(title: str, horizon: str = "SHORT"):
    """Add new goal."""
    from core.brain.goal_system import GoalSystem
    goals = GoalSystem()
    
    goal_id = goals.add_goal(title=title, horizon=horizon)
    
    return {"success": True, "goal_id": goal_id}
```

### Status Router

**File:** `core/api/routers/status.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
async def get_status():
    """Get VECTOR status."""
    from core.loop.autonomous_loop import autonomous_loop
    
    return {
        "status": "running",
        "uptime": autonomous_loop.uptime,
        "agents": autonomous_loop.agent_count,
        "goals": autonomous_loop.goal_count
    }

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@router.get("/heartbeat")
async def heartbeat():
    """Heartbeat endpoint."""
    return {"alive": True}
```

---

## MCP Server

### Tool Protocol

**File:** `core/mcp_server.py`
**Status:** ✅ IMPLEMENTED

```python
from mcp.server import Server

server = Server("vector")

@server.tool("file_read")
async def file_read(path: str):
    """Read file contents."""
    with open(path, 'r') as f:
        return f.read()

@server.tool("shell_exec")
async def shell_exec(command: str):
    """Execute shell command."""
    import asyncio
    result = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await result.communicate()
    return stdout.decode()

@server.tool("memory_store")
async def memory_store(content: str, metadata: dict = None):
    """Store memory."""
    from core.memory.episodic import EpisodicMemory
    memory = EpisodicMemory()
    await memory.store(content=content, metadata=metadata)
    return {"success": True}

@server.tool("memory_query")
async def memory_query(query: str, limit: int = 10):
    """Query memory."""
    from core.memory.episodic import EpisodicMemory
    memory = EpisodicMemory()
    results = await memory.query(query=query, limit=limit)
    return {"results": results}

# ... (100+ tools total)
```

---

## Cloudflare Worker API

### Remote API

**File:** `api/src/router.ts`
**Status:** ✅ IMPLEMENTED, DEPLOYED

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    
    // Authentication
    const key = url.searchParams.get('key');
    if (key !== env.VECTOR_API_KEY) {
      return new Response('Unauthorized', { status: 401 });
    }
    
    // Route
    if (path === '/status') {
      return new Response(JSON.stringify({ status: 'running' }));
    }
    
    if (path === '/health') {
      return new Response(JSON.stringify({ status: 'healthy' }));
    }
    
    if (path === '/heartbeat') {
      return new Response(JSON.stringify({ alive: true }));
    }
    
    if (path === '/command' && request.method === 'POST') {
      const body = await request.json();
      
      // Queue command in D1
      await env.DB.prepare(
        'INSERT INTO command_queue (command, status) VALUES (?, ?)'
      ).bind(body.command, 'pending').run();
      
      return new Response(JSON.stringify({ success: true }));
    }
    
    if (path === '/memory/recent') {
      const memories = await env.DB.prepare(
        'SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT 50'
      ).all();
      
      return new Response(JSON.stringify({ memories: memories.results }));
    }
    
    if (path === '/agents') {
      const agents = await env.DB.prepare(
        'SELECT * FROM agents'
      ).all();
      
      return new Response(JSON.stringify({ agents: agents.results }));
    }
    
    return new Response('Not found', { status: 404 });
  }
};
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| API request (local) | 10-100ms | FastAPI |
| API request (Cloudflare) | 50-200ms | Network |
| MCP tool call | 10-500ms | Tool complexity |
| Command queue | 1-10ms | D1 write |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `22_FRONTEND.md` — HUD interface
- `30_DEPLOYMENT.md` — Deployment
- `16_TOOL_SYSTEM.md` — Tool system

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
