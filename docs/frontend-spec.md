# VECTOR — Complete Backend Specification for Frontend Design

> **Who this is for:** A frontend designer (Claude design) building VECTOR's dashboard UI.  
> **What this is:** Every API endpoint, WebSocket channel, data model, brand rule, and UI requirement — derived by reading the actual Python codebase line by line.  
> **Owner:** Arghyadeep Deb · KIIT CSE 2023-27 · Legion Pro 5 · RTX 5070 Ti  
> **Stack:** FastAPI (Python) backend · Vite + React/TypeScript frontend · Zustand state

---

## 1. Runtime Config

| Variable | Default | Purpose |
|---|---|---|
| `VECTOR_API_KEY` | (unset) | Bearer token for all protected routes. If unset, localhost-only enforcement. |
| `VECTOR_ENV` | `development` | `development` \| `production` |
| `VECTOR_DEBUG` | `false` | Exposes error detail in responses |
| `VECTOR_JWT_SECRET` | (required for collections) | HS256 signing key |
| `VECTOR_JWT_ACCESS_TTL` | `900` | Seconds for JWT access token |
| `VECTOR_JWT_REFRESH_TTL` | `1209600` | Seconds for JWT refresh token (14 days) |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Local LLM inference |

**API base URL:** `http://127.0.0.1:8000`  
**Vite dev server:** `http://localhost:5173`  
**OpenAPI docs:** `/docs` (Swagger), `/redoc`, `/openapi.json`  
**Static HUD:** FastAPI serves built frontend from `/` → `core/ui/dashboard/dist/index.html`

---

## 2. Authentication

### HTTP
All non-public routes require:
```
Authorization: Bearer <VECTOR_API_KEY>
```

**Public routes (no auth needed):**
`/` `/status` `/health` `/docs` `/openapi.json` `/redoc` `/csrf-token`

**Error:** `401 {"detail": "Unauthorized"}` or `403 {"detail": "Remote access requires API key"}`

### WebSocket
Append token as query param:
```
ws://localhost:8000/ws?token=Bearer+<VECTOR_API_KEY>
```
Close code `4001` on auth failure.

### CSRF (browser context only)
1. `GET /csrf-token` → `{"csrf_token": "<64-char hex>"}`
2. Include on every mutation: `X-CSRF-Token: <token>` header
3. TTL: 3600s. Skip for API-key authenticated requests.

### Collections JWT (separate from main auth)
```
POST /api/collections/{name}/auth-with-password
Body: {"username": "...", "password": "..."}
Response: {"token": "<jwt>", "refresh_token": "<jwt>"}

# Use as:
Authorization: Bearer <jwt>

# Refresh:
POST /api/collections/{name}/auth-refresh
Body: {"refresh_token": "..."}
```

---

## 3. Headers Reference

| Header | Direction | Purpose |
|---|---|---|
| `Authorization: Bearer <key>` | Request | Main API auth |
| `X-CSRF-Token: <token>` | Request | Required on POST/PUT/DELETE/PATCH |
| `X-Request-ID` | Response | 8-char UUID trace ID |
| `X-Response-Time-Ms` | Response | Total elapsed ms |
| `X-RateLimit-Limit` | Response | Requests per minute allowed |
| `X-RateLimit-Remaining` | Response | Requests remaining this window |
| `X-System-Version` | Response | VECTOR semver |

---

## 4. Error Format

All errors return JSON:
```json
{
  "error": "Rate limit exceeded",
  "detail": "Too many requests. Retry after 60s",
  "timestamp": "2026-05-29T...",
  "retry_after": 60
}
```
Standard FastAPI validation errors: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`

HTTP status codes: `400` validation · `401` unauthenticated · `403` forbidden · `404` not found · `429` rate limit · `500` server error

---

## 5. Rate Limits

| Route | Limit |
|---|---|
| `/command`, `/ws/command` | 20 req/min |
| `/council` | 10 req/min |
| Everything else | 100 req/min |

Window: 60 seconds per IP per path.

---

## 6. CORS

Allowed origins (all on localhost):
```
http://127.0.0.1:8000   http://localhost:8000
http://127.0.0.1:3000   http://localhost:3000
http://127.0.0.1:5173   http://localhost:5173
```
Credentials: allowed. Methods: GET, POST. Headers: `*`.

---

## 7. WebSocket Channels

### `/ws` — Main Command + Status Stream
```
ws://localhost:8000/ws?token=Bearer+<key>
```
**Client → Server:**
```json
{"action": "ping"}
{"action": "status"}
{"action": "command", "text": "...", "priority": "normal|high"}
{"action": "subscribe", "events": ["DECISION_MADE", "AGENT_HP_CHANGED"]}
```
**Server → Client pushes:**
```json
{"type": "pong"}
{"type": "status", "loop_running": true, "uptime_seconds": 3600, "agents": {...}, "memory": {...}, "models": [...]}
{"type": "response", "text": "...", "action_taken": "...", "processing_ms": 420}
{"type": "orb_state", "state": "idle|listening|processing|speaking"}
{"type": "error", "detail": "..."}
```
Keepalive: 30s timeout. Server pings on silence.

---

### `/ws/state` — Event Bus Bridge
```
ws://localhost:8000/ws/state
```
No auth required. Pushes:
```json
{"type": "state_ready"}
{"type": "state_event", "event_type": "DECISION_MADE|AGENT_HP_CHANGED|TASK_ROUTED|HYPOTHESIS_SURFACED|ANOMALY_DETECTED", "data": {...}, "source": "...", "ts": "..."}
```

---

### `/ws/voice/stream` — Push-to-Talk Voice
```
ws://localhost:8000/ws/voice/stream
```
**Protocol:**
1. Client sends: binary webm/opus audio chunks
2. Client sends: `{"type": "end"}` when done speaking
3. Server replies in sequence:
```json
{"type": "transcript", "text": "Hey VECTOR show me my goals"}
{"type": "response", "text": "Displaying your goals now, sir."}
{"type": "audio", "data": "<base64 wav>", "sample_rate": 24000}
{"type": "done"}
```
Also broadcasts `orb_state` events to all connected `/ws` clients.

---

### `/gesture/ws` — Hand Tracking
```
ws://localhost:8000/gesture/ws
```
Streams MediaPipe hand landmarks + classified gesture:
```json
{"x": 0.72, "y": 0.41, "confidence": 0.94, "gesture": "point|pinch|open_palm|fist|swipe_left|swipe_right|swipe_up|swipe_down"}
```
Gesture → UI action mapping:
| Gesture | Action |
|---|---|
| `point` | Move cyan cursor dot to (x, y) |
| `pinch` (thumb+index) | Synthesize click on widget under cursor |
| `open_palm` | Fire `vector:wake` event (exit locked state) |
| `fist` | Close topmost widget |
| `swipe_left/right` | Dismiss / restore last widget |
| `swipe_up/down` | Pan infinite canvas |

---

### `/camera/ws` — Live Camera Feed
```
ws://localhost:8000/camera/ws
```
Streams JPEG frames as base64 with YOLO detections:
```json
{"frame": "<base64 jpeg>", "detections": [{"class": "person", "confidence": 0.97, "bbox": [x, y, w, h]}]}
```
Control: `POST /camera/start` (body: `{"index": 0}`) · `POST /camera/stop` · `GET /camera/status`

---

### `/notifications/ws` — Hypothesis & Alert Push
```
ws://localhost:8000/notifications/ws
```
Sends pending hypotheses on connect, then live events:
```json
{"event": "hypothesis_surfaced", "data": {"id": "...", "text": "...", "confidence": 0.82}}
```
Ping/pong keepalive.

---

## 8. Server-Sent Events (SSE)

### `GET /sb/sse` — Shadowbroker Live Map Layers
Media-type: `text/event-stream`  
Events: `layer_changed`, `alert`, `task`  
Used by `MapView` widget (live flights, ships, satellites).

### `GET /a2a/events` — A2A Agent Event Stream
Media-type: `text/event-stream`  
Streams agent task execution progress for long-running A2A invocations.

---

## 9. HTTP API — Full Endpoint Reference

### System & Health (public)

| Method | Path | Returns |
|---|---|---|
| GET | `/status` | `{loop_running, uptime_seconds, agents:{count, districts, list}, memory:{...}, models:[...], version}` |
| GET | `/health` | `{checks:{db, ollama, memory, ...}, timestamp}` |
| GET | `/system` | `{cpu_percent, ram_percent, disk_percent, net_bytes_sent, net_bytes_recv}` |
| GET | `/daily` | Daily VECTOR summary (prose) |
| GET | `/csrf-token` | `{csrf_token}` |

---

### Command (Core Intelligence Entry Point)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/command` | `{text, source?, priority?}` | `{response, action_taken, processing_ms, decision:{winner, score, reasoning}}` |
| POST | `/command/feedback` | `{action_id, outcome, reward}` | `{status}` — updates policy memory |

---

### Brain (Goals + Reasoning)

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/brain/goals` | — | `{goals: [{id, title, horizon, priority, progress, tags}]}` |
| POST | `/brain/goals/add` | `{title, horizon:"LONG|MID|SHORT", priority}` | `{goal_id}` |
| GET | `/brain/goals/immediate` | — | `{actions: [{action_type, params, goal_ids, confidence}]}` |
| POST | `/brain/synthesis` | `{outputs, synthesis_type}` | `{synthesis}` |
| POST | `/brain/hypothesis/generate` | `{observation}` | `{hypothesis_id, text, confidence}` |
| GET | `/brain/hypothesis/active` | — | `{hypotheses:[...]}` |
| POST | `/brain/hypothesis/test` | `{hypothesis_id, evidence}` | `{confirmed, updated_confidence}` |
| POST | `/brain/red-team/attack` | `{belief}` | `{attack_vectors, weaknesses}` |
| GET | `/brain/epistemic/summary` | — | `{beliefs:[{key,confidence,staleness}]}` |
| GET | `/brain/reasoning/chains` | — | `{chains:[{id,situation,steps,reward,is_training_data}]}` |
| GET | `/brain/persons` | — | `[{person_id, name, trust_score, beliefs:{}}]` |
| GET | `/brain/persons/{person_id}` | — | `{person_id, name, trust_score, beliefs, interaction_count}` |
| PUT | `/brain/persons/{person_id}/belief` | `{key, value, confidence}` | `{status}` |
| PUT | `/brain/persons/{person_id}/trust` | `{score}` | `{status}` |

---

### Council (High-Stakes Deliberation)

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| POST | `/council` | `{question, stakes:"low|high|critical", context_override?}` | `{session_id, decision, recommendation:"proceed|defer|reject", confidence, votes:[{model,vote,rationale}], chairman_decision}` | Throttled: 10/week · Requires requester HP ≥ 700 |

---

### Memory

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/memory/recent` | `limit=1-50 (default 10)` | `{events:[{id,event_type,content,importance,tags,timestamp,source}]}` |
| GET | `/memory/recent/{event_type}` | `limit` | filtered list |
| GET | `/memory/training-data` | `limit=1-500` | `{training_data:[{situation,steps,action,outcome,reward}]}` |
| GET | `/memory/goals` | — | `{goals, immediate_actions}` |
| GET | `/memory/council/history` | `limit=1-20` | `{sessions:[CouncilSession]}` |
| POST | `/memory/backup` | — | `{status, backup_path}` |
| POST | `/memory/restore` | `{backup_path, overwrite:bool}` | `{status}` |

---

### Agents & City

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/agents` | — | `{agents:[Agent], total}` |
| GET | `/agents/{agent_id}` | — | `Agent` |
| POST | `/agents/award` | `{agent_id, points, reason}` | `{new_hp, tier, model_upgrade?}` |
| GET | `/city/districts` | — | `{districts:[{name, agent_count, agents:[...]}]}` |
| GET | `/city/evolution/generations` | — | `{agents:{id:{generation, hp, parent_id}}}` |
| POST | `/city/evolution/spawn` | `{dead_agent_id, district}` | `{new_agent_id, inherited_lessons}` |
| POST | `/city/agents/history` | `{agent_id}` | `{generations:[...]}` |
| POST | `/city/dispatch` | `{task_type, params}` | `{routed_to, result}` |

---

### Voice

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/voice` | `multipart: audio file` | `{transcript, response, language_detected, action_taken}` |
| GET | `/voice/status` | — | `{stt_engine, tts_engine, wake_model, ambient_running}` |
| POST | `/voice/speak` | `{text}` | `{audio_url}` |
| GET | `/voice/profiles` | — | `[{name, type:"cloned|preset", is_default}]` |
| POST | `/voice/profiles` | `{name, type, ...}` | `{profile_id}` |
| POST | `/voice/profiles/{name}/sample` | `multipart: wav reference` | `{status}` |
| POST | `/voice/profiles/{name}/default` | — | `{status}` |

---

### Inference

| Method | Path | Returns |
|---|---|---|
| GET | `/inference/stats` | `{models:[{name, size, loaded}], active_model}` |
| GET | `/inference/models` | `{models:[], count}` |
| GET | `/inference/providers` | `{providers:[{name, available, requires_key}], count}` |
| POST | `/inference/run` | body: `{model, prompt, system?}` → `{response, tokens_used, latency_ms}` |

---

### Autonomous Loop

| Method | Path | Returns |
|---|---|---|
| GET | `/loop/status` | `{running, tick_count, guard_violations, last_tick_ms, service_tier}` |

---

### Security & Permissions

| Method | Path | Returns |
|---|---|---|
| GET | `/security/status` | `{threat_level:"low|medium|high|critical", anomalies:[], pending_approvals:[{action_id,action_type,params,proposed_by,expires_at}], audit_log_count}` |
| GET | `/security/recent` | `{events:[{action_type,level:"GREEN|YELLOW|RED",approved,timestamp}]}` |
| POST | `/security/confirm/{action_type}` | body: `{action_id}` → `{status}` |

---

### Audit Log

| Method | Path | Returns |
|---|---|---|
| GET | `/audit/recent` | `[{action_id, action_type, params, level, approved, timestamp, merkle_hash}]` |
| GET | `/audit/verify?hash=...&sig=...` | `{valid:bool}` |

---

### Research

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/research/status` | — | `{modes:[], llm_available}` |
| GET | `/research/search` | `query, max_results=5` | `{results:[{title,url,snippet}]}` |
| GET | `/research/news` | `query` | `{articles:[{title,url,published}]}` |
| GET | `/research/papers` | `query, max_results=5` | `{papers:[{title,authors,abstract,url}]}` |
| GET | `/research/reddit` | `subreddit, limit=10` | `{posts:[{title,score,url,comments}]}` |

---

### Health / Wellness

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health/check-fatigue` | — | `{fatigue_score:0-10, ear_score, recommendation}` |
| POST | `/health/sleep` | `{duration_hours, quality:1-5, notes?}` | `{status}` |
| GET | `/health/biometrics` | — | `{sleep_debt, energy_level, stress_level, last_updated}` |
| POST | `/health/exercise` | `{type, duration_min, intensity:"low|medium|high"}` | `{status}` |
| GET | `/health/status` | — | `{fatigue, sleep, energy, recommendations:[]}` |

---

### Finance

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/finance/budget-analyze` | `{period?}` | `{summary, breakdown, recommendations}` |
| GET | `/finance/expenses` | — | `[{amount, category, date, description}]` |
| POST | `/finance/expenses/log` | `{amount, category, description}` | `{id}` |
| GET | `/finance/cost-tracker` | — | `{total_spend_inr, by_category:{...}, budget_remaining}` |

---

### Email & Channels

| Method | Path | Returns |
|---|---|---|
| GET | `/email/recent` | `{total, unread, recent:[{from,subject,preview,timestamp,priority}]}` |
| GET | `/channels/status` | `{channels:[{name, connected, message_count, last_activity}]}` |

---

### Calls

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/calls/screen` | `{caller, context?}` | `{action:"answer|ignore|forward", message}` |
| POST | `/calls/transcribe` | `multipart: audio` | `{transcript}` |
| GET | `/calls/contacts` | — | `[{name, number, tier:"vip|normal|unknown"}]` |

---

### Control (Device Automation)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/control/pc/screenshot` | — | Returns `{image_data: base64}` |
| POST | `/control/pc/type` | `{text, delay_ms?}` | **YELLOW gate** |
| POST | `/control/pc/click` | `{x, y, button:"left|right"}` | **YELLOW gate** |
| POST | `/control/pc/launch-app` | `{app_name, args?}` | **YELLOW gate** |
| GET | `/control/phone/status` | — | `{connected, battery, notifications}` |
| GET | `/control/phone/screenshot` | — | `{image_data: base64}` |

---

### Collections (PocketBase-compatible data layer)

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/api/collections` | — | `[{name, schema, record_count}]` |
| POST | `/api/collections` | `{name, schema:{fields:[{name,type,required}]}}` | `{id}` |
| DELETE | `/api/collections/{name}` | — | `{status}` |
| GET | `/api/collections/{name}/records` | `page, per_page, filter, sort` | `{records:[], total, page, per_page}` |
| GET | `/api/collections/{name}/records/{id}` | — | record object |
| POST | `/api/collections/{name}/records` | record fields | `{id, ...fields, created, updated}` |
| PATCH | `/api/collections/{name}/records/{id}` | partial fields | updated record |
| DELETE | `/api/collections/{name}/records/{id}` | — | `{status}` |
| POST | `/api/files/{name}/{record_id}/{field}` | `multipart: file` | `{url}` |
| GET | `/api/files/{name}/{record_id}/{field}/{filename}` | `?thumb=WxH` | binary file |

Field types: `text`, `number`, `bool`, `date`, `select`, `file`, `relation`, `email`, `url`, `json`, `autodate`, `editor`, `password`

---

### A2A (Agent-to-Agent — Google A2A Protocol)

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | `/.well-known/agent.json` | A2A discovery manifest | Public |
| GET | `/a2a/agents` | `[{name, district, capabilities:[]}]` | Public |
| GET | `/a2a/districts/{name}` | agent manifest | Public |
| POST | `/a2a/districts/{name}/invoke` | body: `{task, params, session_id?, stream?}` → `{task_id, agent, status, output}` | |
| GET | `/a2a/districts/{name}/tasks/{task_id}` | `{status:"pending|running|done|failed", output}` | |
| GET | `/a2a/events` | SSE stream | |

---

### Knowledge & Code Intel

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/knowledge/scan-domain` | `{project_path, output_filename?}` | `{entry_points, files, metadata}` |
| POST | `/knowledge/parse-wiki` | `{wiki_root}` | `{nodes, edges, categories}` |
| POST | `/code_intel/search` | `{query}` | `[{file, line, symbol, context}]` |
| POST | `/code_intel/impact` | `{change}` | `{affected_files:[]}` |
| POST | `/code_intel/symbol` | `{name}` | `[{file, line, type}]` |
| GET | `/code_intel/status` | — | `{indexed, file_count, last_updated}` |

---

### Task Queue & Scheduler

| Method | Path | Returns |
|---|---|---|
| GET | `/scheduler/jobs` | `{total, active, jobs:[{id,name,cron,last_run,next_run}]}` |
| GET | `/queue/retry/stats` | `{pending, retrying, failed_today}` |
| GET | `/queue/retry/items` | `[{id,action,attempts,last_error}]` |
| GET | `/queue/dlq/items` | dead letter items |
| POST | `/queue/retry/{item_id}/replay` | — | `{status}` |

---

### Metering & Tools

| Method | Path | Returns |
|---|---|---|
| GET | `/metering/status` | `{tokens_today, cost_inr_today, by_model:{...}, budget_remaining_inr}` |
| GET | `/tools/registry` | `[{name, category, permission_level, call_count}]` |

---

### Notifications & Nudges

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/nudge/latest` | — | `{nudge_id, text, type, urgency, created_at}` |
| POST | `/nudge/dismiss` | `{nudge_id}` | `{status}` |

---

### External Task Ingestion (ESP32, Phone, Cloud → VECTOR)

| Method | Path | Body | Auth | Rate Limit |
|---|---|---|---|---|
| POST | `/api/v1/tasks` | `{text, source, priority:"low|normal|high", district?}` | `Bearer VECTOR_TASK_API_KEY` | 60/min |
| GET | `/tasks` | — | App-level | — |
| DELETE | `/tasks/{task_id}` | — | App-level | — |

---

## 10. Data Models (TypeScript)

### Agent
```typescript
interface Agent {
  id: string
  name: string
  district: string
  health_points: number          // 0-1000
  generation: number             // increments on resurrection
  tier: string
  model: string                  // assigned Ollama model
  lessons: string[]              // post-mortem insights from ancestors
  best_decisions: string[]
  personality_traits: Record<string, number>
  created_at: string
  last_active: string
}
```
**HP tier → model mapping:**
| HP | Model |
|---|---|
| 800-1000 (Elite) | Claude Sonnet 4.6 |
| 700-799 (Strong) | kimi-k2.6 |
| 500-699 (Healthy) | qwen3:14b |
| 300-499 (Weak) | vector-focus (gemma4:e4b) |
| 0-299 (Critical) | vector-ambient (gemma4:e2b) |

**HP events:** +100 user approved · +50 task done · +30 output used · -30 task failed · -50 output ignored 3× · -100 critical error · 0 HP → death → ghost saved → successor spawned

---

### Goal
```typescript
type Horizon = "LONG" | "MID" | "SHORT"

interface Goal {
  id: string
  title: string
  horizon: Horizon
  priority: number               // 1-10
  progress: number               // 0-1
  tags: string[]
  created_at: string
  last_updated: string
}
```
Pre-seeded goals: KIIT attendance ≥75%, Karpathy ML playlist, VECTOR Phase 1, DSA placement prep, daily git commit

---

### Decision + Candidate
```typescript
interface Candidate {
  action_type: string
  params: Record<string, unknown>
  goal_ids: string[]
  confidence: number
  urgency: number
  timing_score: number
  estimated_cost_inr: number
  goal_alignment: number
  policy_score: number
  total_score: number
}

// Score formula:
// total = 0.30×goal_alignment + 0.25×confidence + 0.20×policy_score
//       + 0.15×urgency + 0.10×timing_score - 0.05×cost_penalty

interface Decision {
  winner: Candidate
  all_candidates: Candidate[]    // always 4, even rejects are logged
  reasoning: string
  timestamp: string
}
```

---

### Permission Gate Result
```typescript
type PermissionLevel = "GREEN" | "YELLOW" | "RED" | "FORBIDDEN"

interface GateResult {
  approved: boolean
  level: PermissionLevel
  executed: boolean
  result: unknown
  reason: string
  timestamp: string
}

// GREEN  (~70%) → auto-execute
// YELLOW (~25%) → execute + async notify
// RED    (~5%)  → council vote → HumanLayer approval (30s timeout → reject)
// FORBIDDEN     → instant block, never executed
```

---

### Council Session
```typescript
interface CouncilSession {
  id: string
  timestamp: string
  question: string
  stage: "deliberation" | "ranking" | "synthesis"
  member_answers: Record<string, string>  // model → answer
  votes: Array<{model: string; vote: "for"|"against"; rationale: string}>
  final_verdict: string
  recommendation: "proceed" | "defer" | "reject"
  confidence: number
  stakes: "low" | "high" | "critical"
  requester_hp: number
}
```

---

### World State (from `/status`)
```typescript
interface WorldState {
  timestamp: string
  time_of_day: "morning"|"afternoon"|"evening"|"night"
  day_of_week: string
  owner: "Arghyadeep Deb"
  version: string
  active_model: string

  recent_episodes: string[]
  memory_stats: {episodic_count: number; semantic_count: number; policy_count: number}
  goal_summary: string

  health: {energy_level: number; fatigue_score: number; sleep_debt_hours: number; stress_level: number}
  presence: "away"|"focused"|"idle"|"unknown"
  screen_summary: string

  calendar: Array<{title: string; due: string; days_until: number; priority: string}>
  finance: {balance_inr?: number; monthly_spend?: number; budget_remaining?: number}
  academic: {attendance_pct?: number; enrolled_courses?: string[]}
  comms: {urgent: number; unread: number; pending: number}
  predictions: {recent_forecasts: number; active_anomalies: number; pending_recommendations: number}
}
```

---

### Memory Records
```typescript
interface EpisodicRecord {
  id: string
  event_type: string
  content: string
  importance: "critical"|"high"|"normal"
  tags: string[]
  timestamp: string
  source: string  // "system" | "agent:CodeReviewer"
}

interface ReasoningChain {
  id: string
  situation: string
  steps: string[]
  action_taken: string
  outcome: string
  reward: number     // 0-1. >0.7 = promoted to training data
  is_training_data: boolean
  timestamp: string
}
```

---

## 11. Districts Reference (33 total)

| # | District | Description |
|---|---|---|
| 01 | governance | LLM Council orchestration, 3-stage deliberative voting |
| 02 | security | ThreatScout, MalwareHunter, NodeGuard — threat monitoring |
| 03 | coding | GitBot, CodeReviewer, BugHunter, ArchitectBot |
| 04 | time_calendar | KIIT Playwright scraper, deadline manager, time blocker |
| 05 | communications | 30+ platform adapters: Telegram, WhatsApp, Discord, Slack, Gmail |
| 06 | memory_curator | LightRAG indexing, Obsidian sync, pattern finding |
| 07 | research | Web search, ArXiv, Reddit miner, news aggregator |
| 08 | intelligence | Pattern detective, news trends, anomaly detection |
| 09 | skills | Skill mapper, gap analyst, mastery tracker |
| 10 | languages | Hindi/Bengali/Assamese/English/Japanese coaches |
| 11 | interview_prep | MockInterviewer, report generator (50-100 page PDF), company researcher |
| 12 | learning | Video ingestor (any URL), concept extractor, course tracker |
| 13 | finance | UPI SMS parser, expense tracker, budget analyst, tax calendar |
| 14 | health | Sleep tracker, fatigue monitor (camera EAR), exercise logger |
| 15 | reflection | 2AM daily reviewer, Obsidian journal writer, growth analyst |
| 16 | startups | HN/Reddit/G2 nightly scanner, idea validator, competitor spy |
| 17 | investment | NSE/BSE stock analyst, fundamentals bot — ANALYSIS ONLY, never trades |
| 18 | content | ScriptGen, SadTalker video, FFmpeg CUDA, YouTube + Instagram upload |
| 19 | agency | ContentStrategist, ClientManager, PerformanceTracker |
| 20 | karpathy_lab | 30min/day ML tracker, OpenMythos training pipeline |
| 21 | projects | ProjectPlanner, DeadlineWatcher (T-7/3/1/0 alerts) |
| 22 | relationships | ContactManager, CommunicationAnalyst |
| 23 | privacy | DataFlowAuditor — cloud vs local enforcement |
| 24 | pattern_detective | BehaviorAnalyst, HabitFinder |
| 25 | news_trends | AINewsBot, MarketTrendsBot, OpportunitySpotter |
| 26 | calls | CallScreener, TranscriptionBot, VoiceResponder |
| 27 | ops | SREMonitor, DevOpsAutomator, IncidentCommander |
| 28 | data_analytics | AnalyticsReporter, PerformanceBenchmarker, DataEngineer |
| 29 | personal_growth | BehavioralNudgeEngine, ZKSteward, FeedbackSynthesizer |
| 30 | documentation | TechnicalWriter, DocGenerator |
| 31 | qa | RealityChecker, EvidenceCollector, APITester, AccessibilityAuditor |
| 32 | chief_of_staff | Morning/evening brief, noise filter, district escalation |
| 33 | marketing | SEOSpecialist, GrowthHacker, SocialMediaStrategist |

---

## 12. UI Screens & Layout

### Voice FSM (Orb State Machine)
```
boot (3.6s scan-in) → idle
idle → [wake word "Hey VECTOR" | open palm gesture | click/Enter] → listening
listening → [speech ends] → processing
processing → [TTS starts] → speaking
speaking → [TTS ends] → idle
idle (60s inactivity) → locked

locked → [wake word | open palm | click] → idle
[security threat] → fortress_mode (opaque black, palm unlock only)
```

---

### Screen Layout

#### Locked Screen
- Black grid background
- Centered VectorOrb (breathing cyan glow)
- HH:MM clock (large, centered top)
- Date and day
- Hint: "SAY 'HEY VECTOR' · WAVE TO WAKE · CLICK / ENTER"

#### Idle / Main Dashboard
```
┌──────────────────────────────────────────────────────┐
│  [ STOCK TICKER MARQUEE — live prices, red▼/green▲ ] │  top bar
├──────────────────────────────────────────────────────┤
│                                                      │
│        [JarvisFrame — cyan border glow 0.18]         │
│                                                      │
│   ◇           ┌─────────────┐           ◇            │  diamond hotspots N/S/E/W
│               │  VectorOrb  │                        │
│   ◇           │   (state)   │           ◇            │
│               └─────────────┘                        │
│                                                      │
│  [Panels arranged in 3 concentric rings around orb]  │
│                                                      │
├──────────────────────────────────────────────────────┤
│  [ NEWS TICKER MARQUEE — BREAKING badge, 120s ]      │  bottom bar
└──────────────────────────────────────────────────────┘
        [corner glyphs — dim cyan decorative]
```

**Glow rule:** Frame glows on INPUT (listening). Orb glows on OUTPUT (speaking). Never both.

---

### Panel Rings

**Ring 1** (8 panels, innermost):
Telemetry · System Metrics · Events · Compass · Model Switcher · Core Status · Daily Info · VectorCode IDE

**Ring 2** (10 panels):
Health · Training Data · Goals · Security · Districts (agent HP cards) · Council · Tasks · Memory Search · Loop Status · Scheduler

**Ring 3** (10 panels, outermost):
Inference · Email · Channels · Providers · Tools Registry · Network · Audit Log · Metering · Video · SEO Data

Panels are draggable widgets on an **InfiniteCanvas**. Voice: "show me goals" → scroll to goals panel.

---

### Key Panel Designs

#### Districts Panel
- Grid of agent cards
- Each card: agent name, district badge, HP bar (0-1000), generation number, last active
- HP color: green >700 · yellow 400-700 · red <400 · grey = dead (ghost)
- Click → expand to agent history + decision log

#### Security Panel
- Threat level badge: LOW (green) / MEDIUM (yellow) / HIGH (orange) / CRITICAL (red)
- Pending approvals count (badge on panel icon)
- Approval queue: action_type, params, proposed_by, expires countdown
- [APPROVE] [DENY] buttons per pending item
- RED-tier approval → modal overlay (30s countdown timer visible)

#### Goals Panel
- Three sections: LONG / MID / SHORT horizon
- Each goal: title, progress bar, priority, tags
- Click goal → inline edit form
- "Add goal" button → mini form

#### Council Panel
- Session list (most recent first)
- Each: question snippet, stakes badge, recommendation badge, confidence %, timestamp
- Expand: member answers, vote breakdown, chairman verdict

#### Memory Panel
- Search input (hybrid FTS5 + semantic)
- Results: importance badge + event_type chip + content + timestamp
- Filter by: event_type, importance, tags

#### Metering Panel
- Tokens today (progress bar vs daily budget)
- Cost in INR today
- Breakdown by model (bar chart)
- Budget remaining

---

## 13. Brand & Design Language

### Personality
> **"Sharp, efficient, calm, precise, slightly dry."**  
> Addresses Arghyadeep as "sir" occasionally — not every sentence.  
> Replies: 1-2 sentences maximum unless detail required.  
> Never says "I cannot" — finds the nearest useful action.

### Visual Identity
| Token | Value |
|---|---|
| Primary glow | `#00CFFF` (cyan) |
| Background | `#000000` / `#0a0a0a` |
| Surface | `#0d1117` / `#111827` |
| Border idle | `rgba(0, 207, 255, 0.18)` |
| Border listening | `rgba(0, 207, 255, 0.65)` |
| Warning | `#F59E0B` |
| Danger | `#EF4444` |
| Success | `#10B981` |
| Text primary | `#E2E8F0` |
| Text muted | `rgba(226, 232, 240, 0.5)` |
| Font | JetBrains Mono / Space Mono |

### Animation Rules
- Orb idle: breathing pulse (scale 1.0 → 1.05 → 1.0, 3s ease-in-out)
- Orb listening: rapid pulse 0.8s
- Orb processing: inner rings spin
- Orb speaking: warm glow
- Boot: black → cyan borders contract → scan line → orb fade in (3.6s)
- Panel open: slide + fade 200ms ease-out
- HP change: bar animates 400ms, flash green/red on direction
- Every animation communicates system state — no purely decorative motion

### Tone
- UI copy: terse, technical
- Labels: "EPISODIC MEMORY" not "Your Memory" · "PERMISSION GATE" not "Ask for Access"
- Timestamps: relative in cards, absolute in detail views
- Numbers: INR for costs · % for progress · integer for HP

---

## 14. Key User Actions

| Action | Trigger | API |
|---|---|---|
| Voice command | Wake word → speak | WS `/ws/voice/stream` |
| Approve RED action | [APPROVE] button | `POST /security/confirm/{action_type}` + CSRF |
| Deny RED action | [DENY] button | same + deny flag |
| Convene council | Button in council panel | `POST /council` |
| Add goal | + in goals panel | `POST /brain/goals/add` |
| Search memory | Search input | `GET /memory/recent` + filter |
| Wake from locked | "Hey VECTOR" / open palm / click | WS `{action:"wake"}` |
| View agent history | Click agent card | `POST /city/agents/history` |
| PC screenshot | Button in control panel | `GET /control/pc/screenshot` |
| Research | Search input | `GET /research/search?query=...` |

---

## 15. Polling Intervals

| Endpoint | Interval | Consumer |
|---|---|---|
| `/status` | 5s | Main state store |
| `/security/status` | 10s | Security panel badge |
| `/agents` | 30s | Districts panel HP bars |
| `/memory/recent` | 30s | Events panel |
| `/scheduler/jobs` | 30s | Scheduler panel |
| `/inference/stats` | 30s | Inference panel |
| `/finance/cost-tracker` | 60s | Metering panel |
| `/brain/goals` | 60s | Goals panel |
| `/memory/council/history` | 60s | Council panel |
| Stock ticker | 30s | Top marquee |
| News ticker | 120s | Bottom marquee |

---

## 16. Resilience / Fallback Rules

| Service down | Frontend behavior |
|---|---|
| Ollama | "Model offline" badge; disable voice + command input |
| Shadowbroker | Map renders, no live layers, IP geolocation only |
| Camera | Placeholder frame, no YOLO |
| MediaPipe | Gesture cursor hidden; voice + click still work |
| Finance APIs | StockTicker shows cached quotes |
| News RSS | NewsTicker shows last 6 cached headlines |
| Kokoro TTS | Voice output works via pyttsx3 fallback |
| Episodic DB | Memory panel: "Memory unavailable — circuit breaker open" |

---

## 17. Multi-Platform Notes

| Platform | UI |
|---|---|
| Legion Pro 5 (primary) | Full desktop dashboard — all panels, voice, gesture, camera |
| Old Android Termux | Voice-only; no visual dashboard |
| Daily phone | Notification cards only — RED approvals, KIIT alerts, nudges |

**Desktop-first.** Mobile is notification-only, not a scaled-down dashboard.

---

## 18. Frontend Tech Stack

| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite |
| State | Zustand |
| Styling | Tailwind CSS + CSS variables |
| Canvas | InfiniteCanvas (custom) |
| 3D | Babylon.js or Three.js |
| Maps | Leaflet (dark tile) |
| Hand tracking | MediaPipe Hands |
| Charts | Recharts or D3 |
| WebSocket | Native browser WebSocket |
| HTTP | Fetch API or Axios |
| Icons | Lucide React |

---

## 19. Quick-Start Integration Checklist

```
1. On app load:
   □ GET /csrf-token → store in memory
   □ GET /status → populate WorldState
   □ Connect WebSocket /ws
   □ Connect WebSocket /ws/state
   □ Connect WebSocket /gesture/ws (if MediaPipe loaded)

2. Auth:
   □ Authorization: Bearer <key> on all fetch calls
   □ X-CSRF-Token on every POST/PUT/DELETE/PATCH

3. Voice:
   □ Wake detected → open /ws/voice/stream
   □ Stream binary audio chunks
   □ Send {"type":"end"} on silence
   □ Receive: transcript → response → audio → done

4. Real-time:
   □ /ws: orb_state → update orb animation
   □ /ws/state: AGENT_HP_CHANGED → update districts panel
   □ /ws/state: DECISION_MADE → flash decision trace in HUD
   □ Poll /security/status 10s → update approval badge

5. RED approval flow:
   □ pending_approvals array from /security/status
   □ Badge on security panel
   □ Click → modal with 30s countdown
   □ POST /security/confirm/{action_type} + action_id + X-CSRF-Token
```
