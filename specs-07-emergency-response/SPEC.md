# SPEC-07: Real-Time Emergency Response System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's emergency response from 15/100 to 85/100 — real-time crisis detection across health, security, system, and environmental domains; automated runbooks; tiered escalation to user via Pushover, SMS, and phone call.

**Architecture:** Four-layer reactive system: detectors watch multiple signals → severity classifier rates the emergency → runbook executor takes automated action → escalation manager notifies user with escalating urgency. All events append to an immutable emergency log for post-mortem analysis.

**Tech Stack:** asyncio, psutil, Pushover API, Twilio (optional VoIP), SQLite (emergency log), httpx, subprocess, watchdog (file system events)

**Score:** Current 15/100 → Target 85/100

---

## 1. Problem Statement

### 1.1 Current Limitations

Emergency response scores 15/100 across six dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Detection | 10/100 | `security-guard Hand` runs every 4 hours. No real-time crisis detection. Health alerts fire but are one-shot — no follow-up if ignored. |
| Response | 20/100 | Health alerts push to Pushover but there's no automated response. If VECTOR detects "heart rate stopped" it just sends a notification — no escalation if unacknowledged. |
| Classification | 5/100 | `ErrorClassifier` in `districts/ops/` classifies software errors only. No severity scoring for emergencies. No distinction between "my laptop is hot" and "smoke detected." |
| Escalation | 0/100 | No escalation protocol. One Pushover notification with no acknowledgment mechanism. If user is asleep/unreachable, emergency is silently dropped. |
| Coverage | 20/100 | Health alerts (HR, movement) exist via `phone_node`. Security scanning runs every 4h. System crash recovery exists in `autonomous_loop.py`. But these are siloed — no unified emergency view. |
| Auditing | 10/100 | No emergency log. No timeline reconstruction. Cannot answer "what happened during the outage at 3AM?" |

### 1.2 Domain Coverage Gaps

| Domain | Current State | Gap |
|--------|--------------|-----|
| Health | HR monitoring via phone_node, movement sensing | No automated response to CRITICAL readings, no escalation |
| Security | 4h security-guard Hand, Pushover on alert | Detection delayed up to 4h, no automated isolation |
| System | Crash recovery in autonomous_loop | Disk full, OOM, GPU hang, process death not covered |
| Network | Phone node heartbeat every 60s | Internet down detection, WiFi disconnection, VPN drop |
| Battery | Battery monitoring on phone_node | No critical battery response (auto-shutdown save) |
| Disk | No monitoring | No disk usage alerts, no automated cleanup |
| Temperature | GPU temp via nvidia-smi (ad-hoc) | No CPU/NVMe temp monitoring, no thermal throttling detection |

### 1.3 Red vs Blue Comparison

| Aspect | Current (Red) | Target (Blue) |
|--------|--------------|---------------|
| Detection latency | Up to 4 hours | <5 seconds |
| Response actions | None | Automated runbooks per severity |
| Escalation stages | 1 (Pushover blast) | 3 (fix → notify → call) |
| False alarm rate | Unknown (never measured) | <1/day after tuning |
| Post-mortem capability | None | Full timeline with response times |
| Coverage | 3 domains (partial) | 5 domains (full) |

---

## 2. Current Architecture

### 2.1 Existing Emergency-Related Code

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Current Emergency "System"                      │
│                                                                     │
│  autonomous_loop.py:                                                │
│    └→ crash recovery wrapper catches exceptions, restarts loops    │
│                                                                     │
│  districts/ops/ErrorClassifier:                                     │
│    └→ classifies software errors only (OOM, timeout, crash)        │
│                                                                     │
│  phone_node/ambient_server.py:                                      │
│    └→ health checks: HR, movement, battery — Pushover alert       │
│                                                                     │
│  phone_node/adb_bridge.py:                                          │
│    └→ phone connectivity — heartbeat to brain server               │
│                                                                     │
│  districts/ops/DevOpsAutomator:                                     │
│    └→ security-guard Hand every 4h (scan + report)                │
│                                                                     │
│  districts/ops/SREMonitor:                                          │
│    └→ system health polling (CPU, RAM, disk — ad-hoc, limited)    │
│                                                                     │
│  Pushover notifications:                                            │
│    └→ PUSHOVER_TOKEN + PUSHOVER_USER — direct message              │
│                                                                     │
│  No escalation, no log, no automated response                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Files

| File | Role | Lines |
|------|------|-------|
| `districts/ops/ErrorClassifier.py` | Software error classification | ~150 |
| `districts/ops/DevOpsAutomator.py` | Security scanning, automation | ~350 |
| `districts/ops/SREMonitor.py` | System health monitoring | ~200 |
| `phone_node/ambient_server.py` | Phone-side health server | ~300 |
| `phone_node/adb_bridge.py` | ADB bridge to phone | ~200 |
| `core/loop/autonomous_loop.py` | Crash recovery (lines 60-95) | 958 |
| `core/config.py` | PUSHOVER_TOKEN, PUSHOVER_USER | 555 |

### 2.3 Current Flow

```
Emergency Event (any domain)
    │
    ▼
┌──────────────────────┐
│ Detection (varies)   │  ← health: phone_node → Pushover
│                      │  ← security: every 4h guard scan → Pushover
│                      │  ← system: process crash → auto-restart
│                      │  ← network: no detection
│                      │  ← disk: no detection
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Single Pushover msg  │  ← no severity, no follow-up
│                      │  ← no acknowledgment required
│                      │  ← no escalation if ignored
└──────────────────────┘
```

---

## 3. Target Architecture

### 3.1 High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       EmergencyResponseSystem                             │
│                                                                          │
│  Signal Sources                                                          │
│    ├─ HealthMonitor (HR, movement, fall)                                 │
│    ├─ SecurityMonitor (intrusion, malware, file changes)                 │
│    ├─ SystemMonitor (CPU, RAM, GPU, disk, temp, processes)              │
│    └─ NetworkMonitor (internet, WiFi, VPN, phone node heartbeat)        │
│         │                                                               │
│         ▼                                                               │
│  ┌────────────────┐                                                     │
│  │EmergencyDetector│  ← correlates signals, deduplicates, debounces     │
│  └───────┬────────┘                                                     │
│          │ (EmergencyEvent)                                             │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │SeverityClassi- │  ← CRITICAL / HIGH / MEDIUM / LOW                   │
│  │fier            │  ← context-aware (time of day, recent history)      │
│  └───────┬────────┘                                                     │
│          │ (ScoredEmergency)                                            │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │RunbookExecutor │  ← per severity + type: auto-actions                │
│  └───────┬────────┘                                                     │
│          │ (ActionResult)                                               │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │EscalationMgr   │  ← Tier 1: auto-fix → Tier 2: Pushover → Tier 3:   │
│  │                │     phone call → Tier 4: emergency contact          │
│  └───────┬────────┘                                                     │
│          │ (EscalationEvent)                                            │
│          ▼                                                              │
│  ┌────────────────┐                                                     │
│  │ EmergencyLog   │  ← append-only, signed, timestamped                 │
│  └────────────────┘                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Signal Sources Detail

```
HEALTH SIGNALS (via phone node):
  - Heart rate: >120 bpm (HIGH), <40 bpm (CRITICAL), flatline (CRITICAL)
  - Movement: no movement >30min while awake (MEDIUM), >2h (HIGH)
  - Fall detection: sudden acceleration + no movement (CRITICAL)
  - Battery: <10% (HIGH), <5% (CRITICAL), charging state changes
  - Phone connectivity: heartbeat >90s missing (MEDIUM), >180s (HIGH)

SECURITY SIGNALS (via districts/ops/):
  - Intrusion detection: failed SSH attempts, new USB devices, unknown WiFi
  - File integrity: unexpected changes to /etc/hosts, .ssh/, key system files
  - Process anomalies: unknown daemons, crypto miners, reverse shells
  - Malware scan: ClamAV or similar detection (MEDIUM/HIGH based on type)

SYSTEM SIGNALS (local monitoring):
  - CPU: >90% for >30s (MEDIUM), >95% for >60s (HIGH)
  - RAM: >85% used (MEDIUM), >95% (HIGH), swap filling (HIGH)
  - GPU: temperature >85°C (MEDIUM), >90°C (HIGH), >95°C (CRITICAL)
  - VRAM: >90% used (MEDIUM), OOM event (CRITICAL)
  - Disk: >85% full (MEDIUM), >95% (HIGH), read errors (CRITICAL)
  - NVMe temperature: >70°C (MEDIUM), >80°C (HIGH)
  - Process death: VECTOR core process dies (CRITICAL), district agent dies (HIGH)
  - OOM killer: any VECTOR process killed by kernel (CRITICAL)

NETWORK SIGNALS (local + phone):
  - Internet: ping failure >30s (MEDIUM), >120s (HIGH)
  - WiFi: disconnection, signal < -70dBm (MEDIUM)
  - VPN: connection drop (HIGH if security context requires VPN)
  - DNS resolution failure (MEDIUM)
  - Phone node heartbeat missing >90s (MEDIUM), >180s (HIGH)
  - Phone node battery critical (HIGH)
```

### 3.3 Severity Classification Matrix

| Severity | Definition | Response Time | Examples |
|----------|-----------|---------------|---------|
| CRITICAL | Imminent harm to user or system | <10s | HR flatline, smoke/fire, kernel OOM, disk failure |
| HIGH | Significant degradation or risk | <30s | GPU >95°C, disk >95%, phone heartbeat lost, intrusion |
| MEDIUM | Warning, potential future issue | <5min | CPU >90%, disk >85%, battery <10%, failed SSH attempts |
| LOW | Informational, no action needed | Logged only | Autonomy resolution warning, minor temp spikes, 1 failed ping |

### 3.4 Response Time Budget

```
CRITICAL:   detect (2s) → classify (1s) → runbook (3s) → escalate (2s) = <10s total
HIGH:       detect (5s) → classify (2s) → runbook (10s) → escalate (5s) = <30s total
MEDIUM:     detect (30s) → classify (5s) → runbook (60s) → escalate (100s) = <5min total
LOW:        detect (60s) → classify (10s) → log only = <90s total
```

### 3.5 Escalation Protocol

```
TIER 1 — Automated Response (0-30s):
  - Execute runbook for emergency type
  - Log all actions taken and their outcomes
  - If successful (e.g., disk cleanup freed space): close incident, log resolution

TIER 2 — Pushover Notification (30s-2min):
  - Send structured emergency notification via Pushover
  - Include: severity, type, description, auto-action taken, required user action
  - Request acknowledgment — emergency is "pending" until acknowledged
  - If acknowledged: close incident, log acknowledgment time + user response

TIER 3 — SMS/Phone Call (2-5min):
  - If CRITICAL emergency unacknowledged after 2 minutes
  - If HIGH emergency unacknowledged after 5 minutes
  - Send SMS via Twilio or push notification via Pushover priority (retry every 30s)
  - Optional: Twilio voice call with TTS emergency description
  - If acknowledged: de-escalate, log

TIER 4 — Emergency Contact (5-10min):
  - If CRITICAL unacknowledged after 5 minutes
  - Notify emergency contact (pre-configured phone number)
  - Send summary: type, severity, time elapsed, last known user status
  - Continue retry loop to user

ACKNOWLEDGMENT: User replies "ack" or "ok VECTOR" or dismisses in dashboard
```

---

## 4. Component Breakdown

### 4.1 EmergencyDetector

**File:** `districts/emergency/detector.py` (new, ~350 lines)

**Responsibility:** Correlates signals from multiple monitors, deduplicates events, applies debounce rules, produces unified `EmergencyEvent`.

```python
@dataclass
class EmergencyEvent:
    event_id: str                          # uuid4
    domain: str                            # "health" | "security" | "system" | "network" | "environment"
    source: str                            # "phone_node" | "sre_monitor" | "security_guard" | "local"
    signal_name: str                       # "hr_flatline" | "disk_full" | "gpu_overheat"
    value: float | str | None              # e.g., 95.2 (% disk), "flatline", 102 (HR bpm)
    threshold: float | str | None          # the threshold that was exceeded
    timestamp: float                       # time.perf_counter()
    raw_message: str                       # original message from signal source
    context: dict                          # additional context (room, process, interface)
    dedup_key: str                         # for deduplication within debounce window


class EmergencyDetector:
    """
    Central signal correlation engine. Receives signals from all monitoring
    sources, deduplicates, debounces, and emits EmergencyEvent.

    Debounce rules:
      - Same dedup_key within 60s: suppress (update existing event's count)
      - Same dedup_key within 300s: reduce severity by one level
      - Different dedup_key within 10s: batch into compound event if related

    Dedup key format: "{domain}:{signal_name}:{source}"
    Example: "system:disk_full:local"

    Subscribes to:
      - HealthMonitor._events asyncio.Queue
      - SecurityMonitor._events asyncio.Queue
      - SystemMonitor._events asyncio.Queue
      - NetworkMonitor._events asyncio.Queue

    Publishes: EmergencyEvent via asyncio.Queue to SeverityClassifier
    """
```

**Detection rules per domain:**

```python
# ── Health Detection Rules ──────────────────────────────────────────
HEALTH_RULES = {
    "hr_flatline": {
        "condition": lambda v: v < 20 or v == 0,
        "default_severity": "CRITICAL",
        "debounce_seconds": 10,
        "sources": ["phone_node"],
    },
    "hr_critical": {
        "condition": lambda v: v < 40 or v > 150,
        "default_severity": "CRITICAL",
        "debounce_seconds": 30,
        "sources": ["phone_node"],
    },
    "hr_high": {
        "condition": lambda v: v < 50 or v > 120,
        "default_severity": "HIGH",
        "debounce_seconds": 60,
        "sources": ["phone_node"],
    },
    "no_movement_awake": {
        "condition": lambda mins: mins > 30,
        "default_severity": "MEDIUM",
        "debounce_seconds": 300,
        "sources": ["phone_node"],
    },
    "fall_detected": {
        "condition": lambda v: v is True,
        "default_severity": "CRITICAL",
        "debounce_seconds": 5,
        "sources": ["phone_node"],
    },
}

# ── Security Detection Rules ────────────────────────────────────────
SECURITY_RULES = {
    "ssh_bruteforce": {
        "condition": lambda count: count > 10,
        "default_severity": "HIGH",
        "debounce_seconds": 300,
        "sources": ["security_guard"],
    },
    "new_usb_device": {
        "condition": lambda v: v is True,
        "default_severity": "HIGH",
        "debounce_seconds": 60,
        "sources": ["sre_monitor"],
    },
    "file_integrity_breach": {
        "condition": lambda v: v is True,
        "default_severity": "CRITICAL",
        "debounce_seconds": 30,
        "sources": ["security_guard"],
    },
    "unknown_process": {
        "condition": lambda v: v is True,
        "default_severity": "MEDIUM",
        "debounce_seconds": 300,
        "sources": ["sre_monitor"],
    },
}

# ── System Detection Rules ──────────────────────────────────────────
SYSTEM_RULES = {
    "cpu_over_90": {
        "condition": lambda pct: pct > 90,
        "duration_seconds": 30,
        "default_severity": "MEDIUM",
        "debounce_seconds": 300,
        "sources": ["sre_monitor"],
    },
    "cpu_over_95": {
        "condition": lambda pct: pct > 95,
        "duration_seconds": 60,
        "default_severity": "HIGH",
        "debounce_seconds": 300,
        "sources": ["sre_monitor"],
    },
    "ram_over_85": {
        "condition": lambda pct: pct > 85,
        "default_severity": "MEDIUM",
        "debounce_seconds": 300,
        "sources": ["sre_monitor"],
    },
    "ram_over_95": {
        "condition": lambda pct: pct > 95,
        "default_severity": "HIGH",
        "debounce_seconds": 120,
        "sources": ["sre_monitor"],
    },
    "gpu_temp_over_85": {
        "condition": lambda c: c > 85,
        "default_severity": "MEDIUM",
        "debounce_seconds": 60,
        "sources": ["sre_monitor"],
    },
    "gpu_temp_over_90": {
        "condition": lambda c: c > 90,
        "default_severity": "HIGH",
        "debounce_seconds": 30,
        "sources": ["sre_monitor"],
    },
    "gpu_temp_over_95": {
        "condition": lambda c: c > 95,
        "default_severity": "CRITICAL",
        "debounce_seconds": 10,
        "sources": ["sre_monitor"],
    },
    "disk_over_85": {
        "condition": lambda pct: pct > 85,
        "default_severity": "MEDIUM",
        "debounce_seconds": 600,
        "sources": ["sre_monitor"],
    },
    "disk_over_95": {
        "condition": lambda pct: pct > 95,
        "default_severity": "HIGH",
        "debounce_seconds": 120,
        "sources": ["sre_monitor"],
    },
    "disk_read_errors": {
        "condition": lambda v: v > 0,
        "default_severity": "CRITICAL",
        "debounce_seconds": 30,
        "sources": ["sre_monitor"],
    },
    "process_death": {
        "condition": lambda proc: proc in ["autonomous_loop", "mcp_server", "core_api"],
        "default_severity": "CRITICAL",
        "debounce_seconds": 5,
        "sources": ["sre_monitor"],
    },
    "oom_kill": {
        "condition": lambda v: v is True,
        "default_severity": "CRITICAL",
        "debounce_seconds": 5,
        "sources": ["sre_monitor"],
    },
}

# ── Network Detection Rules ─────────────────────────────────────────
NETWORK_RULES = {
    "internet_down": {
        "condition": lambda secs: secs > 30,
        "default_severity": "MEDIUM",
        "debounce_seconds": 60,
        "sources": ["sre_monitor"],
    },
    "internet_down_long": {
        "condition": lambda secs: secs > 120,
        "default_severity": "HIGH",
        "debounce_seconds": 60,
        "sources": ["sre_monitor"],
    },
    "phone_heartbeat_lost": {
        "condition": lambda secs: secs > 90,
        "default_severity": "MEDIUM",
        "debounce_seconds": 30,
        "sources": ["sre_monitor"],
    },
    "phone_offline": {
        "condition": lambda secs: secs > 180,
        "default_severity": "HIGH",
        "debounce_seconds": 30,
        "sources": ["sre_monitor"],
    },
    "wifi_disconnected": {
        "condition": lambda v: v is True,
        "default_severity": "MEDIUM",
        "debounce_seconds": 60,
        "sources": ["sre_monitor"],
    },
    "vpn_dropped": {
        "condition": lambda v: v is True,
        "default_severity": "HIGH",
        "debounce_seconds": 30,
        "sources": ["sre_monitor"],
    },
}
```

### 4.2 SeverityClassifier

**File:** `districts/emergency/classifier.py` (new, ~200 lines)

**Responsibility:** Rates emergencies CRITICAL/HIGH/MEDIUM/LOW based on signal values, context, and historical patterns.

```python
@dataclass
class ScoredEmergency:
    event: EmergencyEvent
    severity: str                    # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    severity_score: float            # 0.0-1.0 continuous score
    confidence: float                # 0.0-1.0 how confident in this classification
    context_factors: list[str]       # what influenced the score
    user_available: bool | None      # phone connected, active time?
    escalation_path: str             # which escalation tier to start at


class SeverityClassifier:
    """
    Context-aware severity classification.

    Base severity comes from detection rules. Modifiers:
      - Time of day: CRITICAL at 3AM → escalate faster (user likely asleep)
      - Recurrence: 3rd disk warning in 1h → HIGH instead of MEDIUM
      - User state: if user recently acknowledged → defer non-critical
      - Phone state: if phone disconnected → cannot rely on phone node signals
      - Temporal patterns: GPU temp spike during gaming → MEDIUM not HIGH
      - Co-occurrence: disk full + swap filling + OOM → CRITICAL compound

    Output: EmergencyEvent + severity → ScoredEmergency
    """
```

**Classification modifiers:**

```python
SEVERITY_MODIFIERS = {
    "time_of_day": {
        "night_risk": {"hours": [0, 6], "multiplier": 1.3},       # 12AM-6AM: escalate faster
        "work_hours": {"hours": [9, 17], "multiplier": 0.8},      # 9AM-5PM: can wait slightly
    },
    "recurrence": {
        "1-2 events/hour": {"multiplier": 1.0},
        "3-5 events/hour": {"multiplier": 1.2},
        "5+ events/hour": {"multiplier": 1.5},
    },
    "compound_events": {
        "disk_full + ram_over_95 + swap_filling": {"override": "CRITICAL", "reason": "System capacity failure imminent"},
        "gpu_over_95 + cpu_over_95 + process_death": {"override": "CRITICAL", "reason": "Thermal cascade likely"},
        "phone_offline + internet_down": {"override": "HIGH", "reason": "Both communication channels down"},
    },
    "user_state": {
        "user_acknowledged_recently": {"factor": 0.7},
        "user_asleep": {"factor": 1.4},
        "user_active": {"factor": 0.9},
    },
}
```

### 4.3 RunbookExecutor

**File:** `districts/emergency/runbook.py` (new, ~300 lines)

**Responsibility:** Executes automated response actions based on emergency type and severity.

```python
@dataclass
class RunbookAction:
    action_id: str
    name: str                          # "clean_disk" | "restart_service" | "threat_isolate"
    description: str
    steps: list[dict]                  # ordered steps with commands/methods
    timeout_seconds: int
    risk_level: str                    # "safe" | "caution" | "destructive"
    rollback: list[dict] | None        # undo steps if action fails


@dataclass
class ActionResult:
    runbook_action: RunbookAction
    success: bool
    started_at: float
    completed_at: float
    steps_completed: list[int]
    step_results: list[dict]           # output of each step
    error: str | None
    rollback_performed: bool = False


class RunbookExecutor:
    """
    Executes automated runbooks based on ScoredEmergency.

    Runbook selection: severity + domain + signal_name → runbook
    Each runbook is a list of actions executed sequentially with timeout.

    Safety:
      - "destructive" actions require user confirmation (Pushover → wait 30s)
      - "caution" actions execute automatically but log rollback steps
      - "safe" actions execute immediately (disk cleanup, cache clear)

    Runbooks:
      System/Disk Full (HIGH, MEDIUM):
        1. Identify largest files in temp dirs
        2. Delete cache files older than 24h
        3. Compress old logs
        4. Report freed space
        5. If still >95%: escalate

      System/OOM (CRITICAL):
        1. Identify OOM-killed process
        2. Restart process if it's a VECTOR component
        3. Increase swap if RAM is constrained
        4. Log memory state at time of OOM

      System/GPU Overheat (CRITICAL):
        1. Pause inference workloads
        2. Reduce model batch size
        3. Log GPU process list
        4. If temp continues rising after 30s: notify for shutdown

      Security/Intrusion (HIGH, CRITICAL):
        1. Log all active connections
        2. Isolate interface (if network intrusion)
        3. Rotate credentials for affected services
        4. Save forensic snapshot
        5. Report to user

      Health/Fall (CRITICAL):
        1. Pushover priority notification
        2. Try phone call via Twilio
        3. Play audio alert on laptop speakers
        4. If no acknowledgment in 5min: emergency contact
    """
```

**Runbook registry:**

```python
RUNBOOK_REGISTRY: dict[str, list[dict]] = {
    "system:disk_full": [
        {"action": "analyze_disk", "command": "Get-ChildItem -Path $temp -Recurse | Sort Length", "timeout": 10},
        {"action": "clean_cache", "older_than_hours": 24, "timeout": 30},
        {"action": "compress_logs", "older_than_days": 7, "timeout": 60},
        {"action": "report_freed_space", "timeout": 5},
    ],
    "system:gpu_overheat": [
        {"action": "pause_inference", "timeout": 5},
        {"action": "reduce_batch_size", "new_batch": 1, "timeout": 5},
        {"action": "log_gpu_processes", "timeout": 10},
        {"action": "monitor_temperature", "duration": 30, "timeout": 35},
    ],
    "security:intrusion": [
        {"action": "log_active_connections", "format": "json", "timeout": 10},
        {"action": "save_forensic_snapshot", "timeout": 30},
        {"action": "rotate_credentials", "timeout": 60},
    ],
    "health:fall_detected": [
        {"action": "pushover_priority", "retry_interval": 30, "timeout": 120},
        {"action": "play_audio_alert", "message": "Emergency detected. Are you okay?", "timeout": 10},
        {"action": "twilio_call", "use_tts": True, "timeout": 30},
    ],
    "system:process_death": [
        {"action": "restart_process", "process_name": "$signal", "timeout": 15},
        {"action": "verify_health", "timeout": 10},
        {"action": "log_restart", "timeout": 5},
    ],
    "network:internet_down": [
        {"action": "ping_gateway", "timeout": 5},
        {"action": "restart_network_adapter", "timeout": 15},
        {"action": "verify_dns", "timeout": 5},
        {"action": "report_status", "timeout": 5},
    ],
}
```

### 4.4 EscalationManager

**File:** `districts/emergency/escalation.py` (new, ~250 lines)

**Responsibility:** Tiered escalation protocol with acknowledgment tracking.

```python
@dataclass
class EscalationState:
    emergency: ScoredEmergency
    current_tier: int                 # 1-4
    tier_started_at: float
    acknowledged: bool = False
    acknowledged_by: str | None = None   # "pushover" | "phone" | "dashboard"
    acknowledged_at: float | None = None
    resolved: bool = False
    resolved_at: float | None = None
    escalation_log: list[dict] = field(default_factory=list)


class EscalationManager:
    """
    Manages tiered escalation protocol.

    Tier timing (configurable per severity):
      CRITICAL: Tier 1 (0s) → Tier 2 (30s) → Tier 3 (120s) → Tier 4 (300s)
      HIGH:     Tier 1 (0s) → Tier 2 (60s) → Tier 3 (300s) → Tier 4 (600s)
      MEDIUM:   Tier 1 (0s) → Tier 2 (300s) → no further escalation
      LOW:      Tier 1 only (log)

    Acknowledgment resets escalation timer for current tier.
    If same emergency re-fires within tier window, acceleration factor applies.

    Channels:
      Tier 1: Automated runbook (no user notification)
      Tier 2: Pushover (PUSHOVER_TOKEN + PUSHOVER_USER)
      Tier 3: Phone call (Twilio voice API or VoIP)
      Tier 4: Emergency contact (pre-configured SMS/email)
    """
```

**Escalation channel implementations:**

```python
class EscalationChannels:
    """Concrete implementations for each escalation channel."""

    @staticmethod
    async def pushover_alert(emergency: ScoredEmergency, priority: int = 0) -> bool:
        """Send Pushover notification with acknowledgment callback."""
        payload = {
            "token": CONFIG["pushover"]["token"],
            "user": CONFIG["pushover"]["user"],
            "title": f"[{emergency.severity}] {emergency.event.domain.upper()} Emergency",
            "message": format_emergency_message(emergency),
            "priority": priority,         # 0=normal, 1=high, 2=emergency
            "sound": "siren" if emergency.severity == "CRITICAL" else "persistent",
            "url": "http://localhost:8000/api/emergency/acknowledge",
            "url_title": "Acknowledge Emergency",
            "callback": f"{CONFIG['api']['base_url']}/api/emergency/callback",
            "retry": 30,                  # retry every 30s for priority 2
            "expire": 3600,               # expire after 1 hour
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.pushover.net/1/messages.json", data=payload)
            return resp.status_code == 200

    @staticmethod
    async def twilio_call(emergency: ScoredEmergency) -> bool:
        """Initiate Twilio voice call with TTS emergency description."""
        twilio_sid = CONFIG.get("twilio", {}).get("account_sid")
        twilio_token = CONFIG.get("twilio", {}).get("auth_token")
        if not twilio_sid or not twilio_token:
            logger.warning("Twilio not configured — skipping phone call escalation")
            return False
        message = format_tts_message(emergency)
        call_payload = {
            "To": CONFIG["user"]["phone"],
            "From": CONFIG["twilio"]["from_number"],
            "Twiml": f"<Response><Say>{message}</Say></Response>",
        }
        auth = httpx.BasicAuth(twilio_sid, twilio_token)
        async with httpx.AsyncClient(auth=auth) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Calls.json",
                data=call_payload,
            )
            return resp.status_code == 201

    @staticmethod
    async def laptop_alert(emergency: ScoredEmergency) -> None:
        """Play audio alert on laptop speakers using VECTOR's TTS."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        message = f"Emergency: {emergency.severity} alert in {emergency.event.domain}. {emergency.event.raw_message}"
        await tts.speak_async(message, interrupt=True)

    @staticmethod
    async def emergency_contact_sms(emergency: ScoredEmergency) -> bool:
        """Send SMS to emergency contact via Twilio or Pushover."""
        contact_number = CONFIG.get("emergency", {}).get("contact_phone")
        if not contact_number:
            logger.warning("Emergency contact not configured — skipping Tier 4")
            return False
        # Fall back to Pushover DM to user as last resort
        return await EscalationChannels.pushover_alert(emergency, priority=2)
```

### 4.5 EmergencyLog

**File:** `districts/emergency/log.py` (new, ~150 lines)

**Responsibility:** Append-only, tamper-evident log of all emergencies.

```python
@dataclass
class EmergencyLogEntry:
    event_id: str
    severity: str
    domain: str
    signal_name: str
    detected_at: float
    classified_at: float | None
    severity_score: float
    actions_taken: list[dict]
    escalation_path: list[str]
    acknowledged: bool
    acknowledged_at: float | None
    resolved: bool
    resolved_at: float | None
    duration_seconds: float            # from detection to resolution
    outcome: str                       # "resolved" | "escalated" | "user_acknowledged" | "unresolved"


class EmergencyLog:
    """
    Immutable append-only log using SQLite with hash chain for tamper evidence.

    Schema:
        CREATE TABLE IF NOT EXISTS emergency_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            severity TEXT NOT NULL,
            domain TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            detected_at REAL NOT NULL,
            classified_at REAL,
            severity_score REAL,
            actions_taken TEXT,          -- JSON array
            escalation_path TEXT,        -- JSON array
            acknowledged INTEGER DEFAULT 0,
            acknowledged_at REAL,
            resolved INTEGER DEFAULT 0,
            resolved_at REAL,
            duration_seconds REAL,
            outcome TEXT,
            prev_hash TEXT,              -- SHA256 of previous entry
            entry_hash TEXT UNIQUE,      -- SHA256 of this entry's data + prev_hash
            created_at TEXT DEFAULT (datetime('now'))
        );

    Hash chain:
        entry_hash = SHA256(
            event_id + severity + domain + str(detected_at) +
            json.dumps(actions_taken) + prev_hash
        )

    Provides:
      - append(entry) → inserts with hash verification
      - get_recent(limit=50) → last N entries
      - get_by_domain(domain) → filter by domain
      - verify_chain() → validates hash chain integrity
      - summary(days=7) → statistics for time period
    """
```

**Log summary output:**

```python
# EmergencyLog.summary(7) returns:
{
    "total_emergencies": 42,
    "by_severity": {"CRITICAL": 3, "HIGH": 8, "MEDIUM": 18, "LOW": 13},
    "by_domain": {"system": 22, "network": 10, "security": 6, "health": 4},
    "avg_response_time_seconds": {"CRITICAL": 8.2, "HIGH": 24.5, "MEDIUM": 142.0},
    "avg_resolution_time_seconds": {"CRITICAL": 45.0, "HIGH": 120.3, "MEDIUM": 345.1},
    "outcomes": {"resolved": 30, "user_acknowledged": 8, "escalated": 3, "unresolved": 1},
    "false_alarms": 5,
    "chain_integrity": True,
}
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: Emergency Detector + Severity Classifier + Emergency Log

**Scope:**
- `districts/emergency/detector.py` — EmergencyDetector with all signal rules
- `districts/emergency/classifier.py` — SeverityClassifier with context modifiers
- `districts/emergency/log.py` — EmergencyLog with hash chain
- `districts/emergency/__init__.py` — package exports
- `tests/emergency/test_detector.py`
- `tests/emergency/test_classifier.py`
- `tests/emergency/test_log.py`

**Deliverables:**
1. EmergencyDetector with 20+ detection rules across health/security/system/network
2. Signal source integration: wire phone_node queue, SREMonitor, security guard
3. SeverityClassifier with time-of-day, recurrence, and compound event modifiers
4. EmergencyLog with SQLite storage and hash chain verification
5. Unit tests: rule matching, deduplication, debounce timing, severity modifiers, log integrity

### 5.2 Agent B: Runbook Executor + Escalation Manager + Integration

**Scope:**
- `districts/emergency/runbook.py` — RunbookExecutor with runbook registry
- `districts/emergency/escalation.py` — EscalationManager + EscalationChannels
- Integration with phone node (adb_bridge.py, ambient_server.py)
- Integration with districts/ops/ (DevOpsAutomator, SREMonitor, ErrorClassifier)
- Integration with autonomous_loop.py crash recovery
- `tests/emergency/test_runbook.py`
- `tests/emergency/test_escalation.py`
- `tests/emergency/test_integration.py`

**Deliverables:**
1. RunbookExecutor with 6+ runbooks covering disk, GPU, intrusion, health, process death, network
2. EscalationManager with 4-tier protocol per severity
3. Pushover integration with acknowledgment callbacks
4. Twilio phone call integration (optional, config-gated)
5. Laptop audio alert via VECTOR TTS
6. Integration wiring: phone_node signals connected to detector, SREMonitor events connected
7. Integration tests: end-to-end emergency lifecycle

---

## 6. Implementation Steps

### 6.1 Phase 1: Foundation (Agent A)

**Step 1.1: Create package structure**

- [ ] Create `districts/emergency/` directory
- [ ] Create `districts/emergency/__init__.py` with exports

**Step 1.2: Build EmergencyDetector**

- [ ] Create `districts/emergency/detector.py`
- [ ] Define `EmergencyEvent` dataclass
- [ ] Implement signal source queues (asyncio.Queue per monitor)
- [ ] Implement dedup_key generation per domain and signal
- [ ] Implement debounce window with configurable duration per rule
- [ ] Implement all detection rules from HEALTH_RULES, SECURITY_RULES, SYSTEM_RULES, NETWORK_RULES
- [ ] Wire phone_node health queue → detector
- [ ] Wire SREMonitor events → detector
- [ ] Wire security guard events → detector

**Step 1.3: Build SeverityClassifier**

- [ ] Create `districts/emergency/classifier.py`
- [ ] Define `ScoredEmergency` dataclass
- [ ] Implement base severity from detection rules
- [ ] Implement time-of-day modifier
- [ ] Implement recurrence modifier
- [ ] Implement compound event detection
- [ ] Implement user state modifier

**Step 1.4: Build EmergencyLog**

- [ ] Create `districts/emergency/log.py`
- [ ] Define `EmergencyLogEntry` dataclass
- [ ] Implement SQLite schema with hash chain
- [ ] Implement `append()` with hash verification
- [ ] Implement `verify_chain()` method
- [ ] Implement `summary()` statistics generator

**Step 1.5: Test**

- [ ] `tests/emergency/test_detector.py` — signal matching, dedup, debounce
- [ ] `tests/emergency/test_classifier.py` — severity score modifiers
- [ ] `tests/emergency/test_log.py` — append, read, hash chain verification

### 6.2 Phase 2: Automated Response (Agent B)

**Step 2.1: Build RunbookExecutor**

- [ ] Create `districts/emergency/runbook.py`
- [ ] Define `RunbookAction` and `ActionResult` dataclasses
- [ ] Implement RUNBOOK_REGISTRY with 6+ runbooks
- [ ] Implement action executor with step-by-step execution
- [ ] Implement timeout per action
- [ ] Implement rollback for failed actions
- [ ] Implement safety levels (safe/caution/destructive)

**Step 2.2: Build EscalationManager**

- [ ] Create `districts/emergency/escalation.py`
- [ ] Define `EscalationState` dataclass
- [ ] Implement tiered escalation protocol
- [ ] Implement Pushover channel with acknowledgment callback
- [ ] Implement Twilio voice call channel (config-gated)
- [ ] Implement laptop audio alert channel
- [ ] Implement emergency contact SMS channel
- [ ] Implement acknowledgment handling (Pushover callback + dashboard API)

**Step 2.3: Integration wiring**

- [ ] Create `districts/emergency/main.py` — EmergencyResponseSystem orchestrator
- [ ] Wire ExcalationManager → RunbookExecutor → EmergencyLog → EmergencyDetector
- [ ] Wire phone_node heartbeat monitoring into NetworkMonitor
- [ ] Wire SREMonitor into SystemMonitor
- [ ] Wire security guard into SecurityMonitor
- [ ] Add emergency system startup to `run_vector.py`

**Step 2.4: Test**

- [ ] `tests/emergency/test_runbook.py` — runbook selection, execution, rollback
- [ ] `tests/emergency/test_escalation.py` — tier timing, acknowledgment, channels
- [ ] `tests/emergency/test_integration.py` — end-to-end: detect → classify → runbook → escalate → log

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `districts/emergency/__init__.py` | 10 | Package exports |
| `districts/emergency/detector.py` | 350 | EmergencyDetector with signal rules |
| `districts/emergency/classifier.py` | 200 | SeverityClassifier with context modifiers |
| `districts/emergency/runbook.py` | 300 | RunbookExecutor with action registry |
| `districts/emergency/escalation.py` | 250 | EscalationManager + channels |
| `districts/emergency/log.py` | 150 | EmergencyLog with hash chain |
| `districts/emergency/main.py` | 200 | EmergencyResponseSystem orchestrator |
| `tests/emergency/test_detector.py` | 120 | Detector unit tests |
| `tests/emergency/test_classifier.py` | 100 | Classifier unit tests |
| `tests/emergency/test_log.py` | 80 | Log unit tests |
| `tests/emergency/test_runbook.py` | 100 | Runbook unit tests |
| `tests/emergency/test_escalation.py` | 100 | Escalation unit tests |
| `tests/emergency/test_integration.py` | 150 | End-to-end tests |

### Modify:

| File | Change |
|------|--------|
| `run_vector.py` | Add emergency system startup option |
| `core/config.py` | Add EmergencyConfig (thresholds, Twilio settings, escalation timing) |
| `phone_node/adb_bridge.py` | Add emergency signal queue publishing |
| `phone_node/ambient_server.py` | Add structured emergency events instead of raw Pushover |
| `districts/ops/SREMonitor.py` | Add event publishing to EmergencyDetector queue |
| `districts/ops/DevOpsAutomator.py` | Add security event publishing to EmergencyDetector queue |
| `districts/ops/ErrorClassifier.py` | Add error event publishing for OOM/crash detection |
| `core/loop/autonomous_loop.py` | Add crash event publishing to emergency system |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| CRITICAL detection latency | Up to 4h | <5s | Inject test signal, measure time to EmergencyEvent creation |
| CRITICAL end-to-end response | N/A | <10s | Inject test signal, measure time to Pushover sent |
| HIGH end-to-end response | N/A | <30s | Inject test signal, measure time to first action completed |
| Automated runbook execution | N/A | <30s | Runbook with 4 actions, measure total execution |
| Pushover acknowledgment handling | N/A | <5s | Send ack via callback API, measure state transition |
| Twilio call initiation (if configured) | N/A | <10s | Measure from escalation trigger to call placed |
| Hash chain integrity | N/A | 100% | Insert 1000 entries, verify_chain() passes |
| False alarm rate | Unknown | <1/day | Measure over 7 days, tune thresholds |
| Signal coverage | 3 domains partial | 4 domains full | Count of rule files x signal sources wired |
| Emergency log query speed | N/A | <100ms for 10k entries | SQLite index performance test |

### 8.2 Functional Criteria

1. Health emergency (simulated flatline) → CRITICAL → Pushover within 10s
2. Disk >95% → HIGH → automated cleanup runbook → user notified of freed space
3. GPU >95°C → CRITICAL → inference paused → user notified within 30s
4. 3 disk warnings in 1h → automatic severity escalation to HIGH
5. CRITICAL emergency at 3AM → accelerates to Tier 3 within 2 minutes
6. Pushover acknowledgment → escalation stops → log reflects acknowledgment
7. Emergency log hash chain remains intact after 1000+ entries
8. Downtime during laptop sleep → emergency pending resumes on wake
9. Compound events (disk+RAM+swap) → CRITICAL override with reasoning in log

### 8.3 Negative Criteria (What Must NOT Happen)

1. False alarm rate >1/day after tuning period
2. Broken emergency system crashes main VECTOR loop
3. Emergency log lost on disk failure (WAL mode, fsync)
4. Escalation firing during known maintainance window (configurable quiet hours)
5. Pushover spam — same emergency re-notified within debounce window

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Already in requirements.txt:
httpx>=0.27.0              # Pushover API, Twilio API
loguru>=0.7.2              # Emergency logging
asyncio                    # Standard lib — signal queue management
psutil>=5.9.0              # System monitoring (already in use)

# Add to requirements.txt:
twilio>=8.0.0              # Optional: phone call escalation
```

### 9.2 Hardware Dependencies

- **Phone node (Android via Termux/ADB):** Health signals source. Required for health domain coverage.
- **Twilio account:** Required for phone call escalation (Tier 3). Falls back to Pushover priority if absent.
- **Internet:** Required for Pushover + Twilio. Local alerts (laptop speakers) work offline.

### 9.3 Internal Dependencies

1. **specs-04 (Security):** SecurityMonitor events feed into EmergencyDetector's Security signals. If specs-04 is not yet implemented, security detection defaults to "not wired" until integration.
2. **specs-06 (Health):** Phone node health signals (HR, movement, battery) feed into EmergencyDetector's Health signals. Must integrate with `phone_node/ambient_server.py` event queues.
3. **specs-02 (Event Bus):** Once the event bus exists, EmergencyDetector should subscribe to typed events (`health.alert`, `security.alert`, `system.crash`) instead of monitoring raw queues. Wire both modes for backward compatibility.

### 9.4 Configuration

```python
# EmergencyConfig added to core/config.py
class EmergencyConfig(BaseModel):
    pushover_token: str = ""
    pushover_user: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    user_phone: str = ""
    emergency_contact_phone: str = ""
    escalation_timing: dict = {
        "CRITICAL": {"tier2_seconds": 30, "tier3_seconds": 120, "tier4_seconds": 300},
        "HIGH": {"tier2_seconds": 60, "tier3_seconds": 300, "tier4_seconds": 600},
        "MEDIUM": {"tier2_seconds": 300, "tier3_seconds": 0, "tier4_seconds": 0},
        "LOW": {"tier2_seconds": 0, "tier3_seconds": 0, "tier4_seconds": 0},
    }
    debounce_default_seconds: int = 60
    false_alarm_tuning_days: int = 7
    quiet_hours_start: int = 14  # 2PM (maintenance window)
    quiet_hours_end: int = 15    # 3PM
    enable_twilio: bool = False
    enable_laptop_alert: bool = True
```

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| False alarms from noisy signals (phone gyro, temp spikes) | High | Medium | Tuning period with adaptive thresholds; debounce windows |
| Pushover API rate limit (max 10k/month) | Low | Medium | Rate limit daily alert count; batch non-critical |
| Twilio call fails (no signal, wrong number) | Medium | Low | Fall back to Pushover priority; log failure |
| Emergency system crash takes down VECTOR | Low | High | Emergency system runs as separate process; main loop unaffected |
| Disk full prevents emergency log writes | Low | Critical | Emergency log has separate health check; critical alerts skip log write if disk fails |
| Phone node offline → no health signals | Medium | Medium | Detect missing heartbeat as its own emergency; degrade gracefully |
| Hash chain verification fails on partial write | Low | Medium | WAL mode + fsync; recovery mode on next startup |

---

## 11. Appendix: Emergency Event Flow Examples

### Example 1: Disk Full

```
1. SREMonitor polls disk: 96% used (threshold: 85% MEDIUM, 95% HIGH)
2. EmergencyDetector receives: domain="system", signal="disk_over_95", value=96
3. Debounce check: first occurrence → pass through
4. SeverityClassifier: base=HIGH, recurrence=0 (first time) → modifier=1.0 → final=HIGH
5. RunbookExecutor: selects "system:disk_full" runbook
   → Action 1: analyze_disk (finds 12GB in temp) → success
   → Action 2: clean_cache (removed 8.2GB) → success
   → Action 3: compress_logs (saved 1.3GB) → success
   → Action 4: report: freed 9.5GB, disk now at 81%
6. EscalationManager: Tier 1 complete (automated) → check if resolved → disk at 81% → resolved!
   → Log: resolved, duration=24.7s, actions=[analyze, clean, compress]
   → Pushover: status update (informational)
7. EmergencyLog.append(entry)
```

### Example 2: HR Flatline (Simulated)

```
1. Phone node sends: domain="health", signal="hr_reading", value=0
2. EmergencyDetector: HR < 20 → CRITICAL → EmergencyEvent(severity=CRITICAL)
3. Debounce: debounce_seconds=10 → fast path for CRITICAL
4. SeverityClassifier: CRITICAL base, time=3:05AM (night multiplier 1.3) → score escalated
5. RunbookExecutor: selects "health:fall_detected" runbook
   → Action 1: pushover_priority (priority=2, retry=30s) → sent
   → Action 2: play_audio_alert on laptop → playing
6. EscalationManager:
   Tier 1: runbook executing (0s)
   Tier 2: Pushover sent (30s elapsed, no ack)
   Tier 3: Twilio call initiated (120s elapsed, no ack)
   Tier 4: Emergency contact SMS (300s elapsed, no ack)
7. User acknowledges via Pushover callback at 85s
   → EscalationManager: acknowledged, stop escalation
   → EmergencyLog: outcome="user_acknowledged", duration=85s
```

### Example 3: Compound System Failure

```
1. SREMonitor reports: disk=91%, RAM=92%, swap=78%
2. EmergencyDetector: three MEDIUM events within 30s
3. Debounce: different dedup_keys, but within 10s → compound check
4. SeverityClassifier: compound event match: "disk_full + ram_over_95 + swap_filling"
   → override: CRITICAL, reason="System capacity failure imminent"
5. RunbookExecutor: selects "system:disk_full" runbook (highest priority compound component)
   → Clean disk → clears 5GB
   → Then: memory pressure runbook (secondary) → reduces cache, frees 2GB RAM
6. EscalationManager: CRITICAL → Pushover immediate, phone call after 2min
7. EmergencyLog: compound flag in actions_taken, total duration
```

---

## 12. Appendix: Integration Points

### Phone Node Integration

```python
# In phone_node/ambient_server.py, add:
class HealthEventPublisher:
    """Publishes health events to the EmergencyDetector signal queue."""
    
    def __init__(self, emergency_queue: asyncio.Queue):
        self._queue = emergency_queue
    
    async def publish_hr(self, bpm: int) -> None:
        await self._queue.put({
            "domain": "health",
            "signal": "hr_reading",
            "value": bpm,
            "source": "phone_node",
            "timestamp": time.time(),
        })
    
    async def publish_movement(self, active: bool, minutes_stationary: int) -> None:
        await self._queue.put({
            "domain": "health", 
            "signal": "movement_status",
            "value": minutes_stationary if not active else 0,
            "source": "phone_node",
            "timestamp": time.time(),
        })
    
    async def publish_fall(self, detected: bool) -> None:
        if detected:
            await self._queue.put({
                "domain": "health",
                "signal": "fall_detected",
                "value": True,
                "source": "phone_node",
                "timestamp": time.time(),
            })
```

### SREMonitor Integration

```python
# In districts/ops/SREMonitor.py, add event publishing to detector queue:
class SREEventPublisher:
    def __init__(self, emergency_queue: asyncio.Queue):
        self._queue = emergency_queue
    
    async def publish_system_event(self, metric: str, value: float) -> None:
        await self._queue.put({
            "domain": "system",
            "signal": metric,
            "value": value,
            "source": "sre_monitor",
            "timestamp": time.time(),
        })
    
    async def publish_network_event(self, signal: str, value: float | bool) -> None:
        await self._queue.put({
            "domain": "network",
            "signal": signal,
            "value": value,
            "source": "sre_monitor",
            "timestamp": time.time(),
        })
```
