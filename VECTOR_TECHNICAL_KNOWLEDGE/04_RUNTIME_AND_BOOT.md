# VECTOR Runtime and Boot Sequence

**Purpose:** Complete startup sequence, initialization, entry points  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's runtime is orchestrated by `run_vector.py`, which serves as the main entry point for all execution modes. The system supports multiple modes: autonomous loop, API server, smoke test, doctor check, and memory repair.

**Key Properties:**
- **Never crashes** — all exceptions caught, graceful degradation
- **Modular startup** — components initialize in dependency order
- **Configurable** — modes selected via CLI flags
- **Observable** — file logging for long-running modes
- **Recoverable** — restart recovery, checkpoint support

---

## Entry Points

### 1. Main Entry: `run_vector.py`

**File:** `run_vector.py`  
**Lines:** 598  
**Status:** ✅ IMPLEMENTED, production-reachable

**Purpose:** Main launcher for all VECTOR modes

**CLI Interface:**

```bash
# Autonomous loop (default)
python run_vector.py loop

# API server
python run_vector.py api --host 0.0.0.0 --port 8000

# Smoke test
python run_vector.py smoke

# Doctor check
python run_vector.py doctor

# Production readiness check
python run_vector.py production-check

# Memory repair
python run_vector.py memory-repair
```

**Key Functions:**

```python
def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="VECTOR Launcher")
    subparsers = parser.add_subparsers(dest="mode")
    
    # Loop mode
    loop_parser = subparsers.add_parser("loop", help="Run autonomous loop")
    loop_parser.add_argument("--log-file", help="Log file path")
    
    # API mode
    api_parser = subparsers.add_parser("api", help="Run API server")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8000)
    
    # Smoke test
    subparsers.add_parser("smoke", help="One-shot startup verification")
    
    # Doctor
    subparsers.add_parser("doctor", help="Dependency check")
    
    # Production check
    subparsers.add_parser("production-check", help="Production readiness")
    
    # Memory repair
    subparsers.add_parser("memory-repair", help="Memory database repair")
    
    args = parser.parse_args()
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Configure logging
    if args.mode in ("loop", "api"):
        from loguru import logger
        log_file = getattr(args, "log_file", "data/logs/vector.log")
        logger.add(log_file, rotation="10 MB", retention="7 days")
    
    # Setup exception hooks
    setup_exception_hooks()
    
    # Route to mode
    if args.mode == "loop":
        asyncio.run(run_loop())
    elif args.mode == "api":
        run_api(args.host, args.port)
    elif args.mode == "smoke":
        asyncio.run(smoke_test())
    elif args.mode == "doctor":
        run_doctor()
    elif args.mode == "production-check":
        run_production_check()
    elif args.mode == "memory-repair":
        run_memory_repair()
    else:
        parser.print_help()
        return 1
    
    return 0

async def run_loop():
    """Start autonomous loop."""
    from core.loop.autonomous_loop import AutonomousLoop
    
    # Bootstrap agents
    bootstrap_agents()
    
    # Start sidecars
    _start_sidecars()
    
    # Start background services
    await _start_background_services()
    
    # Start loop
    loop = AutonomousLoop()
    await loop.start()

def run_api(host: str, port: int):
    """Start FastAPI server."""
    import uvicorn
    from core.api.app import app
    
    # Bootstrap agents
    bootstrap_agents()
    
    # Start sidecars
    _start_sidecars()
    
    # Start server
    uvicorn.run(app, host=host, port=port)

async def smoke_test():
    """One-shot startup verification."""
    from core.runtime.doctor import Doctor
    
    doctor = Doctor()
    result = await doctor.smoke_test()
    
    if result.success:
        print("✅ Smoke test passed")
        return 0
    else:
        print(f"❌ Smoke test failed: {result.error}")
        return 1

def run_doctor():
    """Dependency check."""
    from core.runtime.doctor import Doctor
    
    doctor = Doctor()
    result = doctor.check_dependencies()
    
    if result.success:
        print("✅ All dependencies OK")
        return 0
    else:
        print(f"❌ Missing dependencies: {result.missing}")
        return 1

def run_production_check():
    """Production readiness check."""
    from core.runtime.production_check import ProductionCheck
    
    check = ProductionCheck()
    result = check.verify()
    
    if result.ready:
        print("✅ Production ready")
        return 0
    else:
        print(f"❌ Not ready: {result.issues}")
        return 1

def run_memory_repair():
    """Memory database repair."""
    from core.memory.episodic import repair_database
    
    success = repair_database()
    
    if success:
        print("✅ Memory repair complete")
        return 0
    else:
        print("❌ Memory repair failed")
        return 1
```

**Startup Sequence:**

```
1. Load .env (dotenv)
2. Configure file logging (loguru)
3. Setup exception hooks (global error handlers)
4. Parse CLI arguments
5. Route to mode handler

For loop/api modes:
6. Bootstrap agents (from config/agent_manifest.yaml)
7. Start sidecars (ComfyUI, hyperframes, open-webui, shadowbroker)
8. Start background services (AmbientListener, etc.)
9. Start autonomous loop OR API server
```

**Dependencies:** `core/`, `districts/`  
**Callers:** User, launch scripts  
**Production Status:** ✅ Production-reachable

---

## Agent Bootstrap

### Function: `bootstrap_agents()`

**File:** `run_vector.py:120-180`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Load and register all agents from manifest

**Process:**

```python
def bootstrap_agents():
    """Register agents from config/agent_manifest.yaml."""
    import yaml
    from core.city.agent_registry import AgentRegistry
    
    # Load manifest
    with open("config/agent_manifest.yaml") as f:
        manifest = yaml.safe_load(f)
    
    # Register each agent
    registry = AgentRegistry()
    
    for agent_def in manifest["agents"]:
        agent_name = agent_def["name"]
        agent_class = agent_def["class"]
        district = agent_def["district"]
        
        # Import agent class
        module_path, class_name = agent_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        agent_cls = getattr(module, class_name)
        
        # Instantiate
        agent = agent_cls(name=agent_name, district=district)
        
        # Register
        registry.register(agent)
    
    logger.info(f"✅ Bootstrapped {len(registry.list())} agents")
```

**Manifest Format:**

```yaml
# config/agent_manifest.yaml
agents:
  - name: git_bot
    class: districts.coding.git_bot.GitBot
    district: coding
    hp: 500
    description: "Code generation and git operations"
    
  - name: threat_scout
    class: districts.security.threat_scout.ThreatScout
    district: security
    hp: 600
    description: "Threat detection and monitoring"
    
  - name: web_scout
    class: districts.research.web_scout.WebScout
    district: research
    hp: 500
    description: "Web research and information gathering"
  
  # ... (133+ agents)
```

**Dependencies:** `config/agent_manifest.yaml`, `core/city/agent_registry.py`  
**Callers:** `run_vector.py`  
**Production Status:** ✅ Production-reachable

---

## Sidecar Management

### Function: `_start_sidecars()`

**File:** `run_vector.py:200-280`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Start optional sidecar services

**Sidecars:**

| Sidecar | Purpose | Command | Status |
|---------|---------|---------|--------|
| ComfyUI | Image generation | `python main.py --port 8188` | ⚠️ Optional |
| HyperFrames | Video processing | `python server.py` | ⚠️ Optional |
| Open WebUI | LLM chat interface | `open-webui serve` | ⚠️ Optional |
| ShadowBroker | Security monitoring | `python shadow_broker.py` | ⚠️ Optional |

**Process:**

```python
def _start_sidecars():
    """Start optional sidecar services."""
    import subprocess
    from loguru import logger
    
    sidecars = [
        {
            "name": "ComfyUI",
            "command": ["python", "main.py", "--port", "8188"],
            "cwd": "C:/ComfyUI",
            "enabled": os.getenv("VECTOR_ENABLE_COMFYUI") == "1"
        },
        {
            "name": "HyperFrames",
            "command": ["python", "server.py"],
            "cwd": "C:/HyperFrames",
            "enabled": os.getenv("VECTOR_ENABLE_HYPERFRAMES") == "1"
        },
        {
            "name": "Open WebUI",
            "command": ["open-webui", "serve"],
            "enabled": os.getenv("VECTOR_ENABLE_OPENWEBUI") == "1"
        },
        {
            "name": "ShadowBroker",
            "command": ["python", "shadow_broker.py"],
            "enabled": os.getenv("VECTOR_ENABLE_SHADOWBROKER") == "1"
        }
    ]
    
    for sidecar in sidecars:
        if sidecar["enabled"]:
            try:
                subprocess.Popen(
                    sidecar["command"],
                    cwd=sidecar.get("cwd"),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"✅ Started {sidecar['name']}")
            except Exception as e:
                logger.error(f"❌ Failed to start {sidecar['name']}: {e}")
```

**Dependencies:** Environment variables, sidecar installations  
**Callers:** `run_vector.py`  
**Production Status:** ✅ Production-reachable

---

## Background Services

### Function: `_start_background_services()`

**File:** `run_vector.py:300-350`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Start persistent background services

**Services:**

| Service | Purpose | Status |
|---------|---------|--------|
| AmbientListener | Voice wake word detection | ⚠️ Needs Kokoro model |
| HealthMonitor | System health monitoring | ✅ |
| MemoryConsolidator | Memory consolidation (2AM) | ✅ |
| TelemetryReporter | Metrics reporting | ✅ |

**Process:**

```python
async def _start_background_services():
    """Start background services."""
    from core.voice.ambient_listener import AmbientListener
    from core.sensing.health_monitor import HealthMonitor
    from core.memory.consolidation import MemoryConsolidator
    from core.telemetry.reporter import TelemetryReporter
    
    services = []
    
    # Ambient listener (voice)
    if os.getenv("VECTOR_ENABLE_VOICE") == "1":
        listener = AmbientListener()
        await listener.start()
        services.append(listener)
        logger.info("✅ Started AmbientListener")
    
    # Health monitor
    monitor = HealthMonitor()
    await monitor.start()
    services.append(monitor)
    logger.info("✅ Started HealthMonitor")
    
    # Memory consolidator (2AM daily)
    consolidator = MemoryConsolidator()
    await consolidator.schedule_daily(hour=2, minute=0)
    services.append(consolidator)
    logger.info("✅ Started MemoryConsolidator")
    
    # Telemetry reporter
    reporter = TelemetryReporter()
    await reporter.start()
    services.append(reporter)
    logger.info("✅ Started TelemetryReporter")
    
    # Store services for graceful shutdown
    _background_services = services
```

**Dependencies:** `core/voice/`, `core/sensing/`, `core/memory/`, `core/telemetry/`  
**Callers:** `run_vector.py`  
**Production Status:** ✅ Production-reachable

---

## Graceful Shutdown

### Function: `_graceful_shutdown()`

**File:** `run_vector.py:400-450`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Clean shutdown with signal handling

**Process:**

```python
async def _graceful_shutdown():
    """Graceful shutdown handler."""
    from loguru import logger
    
    logger.info("🛑 Initiating graceful shutdown...")
    
    # Stop autonomous loop
    if _autonomous_loop:
        await _autonomous_loop.stop()
        logger.info("✅ Stopped autonomous loop")
    
    # Stop background services
    for service in _background_services:
        await service.stop()
    logger.info("✅ Stopped background services")
    
    # Stop sidecars
    for proc in _sidecar_processes:
        proc.terminate()
    logger.info("✅ Stopped sidecars")
    
    # Flush logs
    from loguru import logger
    logger.complete()
    
    logger.info("✅ Shutdown complete")
```

**Signal Handlers:**

```python
def setup_exception_hooks():
    """Setup global exception handlers."""
    import signal
    
    def signal_handler(signum, frame):
        asyncio.create_task(_graceful_shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Global exception handler
    def exception_handler(loop, context):
        logger.error(f"Unhandled exception: {context['exception']}")
        # Don't crash — log and continue
    
    asyncio.get_event_loop().set_exception_handler(exception_handler)
```

**Dependencies:** Signal handlers, asyncio  
**Callers:** `run_vector.py`  
**Production Status:** ✅ Production-reachable

---

## API Server Startup

### File: `core/api/app.py`

**Lines:** ~500  
**Status:** ✅ IMPLEMENTED

**Purpose:** FastAPI application setup

**Startup Sequence:**

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("🚀 Starting VECTOR API...")
    
    # Bootstrap agents
    bootstrap_agents()
    
    # Start sidecars
    _start_sidecars()
    
    # Initialize components
    await initialize_components()
    
    logger.info("✅ VECTOR API ready")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down VECTOR API...")
    await graceful_shutdown()
    logger.info("✅ Shutdown complete")

app = FastAPI(
    title="VECTOR API",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
from core.api.routers import (
    status,
    health,
    agents,
    memory,
    goals,
    commands,
    districts
)

app.include_router(status.router, prefix="/status")
app.include_router(health.router, prefix="/health")
app.include_router(agents.router, prefix="/agents")
app.include_router(memory.router, prefix="/memory")
app.include_router(goals.router, prefix="/goals")
app.include_router(commands.router, prefix="/commands")
app.include_router(districts.router, prefix="/districts")

# Serve HUD frontend
from fastapi.staticfiles import StaticFiles
app.mount("/hud", StaticFiles(directory="frontend", html=True), name="hud")
```

**Endpoints:**

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `/status` | System status | ✅ |
| `/health` | Health check | ✅ |
| `/agents` | Agent management | ✅ |
| `/memory` | Memory operations | ✅ |
| `/goals` | Goal management | ✅ |
| `/commands` | Command execution | ✅ |
| `/districts` | District operations | ✅ |
| `/hud/` | Web UI | ✅ |

**Dependencies:** FastAPI, uvicorn  
**Callers:** HTTP clients, web browsers  
**Production Status:** ✅ Production-reachable

---

## MCP Server Startup

### File: `core/mcp_server.py`

**Lines:** ~200  
**Status:** ✅ IMPLEMENTED

**Purpose:** Model Context Protocol server

**Startup:**

```python
from mcp.server import Server

server = Server("vector")

@server.tool("file_read")
async def file_read(path: str):
    """Read file contents."""
    # Implementation
    pass

@server.tool("file_write")
async def file_write(path: str, content: str):
    """Write file contents."""
    # Implementation
    pass

# ... (100+ tools)

async def main():
    """Start MCP server."""
    await server.serve(port=9001)

if __name__ == "__main__":
    asyncio.run(main())
```

**Dependencies:** MCP SDK  
**Callers:** Claude Code, MCP clients  
**Production Status:** ✅ Production-reachable

---

## Boot Verification

### Smoke Test

**File:** `run_vector.py:smoke_test()`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Verify startup without running full system

**Process:**

```python
async def smoke_test():
    """One-shot startup verification."""
    from core.runtime.doctor import Doctor
    
    doctor = Doctor()
    result = await doctor.smoke_test()
    
    # Checks:
    # 1. Python version >= 3.11
    # 2. All required packages installed
    # 3. Database accessible
    # 4. Config files present
    # 5. Agent manifest valid
    # 6. Model catalog valid
    # 7. Ollama running (if local mode)
    # 8. API keys present (if cloud mode)
    
    if result.success:
        print("✅ Smoke test passed")
        return 0
    else:
        print(f"❌ Smoke test failed: {result.error}")
        return 1
```

**Doctor Check:**

```python
def run_doctor():
    """Dependency check."""
    from core.runtime.doctor import Doctor
    
    doctor = Doctor()
    result = doctor.check_dependencies()
    
    # Checks:
    # 1. Python packages
    # 2. Node packages
    # 3. Ollama models
    # 4. Database files
    # 5. Config files
    # 6. Environment variables
    # 7. Disk space
    # 8. GPU availability
    
    if result.success:
        print("✅ All dependencies OK")
        return 0
    else:
        print(f"❌ Missing dependencies: {result.missing}")
        return 1
```

**Production Check:**

```python
def run_production_check():
    """Production readiness check."""
    from core.runtime.production_check import ProductionCheck
    
    check = ProductionCheck()
    result = check.verify()
    
    # Checks:
    # 1. All smoke test checks
    # 2. All agents loadable
    # 3. All districts functional
    # 4. Memory systems operational
    # 5. Model inference working
    # 6. Permission gateway configured
    # 7. Logging configured
    # 8. Error handling in place
    
    if result.ready:
        print("✅ Production ready")
        return 0
    else:
        print(f"❌ Not ready: {result.issues}")
        return 1
```

---

## Configuration Loading

### Environment Variables

**File:** `.env`  
**Status:** ✅ Required

**Key Variables:**

```bash
# Core
VECTOR_MODE=loop  # loop, api, smoke, doctor
VECTOR_LOG_LEVEL=INFO
VECTOR_LOG_FILE=data/logs/vector.log

# Models
VECTOR_DEFAULT_PROVIDER=ollama
VECTOR_OLLAMA_URL=http://localhost:11434
VECTOR_CLOUD_PROVIDER=cloudflare

# API Keys (free-tier only at runtime)
VECTOR_ANTHROPIC_API_KEY=sk-ant-...
VECTOR_OPENAI_API_KEY=sk-...
VECTOR_GEMINI_API_KEY=...

# Database
VECTOR_DB_PATH=data/vector.db
VECTOR_DB_ENCRYPT=1

# Sidecars
VECTOR_ENABLE_COMFYUI=0
VECTOR_ENABLE_HYPERFRAMES=0
VECTOR_ENABLE_OPENWEBUI=0
VECTOR_ENABLE_SHADOWBROKER=0

# Voice
VECTOR_ENABLE_VOICE=0

# Permissions
VECTOR_PERMISSION_MODE=autonomous  # autonomous, semi, manual
```

**Loading:**

```python
from dotenv import load_dotenv
load_dotenv()
```

---

## Runtime Modes Comparison

| Mode | Purpose | Duration | Use Case |
|------|---------|----------|----------|
| `loop` | Autonomous operation | Infinite | Production |
| `api` | HTTP server | Until stopped | API access |
| `smoke` | Quick verification | Seconds | CI/CD |
| `doctor` | Dependency check | Seconds | Setup |
| `production-check` | Full verification | Minutes | Pre-deploy |
| `memory-repair` | Database repair | Minutes | Recovery |

---

## Boot Sequence Diagram

```
User: python run_vector.py loop
    ↓
[1] Load .env
    ↓
[2] Configure logging
    ↓
[3] Setup exception hooks
    ↓
[4] Parse CLI (mode=loop)
    ↓
[5] Bootstrap agents
    ├─ Load agent_manifest.yaml
    ├─ Import agent classes
    ├─ Instantiate agents
    └─ Register in AgentRegistry
    ↓
[6] Start sidecars
    ├─ ComfyUI (if enabled)
    ├─ HyperFrames (if enabled)
    ├─ Open WebUI (if enabled)
    └─ ShadowBroker (if enabled)
    ↓
[7] Start background services
    ├─ AmbientListener (if enabled)
    ├─ HealthMonitor
    ├─ MemoryConsolidator (2AM)
    └─ TelemetryReporter
    ↓
[8] Start autonomous loop
    ├─ observe_loop (0.5s)
    ├─ think_loop (event-driven)
    ├─ act_loop (permission-gated)
    └─ reflect_loop (2AM)
    ↓
[VECTOR RUNNING]
    ↓
[SIGINT/SIGTERM]
    ↓
[9] Graceful shutdown
    ├─ Stop autonomous loop
    ├─ Stop background services
    ├─ Stop sidecars
    └─ Flush logs
    ↓
[EXIT]
```

---

## Error Handling

### Global Exception Handlers

**File:** `run_vector.py:setup_exception_hooks()`  
**Status:** ✅ IMPLEMENTED

**Strategy:** Never crash, always log and recover

```python
def setup_exception_hooks():
    """Setup global exception handlers."""
    import signal
    import sys
    
    # Signal handlers
    def signal_handler(signum, frame):
        logger.warning(f"Received signal {signum}")
        asyncio.create_task(_graceful_shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Unhandled exception handler
    def exception_handler(loop, context):
        logger.error(f"Unhandled exception: {context['exception']}")
        # Don't crash — log and continue
    
    asyncio.get_event_loop().set_exception_handler(exception_handler)
    
    # Uncaught exception handler
    def uncaught_exception(exc_type, exc_value, exc_traceback):
        logger.error(f"Uncaught exception: {exc_value}", exc_info=(exc_type, exc_value, exc_traceback))
    
    sys.excepthook = uncaught_exception
```

---

## Performance Characteristics

| Phase | Duration | Bottleneck |
|-------|----------|------------|
| Environment load | <100ms | dotenv parsing |
| Logging setup | <10ms | File I/O |
| Agent bootstrap | 1-5s | Agent instantiation (133+ agents) |
| Sidecar startup | 2-10s | Optional, depends on enabled |
| Background services | 1-3s | Voice model loading |
| Loop startup | <100ms | Event loop creation |
| **Total boot time** | **5-20s** | **Agent bootstrap** |

---

## Known Issues

### Issue 1: Agent Bootstrap Slow

**Symptom:** Boot takes 5+ seconds  
**Root Cause:** 133+ agents instantiated sequentially  
**Impact:** Slow startup  
**Workaround:** Parallel instantiation (not yet implemented)  
**Priority:** LOW

### Issue 2: Sidecar Startup Blocking

**Symptom:** Boot hangs if sidecar fails  
**Root Cause:** Synchronous subprocess.Popen  
**Impact:** Unreliable startup  
**Workaround:** Enable only needed sidecars  
**Priority:** LOW

### Issue 3: Voice Model Loading

**Symptom:** AmbientListener fails to start  
**Root Cause:** Kokoro model not downloaded  
**Impact:** Voice features disabled  
**Workaround:** Download Kokoro model or disable voice  
**Priority:** MEDIUM

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop architecture
- `27_OBSERVABILITY.md` — Logging and monitoring
- `29_CONFIGURATION.md` — Configuration details
- `30_DEPLOYMENT.md` — Deployment procedures

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
