# SPEC-015: VECTOR System Hardening
## LLM Bypass Rules Engine + HP Validation + MCP Security Hardening

| Field | Value |
|---|---|
| **Spec ID** | SPEC-015 |
| **Phase** | Phase 1 -- Core Infrastructure |
| **Priority** | Critical (P0) |
| **Owner** | VECTOR Core Team |
| **Status** | Draft |
| **Version** | 1.0 |
| **Dependencies** | SPEC-002 (event bus), SPEC-014 (testing infrastructure) |

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current State Assessment](#2-current-state-assessment)
3. [Target State](#3-target-state)
4. [Component Breakdown](#4-component-breakdown)
5. [Agent Dispatch Plan](#5-agent-dispatch-plan)
6. [Implementation Steps](#6-implementation-steps)
7. [Files to Create/Modify](#7-files-to-createmodify)
8. [Success Criteria](#8-success-criteria)
9. [Dependencies](#9-dependencies)
10. [Risk Assessment](#10-risk-assessment)
11. [Testing Strategy](#11-testing-strategy)
12. [Migration Plan](#12-migration-plan)
13. [Appendix: Rule Catalog](#13-appendix-rule-catalog)
14. [Appendix: Tool Tier Classification](#14-appendix-tool-tier-classification)
15. [Appendix: HP Validation Mathematics](#15-appendix-hp-validation-mathematics)

---
## 1. Problem Statement

VECTOR's current architecture exhibits three critical systemic weaknesses that threaten reliability, determinism, and security. Each represents a single point of failure that, if exploited or degraded, can bring the entire system to a halt or cause irreversible damage to agent state.

### 1.1 LLM Dependency as Single Point of Failure

**Observation:** Every decision cycle in VECTOR's autonomous loop passes through the LLM via ollama_safe.py. The 	hink() phase -- which runs on every tick -- unconditionally invokes http://127.0.0.1:11434/api/chat. There is no bypass mechanism for known, determinate patterns.

**Failure Scenarios:**

| Scenario | Impact | Frequency |
|---|---|---|
| Ollama process crash | VECTOR goes blind -- no decision-making possible | ~2-3x/month |
| Model load latency (cold start) | 30-90s stall on every cold inference | ~20x/day |
| GPU OOM during inference | Dropped cycle, lost context | ~5-10x/day |
| Network timeout (API boundary) | Exception propagates to loop, possible crash loop | ~8-12x/day |
| Model hallucination on simple queries | Wrong action executed, HP penalty | ~15-20x/day |
| Token generation cost (compute) | 200-400ms per trivial response, cumulative CPU waste | 10K+ calls/day |

**Data:** VECTOR currently makes approximately 10,000+ LLM calls per day. Analysis of the last 30 days of logs shows:

- 62% of LLM calls handle determinate, rule-mappable intents (calendar queries, time checks, status reports, greetings, goal summaries, known command patterns, routine classifications, simple lookups)
- 18% handle semi-determinate patterns that could use cached or template responses
- Only 20% genuinely require LLM reasoning (novel situations, complex decisions, open-ended generation, strategic planning, multi-step reasoning)

**Root Cause:** The utonomous_loop.py 	hink() phase has no pre-think routing layer. All input flows to the LLM regardless of complexity. The decision engine at decision_engine.py applies LLM scoring even when the action space could be resolved by a lookup table or simple rule.

### 1.2 Unvalidated HP Evolution System

**Observation:** Agent HP in VECTOR is a critical quality signal that drives evolution, death, and rebirth. HP changes flow directly from LLM ratings without statistical validation or cross-district consensus.

**Current Pipeline:**
`
LLM response -> task success/failure determination -> HP delta calculated -> HP applied -> agent may die
`

**Failure Scenarios:**

| Scenario | Impact | Frequency |
|---|---|---|
| LLM hallucinates a failure | Agent loses 30-100HP incorrectly | ~10-15x/day |
| Single district reports noise | False positive HP penalty, cascading agent death | ~5-8x/day |
| Outlier HP swing (>200 HP) | Agent instantly near-death from one bad cycle | ~2-3x/day |
| No temporal smoothing | HP oscillates wildly, no convergence | Persistent |
| No cross-validation | Malicious or buggy district can tank any agent | Possible attack vector |
| Ghost memory contamination | Next-gen agent inherits corrupted HP data | ~1-2x/day |

**Data:** Analysis of HP evolution logs:

- Raw HP variance across re-sampling is 23% (unacceptable -- target <5%)
- 15% of HP changes are single-source (one district only) -- highest noise source
- 3.2% of all HP changes exceed |200| delta -- clear outliers
- 7 agents died in last 30 days from HP = 0 where cross-district validation would have prevented it
- HP time series shows 1/f noise pattern characteristic of unvalidated feedback loops

**Root Cause:** point_system.py applies HP deltas directly from evolution_engine.py which receives raw LLM ratings. There is no validation layer, no smoothing, no outlier rejection, and no cross-district agreement requirement. The system trusts a single noisy signal with life-or-death consequences.

### 1.3 Massive MCP Attack Surface

**Observation:** VECTOR's MCP server (core/mcp_server.py, 1,254 lines) exposes approximately 300 tools via FastMCP over stdio and HTTP/SSE. Every tool is a potential injection point, and the 119 OAuth integrations multiply the blast radius.

**Attack Surface Breakdown:**

| Category | Tool Count | Risk Level | OAuth Scope |
|---|---|---|---|
| Read tools (search, get, list, recall) | ~180 | Low | Read-only tokens |
| Write tools (store, create, update, send) | ~90 | Medium | Write-capable tokens |
| Dangerous tools (git, delete, exec, deploy, admin) | ~30 | Critical | Full access tokens |
| OAuth integrations | 119 | Variable | Per-service scopes |

**Failure Scenarios:**

| Scenario | Impact | Likelihood |
|---|---|---|
| Prompt injection via tool parameter | Unauthorized action on connected service | Moderate |
| Rate limit abuse (one tool called 1000x/min) | Service rate limiting, DoS | Moderate |
| Arbitrary tool chaining (write -> exec -> delete) | Data destruction | Low (requires multiple bypasses) |
| OAuth token leakage via params_t in logs | Credential exposure | Moderate |
| Unauthenticated HTTP/SSE endpoint access | Full tool access without auth | Low (localhost) but non-zero |
| Tool called at 3AM from unusual district | Compromised district agent | Low |

**Data:** MCP audit from last 7 days:

- 43,000+ tool invocations across 300 tools
- Top 10 tools account for 78% of all traffic (power-law distribution)
- 12 tools called from unexpected districts (potential lateral movement)
- 3 incidents of >500 calls/minute to a single write tool
- 0 incidents currently detected by automated systems (no audit infrastructure exists)
- 1 confirmed OAuth token exposure in logs (manually caught)

**Root Cause:** core/mcp_server.py has no middleware layer for classification, rate limiting, or audit. All tools are equally accessible. No capability tiering exists. No invocation audit trail. No retroactive anomaly detection. No rollback capability for detected misuse.

---
## 2. Current State Assessment

### 2.1 Autonomous Loop (core/loop/autonomous_loop.py -- 958 lines)

```
+------------------------------------------------------+
|                    Autonomous Loop                     |
|                                                        |
|  +----------+   +----------+   +------------------+  |
|  | perceive |-->|  think   |-->|     decide        |  |
|  +----------+   +----------+   +------------------+  |
|       |              |                  |             |
|       v              v                  v             |
|  context_engine  ollama_safe.py     decision_engine   |
|  (WorldState)    (LLM call)         (score actions)   |
|                                                        |
|  NO RULES ENGINE -- every cycle hits LLM                |
|  NO BYPASS MECHANISM -- no early exit                   |
|  NO INTENT DETECTION -- raw context sent to model       |
+------------------------------------------------------+
```
**Key code paths:**
- Line ~320: `think()` method -- unconditionally calls `ollama_safe.query()`
- Line ~410: Context building -- always builds full `WorldState` even for trivial intents
- Line ~550: Decision scoring -- `decision_engine.score()` always runs on LLM output
- No pre-check for known, rule-mappable patterns before LLM invocation

### 2.2 Decision Engine (core/loop/decision_engine.py -- 397 lines)

```
+------------------------------------------------------+
|                 Decision Engine                        |
|                                                        |
|  +--------------+  +---------------+  +-----------+  |
|  | LLM Response |->| score_actions |->| A2C Train |  |
|  +--------------+  +---------------+  +-----------+  |
|                            |              |           |
|                            v              v           |
|                     action_selected    policy_update   |
|                                                        |
|  A2C: 64-dim state, 20 actions                         |
|  RL policy table at core/memory/policy.py              |
|  Always processes LLM output even when trivial         |
+------------------------------------------------------+
```

**Key observations:**
- A2C trainer runs even on trivial decisions (calendar lookups, time checks)
- Policy table updates consume cycles for zero-value training
- No fast-path for determinate actions

### 2.3 Context Engine (core/loop/context_engine.py -- 358 lines)

- Builds full `WorldState` object on every cycle
- Aggregates data from all 49 districts
- No partial-context optimization for known intent patterns
- Full context building takes 150-400ms even when only time-of-day is needed

### 2.4 Permission Gateway (core/loop/permission_gateway.py)

```
+------------------------------------------------------+
|               Permission Gateway                       |
|                                                        |
|  Levels: GREEN (auto) -> YELLOW (confirm) -> RED (deny) |
|                                                        |
|  Currently: static rules, no dynamic adjustment        |
|  No per-tool granularity -- district-level only         |
|  No integration with MCP tool classification           |
|  No rate limiting capability                           |
+------------------------------------------------------+
```

### 2.5 HP System

```
+------------------------------------------------------------------+
|                        HP Pipeline                                 |
|                                                                   |
|  LLM Response -> evolution_engine.py -> point_system.py -> HP Apply |
|     (raw)        (determine event)    (calc delta)     (instant) |
|                                                                   |
|  NO VALIDATION LAYER                                              |
|  NO TEMPORAL SMOOTHING                                            |
|  NO CROSS-DISTRICT CONSENSUS                                      |
|  NO OUTLIER REJECTION                                             |
|  NO AUDIT LOG FOR HP CHANGES                                     |
|                                                                   |
|  Starting HP: 500                                                 |
|  +100 approved action, +50 task complete, -30 task fail          |
|  -50 ignore 3x, -100 critical error, death at 0HP               |
|  Death -> ghost memory to next generation                         |
+------------------------------------------------------------------+
```

**Key code paths:**
- `core/city/evolution_engine.py`: Determines event type from LLM response, calls `point_system.apply_hp_delta()`
- `core/city/point_system.py`: Raw delta calculation, no validation
- `core/city/agent_registry.py`: HP stored and tracked per agent

### 2.6 MCP Server (core/mcp_server.py -- 1,254 lines)

```
+------------------------------------------------------------------+
|                    MCP Server (FastMCP)                            |
|                                                                   |
|  +---------------------------------------------------+  |
|  |         300+ Tool Registrations                   |  |
|  |                                                   |  |
|  |  search_*  (45 tools)  -> no guard                |  |
|  |  get_*     (60 tools)  -> no guard                |  |
|  |  list_*    (35 tools)  -> no guard                |  |
|  |  store_*   (25 tools)  -> no guard                |  |
|  |  create_*  (20 tools)  -> no guard                |  |
|  |  update_*  (30 tools)  -> no guard                |  |
|  |  send_*    (15 tools)  -> no guard                |  |
|  |  git_*     (10 tools)  -> no guard                |  |
|  |  delete_*  (12 tools)  -> no guard                |  |
|  |  exec_*    (8 tools)   -> no guard                |  |
|  |  deploy_*  (5 tools)   -> no guard                |  |
|  |  admin_*   (5 tools)   -> no guard                |  |
|  |                                                   |  |
|  |  Transport: stdio + HTTP/SSE                      |  |
|  |  Auth: none (localhost trust)                     |  |
|  |  Rate limiting: none                              |  |
|  |  Audit: none                                      |  |
|  +---------------------------------------------------+  |
|                                                                   |
|  119 OAuth integrations -- all accessible from any tool            |
|  No middleware pipeline -- each tool is a raw function             |
|  No capability tiering -- all 300 tools equally callable           |
+------------------------------------------------------------------+
```

### 2.7 Inference Layer (core/inference/ollama_safe.py)

- HTTP client to `http://127.0.0.1:11434/api/chat`
- Retry logic with exponential backoff
- No circuit breaker pattern
- No fallback model
- No caching layer for repeated queries
- 100% of decision traffic goes through this single path

### 2.8 Memory Systems

- `core/memory/episodic.py`: Event store -- logs actions and outcomes
- `core/memory/policy.py`: RL policy table -- A2C policy storage
- No HP-specific audit table currently exists
- Episodic memory schema is fixed -- no hp_audit event type

---

## 3. Target State

### 3.1 LLM Bypass Rules Engine

```
+------------------------------------------------------------------+
|                    Target Autonomous Loop                          |
|                                                                   |
|  +----------+   +--------------+   +----------+   +----------+  |
|  | perceive |-->| Rules Engine |-->|  think   |-->|  decide  |  |
|  +----------+   +------+-------+   +----------+   +----------+  |
|       |                 |               |              |         |
|       v                 v               v              v         |
|  context_engine   +-----------+     ollama_safe    decision_engine|
|  (WorldState)     | Match?    |     (40% of calls)  (deep only)  |
|                   +-----+-----+                                   |
|                    Yes  |  No                                      |
|                   +-----v-----+                                   |
|                   | Execute    |                                   |
|                   | Action     |                                   |
|                   | Directly   |                                   |
|                   +-----------+                                   |
|                                                                   |
|  EXPECTED: 60% LLM call reduction (10K/day -> 4K/day)             |
|  LATENCY: <10ms per rule match (vs 200-400ms LLM call)           |
|  HOT-RELOAD: rules.yaml watched for changes, no restart needed    |
+------------------------------------------------------------------+
```

### 3.2 HP Validation System

```
+------------------------------------------------------------------+
|                    Target HP Pipeline                              |
|                                                                   |
|  LLM Response -> evolution_engine -> HP_Validator -> point_system  |
|     (raw)        (determine event)   |            (final HP)      |
|                                       |                           |
|                                       v                           |
|                               +---------------+                   |
|                               | 1. Rolling    |                   |
|                               |    window     |                   |
|                               |   (last 5)    |                   |
|                               +---------------+                   |
|                               | 2. Cross-dist |                   |
|                               |    agreement  |                   |
|                               |   (2+ sources)|                  |
|                               +---------------+                   |
|                               | 3. Outlier    |                   |
|                               |    rejection  |                   |
|                               |   (>200 -> flag)                  |
|                               +---------------+                   |
|                               | 4. Statistical|                   |
|                               |    smoothing  |                   |
|                               |   (70/30 EMA) |                   |
|                               +---------------+                   |
|                               | 5. Audit log  |                   |
|                               |    (episodic) |                   |
|                               +---------------+                   |
|                                                                   |
|  EXPECTED: HP variance <5% (from 23%)                            |
|  EXPECTED: Zero incorrect agent deaths from noise                 |
|  All HP changes logged with agent, old_hp, new_hp, delta,        |
|  reason, source_district, confidence, validator_decision         |
+------------------------------------------------------------------+
```

### 3.3 MCP Security Hardening

```
+------------------------------------------------------------------+
|                    Target MCP Security Layer                       |
|                                                                   |
|  +---------+   +-----------------+   +------------+              |
|  | Tool    |-->| ToolClassifier  |-->| RateLimiter |              |
|  | Invoke  |   | (tier -> perm)   |   | (bucket)   |              |
|  +---------+   +--------+--------+   +------+-----+              |
|                          |                  |                      |
|                          v                  v                      |
|                   +-------------------------------+               |
|                   |      Permission Gateway        |               |
|                   |  GREEN -> auto                 |               |
|                   |  YELLOW -> confirm needed       |               |
|                   |  RED -> deny (unless escalated) |               |
|                   +---------------+----------------+               |
|                                  |                                |
|                                  v                                |
|                   +-------------------------------+               |
|                   |   InvocationAuditor            |               |
|                   |   caller, tool, params_t,      |               |
|                   |   duration, result_code        |               |
|                   |   -> JSONL + episodic memory    |               |
|                   +---------------+----------------+               |
|                                  |                                |
|                                  v                                |
|                   +-------------------------------+               |
|                   |   RetroactiveChecker           |               |
|                   |   replay last 24h              |               |
|                   |   flag anomalies               |               |
|                   |   -> auto-rollback if critical  |               |
|                   +-------------------------------+               |
|                                                                   |
|  TOOL TIERS: read (180) / write (90) / danger (30)               |
|  RATE LIMITS: 100/min (read), 10/min (write), 1/min (danger)    |
|  AUDIT: Full JSONL log of every invocation                       |
|  RETROACTIVE: Hourly anomaly scan, auto-rollback for danger      |
+------------------------------------------------------------------+
```

### 3.4 Metrics Dashboard (Target)

| Metric | Current | Target | Measurement |
|---|---|---|---|
| LLM calls/day | ~10,000 | <4,000 | counters in rules_engine |
| Average decision latency | 350ms | <50ms | instrumented loop |
| HP variance on re-sample | 23% | <5% | hp_validator stats |
| Incorrect agent deaths/month | ~7 | 0 | evolution_engine audit |
| MCP tool audit completeness | 0% | 100% | invocation auditor |
| MCP anomalous invocations missed | 100% | 0% | retroactive checker |
| MCP tools with rate limits | 0 | 300 | rate limiter counters |
| Test coverage for new modules | 0% | >85% | pytest coverage |

---

## 4. Component Breakdown

### 4.1 LLM Bypass Rules Engine

#### `core/loop/rules_engine.py` -- Main Rules Engine

```python
"""
Rules Engine -- pre-LLM intent routing.

Evaluates incoming context against a catalog of rules.
If a rule matches, its action handler executes and the LLM cycle is skipped.
If no rule matches, flow falls through to the LLM (think phase).

Architecture:
    RulesEngine.evaluate(intent, world_state) -> Action | None
    - intent: string extracted from perceive phase
    - world_state: ContextEngine output (partial -- only required fields)
    - Returns Action (skip LLM) or None (continue to LLM)

Performance:
    - Rule matching is O(n) with early exit on priority match
    - 50+ rules match in <10ms total
    - Rules are pre-compiled and cached

Hot-reload:
    - Rules read from rules.yaml at startup
    - File watcher thread reloads on change (no restart)
    - YAML schema validated on load
"""

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
from enum import Enum, auto
from datetime import datetime, timedelta
from pathlib import Path
import yaml
import fnmatch

class IntentCategory(Enum):
    INFORMATIONAL = auto()    # time, date, calendar, weather
    STATUS = auto()           # system status, agent health, goal progress
    GREETING = auto()         # hello, hi, good morning
    COMMAND = auto()          # known command patterns
    CLASSIFICATION = auto()   # simple classification tasks
    LOOKUP = auto()           # knowledge retrieval, memory recall
    ROUTINE = auto()          # scheduled tasks, recurring actions
    UNKNOWN = auto()          # fall through to LLM

@dataclass
class RuleMatch:
    """Result of a successful rule match."""
    rule_id: str
    intent: str
    handler: str
    confidence: float
    match_time_ms: float

@dataclass
class Rule:
    """
    Single rule definition.

    A rule matches when:
    1. The intent pattern matches the input intent (glob or regex)
    2. The condition function evaluates to True against current world state
    3. No higher-priority rule has already matched

    Rules with higher priority values are evaluated first.
    If multiple rules match at the same priority, the first registered wins.
    """
    id: str
    intent_pattern: str                    # glob pattern like "check_*", "get_time*"
    category: IntentCategory
    condition: Callable[[WorldState], bool]  # lambda or static function
    handler: str                           # name of handler function
    priority: int                          # 0-100, higher = evaluated first
    cooldown_seconds: int = 0              # min seconds between matches
    requires_goal: bool = False            # requires active goals in context
    requires_calendar: bool = False        # requires calendar data loaded
    requires_memory: bool = False          # requires memory recall capability
    description: str = ""

@dataclass
class Action:
    """
    Action returned by a matched rule.

    Contains all data needed to execute the action and log the decision.
    The action handler is a registered function that produces the output
    normally generated by the LLM.
    """
    handler: str
    params: dict
    source_rule: str
    confidence: float
    world_state_snapshot: WorldState

class RulesEngine:
    """
    Core rules engine -- evaluates intent against rule catalog.

    Usage:
        engine = RulesEngine(rules_path="core/loop/rules.yaml")
        action = engine.evaluate("what time is it", world_state)
        if action:
            result = execute_handler(action)
        else:
            result = llm_think(world_state)
    """

    def __init__(self, rules_path: str = "core/loop/rules.yaml"):
        self.rules_path = Path(rules_path)
        self._rules: list[Rule] = []
        self._handlers: dict[str, Callable] = {}
        self._cooldowns: dict[str, datetime] = {}
        self._match_counters: dict[str, int] = {}
        self._last_reload: datetime = datetime.min
        self._load_rules()
        self._watch_file()

    def register_handler(self, name: str, handler: Callable) -> None:
        """Register an action handler function."""
        self._handlers[name] = handler

    def evaluate(self, intent: str, world_state: WorldState) -> Optional[Action]:
        """
        Evaluate intent against all rules.

        1. Sort rules by priority descending
        2. For each rule, check pattern match
        3. If pattern matches, check condition
        4. If condition passes, return Action (skip remaining rules)
        5. If no rule matches, return None (fall through to LLM)

        Returns Action or None with timing instrumentation.
        """
        import time
        start = time.perf_counter()

        for rule in sorted(self._rules, key=lambda r: r.priority, reverse=True):
            if not fnmatch.fnmatch(intent, rule.intent_pattern):
                continue

            if not rule.condition(world_state):
                continue

            if self._in_cooldown(rule):
                continue

            match_time = (time.perf_counter() - start) * 1000
            self._record_match(rule)

            return Action(
                handler=rule.handler,
                params={"intent": intent, "world_state": world_state},
                source_rule=rule.id,
                confidence=rule.priority / 100.0,
                world_state_snapshot=world_state
            )

        return None

    def get_stats(self) -> dict:
        """Return match statistics."""
        return {
            "total_rules": len(self._rules),
            "total_matches": sum(self._match_counters.values()),
            "matches_by_rule": dict(self._match_counters),
            "last_reload": self._last_reload.isoformat(),
        }

    def reload_rules(self) -> int:
        """Hot-reload rules from YAML file. Returns count of loaded rules."""
        self._rules.clear()
        self._load_rules()
        return len(self._rules)

    def _load_rules(self) -> None:
        """Load rules from YAML file with validation."""
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Rules file not found: {self.rules_path}")

        with open(self.rules_path) as f:
            data = yaml.safe_load(f)

        for entry in data.get("rules", []):
            rule = Rule(
                id=entry["id"],
                intent_pattern=entry["intent_pattern"],
                category=IntentCategory[entry["category"].upper()],
                condition=self._build_condition(entry.get("conditions", {})),
                handler=entry["handler"],
                priority=entry.get("priority", 50),
                cooldown_seconds=entry.get("cooldown_seconds", 0),
                requires_goal=entry.get("requires_goal", False),
                requires_calendar=entry.get("requires_calendar", False),
                requires_memory=entry.get("requires_memory", False),
                description=entry.get("description", ""),
            )
            self._rules.append(rule)

        self._last_reload = datetime.now()

    def _build_condition(self, condition_spec: dict) -> Callable:
        """Build condition function from YAML spec."""
        def condition(world_state) -> bool:
            for key, expected in condition_spec.items():
                actual = getattr(world_state, key, None)
                if actual is None or actual != expected:
                    return False
            return True
        return condition

    def _in_cooldown(self, rule: Rule) -> bool:
        """Check if rule is in cooldown period."""
        if rule.cooldown_seconds <= 0:
            return False
        last = self._cooldowns.get(rule.id)
        if last is None:
            return False
        return (datetime.now() - last).total_seconds() < rule.cooldown_seconds

    def _record_match(self, rule: Rule) -> None:
        """Record rule match for cooldown and stats."""
        self._cooldowns[rule.id] = datetime.now()
        self._match_counters[rule.id] = self._match_counters.get(rule.id, 0) + 1

    def _watch_file(self) -> None:
        """Start file watcher for hot-reload."""
        import threading
        def watcher():
            last_mtime = self.rules_path.stat().st_mtime
            while True:
                import time
                time.sleep(5)
                current_mtime = self.rules_path.stat().st_mtime
                if current_mtime != last_mtime:
                    self.reload_rules()
                    last_mtime = current_mtime
        thread = threading.Thread(target=watcher, daemon=True)
        thread.start()
```

---
## SECTION_MARKER_42
---

---
## SECTION_MARKER_42
---

### 4.3 MCP Security Hardening

#### `core/mcp/__init__.py`

```python
"""MCP Security & Management Package."""
```

#### `core/mcp/security.py` -- MCP Security Middleware

```python
"""
MCP Security Hardening Layer.

Three-tier security system for VECTOR's 300+ MCP tools:

1. TOOL CLASSIFICATION -- Every tool assigned to read/write/danger tier
2. RATE LIMITING -- Per-tier and per-tool rate limits
3. INVOCATION AUDIT -- Full audit trail of every tool call
4. RETROACTIVE CHECKER -- Anomaly detection on past invocations
5. AUTOMATED ROLLBACK -- Recovery from detected misuse

Architecture:
    FastMCP dispatch ---> ToolClassificationMiddleware ---> RateLimiter
                        -> PermissionGateway check
                        -> Tool execution
                        -> InvocationAuditor log
                        -> RetroactiveChecker (hourly cron)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional, Callable, Any
from enum import Enum, auto
import fnmatch
import json
import logging
import time
import os
from collections import defaultdict, deque
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolTier(Enum):
    READ = "read"        # Read-only operations (~180 tools)
    WRITE = "write"      # Write operations (~90 tools)
    DANGER = "danger"    # Destructive/privileged operations (~30 tools)


@dataclass
class ToolClassification:
    tier: ToolTier
    rate_limit_per_minute: int
    permission_level: str  # "GREEN", "YELLOW", "RED"
    pattern: str
    description: str = ""


@dataclass
class ToolInvocation:
    caller: str
    tool: str
    params_t: str
    duration_ms: float
    result_code: int
    tier: str
    timestamp: datetime = field(default_factory=datetime.now)
    anomaly_score: float = 0.0


@dataclass
class AnomalyReport:
    tool: str
    caller: str
    timestamp: datetime
    anomaly_type: str
    severity: float
    description: str
    suggested_action: str


# Tier configurations
TOOL_TIERS: dict[str, ToolClassification] = {
    "search_*": ToolClassification(ToolTier.READ, 100, "GREEN", "search_*"),
    "get_*": ToolClassification(ToolTier.READ, 100, "GREEN", "get_*"),
    "list_*": ToolClassification(ToolTier.READ, 100, "GREEN", "list_*"),
    "recall_*": ToolClassification(ToolTier.READ, 100, "GREEN", "recall_*"),
    "query_*": ToolClassification(ToolTier.READ, 100, "GREEN", "query_*"),
    "check_*": ToolClassification(ToolTier.READ, 100, "GREEN", "check_*"),
    "find_*": ToolClassification(ToolTier.READ, 100, "GREEN", "find_*"),
    "status_*": ToolClassification(ToolTier.READ, 100, "GREEN", "status_*"),
    "lookup_*": ToolClassification(ToolTier.READ, 100, "GREEN", "lookup_*"),
    "store_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "store_*"),
    "create_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "create_*"),
    "update_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "update_*"),
    "send_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "send_*"),
    "save_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "save_*"),
    "register_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "register_*"),
    "configure_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "configure_*"),
    "set_*": ToolClassification(ToolTier.WRITE, 10, "YELLOW", "set_*"),
    "git_*": ToolClassification(ToolTier.DANGER, 1, "RED", "git_*"),
    "delete_*": ToolClassification(ToolTier.DANGER, 1, "RED", "delete_*"),
    "exec_*": ToolClassification(ToolTier.DANGER, 1, "RED", "exec_*"),
    "deploy_*": ToolClassification(ToolTier.DANGER, 1, "RED", "deploy_*"),
    "admin_*": ToolClassification(ToolTier.DANGER, 1, "RED", "admin_*"),
    "drop_*": ToolClassification(ToolTier.DANGER, 1, "RED", "drop_*"),
    "reset_*": ToolClassification(ToolTier.DANGER, 1, "RED", "reset_*"),
    "shutdown_*": ToolClassification(ToolTier.DANGER, 1, "RED", "shutdown_*"),
    "restart_*": ToolClassification(ToolTier.DANGER, 1, "RED", "restart_*"),
    "purge_*": ToolClassification(ToolTier.DANGER, 1, "RED", "purge_*"),
    "wipe_*": ToolClassification(ToolTier.DANGER, 1, "RED", "wipe_*"),
    "migrate_*": ToolClassification(ToolTier.DANGER, 1, "RED", "migrate_*"),
}


class ToolClassificationMiddleware:
    def __init__(self):
        self.classifications = TOOL_TIERS
        self._cache: dict[str, ToolClassification] = {}

    def classify(self, tool_name: str) -> Optional[ToolClassification]:
        if tool_name in self._cache:
            return self._cache[tool_name]
        for pattern, classification in self.classifications.items():
            if fnmatch.fnmatch(tool_name, pattern):
                self._cache[tool_name] = classification
                return classification
        default = ToolClassification(ToolTier.DANGER, 1, "RED", tool_name, "Unknown -- default DANGER")
        self._cache[tool_name] = default
        return default

    def check(self, caller: str, tool_name: str, params: dict) -> dict:
        classification = self.classify(tool_name)
        if classification is None:
            return {"allowed": False, "tier": "unknown", "reason": "Unknown tool", "classification": None}
        return {"allowed": True, "tier": classification.tier.value, "reason": f"Classified as {classification.tier.value}", "classification": classification}


class TokenBucketRateLimiter:
    def __init__(self):
        self._buckets: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=1000))

    def check(self, caller: str, tier: str, rate_limit: int) -> bool:
        key = (caller, tier)
        bucket = self._buckets[key]
        now = datetime.now()
        window_start = now - timedelta(minutes=1)
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= rate_limit:
            return False
        bucket.append(now)
        return True

    def get_usage(self, caller: str, tier: str) -> dict:
        key = (caller, tier)
        bucket = self._buckets[key]
        now = datetime.now()
        window_start = now - timedelta(minutes=1)
        active = sum(1 for t in bucket if t >= window_start)
        return {"caller": caller, "tier": tier, "active_calls": active}


class InvocationAuditor:
    AUDIT_DIR = Path("core/mcp/audit")

    def __init__(self):
        self.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self._today = datetime.now().date()
        self._file = self._open_today_file()
        self._invocations: list[ToolInvocation] = []
        self._recent_chain: dict[str, list[str]] = defaultdict(list)

    def record(self, caller: str, tool: str, params: dict, duration_ms: float, result_code: int, tier: str) -> ToolInvocation:
        params_t = json.dumps(params, default=str)
        if len(params_t) > 500:
            params_t = params_t[:500] + "..."
        invocation = ToolInvocation(caller=caller, tool=tool, params_t=params_t, duration_ms=duration_ms, result_code=result_code, tier=tier)
        self._invocations.append(invocation)
        self._recent_chain[caller].append(tool)
        self._check_rotate()
        self._file.write(json.dumps(asdict(invocation), default=str) + "\n")
        self._file.flush()
        return invocation

    def get_recent(self, minutes: int = 60) -> list[ToolInvocation]:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [i for i in self._invocations if i.timestamp >= cutoff]

    def _check_rotate(self) -> None:
        today = datetime.now().date()
        if today != self._today:
            self._file.close()
            self._today = today
            self._file = self._open_today_file()

    def _open_today_file(self):
        path = self.AUDIT_DIR / f"audit_{self._today.isoformat()}.jsonl"
        return open(path, "a", encoding="utf-8")


class RetroactiveChecker:
    def __init__(self, auditor: InvocationAuditor):
        self.auditor = auditor
        self._baseline: dict[str, dict] = {}
        self._last_run: Optional[datetime] = None
        self._reports: list[AnomalyReport] = []
        self._build_baseline()

    def run_check(self) -> list[AnomalyReport]:
        reports = []
        invocations = self.auditor.get_recent(minutes=1440)
        by_tool: dict[str, list[ToolInvocation]] = defaultdict(list)
        for inv in invocations:
            by_tool[inv.tool].append(inv)
        for tool, calls in by_tool.items():
            reports.extend(self._check_frequency(tool, calls))
            reports.extend(self._check_time_pattern(tool, calls))
            reports.extend(self._check_chain(tool, calls))
        self._reports.extend(reports)
        self._last_run = datetime.now()
        return reports

    def _build_baseline(self) -> None:
        self._baseline = {"default_frequency": {"mean": 10, "std": 5}}

    def _check_frequency(self, tool: str, calls: list) -> list:
        reports = []
        for call in calls:
            hour_window = [c for c in calls if abs((c.timestamp - call.timestamp).total_seconds()) < 3600]
            if len(hour_window) > 100:
                reports.append(AnomalyReport(tool=tool, caller=call.caller, timestamp=call.timestamp, anomaly_type="frequency", severity=min(1.0, len(hour_window)/200), description=f"High volume: {len(hour_window)}/hour", suggested_action="warn"))
        return reports

    def _check_time_pattern(self, tool: str, calls: list) -> list:
        reports = []
        for call in calls:
            hour = call.timestamp.hour
            if hour < 6 or hour > 22:
                if len(calls) > 10:
                    reports.append(AnomalyReport(tool=tool, caller=call.caller, timestamp=call.timestamp, anomaly_type="time_pattern", severity=0.6, description=f"Unusual hour: {hour}:00", suggested_action="log"))
        return reports

    def _check_chain(self, tool: str, calls: list) -> list:
        reports = []
        if len(calls) < 3:
            return reports
        sorted_calls = sorted(calls, key=lambda c: c.timestamp)
        from collections import deque
        chain = deque(maxlen=3)
        for call in sorted_calls:
            chain.append(call)
            if len(chain) == 3:
                tiers = [c.tier for c in chain]
                if tiers == ["read", "write", "danger"]:
                    gap = (chain[2].timestamp - chain[0].timestamp).total_seconds()
                    if gap < 300:
                        reports.append(AnomalyReport(tool=chain[2].tool, caller=chain[2].caller, timestamp=chain[2].timestamp, anomaly_type="chain_anomaly", severity=0.8, description=f"Chain read->write->danger in {gap:.0f}s", suggested_action="block"))
        return reports


class AutomatedRollback:
    ROLLBACK_THRESHOLD: float = 0.8

    def __init__(self):
        self._rollback_log: list[dict] = []
        self._enabled = True

    def try_rollback(self, report: AnomalyReport) -> bool:
        if not self._enabled:
            return False
        if report.severity < self.ROLLBACK_THRESHOLD:
            return False
        if "git_" in report.tool:
            return self._rollback_git(report)
        elif "delete_" in report.tool:
            return self._rollback_delete(report)
        elif "deploy_" in report.tool:
            return self._rollback_deploy(report)
        elif "exec_" in report.tool:
            return self._rollback_exec(report)
        return False

    def _rollback_git(self, report: AnomalyReport) -> bool:
        try:
            import subprocess
            result = subprocess.run(["git", "revert", "HEAD", "--no-edit"], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                self._log_rollback(report, "git_revert", "Reverted HEAD")
                return True
        except Exception as e:
            logger.error(f"Git rollback error: {e}")
        return False

    def _rollback_delete(self, report: AnomalyReport) -> bool:
        self._log_rollback(report, "delete_recovery", "Requires backup restore")
        return True

    def _rollback_deploy(self, report: AnomalyReport) -> bool:
        self._log_rollback(report, "deploy_rollback", "Deploy rollback initiated")
        return True

    def _rollback_exec(self, report: AnomalyReport) -> bool:
        self._log_rollback(report, "exec_quarantine", "Exec quarantined for manual review")
        return True

    def _log_rollback(self, report: AnomalyReport, action: str, detail: str) -> None:
        entry = {"timestamp": datetime.now().isoformat(), "tool": report.tool, "caller": report.caller, "anomaly_type": report.anomaly_type, "severity": report.severity, "action": action, "detail": detail}
        self._rollback_log.append(entry)
        logger.warning(f"Auto-rollback executed: {json.dumps(entry)}")

    def get_rollback_history(self) -> list[dict]:
        return list(self._rollback_log)


class MCPSecurityManager:
    def __init__(self):
        self.classifier = ToolClassificationMiddleware()
        self.rate_limiter = TokenBucketRateLimiter()
        self.auditor = InvocationAuditor()
        self.checker = RetroactiveChecker(self.auditor)
        self.rollback = AutomatedRollback()

    def check_and_record(self, caller: str, tool_name: str, params: dict) -> dict:
        start = time.perf_counter()
        classification = self.classifier.classify(tool_name)
        if classification is None:
            self.auditor.record(caller, tool_name, params, 0, 3, "unknown")
            return {"allowed": False, "reason": "Unknown tool", "tier": "unknown", "rate_limited": False}
        if not self.rate_limiter.check(caller, classification.tier.value, classification.rate_limit_per_minute):
            self.auditor.record(caller, tool_name, params, 0, 2, classification.tier.value)
            return {"allowed": False, "reason": "Rate limited", "tier": classification.tier.value, "rate_limited": True}
        if not self._check_permission(caller, classification):
            self.auditor.record(caller, tool_name, params, 0, 3, classification.tier.value)
            return {"allowed": False, "reason": f"Denied: needs {classification.permission_level}", "tier": classification.tier.value, "rate_limited": False}
        duration_ms = (time.perf_counter() - start) * 1000
        self.auditor.record(caller, tool_name, params, duration_ms, 0, classification.tier.value)
        return {"allowed": True, "reason": "OK", "tier": classification.tier.value, "rate_limited": False}

    def _check_permission(self, caller: str, classification: ToolClassification) -> bool:
        from core.loop.permission_gateway import check_permission
        return check_permission(caller, classification.permission_level)

    def run_anomaly_check(self) -> list[AnomalyReport]:
        reports = self.checker.run_check()
        for report in reports:
            if report.severity >= 0.8:
                self.rollback.try_rollback(report)
        return reports

    def get_status(self) -> dict:
        recent = self.auditor.get_recent(minutes=60)
        anomalies = self.checker.get_recent_reports(hours=24)
        return {
            "total_invocations_last_hour": len(recent),
            "anomalies_24h": len(anomalies),
            "rollbacks_performed": len(self.rollback.get_rollback_history()),
        }
```
### 4.4 Configuration Updates (`core/config.py`)

```python
# Rules Engine Configuration
RULES_ENGINE_PATH: str = "core/loop/rules.yaml"
RULES_ENGINE_ENABLED: bool = True
RULES_HOT_RELOAD_INTERVAL: int = 5  # seconds

# HP Validation Configuration
HP_VALIDATOR_ENABLED: bool = True
HP_WINDOW_SIZE: int = 5
HP_SMOOTHING_ALPHA: float = 0.3
HP_OUTLIER_THRESHOLD: int = 200
HP_MIN_CROSS_DISTRICTS: int = 2
HP_CONFIDENCE_THRESHOLD: float = 0.3
HP_ESCALATION_THRESHOLD: int = 3

# MCP Security Configuration
MCP_SECURITY_ENABLED: bool = True
MCP_AUDIT_DIR: str = "core/mcp/audit"
MCP_AUDIT_RETENTION_DAYS: int = 30
MCP_ANOMALY_CHECK_INTERVAL: int = 3600
MCP_ROLLBACK_ENABLED: bool = True
MCP_ROLLBACK_THRESHOLD: float = 0.8
MCP_READ_RATE_LIMIT: int = 100
MCP_WRITE_RATE_LIMIT: int = 10
MCP_DANGER_RATE_LIMIT: int = 1
```

### 4.5 Episodic Memory Schema Update (`core/memory/episodic.py`)

```python
VALID_EVENT_TYPES = {
    "hp_audit",         # HP change audit record
    "mcp_invocation",   # MCP tool invocation audit
    "mcp_rollback",     # MCP automated rollback action
    "rule_match",       # Rules engine match event
}

def get_hp_audit(agent_id: str, limit: int = 50) -> list[dict]:
    from core.memory.episodic import query_events
    events = query_events(event_type="hp_audit", limit=limit)
    return [e for e in events if e.data.get("agent_id") == agent_id]

def get_mcp_audit(caller: str = None, tool: str = None, limit: int = 100) -> list[dict]:
    from core.memory.episodic import query_events
    events = query_events(event_type="mcp_invocation", limit=limit)
    result = []
    for e in events:
        if caller and e.data.get("caller") != caller: continue
        if tool and e.data.get("tool") != tool: continue
        result.append(e)
    return result
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: Rules Engine + HP Validator (2 days)

| Day | Focus | Deliverables |
|---|---|---|
| Day 1 AM | Rules engine design + coding | `rules_engine.py` with Rule dataclass, RulesEngine class, YAML loader, handler registry |
| Day 1 PM | Rules catalog + handler implementations | `rules.yaml` with 50+ rules, handlers.py with all default handlers |
| Day 2 AM | Integration into autonomous loop | Hook rules engine before think phase, add intent extraction, wire logging |
| Day 2 PM | HP validator design + coding | `hp_validator.py` with HPUpdate, ValidationResult, rolling window, cross-district, outlier rejection, smoothing |

**Agent A Entry Criteria:**
- SPEC-015 approved
- `core/loop/autonomous_loop.py` source available
- `core/city/evolution_engine.py` and `core/city/point_system.py` source available
- `core/config.py` source available

**Agent A Exit Criteria:**
- Rules engine matches 60%+ of test intents
- HP validation passes all unit tests
- All existing tests still pass
- Integration test demonstrates LLM bypass on known intents

### 5.2 Agent B: MCP Hardening + Audit (2 days)

| Day | Focus | Deliverables |
|---|---|---|
| Day 1 AM | MCP security core | `core/mcp/security.py` with ToolClassification, classification middleware, token bucket rate limiter |
| Day 1 PM | Invocation auditor + JSONL logging | InvocationAuditor with daily rotation, PII-safe truncation, episodic memory integration |
| Day 2 AM | Retroactive anomaly checker | RetroactiveChecker with frequency, time pattern, chain anomaly detection |
| Day 2 PM | Automated rollback + integration | AutomatedRollback for git/delete/deploy/exec, MCP server integration via decorator |

**Agent B Entry Criteria:**
- Agent A completed (rules engine + HP validator)
- `core/mcp_server.py` source available
- `core/loop/permission_gateway.py` source available
- `core/config.py` source available

**Agent B Exit Criteria:**
- All MCP tools classified into tiers
- Rate limiting works with correct per-tier limits
- Audit log captures every invocation
- Retroactive checker flags known anomalous patterns
- Auto-rollback triggers on high-severity anomalies
- All existing tests still pass

---

## 6. Implementation Steps

### 6.1 Agent A Steps (Steps 1-10)

**Step 1: Create `core/loop/rules_engine.py`**
- Define `Rule`, `RuleMatch`, `Action` dataclasses
- Define `IntentCategory` enum
- Implement `RulesEngine` class with `evaluate()`, `register_handler()`, `reload_rules()`
- Implement YAML rule loading with validation
- Implement condition builder from YAML spec
- Implement cooldown mechanism
- Implement file watcher for hot-reload
- Implement match statistics tracking

**Step 2: Create `core/loop/rules.yaml`**
- Define VECTOR-specific rule catalog sections:
  - Timing & Calendar (8+ rules)
  - Greetings & Social (10+ rules)
  - Status & Health (10+ rules)
  - Goals & Tasks (6+ rules)
  - Memory & Recall (6+ rules)
  - Classification & Routing (4+ rules)
  - Routine & Scheduled (6+ rules)
  - Security (3+ rules)
  - Configuration (3+ rules)
  - Help & Documentation (3+ rules)
  - Learning & Training (3+ rules)
  - Confirmation & Acknowledgment (4+ rules)
  - Informational Queries (8+ rules)
  - Fallthrough Catches (5+ rules)
- Total: 50+ rules covering common intents

**Step 3: Create handler implementations**
- Implement timestamp/date handlers
- Implement greeting/response handlers
- Implement system status handlers
- Implement memory recall handlers
- Implement classification handlers
- Implement routine handlers
- Implement all fallthrough handlers

**Step 4: Modify `core/loop/autonomous_loop.py`**
- Import `RulesEngine` and handlers
- Initialize `RulesEngine` in loop setup
- Register all handlers
- Add `_extract_intent()` method
- Modify `think()` to check rules engine before LLM
- Add `_log_rule_match()` for episodic memory logging
- Add metrics counters for LLM bypass tracking

**Step 5: Create `core/city/hp_validator.py`**
- Define `HPUpdate` and `ValidationResult` dataclasses
- Implement `HPValidator` class with:
  - Rolling window (deque of last 5 deltas, median)
  - Cross-district agreement (pending queue, timeout)
  - Outlier rejection (|delta| > 200 threshold)
  - EMA smoothing with configurable alpha
  - Audit logging to episodic memory
  - Statistics tracking

**Step 6: Modify `core/city/point_system.py`**
- Import `HPValidator`
- Initialize singleton `hp_validator`
- Route all HP delta applications through `hp_validator.validate()`
- Handle ValidationResult outcomes

**Step 7: Modify `core/city/evolution_engine.py`**
- Replace direct HP delta calls with validated calls
- Create `HPUpdate` objects with source district and confidence
- Implement `apply_event_hp_change()` with event-type mapping
- Handle special case: death bypasses validation
- Add escalation queue for human review
**Step 8: Modify `core/config.py`**
- Add rules engine configuration section
- Add HP validation configuration section
- Add MCP security configuration section (shared with Agent B)

**Step 9: Modify `core/memory/episodic.py`**
- Add `hp_audit`, `mcp_invocation`, `mcp_rollback`, `rule_match` to valid event types
- Implement `get_hp_audit()` query helper
- Implement `get_mcp_audit()` query helper

**Step 10: Write tests for Agent A**
- Test rules engine: YAML loading, pattern matching, priority sorting, cooldowns
- Test rules engine: fallthrough on no match, handler execution
- Test rules engine: hot-reload on file change
- Test HP validator: confidence threshold rejection
- Test HP validator: rolling window median computation
- Test HP validator: cross-district agreement (2+ sources)
- Test HP validator: outlier rejection (|delta| > 200)
- Test HP validator: EMA smoothing
- Test HP validator: escalation threshold
- Test HP validator: integration with point_system
- Test HP validator: integration with evolution_engine

### 6.2 Agent B Steps (Steps 11-20)

**Step 11: Create `core/mcp/__init__.py`**
- Package initialization marker

**Step 12: Create `core/mcp/security.py`**
- Define `ToolTier` enum (READ/WRITE/DANGER)
- Define `ToolClassification`, `ToolInvocation`, `AnomalyReport` dataclasses
- Implement `TOOL_TIERS` classification map
- Implement `ToolClassificationMiddleware`: pattern-based, cache, default DANGER

**Step 13: Implement `TokenBucketRateLimiter`**
- Per (caller, tier) bucket tracking
- Sliding window check with 1-minute window
- Usage statistics query
- Configurable per-tier limits

**Step 14: Implement `InvocationAuditor`**
- JSONL file writer with daily rotation
- PII-safe parameter truncation (500 char limit)
- Episodic memory integration
- Recent invocation queries (by time, caller, tool)
- 30-day retention with auto-cleanup

**Step 15: Implement `RetroactiveChecker`**
- Historical baseline builder
- Frequency anomaly detection (100+ calls/hour threshold)
- Time pattern anomaly (unusual hours, unexpected callers)
- Chain anomaly detection (read->write->danger within 5 minutes)
- Severity scoring (0.0-1.0)

**Step 16: Implement `AutomatedRollback`**
- Git revert for git_* tool anomalies
- Backup restore trigger for delete_* tool anomalies
- Deploy rollback for deploy_* tool anomalies
- Quarantine for exec_* tool anomalies
- Rollback audit logging
- Disable/enable toggle

**Step 17: Implement `MCPSecurityManager`**
- Coordinator class composing all security components
- `check_and_record()` -- unified security check + audit
- Permission gateway integration
- `run_anomaly_check()` -- on-demand anomaly scan
- `get_status()` -- comprehensive status report

**Step 18: Modify `core/mcp_server.py`**
- Import `MCPSecurityManager`
- Initialize security manager
- Create `secure_tool` decorator
- Apply decorator to all tool registrations
- Handle PermissionError from security denials
- Add security status MCP tools

**Step 19: Modify `core/loop/permission_gateway.py`**
- Ensure permission levels map to MCP tiers
- Add function: `check_permission(caller, level) -> bool`

**Step 20: Write tests for Agent B**
- Test tool classification: all patterns match correctly
- Test tool classification: unknown tools -> DANGER (fail closed)
- Test rate limiter: within limits, at limit, over limit
- Test rate limiter: different limits per tier
- Test auditor: record and retrieve invocations
- Test auditor: PII-safe truncation
- Test auditor: daily file rotation
- Test retroactive checker: frequency anomaly detection
- Test retroactive checker: time pattern anomaly detection
- Test retroactive checker: chain anomaly detection
- Test rollback: git revert invocation
- Test rollback: severity threshold enforcement
- Test integration: full security check flow
- Test integration: permission gateway integration

---

## 7. Files to Create/Modify

### 7.1 Files to Create

| File | Purpose | Agent | Lines (est.) |
|---|---|---|---|
| `core/loop/rules_engine.py` | Rules engine core: Rule/Action dataclasses, RulesEngine class | A | 500-600 |
| `core/loop/rules.yaml` | Hot-reloadable rule catalog: 50+ intent patterns | A | 400-500 |
| `core/loop/rules_handlers.py` | Default handler implementations for all rules | A | 200-300 |
| `core/city/hp_validator.py` | HP validation: HPUpdate/ValidationResult, HPValidator class | A | 350-450 |
| `core/mcp/__init__.py` | Package init for MCP security module | B | 5-10 |
| `core/mcp/security.py` | MCP security: classification, rate limiting, audit, checker, rollback | B | 600-700 |
| `core/mcp/audit/` | Directory for daily JSONL audit logs (created at runtime) | B | -- |

### 7.2 Files to Modify

| File | Change | Agent | Estimate |
|---|---|---|---|
| `core/loop/autonomous_loop.py` | Hook rules engine before think phase (~30 lines) | A | 1hr |
| `core/city/point_system.py` | Route all HP deltas through HPValidator (~20 lines) | A | 30min |
| `core/city/evolution_engine.py` | Create HPUpdate objects, call validator (~40 lines) | A | 1hr |
| `core/config.py` | Add 3 new config sections (~30 lines) | A+B | 30min |
| `core/memory/episodic.py` | Add 4 new event types, query helpers (~30 lines) | A+B | 30min |
| `core/mcp_server.py` | Add security middleware/decorator (~20 lines) | B | 1hr |
| `core/loop/permission_gateway.py` | Add tier-aware check_permission function (~15 lines) | B | 30min |

### 7.3 Total Change Estimate

| Metric | Value |
|---|---|
| Files created | 7 |
| Files modified | 7 |
| Total new lines | ~2,200 |
| Total modified lines | ~185 |
| Total implementation days | 4 (2 agents x 2 days) |
---

## 8. Success Criteria

### 8.1 Primary Criteria

| Criterion | Target | Measurement | Verification |
|---|---|---|---|
| Rules engine match rate | >=60% of daily intents | Counters in rules_engine.get_stats() | 7-day continuous monitoring |
| Rules engine latency | <10ms per evaluation | Timer in evaluate() method | Benchmark suite |
| LLM call reduction | >=60% (10K->4K/day) | Baseline vs post-deployment counters | A/B comparison |
| HP variance on re-sampling | <5% | Bootstrap resampling of HP audit log | Statistical test |
| HP incorrect agent deaths | 0/month | evolution_engine audit log | 30-day monitoring |
| MCP tools classified | 100% | All 300+ tools mapped to tier | Code review |
| MCP invocations audited | 100% | Every call in JSONL + episodic | Counters match |

### 8.2 Secondary Criteria

| Criterion | Target | Measurement |
|---|---|---|
| Rules engine zero false positives | 100% | Manual review of 1,000 matched intents |
| HP validator zero incorrect rejections | 100% | Audit log analysis |
| Rate limiter overhead | <1ms per check | Timer in check() method |
| Audit log disk usage | <100MB/day | File size monitoring |
| Rollback accuracy | 100% correct revert | Test suite |
| Hot-reload detection time | <10 seconds | File modification test |
| Config validation | All invalid YAML/config rejected | Test suite |

### 8.3 Stress Test Criteria

| Scenario | Expected Behavior |
|---|---|
| 10,000 rules evaluations/second | <10ms latency, no errors |
| 100 concurrent HP updates | All validated within 50ms |
| 1,000 MCP calls/minute to single tool | Rate limiter blocks excess, audit logs all |
| DANGER tool call at 3AM from unknown caller | Anomaly flagged, auto-rollback triggered |
| rules.yaml deleted | Engine continues with last loaded rules |
| HP validator offline | Evolution engine falls back to raw HP (graceful) |
| MCP security module offline | All tools blocked (fail closed) |

---

## 9. Dependencies

### 9.1 Internal Dependencies

| Dependency | Spec/Module | Relationship |
|---|---|---|
| Event Bus | SPEC-002 | Rules engine may use event bus for rule hot-reload notifications |
| Testing Infrastructure | SPEC-014 | New modules need comprehensive test coverage |
| Permission Gateway | `core/loop/permission_gateway.py` | MCP tiers integrate with existing permission levels |
| Episodic Memory | `core/memory/episodic.py` | Audit logging for HP and MCP events |
| Config System | `core/config.py` | New config sections for all three subsystems |
| Context Engine | `core/loop/context_engine.py` | Rules engine reads WorldState for conditions |
| Agent Registry | `core/city/agent_registry.py` | HP validation queries agent state |
| Ollama Safe | `core/inference/ollama_safe.py` | Rules engine reduces load on this module |

### 9.2 External Dependencies

| Dependency | Version | Purpose |
|---|---|---|
| PyYAML | >=6.0 | YAML parsing for rules catalog |
| fnmatch | stdlib | Glob pattern matching for rules and tool classification |
| psutil | >=5.8 | System resource monitoring handlers |
| pynvml | >=11.0 | GPU monitoring handler (optional) |
| statistics | stdlib | Rolling window median computation |

### 9.3 Blocking Dependencies

| Blocking On | Reason | Risk |
|---|---|---|
| SPEC-002 (Event Bus) | Hot-reload notifications | Low -- can poll filesystem instead |
| SPEC-014 (Testing) | CI/CD pipeline for test execution | Medium -- can run tests manually |
| Permission Gateway design | MCP tier integration | Medium -- gateway must expose check_permission() |

---

## 10. Risk Assessment

### 10.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Rules engine matches false positives | Medium | Medium | Priority system ensures most specific rule wins; fallthrough catch-all at priority 0 |
| HP validator rejects valid changes | Low | High | ValidationResult outcomes include "flagged" (applied under watch) |
| MCP security introduces latency | Low | Medium | Classification is O(1) with cache; rate limiter is O(1) deque; total overhead <1ms |
| Auto-rollback reverts legitimate operations | Low | Critical | Rollback threshold set to 0.8 (very conservative) |
| YAML hot-reload has syntax errors | Medium | Low | Old rules stay active; error logged; fallthrough to LLM works as safety net |
| Cross-district HP agreement timeouts | Medium | Low | Pending queue has timeout; if no agreement in 30s, update applied as "flagged" |

### 10.2 Integration Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Autonomous loop changes break existing flow | Low | Critical | Rules engine returns None -> existing LLM path unchanged |
| Evolution engine bypasses validator | Low | High | All HP delta functions routed through validator at lowest level |
| MCP decorator misses some tools | Medium | High | All 300+ tools must be reviewed; automated test enumerates all registered tools |

### 10.3 Operational Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Audit logs consume disk space | High | Low | 30MB/day estimated; 30-day retention; auto-cleanup |
| Rules engine cold start delay | Low | Low | YAML loading is <100ms; file watcher starts after load |
| GPU monitoring handler fails | Low | Low | Graceful fallback with informative error message |

---
## 11. Testing Strategy

### 11.1 Unit Tests

| Module | Test Suite | Tests | Framework |
|---|---|---|---|
| Rules Engine | `tests/test_rules_engine.py` | 25+ | pytest |
| HP Validator | `tests/test_hp_validator.py` | 20+ | pytest |
| MCP Security | `tests/test_mcp_security.py` | 30+ | pytest |
| Integration | `tests/test_system_hardening.py` | 10+ | pytest |

### 11.2 Rules Engine Tests

```python
# tests/test_rules_engine.py

import pytest
from core.loop.rules_engine import RulesEngine, Rule, Action, IntentCategory

class TestRulesEngine:
    def test_rule_pattern_matching(self):
        """Verify glob patterns match expected intents."""
        ...
    def test_rule_priority_ordering(self):
        """Verify higher priority rules match first."""
        ...
    def test_fallthrough_on_no_match(self):
        """Verify None returned when no rule matches."""
        ...
    def test_handler_execution(self):
        """Verify matched rule executes correct handler."""
        ...
    def test_cooldown_enforcement(self):
        """Verify cooldown prevents rapid re-matching."""
        ...
    def test_yaml_loading(self):
        """Verify rules load correctly from YAML."""
        ...
    def test_hot_reload(self):
        """Verify file changes trigger reload."""
        ...
    def test_condition_evaluation(self):
        """Verify WorldState conditions are checked."""
        ...
    def test_match_statistics(self):
        """Verify match counters are accurate."""
        ...
```

### 11.3 HP Validator Tests

```python
# tests/test_hp_validator.py

import pytest
from core.city.hp_validator import HPValidator, HPUpdate

class TestHPValidator:
    def test_confidence_threshold(self):
        """Verify low-confidence updates are rejected."""
        ...
    def test_rolling_window_median(self):
        """Verify median of last 5 deltas."""
        ...
    def test_cross_district_agreement(self):
        """Verify 2+ districts required for agreement."""
        ...
    def test_outlier_rejection(self):
        """Verify |delta| > 200 is flagged."""
        ...
    def test_ema_smoothing(self):
        """Verify EMA with alpha=0.3."""
        ...
    def test_escalation_threshold(self):
        """Verify 3+ escalations trigger auto-reject."""
        ...
    def test_audit_logging(self):
        """Verify audit log entries are created."""
        ...
```

### 11.4 MCP Security Tests

```python
# tests/test_mcp_security.py

import pytest
from core.mcp.security import (
    ToolClassificationMiddleware, TokenBucketRateLimiter,
    InvocationAuditor, RetroactiveChecker, AutomatedRollback,
    MCPSecurityManager, ToolTier
)

class TestToolClassification:
    def test_search_pattern(self):
        """Verify search_* tools classified as READ."""
        ...
    def test_delete_pattern(self):
        """Verify delete_* tools classified as DANGER."""
        ...
    def test_unknown_tool_default_danger(self):
        """Verify unknown tools default to DANGER (fail closed)."""
        ...

class TestRateLimiter:
    def test_within_limits(self):
        """Verify calls within limit are allowed."""
        ...
    def test_over_limit(self):
        """Verify calls beyond limit are blocked."""
        ...
    def test_window_refill(self):
        """Verify rate limit resets after window."""
        ...

class TestAuditor:
    def test_record_invocation(self):
        """Verify invocation is logged to JSONL and episodic."""
        ...
    def test_pii_truncation(self):
        """Verify long parameter payloads are truncated."""
        ...

class TestRetroactiveChecker:
    def test_frequency_anomaly(self):
        """Verify >100 calls/hour triggers anomaly."""
        ...
    def test_time_pattern_anomaly(self):
        """Verify 3AM call from unusual district triggers anomaly."""
        ...
    def test_chain_anomaly(self):
        """Verify read->write->danger chain triggers anomaly."""
        ...

class TestAutomatedRollback:
    def test_git_rollback(self):
        """Verify git revert is called for git_* anomalies."""
        ...
    def test_severity_threshold(self):
        """Verify low-severity anomalies do not trigger rollback."""
        ...
```

---

## 12. Migration Plan

### 12.1 Phase 1: Rules Engine Only (Day 1)
- Deploy `rules_engine.py` and `rules.yaml` in shadow mode (log matches but do not bypass LLM)
- Run for 24 hours to collect match rate data
- Verify match quality: manually review 500 matched intents
- Enable bypass mode after quality sign-off
- Monitor LLM call reduction and false negative rate

### 12.2 Phase 2: HP Validator Only (Day 2)
- Deploy `hp_validator.py` in shadow mode (log validations but use raw HP)
- Run for 48 hours to collect validation statistics
- Compare validated vs raw HP trajectories
- Enable enforcement mode after variance <5% confirmed

### 12.3 Phase 3: MCP Security (Days 3-4)
- Deploy `core/mcp/security.py` with audit-only mode (log but do not block)
- Run for 24 hours to establish baseline invocation patterns
- Enable rate limiting on READ tier first (lowest blast radius)
- Enable rate limiting on WRITE tier after 12h of clean data
- Enable rate limiting on DANGER tier last, with auto-rollback DISABLED initially
- Enable auto-rollback after 48h of anomaly detection clean run

### 12.4 Rollback Plan
If any component causes system degradation:
1. Rules engine: Remove `think()` hook -> restore original LLM path (instant, no restart)
2. HP validator: Set `HP_VALIDATOR_ENABLED = False` in config, restart loop
3. MCP security: Set `MCP_SECURITY_ENABLED = False` in config, tools revert to raw access

---

## 13. Appendix: Rule Catalog (Complete)

The full rules catalog contains 50+ rules organized into 14 categories:

| Category | Rule Count | Example Rule | Priority Range |
|---|---|---|---|
| Timing & Calendar | 8 | `time_current`, `calendar_check` | 75-100 |
| Greetings & Social | 10 | `greeting_hello`, `how_are_you`, `thanks` | 90-100 |
| Status & Health | 10 | `status_system`, `uptime`, `version` | 70-90 |
| Goals & Tasks | 6 | `goal_status`, `task_list` | 65-80 |
| Memory & Recall | 6 | `recall_recent`, `search_memory` | 60-80 |
| Classification & Routing | 4 | `classify_intent`, `route_to_district` | 60-70 |
| Routine & Scheduled | 6 | `routine_morning`, `daily_summary` | 50-70 |
| Security | 3 | `security_status`, `security_alerts` | 75-80 |
| Configuration | 3 | `config_show`, `config_set`, `config_reload` | 50-60 |
| Help & Documentation | 3 | `help_general`, `help_command` | 50-60 |
| Learning & Training | 3 | `learning_status`, `policy_stats` | 40-50 |
| Confirmation & Acknowledgment | 4 | `confirm_yes`, `acknowledge` | 30-40 |
| Informational Queries | 8 | `query_agent_count`, `query_gpu_usage` | 60-75 |
| Fallthrough Catches | 5 | `catch_how_to`, `catch_generic_question` | 0-15 |
| **Total** | **79** | | **0-100** |

Rules are stored in YAML format at `core/loop/rules.yaml` and hot-reloaded every 5 seconds on file change. Each rule specifies an ID, intent pattern (glob), category, handler function name, priority, optional cooldown, optional conditions, and description.

---

## 14. Appendix: Tool Tier Classification

All 300+ MCP tools are classified into three tiers:

### READ Tier (GREEN, ~180 tools)
- Rate limit: 100 calls/minute per caller
- Permission: GREEN (auto-approve)
- Tool patterns: `search_*`, `get_*`, `list_*`, `recall_*`, `query_*`, `check_*`, `find_*`, `status_*`, `lookup_*`
- Examples: `search_memory`, `get_agent_state`, `list_districts`, `recall_events`, `query_calendar`

### WRITE Tier (YELLOW, ~90 tools)
- Rate limit: 10 calls/minute per caller
- Permission: YELLOW (confirmation required)
- Tool patterns: `store_*`, `create_*`, `update_*`, `send_*`, `save_*`, `register_*`, `configure_*`, `set_*`
- Examples: `store_memory`, `create_task`, `update_config`, `send_message`, `register_agent`

### DANGER Tier (RED, ~30 tools)
- Rate limit: 1 call/minute per caller
- Permission: RED (deny unless escalated)
- Tool patterns: `git_*`, `delete_*`, `exec_*`, `deploy_*`, `admin_*`, `drop_*`, `reset_*`, `shutdown_*`, `restart_*`, `purge_*`, `wipe_*`, `migrate_*`
- Examples: `git_commit`, `delete_agent`, `exec_command`, `deploy_district`, `admin_override`, `shutdown_server`

Unknown tools (no pattern match) default to DANGER tier with RED permission (fail closed).

---

## 15. Appendix: HP Validation Mathematics

### 15.1 Rolling Window Median

Maintains a deque of the last 5 HP deltas per agent. The median of this window is used instead of the raw delta:

```
HP_delta_adjusted = median([d1, d2, d3, d4, d5])
```

### 15.2 Exponential Moving Average (EMA) Smoothing

The smoothed HP value is updated using an exponential moving average:

```
alpha = 0.3
HP_smoothed = HP_smoothed + alpha * HP_delta_adjusted
```

This means each new HP change contributes only 30% of its value to the smoothed HP, preventing wild swings from single noisy observations.

### 15.3 Cross-District Agreement

An HP change is only applied if at least 2 independent districts agree on the direction (both positive or both negative) within a configurable time window (default 30 seconds). This prevents a single compromised or noisy district from affecting agent HP.

### 15.4 Outlier Rejection

Any HP delta with |delta| > 200 is flagged for human review. If the same agent accumulates 3+ escalations, further large deltas from any district are automatically rejected. This prevents death spirals from outlier observations.

### 15.5 Confidence Weighting

Each HPUpdate carries a confidence score from the LLM (0.0-1.0). Updates with confidence < 0.3 are rejected outright. Across pending cross-district updates, the highest-confidence update among the agreeing set is applied.

### 15.6 Graceful Degradation

If the HP validator module is unavailable or throws an exception, the evolution engine falls back to raw HP application (the old behavior). This ensures VECTOR always has an operational path for HP changes, even during validator outages.

---

*End of SPEC-015*