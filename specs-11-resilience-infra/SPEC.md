# SPEC-11: Resilience Infrastructure — Circuit Breakers, Chaos Engineering, Hot Failover

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's resilience from 50/100 to 95/100 — circuit breakers on every external call, bulkhead isolation between services, hot-hot failover to a cloud secondary, and chaos engineering that proactively finds weaknesses.

**Architecture:** Wrap every external dependency (Ollama, API calls, database) in a 3-state circuit breaker with configurable thresholds and automatic half-open recovery. Isolate service pools via bulkhead pattern so one failing service doesn't starve others. Deploy a secondary VECTOR instance on Fly.io that mirrors state and takes over within 10s of primary heartbeat failure. Run scheduled chaos experiments that inject failures (kill processes, exhaust memory, throttle CPU, drop packets) and verify automated recovery. Implement graceful degradation tiers so VECTOR degrades functionality rather than crashing entirely. Build automated recovery playbooks for the top 10 failure modes.

**Tech Stack:** asyncio, Docker, Fly.io (secondary), iptables/netsh (network chaos), psutil, prometheus_client, httpx, structlog

**Score:** Current 50/100 → Target 95/100

---

## 1. Problem Statement

### 1.1 Current Limitations

Resilience scores 50/100 across six dimensions:

| Dimension | Score | Issue |
|-----------|-------|--------|
| Crash Recovery | 75/100 | Session persistence works. Loop guard restarts the autonomous loop. Agent rebirth creates new gen from ghost memory. Error classifier routes exceptions. Good baseline. |
| External Dependency Handling | 30/100 | If Ollama goes down, VECTOR crashes. If any API call fails, the calling task fails. No circuit breakers, no retry with backoff, no caching of last-known-good responses. |
| Resource Isolation | 20/100 | All services share the same thread pool, same event loop, same process. A memory leak in the research engine can starve the voice pipeline. One OOM kills everything. |
| Single Point of Failure | 0/100 | One laptop. If the laptop crashes, power goes out, or network drops — VECTOR is dead. No secondary instance, no warm standby, no state mirroring. |
| Chaos Resilience | 0/100 | No proactive failure testing. Weaknesses are discovered in production when real failures happen. No failure injection, no fault tolerance verification. |
| Graceful Degradation | 40/100 | Some fallback chains exist (Ollama → cloud → offline mode) but no tiered service levels. GPU OOM kills inference entirely rather than falling back to CPU with a smaller model. |

### 1.2 Root Causes

1. **No circuit breaker pattern:** Every external call is a direct invocation. No state tracking, no thresholds, no automatic recovery.
2. **Single thread pool:** The asyncio event loop runs everything. A slow operation blocks all other operations.
3. **Single instance:** VECTOR runs on one machine. No heartbeat, no failover, no state replication.
4. **No failure injection:** No automated chaos experiments. Recovery code is untested.
5. **Binary degradation:** Either full functionality or nothing. No graceful reduction in service quality.
6. **No recovery playbooks:** When failures happen (model crash, DB corruption, OOM), recovery is manual.

### 1.3 Impact

- If Ollama crashes during a voice conversation, the user gets a silent timeout
- A memory leak in any subsystem can bring down all of VECTOR
- Power outage = complete service loss for hours
- Recovery from known failure modes requires manual intervention
- No confidence that recovery code actually works until a real disaster happens
- Single laptop limits total uptime to hardware reliability (~99.9% at best)

---

## 2. Current Architecture

### 2.1 Existing Resilience Mechanisms

```
Core Recovery:
  AutonomousLoop._loop_guard()
    → detects loop exit → restarts
  SessionPersistence
    → saves session state to SQLite every 30s
    → recovers on restart
  ErrorClassifier
    → categorizes exceptions
    → routes to appropriate handler

Agent Rebirth (Evolution):
  EvolutionEngine.handle_agent_death()
    → ghost_memory = agent.extract_ghost()
    → new_agent = spawn_generation(ghost_memory)
    → only if HP == 0

Fallback Chains:
  inference_fallback:
    Ollama → cloud API → cached response → error message
  stt_fallback:
    faster-whisper → whisper → deepgram → error
  tts_fallback:
    Kokoro → pyttsx3 → gTTS → error message
```

### 2.2 Key Files

| File | Role | Lines |
|------|------|-------|
| `core/loop/autonomous_loop.py` | Loop guard, error classification, lifecycle | ~600 |
| `core/city/evolution_engine.py` | Agent rebirth, ghost memory | ~350 |
| `core/inference/ollama_safe.py` | Ollama client with retries | ~200 |
| `core/config.py` | Config models (50+ sub-configs) | ~1200 |
| `core/loop/session_persistence.py` | SQLite session save/load | ~200 |
| `core/inference/fallback_manager.py` | Inference fallback chains | ~150 |

### 2.3 Current Failure Handling

```
Ollama call → ollama_safe.chat()
  → retry(3, exponential_backoff)
  → if all fail: fallback_manager.cloud_fallback()
  → if cloud fails: cached_response() or error
  → BUT: no circuit breaker, no state tracking of consecutive failures
  →         no bulkhead — Ollama call blocks the event loop

Process crash → loop guard detects exit
  → logs error → restarts loop
  → session persistence recovers state
  → BUT: in-flight requests are lost
  →         no health check on dependencies before restart

Memory OOM → entire process killed by OS
  → systemd/docker restarts container
  → BUT: no warning before OOM
  →         no graceful degradation (lower model size, reduce batch)
```

---

## 3. Target Architecture

### 3.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Resilience Layer                                    │
│                                                                          │
│  Every External Call → CircuitBreaker → BulkheadExecutor → Target        │
│                              │                                            │
│                         [closed/half-open/open]                          │
│                              │                                            │
│  Health Monitor ────────► Heartbeat ────────► Hot Failover (Fly.io)      │
│       │                        │                                         │
│       ▼                        ▼                                         │
│  ChaosMonkey ─────► Inject Failure ───► Verify Recovery                  │
│       │                                                                  │
│       ▼                                                                  │
│  GracefulDegradation ──► tiered_service_level()                          │
│       │                                                                  │
│       ▼                                                                  │
│  RecoveryPlaybooks ──► auto_recover(failure_type)                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Service Bulkheads

```
┌──────────────────────────────────────────────────────────────────┐
│                      BulkheadExecutor                              │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐              │
│  │ Voice Pool  │  │ Inference    │  │ Research    │              │
│  │ (4 workers) │  │ Pool         │  │ Pool        │              │
│  │             │  │ (2 workers)  │  │ (1 worker)  │              │
│  ├─────────────┤  ├──────────────┤  ├─────────────┤              │
│  │ VAD         │  │ Ollama       │  │ Web search  │              │
│  │ ASR         │  │ Cloud API    │  │ Paper fetch │              │
│  │ TTS         │  │ Embeddings   │  │ Code exec   │              │
│  │ Speaker ID  │  │              │  │             │              │
│  └─────────────┘  └──────────────┘  └─────────────┘              │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐              │
│  │ Memory Pool │  │ Comms Pool   │  │ Admin Pool  │              │
│  │ (2 workers) │  │ (2 workers)  │  │ (1 worker)  │              │
│  ├─────────────┤  ├──────────────┤  ├─────────────┤              │
│  │ SQLite      │  │ Telegram     │  │ Config      │              │
│  │ Redis       │  │ Email        │  │ Health      │              │
│  │ Vector DB   │  │ WebSocket    │  │ Metrics     │              │
│  └─────────────┘  └──────────────┘  └─────────────┘              │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 State Machine: Circuit Breaker

```
                  ┌──────────────┐
                  │   CLOSED     │  Normal operation. Calls pass through.
                  │   (normal)   │  Failure count = 0.
                  └──────┬───────┘
                         │ failure_threshold exceeded (default: 5 consecutive)
                  ┌──────▼───────┐
                  │    OPEN      │  Calls rejected immediately.
                  │   (tripped)  │  Failure count = threshold.
                  └──────┬───────┘
                         │ timeout_sec elapsed (default: 30)
                  ┌──────▼───────┐
                  │  HALF-OPEN   │  Probe call allowed.
                  │   (probing)  │  Other calls still rejected.
                  └──────┬───────┘
                    ┌────┴────┐
                  success   failure
                    │         │
                    ▼         ▼
                CLOSED     OPEN
           (count reset)  (reset timeout)
```

### 3.4 Graceful Degradation Tiers

```
Level 5 (FULL): All services operational. GPU models, streaming, real-time.
Level 4 (REDUCED): GPU memory constrained. Smaller models, reduced batch.
Level 3 (DEGRADED): GPU unavailable. CPU inference, larger latency.
Level 2 (MINIMAL): Ollama unavailable. Cloud API fallback, cached responses.
Level 1 (EMERGENCY): Network unavailable. Offline mode, local responses only.
Level 0 (SURVIVAL): Critical infrastructure only. Heartbeat, state sync, no user interaction.

Current capability detection:
  GPU: check torch.cuda.is_available(), memory usage, OOM history
  Ollama: check /api/tags response, recent failure rate
  Network: check connectivity to cloud APIs, DNS resolution
  Disk: check free space, write latency
  Memory: check RAM usage, swap usage, OOM score
```

### 3.5 Failure Injection Taxonomy

```
ChaosMonkey Failure Types:

Process Level:
  - kill_process(name) — kill specific VECTOR subprocess
  - crash_thread(pool) — crash a bulkhead thread
  - oom_process() — allocate memory until near OOM

Network Level:
  - drop_packets(host, percentage) — drop N% of packets to target
  - delay_packets(host, ms) — add latency to target
  - block_port(port) — block specific port
  - dns_failure(domain) — make DNS resolution fail

Resource Level:
  - exhaust_cpu(percentage, duration) — burn CPU cycles
  - exhaust_memory(mb) — allocate memory
  - exhaust_disk(mb) — fill disk space
  - throttle_io(limit) — limit disk IOPS

Dependency Level:
  - corrupt_file(path) — corrupt a database file
  - drop_table() — simulate DB corruption (on replica)
  - return_error(endpoint) — make API return 500
  - slow_response(endpoint, ms) — make API respond slowly
```

---

## 4. Component Breakdown

### 4.1 CircuitBreaker

**File:** `core/resilience/circuit_breaker.py`

**Purpose:** Wrap all external calls with state tracking, automatic tripping, and recovery probing.

**Key Methods:**

```python
class CircuitBreakerState(Enum):
    CLOSED = "closed"         # Normal operation
    OPEN = "open"             # Tripped — fast-fail
    HALF_OPEN = "half_open"   # Probing for recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_s: float = 30.0
    half_open_max_calls: int = 1
    success_threshold: int = 2         # consecutive successes to close

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.last_success_time: float | None = None
        self.config = config

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Call fn with circuit breaker protection."""

    async def _do_call(self, fn: Callable, *args, **kwargs) -> Any:
        """Execute the call and track success/failure."""

    def _on_success(self):
        self.failure_count = 0
        self.success_count += 1
        if self.state == CircuitBreakerState.HALF_OPEN and self.success_count >= self.config.success_threshold:
            self.state = CircuitBreakerState.CLOSED
            self.success_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.success_count = 0
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = time.time()

    def get_state(self) -> CircuitBreakerState:
        """Current state with automatic half-open transition on timeout."""

class CircuitBreakerRegistry:
    """Singleton registry of all circuit breakers. Exposes metrics for monitoring."""
    
    def register(self, name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
    def get(self, name: str) -> CircuitBreaker:
    def all_states(self) -> dict[str, CircuitBreakerState]:
    def metrics(self) -> dict:  # Failure rates, state changes, current states
```

**Configuration per service (in `core/config.py`):**
```python
@dataclass
class CircuitBreakerConfig:
    ollama: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=5, timeout=30)
    cloud_api: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=60)
    memory_db: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=10)
    vector_db: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=15)
    research_web: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=60)
    voice_asr: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=15)
    voice_tts: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=15)
    telegram: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=30)
    email: CircuitBreakerConfigItem = CircuitBreakerConfigItem(threshold=3, timeout=30)
```

**Integration Pattern:**
```python
# Before:
response = await ollama_client.chat(messages)

# After:
breaker = circuit_breakers.get("ollama")
response = await breaker.call(ollama_client.chat, messages)
```

### 4.2 BulkheadExecutor

**File:** `core/resilience/bulkhead_executor.py`

**Purpose:** Isolate service pools so one failing service cannot starve others.

**Key Methods:**

```python
class BulkheadConfig:
    voice: int = 4      # max concurrent voice operations
    inference: int = 2   # max concurrent inference calls
    research: int = 1    # max concurrent research operations
    memory: int = 2      # max concurrent memory operations
    comms: int = 2       # max concurrent communication operations
    admin: int = 1       # max concurrent admin operations

class BulkheadExecutor:
    def __init__(self, config: BulkheadConfig):
        self.pools: dict[str, asyncio.Semaphore] = {
            "voice": asyncio.Semaphore(config.voice),
            "inference": asyncio.Semaphore(config.inference),
            "research": asyncio.Semaphore(config.research),
            "memory": asyncio.Semaphore(config.memory),
            "comms": asyncio.Semaphore(config.comms),
            "admin": asyncio.Semaphore(config.admin),
        }
        self.queues: dict[str, asyncio.Queue] = {
            pool: asyncio.Queue(maxsize=100) for pool in self.pools
        }
        self.active_counts: dict[str, int] = {pool: 0 for pool in self.pools}

    async def execute(self, pool: str, fn: Callable, *args, **kwargs) -> Any:
        """Execute fn in the given pool. If pool is full, wait (with timeout)."""

    async def execute_or_fallback(self, pool: str, fn: Callable, fallback: Callable, *args, **kwargs) -> Any:
        """Try to execute; if pool timeout, run fallback immediately."""

    def get_active_counts(self) -> dict[str, int]:
        """Current active operations per pool for monitoring."""

    def get_queue_sizes(self) -> dict[str, int]:
        """Current queue depths per pool for monitoring."""
```

**Integration:**
```python
# Before:
result = await research_engine.analyze(topic)

# After:
result = await bulkhead.execute("research", research_engine.analyze, topic)
```

### 4.3 HotFailover

**File:** `core/resilience/hot_failover.py`

**Purpose:** Run a secondary VECTOR instance on Fly.io (or other cloud) that mirrors state and takes over on primary failure.

**Key Methods:**

```python
class HotFailover:
    def __init__(self):
        self.primary_id = self._get_machine_id()
        self.secondary_url = config.failover.secondary_url
        self.heartbeat_interval_s = 5.0
        self.missed_heartbeats = 0
        self.max_missed_heartbeats = 3  # 15s without heartbeat = failover

    async def start_primary(self):
        """Primary: start heartbeat sender and state mirroring."""

    async def start_secondary(self):
        """Secondary: start heartbeat listener. If primary heartbeat lost, take over."""

    async def send_heartbeat(self):
        """Primary: POST heartbeat + state digest to secondary endpoint."""

    async def listen_heartbeat(self):
        """Secondary: listen for heartbeats from primary."""

    async def take_over(self):
        """Secondary: promote to primary. Load state, start services."""

    async def relinquish(self):
        """Primary: on recovery, sync state back, then step down or become secondary."""

    @dataclass
    class StateDigest:
        timestamp: float
        loop_state: dict          # current autonomous loop state
        active_sessions: list     # active voice/chat sessions
        memory_pending: int       # pending memory writes
        circuit_breaker_states: dict
        bulkhead_active_counts: dict
        generation: int           # evolution generation
        config_hash: str          # detect config drift
```

**State Mirroring:**
```
Primary → Secondary (every 5s):
  POST /api/v1/failover/heartbeat
  Body: StateDigest JSON

Primary stores:
  - Episodic memory (SQLite → WAL mode, continuous replication)
  - Policy memory (RL table → WAL replication)
  - Session state (session_persistence → WAL replication)

On failover:
  1. Secondary detects 3 missed heartbeats (15s)
  2. Secondary loads last known state digest
  3. Secondary replays any pending memory writes from WAL
  4. Secondary promotes to primary: start autonomous loop, start services
  5. Secondary sends alert: "Failover complete. Primary at <ip> is down."
  6. All user requests now route to secondary

On primary recovery:
  1. Primary detects secondary is active
  2. Primary syncs state FROM secondary (catch up on missed changes)
  3. Primary either becomes secondary or waits for manual promote
```

### 4.4 ChaosMonkey

**File:** `core/resilience/chaos_monkey.py`

**Purpose:** Schedule random failure injections, verify automated recovery, report results.

**Key Methods:**

```python
class ChaosMonkey:
    def __init__(self):
        self.enabled = False  # OFF by default
        self.schedule = config.chaos.schedule_interval_h  # default: 24h
        self.failure_injectors: list[FailureInjector] = [
            ProcessKillInjector(),
            NetworkChaosInjector(),
            ResourceExhaustInjector(),
            DependencyFailureInjector(),
        ]
        self.results: list[ChaosExperiment] = []

    async def run_scheduled(self):
        """Run all failure experiments on schedule."""

    async def run_experiment(self, injector: FailureInjector) -> ChaosExperiment:
        """Run a single chaos experiment with verify → inject → verify flow."""

    async def run_random_experiment(self):
        """Pick a random failure type and run it."""

    async def run_all_experiments(self):
        """Run every failure type sequentially. Reports summary."""

    def generate_report(self) -> str:
        """Markdown report: experiments run, pass/fail, recovery time, recommendations."""
```

**FailureInjector Base:**
```python
class FailureInjector(ABC):
    name: str
    description: str
    risk_level: str  # "low" | "medium" | "high" — high only if explicitly enabled

    @abstractmethod
    async def verify_healthy(self) -> bool:
        """Verify system is healthy before injection."""

    @abstractmethod
    async def inject(self):
        """Inject the failure."""

    @abstractmethod
    async def verify_recovery(self) -> tuple[bool, float]:
        """Verify recovery within expected time. Returns (recovered, time_s)."""

    @abstractmethod
    async def cleanup(self):
        """Restore system to normal state."""

    async def run(self) -> ChaosExperiment:
        """Full experiment lifecycle."""
```

**Concrete Injectors:**

```python
class ProcessKillInjector(FailureInjector):
    async def inject(self):
        target = random.choice(["ollama", "voice_ws", "research_worker"])
        process_name = {"ollama": "ollama.exe", "voice_ws": "python", "research_worker": "python"}[target]
        # Kill specific process. VECTOR should detect and restart.

class NetworkChaosInjector(FailureInjector):
    async def inject(self):
        # Windows: netsh to block port 11434 (Ollama)
        # Linux: iptables -A INPUT -p tcp --dport 11434 -j DROP
        # VECTOR should detect Ollama unreachable → circuit breaker → fallback

class ResourceExhaustInjector(FailureInjector):
    async def inject(self):
        # Memory: allocate 80% of available RAM
        # CPU: spawn CPU-burning processes
        # Disk: write large file to fill disk to 95%
        # VECTOR should detect → graceful degradation → recovery

class DependencyFailureInjector(FailureInjector):
    async def inject(self):
        # Make memory DB return errors
        # Make vector DB return empty results
        # Make TTS return corrupted audio
        # VECTOR should detect → fallback → circuit breaker
```

### 4.5 GracefulDegradation

**File:** `core/resilience/graceful_degradation.py`

**Purpose:** Detect resource constraints and degrade functionality gracefully rather than crashing.

**Key Methods:**

```python
class GracefulDegradation:
    def __init__(self):
        self.current_tier = ServiceTier.FULL
        self.capabilities: dict[str, bool] = {}  # service_name → available

    async def evaluate_tier(self) -> ServiceTier:
        """Check GPU, RAM, disk, network, Ollama → determine current tier."""

    def get_available_services(self) -> dict[str, bool]:
        """Which services are available at current tier."""

    def get_service_limits(self, service: str) -> dict:
        """Resource limits for a service at current tier (batch size, model size, etc)."""

    async def auto_degrade(self):
        """If resource pressure detected, drop to next tier."""

    async def auto_escalate(self):
        """If resources recovered, escalate back up."""

    def notify_tier_change(self, old: ServiceTier, new: ServiceTier):
        """Log tier change and notify user."""
```

**Tier Definitions:**
```python
class ServiceTier(IntEnum):
    FULL = 5
    REDUCED = 4
    DEGRADED = 3
    MINIMAL = 2
    EMERGENCY = 1
    SURVIVAL = 0

class ServiceCapability(Enum):
    GPU_INFERENCE = "gpu_inference"
    STREAMING_TTS = "streaming_tts"
    SPEAKER_ID = "speaker_id"
    RESEARCH_WEB = "research_web"
    CODE_EXECUTION = "code_execution"
    MEMORY_WRITE = "memory_write"
    TELEGRAM = "telegram"
    DASHBOARD = "dashboard"
    VOICE = "voice"

TIER_CAPABILITIES = {
    ServiceTier.FULL: {
        ServiceCapability.GPU_INFERENCE: True,
        ServiceCapability.STREAMING_TTS: True,
        ServiceCapability.SPEAKER_ID: True,
        ServiceCapability.RESEARCH_WEB: True,
        ServiceCapability.CODE_EXECUTION: True,
        ServiceCapability.MEMORY_WRITE: True,
        ServiceCapability.TELEGRAM: True,
        ServiceCapability.DASHBOARD: True,
        ServiceCapability.VOICE: True,
    },
    ServiceTier.DEGRADED: {
        # GPU OOM → CPU inference, smaller model
        ServiceCapability.GPU_INFERENCE: False,       # CPU mode
        ServiceCapability.STREAMING_TTS: False,        # Non-streaming
        ServiceCapability.SPEAKER_ID: False,           # Disabled
        ServiceCapability.RESEARCH_WEB: True,
        ServiceCapability.CODE_EXECUTION: True,
        ServiceCapability.MEMORY_WRITE: True,
        ServiceCapability.TELEGRAM: True,
        ServiceCapability.DASHBOARD: True,
        ServiceCapability.VOICE: True,                 # Higher latency
    },
    ServiceTier.EMERGENCY: {
        # Ollama down, network down → cached responses, offline
        ServiceCapability.GPU_INFERENCE: False,
        ServiceCapability.STREAMING_TTS: False,
        ServiceCapability.SPEAKER_ID: False,
        ServiceCapability.RESEARCH_WEB: False,
        ServiceCapability.CODE_EXECUTION: False,
        ServiceCapability.MEMORY_WRITE: True,          # Buffer for later sync
        ServiceCapability.TELEGRAM: False,
        ServiceCapability.DASHBOARD: True,             # Show offline status
        ServiceCapability.VOICE: False,
    },
}
```

### 4.6 RecoveryPlaybooks

**File:** `core/resilience/recovery_playbooks.py`

**Purpose:** Automated recovery procedures per failure type.

**Key Methods:**

```python
class RecoveryPlaybooks:
    def __init__(self):
        self.playbooks: dict[str, RecoveryPlaybook] = {
            "model_crash": self._recover_model_crash,
            "db_corruption": self._recover_db_corruption,
            "oom": self._recover_oom,
            "network_partition": self._recover_network_partition,
            "disk_full": self._recover_disk_full,
            "config_corrupt": self._recover_config_corrupt,
            "process_hang": self._recover_process_hang,
            "gpu_failure": self._recover_gpu_failure,
        }

    async def recover(self, failure_type: str, context: dict) -> RecoveryResult:
        """Execute the appropriate recovery playbook."""

    async def _recover_model_crash(self, context: dict) -> RecoveryResult:
        """Ollama model crashed. Steps: 1. Detect. 2. Kill orphaned processes.
           3. Restart Ollama. 4. Wait for /api/tags. 5. Load fallback model.
           6. Cache fallback. 7. Log incident."""

    async def _recover_db_corruption(self, context: dict) -> RecoveryResult:
        """SQLite DB corrupt. Steps: 1. Detect corruption. 2. Switch to last known
           good backup. 3. Attempt repair on corrupt DB. 4. If repair succeeds,
           merge. 5. If not, maintain backup and log corruption."""

    async def _recover_oom(self, context: dict) -> RecoveryResult:
        """Out of memory. Steps: 1. Trigger graceful degradation. 2. Stop non-critical
           services. 3. Clear caches. 4. Reduce model size. 5. Monitor memory.
           6. Escalate when stable."""

    async def _recover_network_partition(self, context: dict) -> RecoveryResult:
        steps = [
            "Detect partition: ping cloud APIs fail, local services work",
            "Enter EMERGENCY tier: disable web-dependent services",
            "Enable offline mode: cached responses, local-only",
            "Start network retry: exponential backoff, check every 30s",
            "On reconnect: flush buffered messages, re-enable services, escalate tier",
        ]
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: CircuitBreaker + BulkheadExecutor

**Responsibility:** Wrap all external calls in circuit breakers, isolate service pools.

**Tasks:**
1. Create `core/resilience/__init__.py` with ResilienceLayer facade
2. Create `core/resilience/circuit_breaker.py` with 3-state breaker + registry
3. Create `core/resilience/bulkhead_executor.py` with semaphore pools
4. Add `CircuitBreakerConfig` and `BulkheadConfig` to `core/config.py`
5. Create `core/resilience/circuit_breaker_integration.py` — wiring guide for all existing call sites
6. Integrate circuit breaker into: `ollama_safe.py`, `district_llm.py`, `vectorcode_llm.py`, `llm_providers.py`
7. Integrate circuit breaker into: `core/memory/episodic.py` (SQLite), `core/research_engine/` (web calls)
8. Integrate bulkhead executor into: autonomous loop, voice pipeline, research engine
9. Create `core/resilience/metrics.py` — Prometheus-style metrics for circuit breaker states and bulkhead utilization
10. Write tests: `tests/resilience/test_circuit_breaker.py`, `tests/resilience/test_bulkhead_executor.py`

### 5.2 Agent B: HotFailover + GracefulDegradation

**Responsibility:** Secondary cloud instance, state mirroring, tiered service levels.

**Tasks:**
1. Create `core/resilience/hot_failover.py` with heartbeat sender/listener
2. Create `core/resilience/hot_failover_api.py` — FastAPI endpoints for failover communication
3. Create `core/resilience/hot_failover_state.py` — StateDigest model and state replication logic
4. Create `core/resilience/graceful_degradation.py` with tier evaluation and capability mapping
5. Integrate degradation into: `core/inference/ollama_safe.py` (CPU fallback), `core/voice/` (disable speaker ID), `core/research_engine/` (disable web research)
6. Create deployment config: `fly.toml` for secondary instance
7. Create `scripts/deploy_secondary.py` — Fly.io deployment script
8. Add `FailoverConfig` and `GracefulDegradationConfig` to `core/config.py`
9. Write tests: `tests/resilience/test_hot_failover.py`, `tests/resilience/test_graceful_degradation.py`

### 5.3 Agent C: ChaosMonkey + RecoveryPlaybooks

**Responsibility:** Scheduled failure injection, automated recovery procedures.

**Tasks:**
1. Create `core/resilience/chaos_monkey.py` with FailureInjector base and scheduler
2. Create `core/resilience/injectors/process_kill.py` — kill specific processes
3. Create `core/resilience/injectors/network_chaos.py` — packet drop/latency/block
4. Create `core/resilience/injectors/resource_exhaust.py` — CPU/RAM/disk exhaustion
5. Create `core/resilience/injectors/dependency_failure.py` — API 500s, slow responses
6. Create `core/resilience/recovery_playbooks.py` with 8 automated playbooks
7. Create `core/resilience/chaos_scheduler.py` — integration with autonomous loop
8. Add `ChaosConfig` to `core/config.py`
9. Create `core/resilience/chaos_report.py` — structured report generation
10. Write tests: `tests/resilience/test_chaos_monkey.py`, `tests/resilience/test_recovery_playbooks.py`

---

## 6. Implementation Steps

### 6.1 Phase 1: Circuit Breakers + Bulkheads (Agent A)

**Step 1.1: Core resilience module**
- [ ] Create `core/resilience/` package with `__init__.py`
- [ ] Create `core/resilience/circuit_breaker.py` — CircuitBreaker class, CircuitBreakerConfig, CircuitBreakerRegistry
- [ ] Create `core/resilience/bulkhead_executor.py` — BulkheadExecutor with semaphore pools
- [ ] Add config models to `core/config.py`

**Step 1.2: Circuit breaker integration**
- [ ] Integrate into `core/inference/ollama_safe.py` — wrap `chat()` and `generate()`
- [ ] Integrate into `core/inference/district_llm.py` — wrap all LLM calls
- [ ] Integrate into `core/inference/vectorcode_llm.py` — wrap vectorcode LLM calls
- [ ] Integrate into `core/inference/llm_providers.py` — wrap cloud API calls
- [ ] Integrate into `core/memory/episodic.py` — wrap SQLite read/write
- [ ] Integrate into `core/research_engine/` — wrap web fetch and paper search calls
- [ ] Integrate into `core/voice/` — wrap ASR, TTS, and speaker ID calls

**Step 1.3: Bulkhead integration**
- [ ] Wrap voice pipeline operations in voice pool
- [ ] Wrap inference calls in inference pool
- [ ] Wrap research operations in research pool
- [ ] Wrap memory operations in memory pool
- [ ] Wrap comms operations in comms pool

**Step 1.4: Metrics**
- [ ] Create `core/resilience/metrics.py` — state tracking, failure rates, utilization
- [ ] Expose metrics via simple HTTP endpoint for dashboard

**Step 1.5: Test**
- [ ] Circuit breaker: CLOSED → OPEN on threshold failures, OPEN → HALF_OPEN on timeout, HALF_OPEN → CLOSED on success
- [ ] Bulkhead: overload one pool, verify other pools unaffected
- [ ] Integration: verify circuit breaker wraps all call sites

### 6.2 Phase 2: Hot Failover + Graceful Degradation (Agent B)

**Step 2.1: Hot failover core**
- [ ] Create `core/resilience/hot_failover.py` — heartbeat sender/listener
- [ ] Create `core/resilience/hot_failover_state.py` — StateDigest, state replication
- [ ] Create `core/resilience/hot_failover_api.py` — FastAPI routes for heartbeat

**Step 2.2: State replication**
- [ ] Implement SQLite WAL continuous replication between primary and secondary
- [ ] Implement session state sync
- [ ] Implement circuit breaker state sync
- [ ] Test: primary crash → secondary take over within 15s

**Step 2.3: Secondary deployment**
- [ ] Create `fly.toml` for Fly.io deployment
- [ ] Create `scripts/deploy_secondary.py`
- [ ] Create Dockerfile for secondary instance
- [ ] Set up GitHub Actions for automatic secondary deployment

**Step 2.4: Graceful degradation**
- [ ] Create `core/resilience/graceful_degradation.py`
- [ ] Implement resource detection (GPU, RAM, disk, network, Ollama)
- [ ] Implement tier transitions with notification
- [ ] Integrate with inference engine: GPU OOM → CPU fallback
- [ ] Integrate with voice: memory pressure → disable speaker ID
- [ ] Integrate with research: network down → disable web research

**Step 2.5: Test**
- [ ] Hot failover: kill primary → secondary takes over in <15s
- [ ] Graceful degradation: simulate GPU OOM → verify CPU fallback
- [ ] Graceful escalation: restore resources → verify full tier returns

### 6.3 Phase 3: Chaos Monkey + Recovery Playbooks (Agent C)

**Step 3.1: Chaos monkey core**
- [ ] Create `core/resilience/chaos_monkey.py`
- [ ] Create FailureInjector base class
- [ ] Create ChaosExperiment data model
- [ ] Create scheduler

**Step 3.2: Failure injectors**
- [ ] Create `core/resilience/injectors/process_kill.py`
- [ ] Create `core/resilience/injectors/network_chaos.py`
- [ ] Create `core/resilience/injectors/resource_exhaust.py`
- [ ] Create `core/resilience/injectors/dependency_failure.py`

**Step 3.3: Recovery playbooks**
- [ ] Create `core/resilience/recovery_playbooks.py`
- [ ] Implement model_crash playbook
- [ ] Implement db_corruption playbook
- [ ] Implement oom playbook
- [ ] Implement network_partition playbook
- [ ] Implement disk_full playbook
- [ ] Implement config_corrupt playbook
- [ ] Implement process_hang playbook
- [ ] Implement gpu_failure playbook

**Step 3.4: Scheduling + reporting**
- [ ] Integrate ChaosMonkey with autonomous loop (default: daily at 3am)
- [ ] Create `core/resilience/chaos_report.py` — structured report generation
- [ ] Add chaos results to autonomous loop log

**Step 3.5: Test**
- [ ] Each failure injector: inject → verify system response → cleanup
- [ ] Each recovery playbook: simulate failure → run playbook → verify recovery
- [ ] Full chaos experiment: inject → measure recovery time → pass/fail

### 6.4 Phase 4: Integration + Hardening

- [ ] All circuit breakers, bulkheads, degradation wired together
- [ ] Hot failover end-to-end: crash primary, verify secondary serves requests
- [ ] Chaos experiment: inject 3 simultaneous failures, verify system survives
- [ ] Recovery playbooks: verify each playbook completes successfully
- [ ] Performance: verify circuit breaker overhead <1ms per call
- [ ] Performance: verify bulkhead overhead <0.5ms per call
- [ ] Documentation: resilience architecture in `docs/resilience.md`

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `core/resilience/__init__.py` | ~50 | ResilienceLayer facade |
| `core/resilience/circuit_breaker.py` | ~300 | 3-state circuit breaker + registry |
| `core/resilience/bulkhead_executor.py` | ~200 | Semaphore-based service isolation |
| `core/resilience/hot_failover.py` | ~350 | Heartbeat + failover orchestration |
| `core/resilience/hot_failover_state.py` | ~150 | StateDigest, replication logic |
| `core/resilience/hot_failover_api.py` | ~100 | FastAPI heartbeat endpoints |
| `core/resilience/graceful_degradation.py` | ~250 | Tier detection and capability mapping |
| `core/resilience/chaos_monkey.py` | ~200 | Failure injection engine + scheduler |
| `core/resilience/chaos_scheduler.py` | ~80 | Autonomous loop integration |
| `core/resilience/chaos_report.py` | ~100 | Chaos experiment report generation |
| `core/resilience/recovery_playbooks.py` | ~400 | 8 automated recovery procedures |
| `core/resilience/metrics.py` | ~150 | Prometheus-style metrics collection |
| `core/resilience/injectors/__init__.py` | ~20 | Injector package |
| `core/resilience/injectors/process_kill.py` | ~100 | Process termination injector |
| `core/resilience/injectors/network_chaos.py` | ~150 | Network failure injector |
| `core/resilience/injectors/resource_exhaust.py` | ~120 | CPU/RAM/disk exhaustion injector |
| `core/resilience/injectors/dependency_failure.py` | ~100 | API failure injector |
| `fly.toml` | ~30 | Fly.io secondary deployment config |
| `scripts/deploy_secondary.py` | ~80 | Automated secondary deployment |
| `tests/resilience/test_circuit_breaker.py` | ~150 | Circuit breaker tests |
| `tests/resilience/test_bulkhead_executor.py` | ~100 | Bulkhead tests |
| `tests/resilience/test_hot_failover.py` | ~120 | Failover tests |
| `tests/resilience/test_graceful_degradation.py` | ~100 | Degradation tests |
| `tests/resilience/test_chaos_monkey.py` | ~150 | Chaos tests |
| `tests/resilience/test_recovery_playbooks.py` | ~200 | Recovery playbook tests |

### Modify:

| File | Change |
|------|--------|
| `core/config.py` | Add ResilienceConfig (circuit_breaker, bulkhead, failover, degradation, chaos sections) |
| `core/loop/autonomous_loop.py` | Add chaos monkey schedule, circuit breaker health check, graceful degradation monitor |
| `core/inference/ollama_safe.py` | Wrap calls in circuit breaker + bulkhead |
| `core/inference/district_llm.py` | Wrap calls in circuit breaker |
| `core/inference/llm_providers.py` | Wrap cloud API calls in circuit breaker |
| `core/memory/episodic.py` | Wrap SQLite calls in circuit breaker |
| `core/voice/ambient_listener.py` | Wrap voice ops in bulkhead |
| `core/research_engine/__init__.py` | Wrap research ops in bulkhead |
| `core/coding_assistant/code_executor.py` | Wrap exec calls in circuit breaker |
| `core/api/routers/health.py` | Add detailed health check (circuit breaker states, bulkhead utilization, degradation tier) |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| Circuit breaker overhead | N/A | <1ms per call | Benchmark circuit_breaker.call() vs direct call |
| Circuit breaker recovery time | N/A | <30s | Inject failure, measure time to CLOSED state return |
| Bulkhead isolation | N/A | 100% | Overload one pool, verify other pools throughput unchanged |
| Hot failover detection time | N/A | <15s | Kill primary process, measure secondary detection |
| Hot failover takeover time | N/A | <10s | From detection to secondary serving requests |
| Graceful degradation response | N/A | <5s | Inject GPU OOM, measure tier transition |
| Chaos experiment pass rate | N/A | >90% | Run all experiments, count passes |
| Recovery playbook success | N/A | 100% | Run each playbook against simulated failure |
| Simultaneous failure survival | N/A | 3 failures | Inject 3 simultaneous failures, verify system operational |
| Recovery under 30s | N/A | 100% | From failure injection to full recovery |
| User-visible downtime | N/A | 0% | Failover and degradation should be transparent |

### 8.2 Qualitative Criteria

1. Circuit breakers are invisible under normal operation — no performance impact felt
2. When a service fails, only that service degrades — voice continues during research failure
3. Power cycling the laptop recovers within 30s with full state
4. Chaos experiments run silently at 3am — user never notices
5. Recovery from known failure modes is fully automatic
6. The dashboard shows live resilience status (circuit breaker states, tier level, failover status)

### 8.3 Regression Checks

1. All existing tests pass: `pytest tests/`
2. Normal operation performance is not degraded by resilience layer
3. Existing fallback chains still work (Ollama → cloud → cached)
4. Agent rebirth (evolution engine) still works after circuit breaker integration
5. Session persistence still saves/loads correctly
6. Autonomous loop still runs with resilience layer active
7. Voice pipeline latency is not increased by circuit breaker wrapping

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Add to requirements.txt:
psutil>=5.9.0                # System resource monitoring (CPU, RAM, disk)
prometheus-client>=0.19.0     # Metrics exposition for dashboard
httpx>=0.26.0                 # HTTP client (likely already present — use for failover heartbeat)
structlog>=24.0.0             # Structured logging with context (already present)
```

### 9.2 System Requirements

- Fly.io account (or other cloud provider) for secondary instance
- Primary: Windows (netsh for network chaos) or Linux (iptables for network chaos)
- Secondary: Linux (Fly.io runs Docker containers on Linux)
- Docker for secondary deployment
- 512MB additional RAM on secondary (minimum for basic services)
- Database replication requires SQLite WAL mode (already enabled)

### 9.3 Internal Dependencies

1. **specs-02 (Parallel Distribution):** Hot failover state mirroring should eventually use EventBus for async replication. For now, direct HTTP POST.
2. **specs-04 (Security):** Chaos experiments should not trigger security alerts. ChaosMonkey should register with security system to suppress false positives during experiments.
3. **specs-08 (Dashboard):** Resilience metrics should surface on dashboard. Circuit breaker states, tier level, chaos experiment history — all dashboard-ready.

---

## 10. Rollout Plan

### Phase 1 (Week 1): Circuit Breakers + Bulkheads
- Core resilience module with circuit breakers and bulkheads
- Integrated into all inference, memory, and research call sites
- Metrics exposed

### Phase 2 (Week 2): Graceful Degradation
- Tier detection working
- Degradation integrated with inference, voice, and research
- Hot failover core (heartbeat, state sync)

### Phase 3 (Week 3): Hot Failover
- Secondary instance deployed on Fly.io
- State mirroring working
- Failover automated and tested

### Phase 4 (Week 4): Chaos Engineering + Recovery Playbooks
- All failure injectors working
- All recovery playbooks tested
- Daily chaos schedule active
- E2E: 3 simultaneous failures → survival verified

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Circuit breaker adds latency to every call | Low | Medium | Async state updates; benchmark to verify <1ms overhead |
| Hot failover splits state (split-brain) | Low | High | Heartbeat includes generation counter; manual promote on conflict |
| Chaos experiments cause real damage | Medium | High | ChaosMonkey is OFF by default; high-risk experiments require explicit enable |
| Graceful degradation oscillates between tiers | Low | Medium | Hysteresis: 60s cooldown between tier transitions |
| Fly.io costs for secondary instance | Medium | Low | Secondary runs minimal services; ~$5-10/month |
| Network chaos injector requires admin rights | High | Medium | Log warning if admin rights not available; skip network tests gracefully |
