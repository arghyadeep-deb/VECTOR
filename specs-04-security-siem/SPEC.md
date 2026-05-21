# SPEC-04: Security SIEM & Automated Incident Response

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This spec requires 4 parallel agents and careful sequencing of shared schemas.

**Goal:** Transform VECTOR's software-level security (prompt injection, SSRF guard, taint tracker) into a full SIEM-like system with network monitoring, real-time threat detection, centralized log aggregation, automated incident playbooks, and a live security dashboard.

**Architecture:** Build a 6-component security stack on top of the existing districts/security/ agents and core/security/ guards. NetworkMonitor captures packets via scapy. LogAggregator centralizes JSON structured logs from all VECTOR services. DetectionRules engine runs YAML rules in real-time. AlertManager deduplicates, scores, and routes alerts. IncidentPlaybookRunner executes automated response playbooks. SecurityDashboard provides live threat visualization.

**Tech Stack:** scapy (packet capture), structured logging (loguru JSON sink), YAML rule engine (custom), SQLite (alert store), Pushover (notifications), FastAPI/React (dashboard), asyncio (concurrent monitors)

**Score:** Current 38/100 — Target 85/100

---

## 1. Problem Statement

### 1.1 Current Security Gaps

| Dimension | Score | Issue |
|-----------|-------|-------|
| Network Monitoring | 5/100 | Zero network-level detection. No packet capture, no connection tracking, no DNS monitoring. If an attacker establishes a C2 channel on the local network, VECTOR cannot detect it. |
| Log Aggregation | 20/100 | Services log via loguru to separate files. No centralized log collection, no structured JSON schema, no search, no correlation across services. |
| Threat Detection | 40/100 | ThreatScout checks running processes for suspicious names. NodeGuard watches file integrity. No real-time detection, no signature matching, no behavioral analysis. |
| Alert Management | 30/100 | Pushover works for critical alerts but there's no deduplication, no severity scoring, no alert routing, no suppression. Every detection fires immediately without context. |
| Incident Response | 10/100 | No automated playbooks. Security alerts require manual investigation. No isolation, no IP blocking, no key rotation automation. Response time is unbounded. |
| Security Visibility | 25/100 | No dashboard. No historical alert view. No security health score. No trend analysis. User is blind to security posture between alerts. |

### 1.2 Root Causes

1. **No network layer instrumentation:** VECTOR runs on a local machine with network access but never inspects traffic. An outbound C2 beacon or port scan from another machine on the LAN goes completely undetected.

2. **Isolated logging:** Each module writes its own log file. The context engine (14 domains), research_engine (34 sub-modules), phone_node, voice pipeline, and all 8 districts each log independently. No single view exists.

3. **Stateless security agents:** ThreatScout, MalwareHunter, and NodeGuard run on timer-based cycles and check state at that moment. They don't track trends, don't correlate events, and don't remember past detections beyond what episodic memory stores.

4. **Manual response only:** When a threat is detected (e.g., suspicious process), VECTOR logs it and optionally sends a Pushover alert. No automated containment — no process kill, no IP block, no credential rotation, no evidence snapshot.

### 1.3 Measured Impact

- Time to detect port scan: N/A (undetectable)
- Time to detect C2 beacon: N/A (undetectable)
- Prompt injection detection rate: ~70% (core/security/prompt_injection.py rules)
- Alert noise: every detection fires once per cycle with no dedup
- Time to incident response: minutes to hours (manual)
- Log query time: minutes (manual grep across files)
- Security posture visibility: zero (no dashboard)

---

## 2. Current Architecture

### 2.1 districts/security/ Agents

| Agent | File | Capability | Gap |
|-------|------|-----------|-----|
| ThreatScout | `districts/security/threat_scout.py` | Scans running processes for suspicious names, monitors Windows event logs for error spikes | No network visibility, no real-time detection |
| MalwareHunter | `districts/security/malware_hunter.py` | Scans files for known malware signatures | Signature-based only, no behavioral detection |
| NodeGuard | `districts/security/node_guard.py` | Monitors file integrity via checksums | No process-level or network-level monitoring |
| DataRedactor | `districts/security/data_redactor.py` | Redacts PII/keys from outputs | Only applied at output layer |
| ThreatDetectionEngineer | `districts/security/threat_detection_engineer.py` | LLM-based threat analysis | Slow, expensive, not real-time |

### 2.2 core/security/ Guards

| Module | File | Capability |
|--------|------|-----------|
| PromptInjection | `core/security/prompt_injection.py` | Detects prompt injection attempts in user input |
| SSRFGuard | `core/security/ssrf_guard.py` | Validates URLs to prevent server-side request forgery |
| TaintTracker | `core/security/taint_tracker.py` | Tracks tainted data flow through the system |

### 2.3 Existing Infrastructure

- **Pushover:** Configured via PUSHOVER_TOKEN and PUSHOVER_USER in .env. Used for critical alerts.
- **Phone node:** `phone_node/ambient_server.py` sends heartbeat every 60s.
- **Context engine:** `core/loop/context_engine.py` maintains 14-domain world state.
- **Event bus:** Planned in specs-02 (Redis pub/sub). Not yet available — this spec integrates directly first, with event bus adapter as a future upgrade.
- **Config:** `core/config.py` (Pydantic V2). All new components register their settings here.

---

## 3. Target Architecture

```
                      ┌─────────────────────────────────────┐
                      │         SecurityDashboard            │
                      │   (FastAPI + React, live WebSocket)  │
                      └──────────┬──────────────────────────┘
                                 │ Query
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
     │ NetworkMonitor│  │ LogAggregator│  │  AlertManager     │
     │ (scapy)      │  │ (JSON logs)  │  │ (dedup, severity) │
     └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
            │                 │                    │
            ▼                 ▼                    ▼
     ┌─────────────────────────────────────────────────────┐
     │               DetectionRules Engine                  │
     │  (YAML rules: port scans, brute force, exfil, etc.) │
     └──────────────────────┬──────────────────────────────┘
                            │ Trigger
                            ▼
     ┌─────────────────────────────────────────────────────┐
     │           IncidentPlaybookRunner                     │
     │  (isolate process, block IP, rotate keys, notify)    │
     └─────────────────────────────────────────────────────┘
                            │
                            ▼
     ┌─────────────────────────────────────────────────────┐
     │               Data Stores                            │
     │  SQLite: alerts, events, playbook executions          │
     │  JSON: aggregated logs (rotated daily)               │
     │  YAML: detection rules (versioned in /rules/)        │
     └─────────────────────────────────────────────────────┘
```

### 3.1 Data Flow

1. **NetworkMonitor** captures packets via scapy, extracts metadata (src/dst IP, ports, protocols, DNS queries, TLS SNI), publishes structured events to DetectionRules.
2. **LogAggregator** receives JSON-structured logs from all VECTOR services via a loguru sink. Routes critical log lines to DetectionRules for correlation.
3. **DetectionRules** engine evaluates events against YAML rules. Each rule produces 0..N alerts with severity, evidence, and recommendation.
4. **AlertManager** receives alerts, deduplicates (same rule+target within TTL), scores severity, and forwards high-severity alerts to IncidentPlaybookRunner + Pushover.
5. **IncidentPlaybookRunner** receives high-severity alerts, matches them to playbooks (YAML), executes automated response steps with confirmation checkpoints, logs execution.
6. **SecurityDashboard** queries SQLite stores via a FastAPI backend, renders live threat view via React + WebSocket.

---

## 4. Component Breakdown

### 4.1 NetworkMonitor

**Purpose:** Real-time packet capture and analysis for threat detection on the local network interface.

**File:** `districts/security/network_monitor.py`

**Capabilities:**
- Capture packets via scapy on the primary network interface (auto-detect or configurable)
- Extract key metadata: src/dst IP, src/dst port, protocol (TCP/UDP/ICMP/DNS/HTTP/TLS), packet count per flow
- Detect port scans: SYN scan, FIN scan, NULL scan, UDP scan patterns (multiple ports to same IP in short window)
- Detect DNS tunneling: high entropy subdomains, excessive query volume to single domain, unusual record types
- Detect suspicious connections: known malicious IPs (via local blocklist + Threat Intelligence feed stub), unusual outbound ports, connections to non-HTTP ports on known services
- Track connection rates: connection attempts per second, per-destination connection count, failed connection ratio
- Export events as structured JSON dicts to DetectionRules

**Class structure:**
```python
class NetworkMonitor:
    async def start_capture(self, interface: str = None)
    async def stop_capture(self)
    async def _capture_loop(self)
    def _analyze_packet(self, packet) -> dict | None
    async def _detect_port_scan(self, flow_key: str) -> dict | None
    def _check_dns_tunneling(self, dns_query: str) -> float  # entropy score
    def _check_blocklist(self, ip: str) -> bool
    def _get_traffic_stats(self) -> dict  # rates, top talkers
```

**Configuration (registered in core/config.py):**
```python
NETWORK_MONITOR_INTERFACE: str = ""  # auto-detect if empty
NETWORK_MONITOR_PROMISCUOUS: bool = False
NETWORK_MONITOR_SNAPLEN: int = 65535
NETWORK_MONITOR_FILTER: str = "ip"  # BPF filter
NETWORK_MONITOR_SCAN_THRESHOLD: int = 20  # ports to same IP within window
NETWORK_MONITOR_SCAN_WINDOW: int = 5  # seconds
NETWORK_MONITOR_DNS_ENTROPY_THRESHOLD: float = 3.5
NETWORK_MONITOR_BLOCKLIST_PATH: str = "data/security/ip_blocklist.txt"
```

**Dependencies:** `scapy>=2.5.0` (requires Npcap on Windows — installer handled by setup script), asyncio, loguru

### 4.2 LogAggregator

**Purpose:** Centralized structured log collection from all VECTOR services with search, correlation, and forwarding to DetectionRules.

**File:** `districts/security/log_aggregator.py`

**Capabilities:**
- Define a standard JSON log schema for all VECTOR services
- Provide a loguru sink that all modules use → writes to a shared rotating JSON log directory
- Collect logs from: core/loop, core/security, districts/*, phone_node, core/research_engine, voice pipeline, core/sensing
- Parse and index log entries by service name, log level, timestamp, and correlation ID
- Detect log anomalies: error rate spikes, unusual silence from a service, repeated failures
- Forward matching log events to DetectionRules (configurable patterns — e.g., "auth failure" events, "connection refused")
- Log retention: 30 days rotating, with compression on rotation

**Standard Log Schema:**
```python
@dataclass
class LogEvent:
    timestamp: datetime        # ISO 8601 UTC
    service: str               # "security.threat_scout", "core.loop", etc.
    correlation_id: str | None # UUID for tracing request chains
    level: str                 # "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    message: str
    module: str                # __name__ of emitting module
    extra: dict                # arbitrary structured context
    host: str                  # local hostname
```

**LogAggregator sink:**
```python
def vector_log_sink(message):
    # Called by loguru for every log message
    # Writes to: data/logs/aggregated/{service}/{date}.jsonl
    # Forwards WARNING+ to DetectionRules event queue
```

**Configuration:**
```python
LOG_AGGREGATOR_DIR: str = "data/logs/aggregated"
LOG_AGGREGATOR_RETENTION_DAYS: int = 30
LOG_AGGREGATOR_MAX_SIZE_MB: int = 100
LOG_AGGREGATOR_FORWARD_LEVEL: str = "WARNING"  # minimum level to forward to DetectionRules
```

### 4.3 DetectionRules

**Purpose:** YAML-based rule engine that evaluates events from NetworkMonitor and LogAggregator against threat signatures and behavioral patterns.

**File:** `districts/security/detection_rules.py`

**Rule Format (YAML):**
```yaml
rules:
  - id: "port_scan_syn"
    name: "SYN Port Scan Detected"
    description: "Detects rapid SYN scans against multiple ports"
    source: "network_monitor"
    condition:
      type: "rate"
      field: "event_type"
      value: "syn_packet"
      threshold: 20
      window: 5  # seconds
      aggregation: "dst_ip"
    severity: 7  # 1-10
    response:
      - "alert"
      - "pushover"
    tags: ["recon", "port_scan"]

  - id: "dns_tunneling_high_entropy"
    name: "Possible DNS Tunneling"
    description: "DNS query with abnormally high subdomain entropy"
    source: "network_monitor"
    condition:
      type: "threshold"
      field: "dns_entropy"
      operator: ">"
      value: 3.5
    severity: 8
    response:
      - "alert"
      - "pushover"
      - "playbook:investigate_dns"
    tags: ["exfiltration", "dns"]

  - id: "auth_brute_force"
    name: "Authentication Brute Force Attempt"
    description: "Multiple auth failures from same source in short window"
    source: "log_aggregator"
    condition:
      type: "rate"
      field: "log_pattern"
      pattern: "(auth|login|authentication).*(fail|denied|invalid)"
      threshold: 5
      window: 60
      aggregation: "extra.source_ip"
    severity: 6
    response:
      - "alert"
      - "playbook:rate_limit_source"
    tags: ["auth", "brute_force"]

  - id: "prompt_injection_attempt"
    name: "Prompt Injection Attempt"
    description: "Detected prompt injection in user input"
    source: "core_security"
    condition:
      type: "presence"
      field: "event_type"
      value: "prompt_injection_detected"
    severity: 9
    response:
      - "alert"
      - "pushover"
      - "playbook:log_and_notify"
    tags: ["llm", "injection"]

  - id: "data_exfil_large_outbound"
    name: "Large Outbound Data Transfer"
    description: "Unusual volume of outbound data to single destination"
    source: "network_monitor"
    condition:
      type: "rate"
      field: "bytes_out"
      threshold: 10485760  # 10MB
      window: 300  # 5 minutes
      aggregation: "dst_ip"
    severity: 9
    response:
      - "alert"
      - "pushover"
      - "playbook:investigate_exfil"
    tags: ["exfiltration", "data_loss"]

  - id: "service_silence"
    name: "Service Heartbeat Missing"
    description: "Expected service heartbeat not received within TTL"
    source: "log_aggregator"
    condition:
      type: "absence"
      field: "service_heartbeat"
      window: 120  # seconds
    severity: 8
    response:
      - "alert"
      - "pushover"
      - "playbook:restart_service"
    tags: ["availability", "heartbeat"]
```

**Engine capabilities:**
- Load rules from `data/security/rules/*.yaml` at startup, hot-reload on SIGHUP
- Receive events asynchronously via an asyncio.Queue
- Evaluate each event against all matching rules (filtered by source)
- Produce Alert objects with: id, rule_id, timestamp, severity, source, evidence (dict), status ("open"/"closed")
- Track rule match counts for tuning
- Support rule enable/disable via YAML `enabled: true/false`

**Rule conditions supported:**
- `presence`: event with matching field/value exists
- `absence`: expected event not received within window
- `threshold`: numeric field exceeds operator+value
- `rate`: count of matching events exceeds threshold in window
- `pattern`: regex match on string field
- `composite`: AND/OR/NOT of multiple conditions (advanced rules)
- `correlation`: two different events from different sources in time window (e.g., port scan + auth failure from same IP)

**Configuration:**
```python
DETECTION_RULES_DIR: str = "data/security/rules"
DETECTION_RULES_HOT_RELOAD: bool = True
DETECTION_RULES_MAX_EVENTS_PER_SECOND: int = 1000
DETECTION_RULES_EVENT_QUEUE_SIZE: int = 10000
```

### 4.4 AlertManager

**Purpose:** Deduplicate, score, and route security alerts to the appropriate channels.

**File:** `districts/security/alert_manager.py`

**Capabilities:**
- Receive alerts from DetectionRules asynchronously
- Deduplication: same rule_id + target (e.g., IP, process) within configurable TTL produces only one alert (option to increment count)
- Severity scoring: base severity from rule + modifiers (repeat count, time of day, related alerts)
- Alert lifecycle: NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED
- Routing: configurable per-severity thresholds for Pushover, Dashboard critical section, Playbook trigger
- Throttling: maximum N alerts per source per hour to prevent flood
- Periodic summary: combined digest of low-severity alerts every 15 minutes
- Storage: SQLite database for alerts (schema below)
- Query API: GET /api/alerts with filters (severity, status, source, time range)

**SQLite Schema (alerts.db):**
```sql
CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    severity INTEGER NOT NULL,
    source TEXT NOT NULL,
    target TEXT,               -- the IP, process, service that triggered
    title TEXT NOT NULL,
    description TEXT,
    evidence TEXT,             -- JSON dict
    status TEXT DEFAULT 'new', -- new|acknowledged|investigating|resolved|closed
    playbook_id TEXT,
    playbook_status TEXT,      -- pending|running|completed|failed
    count INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    resolved_at TEXT,
    tags TEXT                  -- JSON array
);

CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX idx_alerts_rule_target ON alerts(rule_id, target);
```

**Alert dedup logic:**
```python
def _dedup_key(self, alert: Alert) -> str:
    return f"{alert.rule_id}:{alert.target}"

# Within DEDUP_TTL (default 300s), same key increments count instead of new alert
# After TTL expires, a new occurrence creates a fresh alert
```

**Configuration:**
```python
ALERT_DEDUP_TTL_SECONDS: int = 300
ALERT_PUSHOVER_MIN_SEVERITY: int = 7
ALERT_PLAYBOOK_MIN_SEVERITY: int = 8
ALERT_MAX_PER_SOURCE_PER_HOUR: int = 50
ALERT_DIGEST_INTERVAL_MINUTES: int = 15
ALERT_DB_PATH: str = "data/security/alerts.db"
```

### 4.5 IncidentPlaybookRunner

**Purpose:** Execute automated security incident response playbooks based on alert triggers.

**File:** `districts/security/incident_playbook_runner.py`

**Playbook Format (YAML):**
```yaml
playbooks:
  - id: "investigate_dns"
    name: "Investigate DNS Tunneling"
    trigger_rules: ["dns_tunneling_high_entropy"]
    steps:
      - action: "capture_packets"
        params:
          filter: "port 53 and host {target}"
          duration: 30
        description: "Capture DNS packets to {target} for 30 seconds"
      - action: "analyze_dns"
        params:
          sample_size: 100
        description: "Extract top 100 DNS queries for entropy analysis"
      - action: "check_process"
        params:
          process_name: None  # any process making DNS queries
        description: "Identify which process is making the DNS queries"
      - action: "notify"
        params:
          message: "DNS tunneling investigation complete for {target}. Evidence: {evidence_path}"
          priority: 1
    rollback:
      - action: "notify"
        params:
          message: "DNS investigation playbook rolled back"
    timeout: 120

  - id: "investigate_exfil"
    name: "Investigate Data Exfiltration"
    trigger_rules: ["data_exfil_large_outbound"]
    steps:
      - action: "snapshot_connections"
        params:
          target: "{target}"
        description: "Snapshot all active connections to {target}"
      - action: "block_ip"
        params:
          ip: "{target}"
          duration: 3600  # 1 hour block
        description: "Block outbound IP {target} for 1 hour"
        confirm: true    # requires user confirmation
      - action: "rotate_keys"
        description: "Rotate API keys as precaution"
        confirm: true
      - action: "notify"
        params:
          message: "Data exfiltration playbook executed. Blocked {target} for 1 hour. Keys rotated."
          priority: 1
    rollback:
      - action: "unblock_ip"
        params:
          ip: "{target}"
      - action: "notify"
        params:
          message: "Unblocked {target}. Rollback complete."
    timeout: 300
```

**Supported actions:**
- `capture_packets`: Start a tcpdump/scapy capture to a pcap file with filter
- `analyze_dns`: Run DNS entropy analysis on captured packets
- `check_process`: List processes making network connections to target
- `block_ip`: Add Windows Firewall rule to block outbound/inbound to IP (via `netsh advfirewall`)
- `unblock_ip`: Remove Windows Firewall block rule
- `rotate_keys`: Trigger key rotation (calls core/security credential rotation)
- `snapshot_connections`: Save current netstat output + process list
- `isolate_process`: Kill a specific process by PID/name (Windows `taskkill`)
- `notify`: Send Pushover notification with message
- `log_evidence`: Write structured evidence bundle to data/security/incidents/

**Playbook execution:**
- Runs in a dedicated asyncio task with timeout
- Each step logs success/failure to incident record
- `confirm: true` steps pause and notify user via Pushover + wait for confirmation (or timeout and proceed)
- On any step failure: attempt rollback (reverse steps in order) unless `ignore_failure: true`
- Full execution log saved to incident record
- Playbook status: pending → running → completed / failed / rolled_back

**Incident store (SQLite, same db as alerts):**
```sql
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    playbook_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    steps JSON,           -- array of step results
    evidence_path TEXT,
    error TEXT,
    FOREIGN KEY (alert_id) REFERENCES alerts(id)
);
```

**Configuration:**
```python
PLAYBOOK_DIR: str = "data/security/playbooks"
PLAYBOOK_CONFIRM_TIMEOUT: int = 300  # seconds to wait for user confirmation
PLAYBOOK_MAX_EXECUTION_TIME: int = 600
PLAYBOOK_CONFIRMATION_CHANNEL: str = "pushover"  # or "dashboard"
```

### 4.6 SecurityDashboard

**Purpose:** Real-time visualization of security posture, live threats, alert history, and system health.

**Technology:** FastAPI backend + React frontend, WebSocket for live updates.

**File:** `dashboard/security_dashboard/`

**Backend (dashboard/security_dashboard/api.py):**
- `GET /api/alerts` — paginated, filterable alert list
- `GET /api/alerts/{id}` — single alert detail with evidence
- `GET /api/alerts/stats` — severity distribution, top rules, recent counts
- `GET /api/incidents` — recent playbook executions
- `GET /api/incidents/{id}` — full incident with steps
- `GET /api/network/stats` — connection rates, top talkers, protocol distribution
- `GET /api/health` — security system component status (green/yellow/red)
- `WS /api/ws/live` — WebSocket pushing new alerts in real-time
- `POST /api/alerts/{id}/acknowledge` — mark alert acknowledged
- `POST /api/alerts/{id}/resolve` — mark alert resolved

**Frontend (dashboard/security_dashboard/):**
- Live alert feed (WebSocket) — newest alerts stream in
- Alert timeline — scatter plot of alert severity over time
- Security health score — composite percentage (network OK, rules loaded, log aggregator running, etc.)
- Top threats — most frequent/severity rules in last 24h
- Network traffic overview — top talkers, protocol pie, connection rate gauge
- Incident log — recent playbook executions with status badges
- Configuration panel — toggle rules on/off, adjust severity thresholds

**How to serve:**
- FastAPI app runs on port 8844 (configurable)
- Serves React static build from `dashboard/security_dashboard/build/`
- WebSocket endpoint for live push
- VECTOR autonomous loop starts the dashboard as a background task if enabled

**Configuration:**
```python
SECURITY_DASHBOARD_ENABLED: bool = False  # opt-in
SECURITY_DASHBOARD_PORT: int = 8844
SECURITY_DASHBOARD_HOST: str = "127.0.0.1"
SECURITY_DASHBOARD_REFRESH_MS: int = 2000
```

---

## 5. Agent Dispatch Plan

### Agent A: NetworkMonitor + Packet Capture

**Focus:** Build the network monitoring layer.

**Tasks:**
1. Install Npcap dependency (or verify)
2. Implement `districts/security/network_monitor.py` with scapy capture loop
3. Implement port scan detection (SYN, FIN, NULL, UDP)
4. Implement DNS tunneling detection (entropy analysis)
5. Implement blocklist check
6. Implement connection rate tracking
7. Register config in `core/config.py`
8. Write unit tests

**Estimated effort:** 3-4 hours

### Agent B: LogAggregator + Structured Logging Retrofit

**Focus:** Build centralized logging and retrofit all modules.

**Tasks:**
1. Implement `districts/security/log_aggregator.py` with loguru JSON sink
2. Define standard LogEvent schema
3. Retrofit `core/loop/` modules to use structured logging
4. Retrofit `districts/security/` agents to use structured logging
5. Retrofit `phone_node/ambient_server.py` to use structured logging
6. Implement log anomaly detection (error rate spikes, service silence)
7. Add forwarder from LogAggregator to DetectionRules event queue
8. Register config
9. Write unit tests

**Estimated effort:** 3-4 hours

### Agent C: DetectionRules + AlertManager

**Focus:** Build the detection engine and alert management.

**Tasks:**
1. Implement `districts/security/detection_rules.py`
2. Create YAML rule format and parser
3. Implement all rule condition types (presence, absence, threshold, rate, pattern)
4. Create initial rule set (5+ rules)
5. Implement `districts/security/alert_manager.py`
6. Implement dedup, severity scoring, routing
7. Implement SQLite schema and storage
8. Wire Pushover integration for high-severity alerts
9. Register config
10. Write unit tests

**Estimated effort:** 4-5 hours

### Agent D: IncidentPlaybookRunner + SecurityDashboard

**Focus:** Build automated response and visualization.

**Tasks:**
1. Implement `districts/security/incident_playbook_runner.py`
2. Create playbook YAML format and parser
3. Implement playbook actions (block_ip, notify, capture_packets, etc.)
4. Implement confirmation gates and rollback
5. Implement FastAPI backend for dashboard
6. Implement React frontend with WebSocket live feed
7. Wire dashboard into VECTOR autonomous loop startup
8. Create initial playbooks (investigate_dns, investigate_exfil, etc.)
9. Register config
10. Write integration tests

**Estimated effort:** 5-6 hours

---

## 6. Implementation Steps

### Phase 1: Foundation (Agent B + Agent C schema)

- [ ] **1.1** Create shared schema module: `core/security/events.py` — Alert, LogEvent, NetworkEvent, Incident Pydantic models
- [ ] **1.2** Create `data/security/` directory structure (rules/, playbooks/, incidents/)
- [ ] **1.3** Register all new config values in `core/config.py`
- [ ] **1.4** Add `scapy>=2.5.0` to requirements.txt

### Phase 2: Log Aggregation (Agent B)

- [ ] **2.1** Implement `districts/security/log_aggregator.py` — loguru sink + centralized writer
- [ ] **2.2** Retrofit core/loop modules: add `correlation_id` and structured `extra` dict to all loguru calls
- [ ] **2.3** Retrofit districts/security/ agents: switch from print/basic logging to loguru JSON structured
- [ ] **2.4** Retrofit phone_node: add service name + correlation_id to ambient_server.py heartbeats
- [ ] **2.5** Implement log rotation, retention policy, compression
- [ ] **2.6** Implement log anomaly detection (error rate spikes, service silence detection)
- [ ] **2.7** Unit tests for LogAggregator

### Phase 3: Network Monitoring (Agent A)

- [ ] **3.1** Implement packet capture loop with scapy
- [ ] **3.2** Implement flow metadata extraction (IPs, ports, protocols, DNS, TLS SNI)
- [ ] **3.3** Implement port scan detection
- [ ] **3.4** Implement DNS tunneling detection (subdomain entropy)
- [ ] **3.5** Implement blocklist checking
- [ ] **3.6** Implement traffic stats collector (connection rates, top talkers)
- [ ] **3.7** Unit tests for NetworkMonitor

### Phase 4: Detection Engine (Agent C)

- [ ] **4.1** Implement YAML rule loader with hot-reload
- [ ] **4.2** Implement all condition evaluators (presence, absence, threshold, rate, pattern)
- [ ] **4.3** Implement composite condition support (AND/OR/NOT)
- [ ] **4.4** Implement event queue and async rule evaluation loop
- [ ] **4.5** Create initial rule set (min 5 rules covering port scan, DNS tunnel, auth brute force, prompt injection, data exfil)
- [ ] **4.6** Wire DetectionRules to receive events from NetworkMonitor and LogAggregator
- [ ] **4.7** Unit tests for DetectionRules

### Phase 5: Alert Management (Agent C)

- [ ] **5.1** Implement AlertManager with dedup, severity scoring, throttling
- [ ] **5.2** Implement Alert lifecycle (new → acknowledged → investigating → resolved → closed)
- [ ] **5.3** Implement Pushover routing for severity >= 7
- [ ] **5.4** Implement SQLite alert storage with schema
- [ ] **5.5** Implement digest generation for low-severity alerts
- [ ] **5.6** Unit tests for AlertManager

### Phase 6: Incident Response (Agent D)

- [ ] **6.1** Implement Playbook YAML parser and loader
- [ ] **6.2** Implement playbook executor with step-by-step orchestration
- [ ] **6.3** Implement all playbook actions (block_ip, unblock_ip, capture_packets, kill_process, rotate_keys, notify, log_evidence)
- [ ] **6.4** Implement confirmation gates (pause and wait for user via Pushover)
- [ ] **6.5** Implement rollback on failure
- [ ] **6.6** Wire AlertManager → IncidentPlaybookRunner for severity >= 8
- [ ] **6.7** Create initial playbooks (investigate_dns, investigate_exfil, rate_limit_source, restart_service)
- [ ] **6.8** Unit tests for IncidentPlaybookRunner

### Phase 7: Dashboard (Agent D)

- [ ] **7.1** Implement FastAPI backend with REST endpoints + WebSocket
- [ ] **7.2** Implement React frontend with live alert feed, timeline chart, health score
- [ ] **7.3** Implement network traffic overview component
- [ ] **7.4** Wire WebSocket push from AlertManager to dashboard clients
- [ ] **7.5** Add dashboard startup to VECTOR autonomous loop (config-gated)
- [ ] **7.6** Integration tests for dashboard

### Phase 8: Integration & Hardening

- [ ] **8.1** Write integration test: port scan from another machine → detected within 5s
- [ ] **8.2** Write integration test: prompt injection → detected → alert → Pushover
- [ ] **8.3** Write integration test: DNS tunneling → detected → playbook executes
- [ ] **8.4** Test alert dedup: same event emitted 10 times → 1 alert with count=10
- [ ] **8.5** Test playbook rollback: block_ip step fails → unblock_ip is called
- [ ] **8.6** Test dashboard WebSocket: new alert appears within 2s
- [ ] **8.7** Edge case: Npcap not installed → NetworkMonitor logs warning and runs in degraded mode (log-only)
- [ ] **8.8** Edge case: scapy capture error → retry 3 times, then disable with alert
- [ ] **8.9** Edge case: 1000 events/sec flood → DetectionRules throttles at 1000/s, AlertManager dedups aggressively

---

## 7. Files to Create/Modify

### New Files

| File | Purpose | Agent |
|------|---------|-------|
| `districts/security/network_monitor.py` | Packet capture + analysis | A |
| `districts/security/log_aggregator.py` | Centralized log collection | B |
| `districts/security/detection_rules.py` | YAML rule engine | C |
| `districts/security/alert_manager.py` | Alert dedup/routing/storage | C |
| `districts/security/incident_playbook_runner.py` | Automated response playbooks | D |
| `dashboard/security_dashboard/api.py` | FastAPI backend | D |
| `dashboard/security_dashboard/app.py` | React app entry | D |
| `data/security/rules/default_rules.yaml` | Initial detection rule set | C |
| `data/security/playbooks/default_playbooks.yaml` | Initial playbook set | D |
| `data/security/ip_blocklist.txt` | Known malicious IPs (seed with examples) | A |
| `tests/districts/security/test_network_monitor.py` | Tests | A |
| `tests/districts/security/test_log_aggregator.py` | Tests | B |
| `tests/districts/security/test_detection_rules.py` | Tests | C |
| `tests/districts/security/test_alert_manager.py` | Tests | C |
| `tests/districts/security/test_incident_playbook_runner.py` | Tests | D |

### Modified Files

| File | Change | Agent |
|------|--------|-------|
| `core/config.py` | Add all NETWORK_MONITOR_*, LOG_*, DETECTION_*, ALERT_*, PLAYBOOK_*, SECURITY_DASHBOARD_* settings | All |
| `core/loop/autonomous_loop.py` | Add security SIEM startup (LogAggregator, NetworkMonitor, DetectionRules, AlertManager, Dashboard) | B/D |
| `phone_node/ambient_server.py` | Add structured logging with correlation_id | B |
| `requirements.txt` | Add scapy, fastapi, uvicorn, websockets | All |

---

## 8. Success Criteria

| Criterion | Measurement | Threshold |
|-----------|------------|-----------|
| Port scan detection | Time from scan start to alert | < 5 seconds |
| Prompt injection catch rate | Detection ratio on test injections | >= 95% |
| DNS tunneling detection | Entropy-based detection of test tunnel | >= 90% |
| Alert dedup | Same event 10x → single alert with count=10 | Pass |
| Automated playbook response | Time from alert to first action | < 30 seconds |
| Log aggregation | All VECTOR services emitting to central store | >= 90% of modules |
| Dashboard live feed | WebSocket latency from alert to dashboard | < 2 seconds |
| Security posture score | Composite health score | >= 85/100 |
| Pushover alerts | High-severity alerts routed within 5s | Pass |
| Playbook rollback | Simulated step failure → rollback executes fully | Pass |

### Known Limitations (Future Specs)

- **Event bus integration:** When specs-02 event bus is available, replace direct event queues with Redis pub/sub.
- **Threat intelligence feeds:** Current blocklist is static. Future: integrate AlienVault OTX, MISP, or VirusTotal API.
- **ML-based detection:** Rules are hand-crafted YAML. Future: behavioral ML models for anomaly detection.
- **Encrypted traffic analysis:** scapy cannot decrypt HTTPS. Future: TLS proxy or JA3 fingerprinting.
- **Distributed monitoring:** Single machine only. Future: agent deployment on multiple network nodes.

---

## 9. Dependencies

### Upstream Dependencies (must exist first)
- specs-02 (event bus) — optional, can integrate directly via asyncio.Queue and migrate later
- `core/config.py` (Pydantic V2) — exists and functional
- `phone_node/ambient_server.py` — exists, needs log retrofitting
- `districts/security/threat_scout.py` — exists, needs log retrofitting

### External Dependencies (to install)
- `scapy>=2.5.0` (packet capture, requires Npcap on Windows)
- `fastapi>=0.104.0` (dashboard backend)
- `uvicorn[standard]>=0.24.0` (dashboard server)
- `websockets>=12.0` (dashboard live feed)
- `react>=18` (dashboard frontend, via npm)
- Node.js 18+ (for React build)

### Runtime Dependencies
- Npcap 1.79+ (Windows packet capture driver) — included in setup instructions
- Write access to `data/security/` directory
- Pushover API credentials (already configured in .env)
- Port 8844 available (or configured alternate)

### Downstream Dependents
- specs-07 (Emergency Response) — may integrate playbook execution for emergency scenarios
- specs-05 (Predictive Analytics) — may consume security alert trends for prediction
- specs-08 (AR Dashboard) — may visualize security posture in AR
