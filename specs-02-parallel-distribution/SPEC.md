# SPEC-02: Parallel Distribution & Event-Driven Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's monolithic sequential loop into an event-driven microservice mesh handling 10+ concurrent tasks with sub-100ms event delivery, autonomous worker scaling, and zero single points of failure.

**Architecture:** Replace `asyncio.gather` with a Redis pub/sub event bus. Slice `core/` into 6 independent services (voice, research, security, memory, inference, communications) each running in their own process/thread pool. An orchestrator replaces `autonomous_loop.py` — event-driven, no polling, horizontal scaling.

**Tech Stack:** Redis (pub/sub + streams), FastAPI (API gateway), asyncio (worker pools), Pydantic (event schemas), loguru (distributed tracing), Docker Compose (service orchestration)

**Score:** Current 12/100 → Target 85/100

---

## 1. Problem Statement

### 1.1 Current Limitations

Parallel processing scores 12/100 across five dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Task Concurrency | 10/100 | `asyncio.gather` runs 11 coroutines but the `think_loop` processes one decision at a time. Voice, research, coding, security all block on the single think→act pipeline. |
| Throughput | 15/100 | Maximum 2 think cycles per minute (10s evaluate cycle). Cannot handle overlapping intents — if voice requests weather while research is running, the research blocks the weather. |
| Fault Isolation | 20/100 | A crash in voice (e.g., Whisper OOM) can bring down the entire process. `return_exceptions=True` helps but one coroutine's memory leak or deadlock blocks all. |
| Scaling | 0/100 | All code runs in one Python process on one machine. Zero horizontal scaling. Cannot distribute work to other machines (phone node, edge devices). |
| State Sharing | 15/100 | Components share state via lazy-loaded singletons (`_get_context()`, `_get_goals()`). No isolation — one component's mutation affects all. No formal message passing. |

### 1.2 Root Causes

1. **Sequential think loop:** `_think_tick()` evaluates 4 candidates, picks a winner, executes `_act_on()`, then waits 10 seconds. During those 10 seconds, all other coroutines (`observe_loop`, `reflect_loop`, etc.) wait for the think to complete. The `asyncio.gather` concurrency is illusionary — the think loop is the bottleneck.

2. **Shared process space:** Everything from voice to trading to security runs in one Python process. A 30-second blocking call in `vector_hedgebot` (e.g., API request) blocks the voice response.

3. **No event system:** The only inter-component communication is through mutable instance state (`self._pending_voice`, `self._gateway`, etc.). No producer/consumer pattern, no pub/sub, no message queues.

4. **Polling, not event-driven:** `observe_loop` polls at 0.5s, `think_loop` at 10s, `scheduler_loop` at 30s, `reflect_loop` at 24h. Everything is timer-based, even when events are available immediately (e.g., voice intent ready immediately after classification).

### 1.3 Measured Impact

- Voice intent → action: 2-5s (research is the bottleneck, not voice)
- WebSocket response during heavy research: timeout failures (30s+)
- Simultaneous requests: max 1 (sequential processing)
- CPU utilization during idle: ~15% (polling overhead)
- CPU utilization during load: unable to saturate (blocked on LLM I/O)
- Memory: single process, single Python GIL

---

## 2. Current Architecture

### 2.1 Process Model

```
┌────────────────────────────────────────────────────────────────┐
│                   Single Python Process                         │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              AutonomousLoop.run_forever()                  │  │
│  │                                                           │  │
│  │  asyncio.gather(                                          │  │
│  │    observe_loop(),       # 0.5s timer poll                │  │
│  │    think_loop(),         # 10s timer, ONE decision        │  │
│  │    reflect_loop(),      # 24h timer                       │  │
│  │    sync_loop(),         # 48h timer                       │  │
│  │    obsidian_loop(),     # file watcher                    │  │
│  │    phone_loop(),        # 60s timer                       │  │
│  │    vectorcode_loop(),   # MCP server lifecycle            │  │
│  │    scheduler_loop(),    # 30s timer                       │  │
│  │    ambient_scheduler_loop(), # 60s timer                  │  │
│  │    hypothesis_loop(),   # 4h timer                        │  │
│  │  )                                                        │  │
│  │                                                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐      │  │
│  │  │ Voice STT   │  │ Whisper     │  │ Kokoro TTS   │      │  │
│  │  │ Thread pool │  │ GPU process │  │ Thread pool  │      │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘      │  │
│  │                                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │  │
│  │  │ Ollama calls │  │ SQLite DB    │  │ HTTP clients │    │  │
│  │  │ (httpx I/O)  │  │ (aiofiles)   │  │ (polling)    │    │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  MEMORY: ~2-4GB RSS (Whisper: 4GB VRAM, Kokoro: 1GB)          │
│  CPU: ~15% idle, ~60% under load (GIL-bound)                  │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Files

| File | Role | Lines | Concurrency Model |
|------|------|-------|-------------------|
| `core/loop/autonomous_loop.py` | Main loop orchestrator | 958 | asyncio.gather, 10 coroutines |
| `core/loop/decision_engine.py` | Scoring 4 candidates | 397 | Synchronous, single-threaded |
| `core/loop/context_engine.py` | World state builder | 358 | Synchronous, blocking OCR |
| `core/loop/workflow_runner.py` | DAG workflow executor | ~200 | Sequential DAG steps |
| `core/loop/task_queue.py` | Background task queue | ~150 | asyncio.Queue, limited concurrency |
| `core/loop/cron_jobs.py` | Scheduled job registry | ~100 | Timer-based |
| `core/voice/ambient_listener.py` | Voice orchestrator | 476 | Blocking pipeline |
| `core/mcp_server.py` | MCP tool server | 1254 | FastMCP per-request handling |
| `core/api/routers/*.py` | FastAPI endpoints | 50-200 each | Per-request async |

### 2.3 Thread Pool Usage

| Thread Pool | Used By | Purpose | Max Workers |
|-------------|---------|---------|-------------|
| `asyncio.to_thread` | stt.py | Whisper transcription | 1 (blocking) |
| `asyncio.to_thread` | tts.py | Kokoro TTS generation | 1 (blocking) |
| `asyncio.to_thread` | ambient_listener | record_and_transcribe | 1 (blocking) |
| Default executor | FastAPI | CPU-bound route handlers | configurable (default min=5) |

---

## 3. Target Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         API Gateway (FastAPI)                           │
│                         port 8000                                       │
│  HTTP REST + WebSocket                                                  │
└────────┬────────────────────────┬─────────────────┬────────────────────┘
         │                        │                  │
         ▼                        ▼                  ▼
┌─────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  Event Bus       │   │  Event Bus       │   │  Event Bus       │
│  (Redis)         │   │  (Redis)         │   │  (Redis)         │
│  pub/sub +       │   │  streams         │   │  consumer groups │
│  streams         │   │                  │   │                  │
└─────────────────┘   └──────────────────┘   └──────────────────┘
         │                        │                  │
         ▼                        ▼                  ▼
┌─────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐
│ voice_svc   │  │ research_  │  │ security_  │  │ memory_svc  │
│ (port 8101) │  │ svc (8102) │  │ svc (8103) │  │ (port 8104) │
│ 2 workers   │  │ 3 workers  │  │ 1 worker   │  │ 2 workers   │
├─────────────┤  ├────────────┤  ├────────────┤  ├─────────────┤
│ wake/STT    │  │ web search │  │ threat     │  │ episodic    │
│ TTS         │  │ arxiv      │  │ scan       │  │ policy      │
│ speaker ID  │  │ digest     │  │ malware    │  │ ghost       │
│ lang detect │  │ hypothesis │  │ detection  │  │ obsidian    │
└─────────────┘  └────────────┘  └────────────┘  └─────────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ inference_svc│  │ communic-   │  │ health_      │  │ orchestrator │
│ (port 8105)  │  │ ations_svc  │  │ registry     │  │ (port 8099)  │
│ 4 workers    │  │ (port 8106) │  │ (port 8107)  │  │ 1 worker     │
├──────────────┤  ├──────────────┤  ├──────────────┤  ├──────────────┤
│ ollama calls │  │ telegram     │  │ service disc │  │ event router │
│ model router │  │ whatsapp     │  │ health polls │  │ workflow mgr │
│ LLM chain    │  │ email        │  │ metrics      │  │ goal monitor │
│ reasoning    │  │ pushover     │  │ leaderboard  │  │ dead letter  │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### 3.2 Event Bus Design (Redis)

```python
# ── Event Schema ────────────────────────────────────────────────────────

@dataclass
class VectorEvent:
    """Base event — all events must inherit from this."""
    event_id: str               # uuid4
    event_type: str             # "voice.transcript_ready"
    source: str                 # "voice_svc"
    timestamp: float            # time.time()
    ttl_seconds: int = 300      # auto-expire after 5 min
    correlation_id: str | None = None  # for tracing request chains
    payload: dict = field(default_factory=dict)


# ── Event Types (Typed) ─────────────────────────────────────────────────

class VoiceTranscriptReady(VectorEvent):
    event_type: str = "voice.transcript_ready"
    payload: dict = {
        "text": str,
        "session_id": str,
        "speaker": str,
        "confidence": float,
        "language": str,
    }

class VoiceIntentReady(VectorEvent):
    event_type: str = "voice.intent_ready"
    payload: dict = {
        "intents": list,      # list of {action_type, params, confidence}
        "transcript": str,
        "session_id": str,
    }

class ResearchRequest(VectorEvent):
    event_type: str = "research.request"
    payload: dict = {
        "query": str,
        "sources": list,      # ["web", "arxiv", "news"]
        "max_results": int,
        "callback_topic": str | None,  # optional: publish results here
    }

class ResearchResult(VectorEvent):
    event_type: str = "research.result"
    payload: dict = {
        "query": str,
        "results": list,
        "confidence": float,
    }

class SecurityAlert(VectorEvent):
    event_type: str = "security.alert"
    payload: dict = {
        "alert_type": str,    # "malware", "intrusion", "phishing"
        "severity": float,
        "details": dict,
    }

class CodeTask(VectorEvent):
    event_type: str = "code.task"
    payload: dict = {
        "action": str,        # "review", "fix", "generate"
        "files": list[str],
        "description": str,
    }

class MemoryStore(VectorEvent):
    event_type: str = "memory.store"
    payload: dict = {
        "event_type": str,
        "content": str,
        "tags": list[str],
        "source": str,
        "importance": str,
    }

class InferenceRequest(VectorEvent):
    event_type: str = "inference.request"
    payload: dict = {
        "model": str,
        "messages": list[dict],
        "options": dict,
        "timeout": float,
    }

class InferenceResult(VectorEvent):
    event_type: str = "inference.result"
    payload: dict = {
        "request_id": str,
        "content": str,
        "model": str,
        "latency_ms": float,
        "tokens_in": int,
        "tokens_out": int,
    }


# ── Redis Event Bus ──────────────────────────────────────────────────────

class EventBus:
    """
    Central message backbone using Redis pub/sub + streams.

    PUB/SUB: For broadcast events (state changes, alerts).
      - Any number of subscribers
      - Ephemeral — if subscriber is down, message is lost
      - Prefix: "vector:pub:"

    STREAMS + CONSUMER GROUPS: For task distribution.
      - Each event type has its own stream
      - Consumer groups distribute work across workers
      - Persistent — messages stay until acknowledged
      - Prefix: "vector:stream:"

    Pattern:
      Producer: bus.publish(VoiceTranscriptReady(...))
      Consumer: bus.subscribe("voice.transcript_ready", handler_fn)

    Connection pooling: single Redis connection pool per service.
    """
```

### 3.3 Service Definitions

**voice_svc** (port 8101):
- Subscribes to: `inference.result` (for TTS calls), `voice.transcript_ready` (self-published)
- Publishes: `voice.transcript_ready`, `voice.intent_ready`, `inference.request`
- Workers: 2 (one for STT, one for TTS + classify)
- Dependencies: Whisper (GPU), Kokoro (CPU), Redis
- Startup: `python core/services/voice_svc/main.py`

**research_svc** (port 8102):
- Subscribes to: `research.request`
- Publishes: `research.result`, `memory.store`
- Workers: 3 (web search, arxiv, news — parallel)
- Dependencies: httpx, Redis
- Startup: `python core/services/research_svc/main.py`

**security_svc** (port 8103):
- Subscribes to: periodic scan triggers, file change events from obsidian_svc
- Publishes: `security.alert`, `memory.store`
- Workers: 1 (lightweight, most work is async I/O)
- Dependencies: psutil, Redis
- Startup: `python core/services/security_svc/main.py`

**memory_svc** (port 8104):
- Subscribes to: `memory.store`, `memory.recall`
- Publishes: `memory.recall_result`
- Workers: 2 (one for writes, one for reads)
- Dependencies: SQLite (or Turso), Redis
- Startup: `python core/services/memory_svc/main.py`

**inference_svc** (port 8105):
- Subscribes to: `inference.request`
- Publishes: `inference.result`
- Workers: 4 (LLM calls are I/O-bound, 4 concurrent Ollama calls)
- Dependencies: Ollama (HTTP), Redis
- Startup: `python core/services/inference_svc/main.py`

**communications_svc** (port 8106):
- Subscribes to: `comms.send`, voice intents that need notification
- Publishes: `comms.status`, `memory.store`
- Workers: 2 (Telegram, WhatsApp, email — parallel channels)
- Dependencies: httpx, Redis
- Startup: `python core/services/comms_svc/main.py`

### 3.4 Orchestrator

**File:** `core/services/orchestrator/main.py` (new, ~400 lines)

Replaces `autonomous_loop.py` as the central coordination point. Event-driven, no polling loops.

```python
class Orchestrator:
    """
    Central event coordinator. Replaces AutonomousLoop.run_forever().

    Responsibilities:
      1. Route events to correct services (via event bus)
      2. Monitor service health (via HealthRegistry)
      3. Track active goals and trigger evaluation on state changes
      4. Handle dead-letter queue (retry failed events)
      5. Schedule recurring tasks (replaces cron-driven loops)
      6. Maintain correlation IDs for request tracing

    Architecture:
      - Single asyncio process (lightweight, no blocking I/O)
      - Listens to ALL event types
      - Routes events based on subscription registry
      - Fires scheduled tasks via asyncio (no polling)

    Loops replaced:
      - observe_loop → SpeechStreamer publishes audio chunks directly
      - think_loop → GoalGuard triggers evaluation on goal state change
      - scheduler_loop → Orchestrator fires due tasks
      - reflect_loop → Orchestrator schedules 2AM task
      - sync_loop → Orchestrator schedules 48h task
      - hypothesis_loop → Orchestrator schedules 4h task
      - ambient_scheduler_loop → Orchestrator's scheduled task runner
    """
```

### 3.5 API Gateway

**File:** `core/api/gateway.py` (modified from existing `api/app.py`)

```python
class APIGateway:
    """
    FastAPI application that serves as the external entry point.

    Routes:
      /api/v1/* → proxy to internal services via HTTP
      /ws/* → WebSocket endpoints, publish events to bus

    Internal service discovery via HealthRegistry:
      GET /api/v1/voice/transcribe → voice_svc:8101
      GET /api/v1/research/search → research_svc:8102

    Rate limiting per endpoint (Redis-based sliding window):
      60 req/min for voice, 30 req/min for research, 10 req/min for inference
    """
```

### 3.6 HealthRegistry

**File:** `core/services/health_registry/main.py` (new, ~200 lines)

```python
class HealthRegistry:
    """
    Service discovery + health check coordinator.

    Each service must:
      1. Register on startup (POST /register)
      2. Send heartbeats every 15s
      3. Deregister on shutdown

    HealthRegistry exposes:
      GET /status → JSON list of all services and their state
      GET /status/{service_name} → single service detail
      POST /register → register a service
      POST /heartbeat → update heartbeat timestamp

    State machine:
      REGISTERED → ONLINE (first heartbeat) → DEGRADED (missed 2 heartbeats) → OFFLINE (missed 5)
    """
```

---

## 4. Component Breakdown

### 4.1 EventBus

**Files:**
- `core/event_bus/__init__.py` — exports
- `core/event_bus/redis_bus.py` — Redis pub/sub + streams implementation
- `core/event_bus/types.py` — all typed event dataclasses
- `core/event_bus/base.py` — abstract EventBus interface (for testing with in-memory bus)

```python
# core/event_bus/redis_bus.py

class RedisEventBus:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._redis = aioredis.from_url(redis_url, decode_responses=False)

    async def publish(self, event: VectorEvent) -> None:
        """Publish to both pub/sub channel AND stream."""
        channel = f"vector:pub:{event.event_type}"
        stream = f"vector:stream:{event.event_type}"
        payload = self._serialize(event)
        await asyncio.gather(
            self._redis.publish(channel, payload),
            self._redis.xadd(stream, {"data": payload}, maxlen=1000),
        )

    async def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to pub/sub channel. Run in background task."""
        channel = f"vector:pub:{event_type}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                event = self._deserialize(message["data"])
                await handler(event)

    async def stream_subscribe(self, event_type: str, group: str, handler: Callable) -> None:
        """Subscribe to stream with consumer group. Reliable delivery."""
        stream = f"vector:stream:{event_type}"
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except aioredis.ResponseError:
            pass  # group already exists
        while True:
            messages = await self._redis.xreadgroup(group, f"consumer-{uuid4().hex[:8]}",
                                                    {stream: ">"}, count=1, block=1000)
            for stream_name, entries in messages:
                for entry_id, data in entries:
                    event = self._deserialize(data["data"])
                    try:
                        await handler(event)
                        await self._redis.xack(stream, group, entry_id)
                    except Exception:
                        await asyncio.sleep(1)  # retry on next poll

    def _serialize(self, event: VectorEvent) -> bytes:
        return orjson.dumps(asdict(event))

    def _deserialize(self, data: bytes) -> VectorEvent:
        raw = orjson.loads(data)
        event_type = raw["event_type"]
        cls = EVENT_TYPE_MAP.get(event_type)
        if cls is None:
            return VectorEvent(**raw)
        return cls(**raw)
```

### 4.2 Event Types Registry

```python
# core/event_bus/types.py

EVENT_TYPE_MAP: dict[str, type[VectorEvent]] = {
    "voice.transcript_ready": VoiceTranscriptReady,
    "voice.intent_ready": VoiceIntentReady,
    "research.request": ResearchRequest,
    "research.result": ResearchResult,
    "security.alert": SecurityAlert,
    "code.task": CodeTask,
    "memory.store": MemoryStore,
    "memory.recall": MemoryRecallRequest,
    "memory.recall_result": MemoryRecallResult,
    "inference.request": InferenceRequest,
    "inference.result": InferenceResult,
    "comms.send": CommsSend,
    "comms.status": CommsStatus,
    "health.ping": HealthPing,
    "health.pong": HealthPong,
    "goal.update": GoalUpdate,
    "goal.trigger": GoalTrigger,
    "system.shutdown": SystemShutdown,
}
```

### 4.3 AgentWorkerPool

**File:** `core/event_bus/worker_pool.py` (new, ~250 lines)

```python
class AgentWorkerPool:
    """
    Manages a pool of asyncio workers that subscribe to event streams.

    Each worker runs in a background task, reads from a specific event stream,
    processes the event, and acknowledges it.

    Example:
        pool = AgentWorkerPool()
        pool.register("voice.transcript_ready", handle_transcript, workers=3)
        pool.register("research.request", handle_research, workers=4)
        await pool.start()

    Graceful shutdown:
        await pool.stop()
        # Waits for all in-flight events to complete (up to 30s timeout)
    """
```

### 4.4 Microservice Template

**File:** `core/services/service_template.py` (new, ~150 lines) — base class for all services

```python
class MicroService:
    """
    Base class for all microservices.

    Provides:
      - EventBus connection (auto-initialized)
      - HealthRegistry registration (auto on startup)
      - Graceful shutdown (SIGTERM handler)
      - Structured logging with service name tag
      - Config loading from environment + shared config

    Usage:
        class VoiceService(MicroService):
            async def start(self):
                self.bus.subscribe("inference.result", self.handle_inference_result)
                # ...

        if __name__ == "__main__":
            svc = VoiceService(name="voice_svc", port=8101)
            svc.run()
    """
```

### 4.5 Service Extractions

Each service extraction follows this pattern:
1. Create `core/services/{name}/` directory
2. Move relevant modules from `core/` into the service (or import from `core/`)
3. Create `main.py` with MicroService subclass
4. Create `Dockerfile` for containerized deployment
5. Create `docker-compose` entry

**voice_svc** — extracts from `core/voice/`:
- `MicroService` → `VoiceService`
- Subscribes to: nothing initially (self-contained streaming pipeline)
- Publishes: `voice.intent_ready`
- Keeps: `ambient_listener.py`, `stt.py`, `tts.py`, `wake_word.py`, `speaker_id.py`, `streamer.py`

**research_svc** — extracts from `core/research/` (existing) + districts:
- Subscribes to: `research.request`
- Publishes: `research.result`
- Keeps: web search, arxiv, news, arxiv scraping

**inference_svc** — extracts from `core/inference/`:
- Subscribes to: `inference.request`
- Publishes: `inference.result`
- Keeps: `ollama_safe.py`, model routing, provider chain

**memory_svc** — extracts from `core/memory/`:
- Subscribes to: `memory.store`, `memory.recall`
- Publishes: `memory.recall_result`
- Keeps: `episodic.py`, `policy.py`, ghost memory

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: EventBus + Event Schema

**Scope:**
- `core/event_bus/` — RedisEventBus, typed events, worker pool
- Docker Compose Redis service
- Tests: `tests/event_bus/test_redis_bus.py`, `tests/event_bus/test_types.py`

**Files to create:**
- `core/event_bus/__init__.py`
- `core/event_bus/base.py` — abstract EventBus interface
- `core/event_bus/types.py` — all 18+ typed event dataclasses + EVENT_TYPE_MAP
- `core/event_bus/redis_bus.py` — RedisEventBus with pub/sub + streams
- `core/event_bus/worker_pool.py` — AgentWorkerPool
- `tests/event_bus/test_redis_bus.py`
- `tests/event_bus/test_types.py`
- `tests/event_bus/test_worker_pool.py`

**Files to modify:**
- `docker-compose.yml` — add Redis service
- `requirements.txt` — add `redis[hiredis]`, `orjson`

**Key decisions:**
- Redis connection URL: `CONFIG["event_bus"]["redis_url"]` default `redis://localhost:6379`
- Stream maxlen: 1000 per stream (prevents memory growth)
- Consumer group: one per service type (e.g., "voice_svc", "research_svc")
- Retry policy: 3 retries with 1s backoff, then dead-letter stream

### 5.2 Agent B: Worker Pool + Microservice Framework

**Scope:**
- `core/services/service_template.py` — MicroService base class
- `core/services/health_registry/` — HealthRegistry service
- Docker Compose health_registry service
- Tests: `tests/services/test_service_template.py`

**Files to create:**
- `core/services/service_template.py`
- `core/services/health_registry/main.py`
- `core/services/health_registry/__init__.py`
- `tests/services/test_service_template.py`

**Files to modify:**
- `docker-compose.yml` — add health_registry service
- `core/config.py` — add EventBusConfig, HealthConfig sub-models

### 5.3 Agent C: voice_svc Extraction

**Scope:**
- Extract `core/voice/` into independent microservice
- Wire EventBus publishing for voice intents
- Keep backward compatibility for non-event-bus mode

**Files to create:**
- `core/services/voice_svc/main.py`
- `core/services/voice_svc/__init__.py`
- `core/services/voice_svc/Dockerfile`

**Files to modify:**
- `core/voice/ambient_listener.py` — add EventBus publishing
- `core/voice/__init__.py` — expose for import by service

### 5.4 Agent D: research_svc + memory_svc Extraction

**Scope:**
- Extract `core/research/` and `core/memory/` into independent services
- Wire EventBus subscriptions + publishing
- Keep backward compatibility

**Files to create:**
- `core/services/research_svc/main.py`
- `core/services/research_svc/__init__.py`
- `core/services/memory_svc/main.py`
- `core/services/memory_svc/__init__.py`

**Files to modify:**
- `core/memory/episodic.py` — add EventBus integration
- `core/config.py` — add service-specific config

### 5.5 Agent E: API Gateway + Orchestrator Rewrite

**Scope:**
- Modify existing FastAPI app to act as API gateway
- Rewrite `autonomous_loop.py` → orchestrator
- Wire service discovery via HealthRegistry
- Monolith mode (all services in-process) + distributed mode

**Files to create:**
- `core/services/orchestrator/main.py`
- `core/services/orchestrator/__init__.py`
- `core/api/gateway.py` — new API gateway (refactor from existing `app.py`)

**Files to modify:**
- `core/loop/autonomous_loop.py` — deprecate polling loops, add event-driven mode
- `core/api/app.py` — add gateway routing
- `core/api/dependencies.py` — add service discovery dependency
- `run_vector.py` — add orchestrator startup mode

---

## 6. Implementation Steps

### 6.1 Phase 1: Event Bus Foundation (Agent A)

**Step 1.1: Create event types**
- [ ] Create `core/event_bus/types.py` with VectorEvent base + all typed events
- [ ] Define EVENT_TYPE_MAP for deserialization

**Step 1.2: Create EventBus base interface**
- [ ] `core/event_bus/base.py` with abstract publish/subscribe/stream_subscribe
- [ ] `core/event_bus/__init__.py` exports

**Step 1.3: Implement RedisEventBus**
- [ ] `core/event_bus/redis_bus.py` with Redis pub/sub + streams
- [ ] Serialization with orjson (4x faster than stdlib json)
- [ ] Consumer group management for reliable delivery

**Step 1.4: Create WorkerPool**
- [ ] `core/event_bus/worker_pool.py` with configurable worker count
- [ ] Graceful shutdown: drain in-flight tasks

**Step 1.5: Add Redis to Docker Compose**
- [ ] Modify `docker-compose.yml`:
```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
```

**Step 1.6: Test**
- [ ] `tests/event_bus/test_types.py` — serialization roundtrip for all events
- [ ] `tests/event_bus/test_redis_bus.py` — publish/subscribe/stream_subscribe
- [ ] `tests/event_bus/test_worker_pool.py` — worker lifecycle

### 6.2 Phase 2: Service Framework (Agent B)

**Step 2.1: Create MicroService base**
- [ ] `core/services/service_template.py` with lifecycle management
- [ ] HealthRegistry auto-registration on startup
- [ ] Graceful shutdown via signal handlers

**Step 2.2: Create HealthRegistry service**
- [ ] FastAPI app with /register, /heartbeat, /status endpoints
- [ ] In-memory registry with Redis persistence fallback
- [ ] 15s heartbeat interval monitoring

**Step 2.3: Add config sections**
- [ ] `EventBusConfig` in `core/config.py`
- [ ] `ServiceConfig` for each microservice

### 6.3 Phase 3: Service Extractions (Agents C + D)

**Step 3.1: Extract voice_svc**
- [ ] Create `core/services/voice_svc/main.py`
- [ ] Wire `AmbientListener` to publish `voice.intent_ready` via EventBus
- [ ] Test: voice intent appears on event bus

**Step 3.2: Extract research_svc**
- [ ] Create `core/services/research_svc/main.py`
- [ ] Subscribe to `research.request`, publish `research.result`

**Step 3.3: Extract memory_svc**
- [ ] Create `core/services/memory_svc/main.py`
- [ ] Subscribe to `memory.store`, handle reads/writes

### 6.4 Phase 4: Orchestrator + Gateway (Agent E)

**Step 4.1: Create Orchestrator**
- [ ] `core/services/orchestrator/main.py`
- [ ] Event routing based on subscription registry
- [ ] Scheduled task runner (replaces cron jobs)
- [ ] Goal evaluation on state change (not timer)

**Step 4.2: Create API Gateway**
- [ ] `core/api/gateway.py` with service proxy routes
- [ ] Rate limiting via Redis sliding window
- [ ] Service discovery via HealthRegistry

**Step 4.3: Deprecate polling loops**
- [ ] Mark `autonomous_loop.py` as legacy
- [ ] Add "mode" flag: `mode="monolith"` (current) or `mode="distributed"` (new)

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `core/event_bus/__init__.py` | 10 | Package exports |
| `core/event_bus/base.py` | 60 | Abstract EventBus interface |
| `core/event_bus/types.py` | 180 | Typed event dataclasses + registry |
| `core/event_bus/redis_bus.py` | 250 | Redis pub/sub + streams implementation |
| `core/event_bus/worker_pool.py` | 150 | Configurable worker pool |
| `core/services/service_template.py` | 150 | MicroService base class |
| `core/services/health_registry/main.py` | 200 | Health check service |
| `core/services/health_registry/__init__.py` | 5 | Package init |
| `core/services/orchestrator/main.py` | 400 | Event routing + scheduled tasks |
| `core/services/orchestrator/__init__.py` | 5 | Package init |
| `core/services/voice_svc/main.py` | 80 | Voice microservice entrypoint |
| `core/services/voice_svc/__init__.py` | 5 | Package init |
| `core/services/research_svc/main.py` | 80 | Research microservice entrypoint |
| `core/services/research_svc/__init__.py` | 5 | Package init |
| `core/services/memory_svc/main.py` | 80 | Memory microservice entrypoint |
| `core/services/memory_svc/__init__.py` | 5 | Package init |
| `core/services/inference_svc/main.py` | 80 | Inference microservice entrypoint |
| `core/services/inference_svc/__init__.py` | 5 | Package init |
| `core/services/comms_svc/main.py` | 80 | Comms microservice entrypoint |
| `core/services/comms_svc/__init__.py` | 5 | Package init |
| `core/api/gateway.py` | 200 | API gateway with service proxying |
| `tests/event_bus/test_redis_bus.py` | 120 | Event bus tests |
| `tests/event_bus/test_types.py` | 80 | Event serialization tests |
| `tests/event_bus/test_worker_pool.py` | 80 | Worker pool tests |
| `tests/services/test_service_template.py` | 60 | MicroService base tests |

### Modify:

| File | Change |
|------|--------|
| `core/config.py` | Add EventBusConfig, DictConfig for service discovery |
| `core/voice/ambient_listener.py` | Add EventBus publishing |
| `core/voice/__init__.py` | Export for service import |
| `core/memory/episodic.py` | Add EventBus integration |
| `core/loop/autonomous_loop.py` | Add distributed mode flag |
| `core/api/app.py` | Add gateway routing |
| `docker-compose.yml` | Add Redis + health_registry + microservices |
| `run_vector.py` | Add orchestrator startup option |
| `requirements.txt` | Add `redis[hiredis]`, `orjson` |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| Concurrent task handling | 1 | 10+ | Fire 10 simultaneous research requests, measure completion |
| Event delivery latency | N/A | <50ms (p99) | Measure time from publish to subscriber callback |
| Voice → action latency (under load) | 2-5s | <800ms | Fire research request, immediately ask voice question |
| LLM inference concurrency | 1 call at a time | 4 concurrent calls | Fire 4 inference requests simultaneously |
| Fault isolation | Process crash kills all | Single service crash = isolated | Kill voice_svc, verify research_svc continues |
| Service startup time | N/A | <2s | Measure from `docker compose up` to health OK |
| Throughput (research requests/min) | ~6 (one per 10s) | 60+ | Load test with concurrent requests |
| Memory per service | Monolith: 2-4GB | Each service: 200-500MB | `docker stats` after 1h running |
| Orchestrator CPU usage | N/A | <5% idle | Orchestrator should do no heavy work |
| Polling cycles eliminated | 10 timer loops | 0 | Count of asyncio.sleep-based loops in orchestrator |

### 8.2 Functional Criteria

1. Voice intent → event bus → research service → event bus → response works end-to-end
2. Security alert event triggers immediate notification (Pushover/Telegram)
3. Memory store events are persisted within 100ms of publishing
4. Health registry detects offline service within 45s (3 missed heartbeats)
5. Dead-letter queue captures failed events for manual inspection
6. API gateway routes `/api/v1/research/search` to research_svc
7. Rate limit at 60 req/min triggers 429 response correctly
8. Services can run both in Docker and standalone (development mode)

### 8.3 Backward Compatibility

1. `AutonomousLoop.run_forever()` still works in monolith mode
2. All existing `CONFIG["..."]` access patterns work unchanged
3. All existing API routes work through the gateway
4. Voice pipeline works without Redis (fallback to direct calling)
5. All existing tests pass in monolith mode

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Add to requirements.txt:
redis[hiredis]>=5.1.0      # Redis client with C parser for speed
orjson>=3.9.0               # Fast JSON serialization (4x stdlib)
httpx>=0.27.0               # Already present — service-to-service HTTP
```

### 9.2 Infrastructure

- **Redis 7+** — must be running for distributed mode
- Docker Compose — for multi-service orchestration
- Optional: Docker for containerized deployments

### 9.3 Internal Dependencies

1. **specs-01 (Voice Pipeline):** The event bus needs voice events (`voice.transcript_ready`, `voice.intent_ready`) to demonstrate the value. However, the event bus itself is independent and can be built/tested first.
2. **specs-03 (Personality Engine):** Personality updates can be event-driven (`personality.tone_update`) once the event bus exists.
3. **Core config:** `EventBusConfig` must be added to `core/config.py` before services can read Redis URL.

### 9.4 Migration Path

```
Phase 1: Monolith + EventBus (current loop still runs, publishes events)
Phase 2: EventBus → one extracted service (voice_svc runs standalone)
Phase 3: All services extracted (monolith becomes orchestrator)
Phase 4: Orchestrator replaces autonomous_loop (no more polling)
Phase 5: Containerized deployment (Docker Compose for all services)
```

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Redis becomes SPOF | Low | High | Redis Sentinel fallback; in-memory EventBus for dev |
| Event bus adds latency to voice path | Medium | High | Pub/sub is <1ms; benchmark before production |
| Service extraction breaks imports | High | Medium | Keep `core/voice/` importable; add shim layer |
| Docker overhead on Legion Pro 5 | Medium | Low | Services can run bare-metal; Docker is optional |
| Orchestrator replaces working loop | Low | High | Phase 4 is last; monolith mode always available |
| Redis OOM with stream buffer | Low | Medium | Maxlen=1000 on all streams; monitor with `INFO` |

---

## 11. Appendix: Service Communication Diagram

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  WebSocket  │     │  HTTP REST  │     │  Dashboard  │
│  (voice)    │     │  (API)      │     │  (UI)       │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────┐
│                 API Gateway (port 8000)               │
│  FastAPI + rate limiting + auth + service proxy      │
└──────┬──────────────────────┬──────────────────┬─────┘
       │                      │                  │
       ▼                      ▼                  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ voice_svc    │    │ research_svc │    │ inference_svc│
│ 8101         │    │ 8102         │    │ 8105         │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ STT GPU      │    │ web search   │    │ ollama_host  │
│ TTS CPU      │    │ arxiv        │    │ model router │
│ speaker ID   │    │ news         │    │ provider chn │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │     Redis        │
                  │  Event Bus       │
                  │  pub/sub +       │
                  │  streams         │
                  └──────────────────┘
                           ▲
                           │
                  ┌────────┴────────┐
                  │                 │
         ┌────────┴───┐    ┌───────┴──────┐
         │ memory_svc │    │ comms_svc    │
         │ 8104       │    │ 8106         │
         ├────────────┤    ├──────────────┤
         │ episodic   │    │ telegram     │
         │ policy     │    │ whatsapp     │
         │ ghost      │    │ email        │
         └────────────┘    └──────────────┘
```

### Service Dependency Graph

```
                 ┌──────────────┐
                 │  API Gateway │
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
          ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │voice_svc │  │research  │  │inference │
   │          │  │_svc      │  │_svc      │
   │ needs:   │  │ needs:   │  │ needs:   │
   │ inference│  │ memory   │  │ (stand-  │
   │ memory   │  │          │  │ alone)   │
   └──────────┘  └──────────┘  └──────────┘
        │              │
        └──────┬───────┘
               ▼
        ┌──────────┐
        │memory_svc│
        │ (stand-  │
        │ alone)   │
        └──────────┘
```
