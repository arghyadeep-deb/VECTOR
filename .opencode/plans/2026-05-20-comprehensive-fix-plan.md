# Comprehensive VECTOR Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 26 known bugs across governor, frontend, voice, memory, permissions/loop, and low-severity issues, then clean up working tree and commit new modules.

**Architecture:** Two-phase approach — Phase 1 applies targeted fixes to production code files; Phase 2 commits the ~650 dirty/untracked files from today's restructuring.

**Tech Stack:** React/TypeScript (frontend), Python/FastAPI (backend), SQLite (memory), Zustand (state)

---

## Phase 1 — Bug Fixes

### Group A: Governor Routing Bugs (CRITICAL)

#### Task A1: Deduplicate DISTRICT_TASK_MAP keys

**Files:**
- Modify: `core/city/governor.py`

**Context:** 15 keys appear 2+ times in the 700+ entry dict. Python preserves insertion order, first-match wins. 13 of the 15 are routing bugs where later (correct) districts are unreachable.

- [ ] **Step 1: Identify the 15 duplicate keys and their intended districts**

The 13 buggy duplicates:
| Key | Currently routes to | Should route to |
|-----|-------------------|-----------------|
| `market_research` | investment | marketing + research |
| `news` | research | research + news_trends |
| `frontend` | engineering | engineering + coding |
| `devops` | engineering | engineering + ops |
| `ab_test` | marketing | marketing + projects |
| `competitive_analysis` | marketing | marketing + strategy |
| `pipeline` | sales | sales + agency |
| `proposal` | sales | sales + agency |
| `executive_brief` | support | support + chief_of_staff |
| `accessibility` | testing | testing + qa |
| `reality_check` | testing | testing + qa |
| `executive_brief` | support | support + chief_of_staff |

- [ ] **Step 2: Fix routing — make `DISTRICT_TASK_MAP` use multi-value routing**

Change `route_task()` to find ALL matching districts, not just the first.

```python
def route_task(self, task_type: str) -> list[str]:
    normalized = task_type.lower().strip()
    if normalized in self.district_task_map:
        return self.district_task_map[normalized]
    for keyword, districts in self.district_task_map.items():
        if keyword in normalized:
            return districts
    return self._llm_classify(normalized)
```

Change `DISTRICT_TASK_MAP` values from single strings to lists where needed. Remove the 13 second-occurrence entries entirely.

- [ ] **Step 3: Update `dispatch()` to iterate districts**

```python
districts = self.route_task(task.get("type", ""))
if not districts:
    return {"status": "error", "message": "Unknown task type"}
if isinstance(districts, str):
    districts = [districts]

for district in districts:
    agent = self.agent_registry.get_best_for_district(district)
    if agent:
        break

if not agent:
    return {"status": "no_agents", "district": districts[0]}
```

- [ ] **Step 4: Commit**

```bash
git add core/city/governor.py
git commit -m "fix: deduplicate DISTRICT_TASK_MAP — 13 routing bugs fixed, multi-value routing"
```

#### Task A2: Fill empty shell districts or remove from map

**Files:**
- Create: `districts/[district]/agent.py` for each of 13 empty districts

**Context:** 13 districts (`academic/`, `engineering/`, `game_development/`, `paid_media/`, `product/`, `project_management/`, `sales/`, `spatial_computing/`, `specialized/`, `strategy/`, `support/`, `testing/`, `core/`) have only `__init__.py`. Tasks routed there return `no_agents`.

- [ ] **Step 1: Create stub agents for each empty district**

```python
"""[District name] district — handles [task types]."""
import logging
logger = logging.getLogger(__name__)

async def handle_task(task_type: str, params: dict) -> dict:
    logger.info(f"[district] received: {task_type}")
    return {
        "status": "stub",
        "district": "[district-name]",
        "task_type": task_type,
        "message": "Agent not yet implemented. Task logged.",
    }
```

- [ ] **Step 2: Commit**

```bash
git add districts/academic/agent.py districts/core/agent.py districts/engineering/agent.py districts/game_development/agent.py districts/paid_media/agent.py districts/product/agent.py districts/project_management/agent.py districts/sales/agent.py districts/spatial_computing/agent.py districts/specialized/agent.py districts/strategy/agent.py districts/support/agent.py districts/testing/agent.py

git commit -m "fix: add stub agents for 13 empty shell districts — tasks now return meaningful status instead of silent no_agents"
```

---

### Group B: Frontend Bugs (HIGH)

#### Task B1: Fix ReactorGroup pointerEvents blocking drag

**Files:**
- Modify: `core/ui/dashboard/src/components/ReactorGroup.tsx`

- [ ] **Step 1: Remove `pointerEvents: 'none'` from the outer wrapper**

```tsx
<div
  style={{
    position: 'fixed',
    inset: 0,
    zIndex: Z.ARC_REACTOR,
    overflow: 'visible',
  }}
>
```

- [ ] **Step 2: Fix `isDragging` ref being read at render time**

Change from ref to state:
```tsx
const [isDragging, setIsDragging] = useState(false);
// ...
style={{ transition: `transform ${isDragging ? 'none' : '0.3s ease-out'}` }}
```

- [ ] **Step 3: Verify with build**

```bash
cd core/ui/dashboard && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add core/ui/dashboard/src/components/ReactorGroup.tsx
git commit -m "fix: reactor drag broken by pointerEvents:none; fix isDragging render-time ref read"
```

#### Task B2: Fix GestureOverlay stale closure bug

**Files:**
- Modify: `core/ui/dashboard/src/components/GestureOverlay.tsx`

- [ ] **Step 1: Store handleGesture in a ref**

```tsx
const handleGestureRef = useRef(handleGesture);
handleGestureRef.current = handleGesture;
```

In the WebSocket message handler, call `handleGestureRef.current(data.gesture)` instead of directly calling `handleGesture`.

- [ ] **Step 2: Verify build**

```bash
cd core/ui/dashboard && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add core/ui/dashboard/src/components/GestureOverlay.tsx
git commit -m "fix: gesture overlay stale closure — handleGesture now reads latest state via ref"
```

#### Task B3: Clean up 4 orphaned components

**Files:**
- Delete: `core/ui/dashboard/src/components/ArcReactor.tsx`
- Delete: `core/ui/dashboard/src/components/CentralHologram.tsx`
- Delete: `core/ui/dashboard/src/components/ClaimsBoard.tsx`
- Delete: `core/ui/dashboard/src/components/CoherenceMonitor.tsx`

- [ ] **Step 1: Check imports**

```bash
rg "ArcReactor|CentralHologram|ClaimsBoard|CoherenceMonitor" --type tsx --type ts
```

- [ ] **Step 2: Delete orphaned components**

```bash
git rm core/ui/dashboard/src/components/ArcReactor.tsx core/ui/dashboard/src/components/CentralHologram.tsx core/ui/dashboard/src/components/ClaimsBoard.tsx core/ui/dashboard/src/components/CoherenceMonitor.tsx
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove 4 orphaned frontend components (ArcReactor, CentralHologram, ClaimsBoard, CoherenceMonitor)"
```

#### Task B4: Fix double-mounted 6 HUD panels

**Files:**
- Modify: `core/ui/dashboard/src/App.tsx`

- [ ] **Step 1: Remove the 6 HUD panels from InfiniteCanvas panels array**

Remove `{ id: 'compass', ... }`, `{ id: 'telemetry', ... }`, `{ id: 'systemMetrics', ... }`, `{ id: 'coreStatus', ... }`, `{ id: 'dailyInfo', ... }`, `{ id: 'health', ... }` from the `panels` array passed to `<InfiniteCanvas panels={panels}>`.

- [ ] **Step 2: Verify build**

```bash
cd core/ui/dashboard && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add core/ui/dashboard/src/App.tsx
git commit -m "fix: remove 6 HUD panels from InfiniteCanvas to stop double mounting"
```

#### Task B5: Eliminate PANEL_POSITIONS duplication

**Files:**
- Modify: `core/ui/dashboard/src/App.tsx`

- [ ] **Step 1: Import PANEL_POSITIONS from vectorStore in App.tsx**

```tsx
import { PANEL_POSITIONS } from '../store/vectorStore';

const PANEL_COMPONENTS = {
  telemetry: TelemetryPanel,
  systemMetrics: SystemMetricsPanel,
  events: EventsPanel,
  compass: CompassPanel,
  modelSwitcher: ModelSwitcherPanel,
  coreStatus: CoreStatusPanel,
  dailyInfo: DailyInfoPanel,
  vectorCode: VectorCodePanel,
  // ... all 64 panels
} as const;

const panels: PanelPlacement[] = Object.entries(PANEL_POSITIONS).map(([id, pos]) => {
  const Component = PANEL_COMPONENTS[id as keyof typeof PANEL_COMPONENTS];
  if (!Component) return null;
  return { id, worldX: pos.x, worldY: pos.y, component: Component };
}).filter(Boolean) as PanelPlacement[];
```

- [ ] **Step 2: Verify build**

```bash
cd core/ui/dashboard && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add core/ui/dashboard/src/App.tsx
git commit -m "refactor: derive panel placements from vectorStore PANEL_POSITIONS — single source of truth"
```

#### Task B6: Fix InfiniteCanvas side-effect in render body

**Files:**
- Modify: `core/ui/dashboard/src/components/InfiniteCanvas.tsx`

- [ ] **Step 1: Move cameraRef assignment into useEffect**

```tsx
useEffect(() => {
  if (cameraRef) cameraRef.current = camera;
}, [camera]);
```

- [ ] **Step 2: Commit**

```bash
git add core/ui/dashboard/src/components/InfiniteCanvas.tsx
git commit -m "fix: move cameraRef assignment from render body to useEffect"
```

#### Task B7: Fix BootSequence RAF double-fire

**Files:**
- Modify: `core/ui/dashboard/src/components/BootSequence.tsx`

- [ ] **Step 1: Add phase ref for RAF guard**

```tsx
const phaseRef = useRef(phase);
phaseRef.current = phase;

function animateScan(timestamp: number) {
  if (phaseRef.current !== 'scanline') {
    cancelAnimationFrame(rafIdRef.current!);
    return;
  }
  // ...existing animation logic...
}
```

- [ ] **Step 2: Commit**

```bash
git add core/ui/dashboard/src/components/BootSequence.tsx
git commit -m "fix: prevent RAF double-fire during boot phase transition"
```

---

### Group C: Voice Pipeline Bugs (HIGH)

#### Task C1: Fix cross-session conversation history contamination

**Files:**
- Modify: `core/voice/ambient_listener.py`
- Modify: `core/api/routers/voice.py`

- [ ] **Step 1: Add optional history param to `_classify_intent`**

```python
async def _classify_intent(
    self,
    text: str,
    hydration: str,
    conversation_history: list[dict] | None = None
) -> dict:
    history = conversation_history if conversation_history is not None else self._conversation_history
    # ... use `history` instead of `self._conversation_history` throughout ...
```

- [ ] **Step 2: Update voice.py to pass empty history**

```python
result = await listener._classify_intent(text, hydration, conversation_history=[])
```

- [ ] **Step 3: Commit**

```bash
git add core/voice/ambient_listener.py core/api/routers/voice.py
git commit -m "fix: prevent cross-session conversation history contamination in voice API"
```

#### Task C2: Fix voice_ws hardcoded model + missing security

**Files:**
- Modify: `core/api/routers/voice_ws.py`

- [ ] **Step 1: Add personality, context, model router, and permission gateway**

```python
context = context_engine.session_hydration_prompt()
system_prompt = VECTOR_PERSONALITY + "\n" + context

response = ollama.chat(
    model=CONFIG["models"].get("ambient", "vector-ambient"),
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
)

gateway = PermissionGateway()
action = Action(action_type="voice_chat", params={"input": text})
result = await gateway.execute(action)
if result.get("status") == "blocked":
    await websocket.send_json({"type": "error", "message": "Blocked by security"})
    return
```

- [ ] **Step 2: Commit**

```bash
git add core/api/routers/voice_ws.py
git commit -m "fix: voice_ws now uses model router, personality prompt, context hydration, and permission gateway"
```

#### Task C3: Fix STT delegation crash (FasterWhisper/Deepgram)

**Files:**
- Modify: `core/voice/stt.py`

- [ ] **Step 1: Extract shared recording logic to standalone function**

```python
async def record_until_silence(duration_sec: float = 5.0) -> np.ndarray:
    """Standalone VAD recording — shared by all STT engines."""
    import sounddevice as sd
    frames = []
    silent_chunks = 0
    silence_threshold = 0.01
    max_silent_chunks = 6
    chunk_duration = 0.1
    max_chunks = int(duration_sec / chunk_duration)

    for _ in range(max_chunks):
        chunk = sd.rec(int(16000 * chunk_duration), samplerate=16000, channels=1, dtype='float32')
        sd.wait()
        rms = np.sqrt(np.mean(chunk**2))
        frames.append(chunk)
        if rms < silence_threshold:
            silent_chunks += 1
        else:
            silent_chunks = 0
        if silent_chunks >= max_silent_chunks:
            break

    return np.concatenate(frames) if frames else np.array([])
```

Each STT class calls this function and then its own `transcribe()`.

- [ ] **Step 2: Commit**

```bash
git add core/voice/stt.py
git commit -m "fix: prevent AttributeError in FasterWhisperSTT/DeepgramSTT record_and_transcribe delegation"
```

#### Task C4: Fix openWakeWord always returning "conversation" mode

**Files:**
- Modify: `core/voice/wake_word.py`

- [ ] **Step 1: Add post-wake phrase detection**

```python
async def _listen_openwakeword(self):
    # ... existing detection ...
    prediction = ow_model.predict(frame)
    if prediction.get("hey_vector", 0) > self.threshold:
        # After wake, listen for mode phrase
        mode_audio = await self._record_chunk(2.0)
        mode_text = await self._transcribe(mode_audio)
        return self._match_phrase_mode(mode_text.lower())
    return None
```

- [ ] **Step 2: Commit**

```bash
git add core/voice/wake_word.py
git commit -m "fix: openWakeWord path now detects deep_think and private modes via post-wake transcription"
```

---

### Group D: Memory System Bugs (HIGH)

#### Task D1: Fix SemanticMemory — add persistence and fix docstring

**Files:**
- Modify: `core/memory/semantic.py`

- [ ] **Step 1: Rewrite with SQLite persistence**

```python
class SemanticMemory:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = Path.home() / ".vector" / "semantic_memory.db"
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS concepts (
                name TEXT PRIMARY KEY,
                concept_type TEXT,
                properties TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_relations (
                subject TEXT, relation TEXT, object TEXT,
                UNIQUE(subject, relation, object)
            )
        """)
```

- [ ] **Step 2: Fix the docstring — remove references to Ollama, ChromaDB, and EpisodicMemory**

- [ ] **Step 3: Commit**

```bash
git add core/memory/semantic.py
git commit -m "fix: add SQLite persistence to SemanticMemory, fix false docstring about Ollama/ChromaDB"
```

#### Task D2: Fix MultiDBManager — implement D1, fix cloud short-circuit, sync all tables

**Files:**
- Modify: `core/memory/multi_db_manager.py`

- [ ] **Step 1: Implement `_write_d1()`**

```python
async def _write_d1(self, table: str, data: dict) -> bool:
    # Cloudflare D1 write via Workers API
    try:
        account_id = CONFIG.get("cloudflare", {}).get("account_id")
        api_token = CONFIG.get("cloudflare", {}).get("api_token")
        database_id = CONFIG.get("cloudflare", {}).get("d1_database_id")
        if not all([account_id, api_token, database_id]):
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query",
                headers={"Authorization": f"Bearer {api_token}"},
                json={"sql": f"INSERT OR REPLACE INTO {table} ..."},
            )
        return resp.status_code == 200
    except Exception:
        return False
```

- [ ] **Step 2: Fix `write_cloud()` to try all backends**

Remove early return after first success. Log failures and try next backend.

- [ ] **Step 3: Extend pull methods to sync all 6 allowed tables**

Loop over `_ALLOWED_TABLES` instead of hardcoding `episodic_memory`.

- [ ] **Step 4: Commit**

```bash
git add core/memory/multi_db_manager.py
git commit -m "fix: implement D1 write, fix cloud short-circuit to try all backends, sync all memory tables"
```

---

### Group E: Permissions & Loop Bugs (HIGH)

#### Task E1: Fix capability check fails open

**Files:**
- Modify: `core/loop/permission_gateway.py`

- [ ] **Step 1: Change fail-open to fail-closed**

```python
return False, f"capability check error ({e})"
# instead of:
# return True, f"capability check skipped ({e})"
```

- [ ] **Step 2: Commit**

```bash
git add core/loop/permission_gateway.py
git commit -m "fix: capability check now fails closed instead of silently allowing all actions"
```

#### Task E2: Connect LoopGuardState to autonomous loop sub-loops

**Files:**
- Modify: `core/loop/autonomous_loop.py`

- [ ] **Step 1: Add loop guard calls to observe and think loops**

```python
guard = self._get_loop_guard()
guard.tick()
if guard.is_terminated:
    logger.warning("Loop terminated by guard — resetting")
    guard.reset()
```

- [ ] **Step 2: Commit**

```bash
git add core/loop/autonomous_loop.py
git commit -m "fix: connect LoopGuard to all sub-loops — phantom detection, iteration limits, stall detection now active"
```

#### Task E3: Fix `_capture_loop_error` dir() bug

**Files:**
- Modify: `core/loop/autonomous_loop.py`

- [ ] **Step 1: Fix dir() → locals()**

```python
distr = str(getattr(winner, 'district', '')) if winner is not None else ''
```

- [ ] **Step 2: Commit**

```bash
git add core/loop/autonomous_loop.py
git commit -m "fix: _capture_loop_error dir() → locals() so winner district appears in crash reports"
```

#### Task E4: Remove duplicate ghost persistence code

**Files:**
- Modify: `core/city/evolution_engine.py`

- [ ] **Step 1: Replace duplicate with delegation**

```python
async def _persist_agent_history(self, ghost: dict) -> None:
    registry = get_registry()
    registry._persist_ghost(ghost)
```

- [ ] **Step 2: Commit**

```bash
git add core/city/evolution_engine.py
git commit -m "refactor: delegate ghost persistence to AgentRegistry — remove duplicate code"
```

---

### Group F: Low-Severity Bugs

#### Task F1: Fix VoiceConfig missing fields

**Files:**
- Modify: `core/config.py`

- [ ] **Step 1: Add missing fields**

```python
class VoiceConfig(BaseModel):
    whisper_model: str = "large-v3"
    stt_engine: str = "whisper"
    device: str = "cuda"
    compute_type: str = "float16"
    kokoro_model_dir: str = str(Path(__file__).parent.parent / "models" / "kokoro")
    kokoro_speed: float = Field(0.85, ge=0.1, le=3.0)
    wake_threshold: float = Field(0.5, ge=0.0, le=1.0)
    record_duration_sec: float = Field(5.0, ge=1.0, le=120.0)
    sample_rate: int = Field(16000, ge=8000, le=96000)
    wake_phrase: str = "hey_vector"
```

- [ ] **Step 2: Commit**

```bash
git add core/config.py
git commit -m "fix: add missing stt_engine, device, compute_type fields to VoiceConfig"
```

#### Task F2: Remove `_trim_trailing_silence` dead code

**Files:**
- Modify: `core/voice/stt.py`

- [ ] **Step 1: Delete the dead function**

```bash
git add core/voice/stt.py
git commit -m "chore: remove dead _trim_trailing_silence function from stt.py"
```

#### Task F3: Fix gTTS temp file leak

**Files:**
- Modify: `core/voice/tts.py`

- [ ] **Step 1: Wrap temp file in try/finally**

```python
tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
try:
    tts.save(tmp.name)
    playsound(tmp.name)
finally:
    os.unlink(tmp.name)
```

- [ ] **Step 2: Commit**

```bash
git add core/voice/tts.py
git commit -m "fix: ensure gTTS temp file is cleaned up on play failure"
```

#### Task F4: Fix ServiceLocator vs app.state duplication

**Files:**
- Modify: `core/api/dependencies.py`

- [ ] **Step 1: Check app.state first**

```python
def get_context_engine(request: Request = None):
    if request and hasattr(request.app.state, 'context_engine'):
        return request.app.state.context_engine
    return _lazy_get_or_create(request, "context_engine", ContextEngine)
```

- [ ] **Step 2: Commit**

```bash
git add core/api/dependencies.py
git commit -m "fix: ServiceLocator checks app.state first to avoid duplicate singletons"
```

#### Task F5: Log MemoryTree silent swallow

**Files:**
- Modify: `core/memory/episodic.py`

- [ ] **Step 1: Replace bare except with logging**

```python
try:
    from core.engine.memory_tree.tree_builder import MemoryTree
except Exception as e:
    logger.debug(f"MemoryTree ingestion skipped: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add core/memory/episodic.py
git commit -m "fix: log MemoryTree ingestion failures instead of silently swallowing"
```

---

## Phase 2 — Commit Working Tree

**Context:** ~200 files staged for deletion, ~50 modified, ~400+ untracked. Massive restructuring from today.

#### Task G1: Commit staged deletions

- [ ] **Step 1: Review deletions**

```bash
git diff --cached --diff-filter=D --name-only
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove old agents/districts, core/{openhuman,mirofish,vibe_trading,fincept}, dashboard/src-tauri"
```

#### Task G2: Commit staged modifications

- [ ] **Step 1: Review modifications**

```bash
git diff --cached --name-only
```

- [ ] **Step 2: Commit in logical groups**

```bash
git commit -m "chore: update API routers (a2a, ads, agents, investment, research, simulation, tasks, voice)"
git commit -m "chore: update city engine, inference, memory, and sandbox"
git commit -m "chore: update dashboard UI components"
git commit -m "chore: update docs, scripts, tests, vectorcode"
```

#### Task G3: Stage and commit untracked files

- [ ] **Step 1: Review untracked files**

```bash
git ls-files --others --exclude-standard
```

- [ ] **Step 2: Stage and commit in groups**

```bash
git add districts/ && git commit -m "feat: add 48-district city structure"
git add core/api/routers/ && git commit -m "feat: add 40+ new API routers"
git add core/engine/ core/coding_assistant/ core/trading/ core/scraper/ core/brain_hooks/ && git commit -m "feat: add core engine, coding assistant, trading graph, scraper, brain hooks"
```

#### Task G4: Final verification

- [ ] **Step 1: Confirm clean working tree**

```bash
git status --short
```
Expected: empty output.

- [ ] **Step 2: Push if remote configured**

```bash
git push
```

---

## Task Summary

| Task | Area | Severity | Files Changed | Est. Time |
|------|------|----------|--------------|-----------|
| A1 | Governor routing | CRITICAL | 1 | 10 min |
| A2 | Empty shell districts | HIGH | 13 new | 15 min |
| B1 | Reactor drag | HIGH | 1 | 5 min |
| B2 | Gesture closure | HIGH | 1 | 5 min |
| B3 | Orphaned components | MEDIUM | 4 deleted | 5 min |
| B4 | Double HUD panels | MEDIUM | 1 | 5 min |
| B5 | PANEL_POSITIONS dup | MEDIUM | 1 | 10 min |
| B6 | Camera render side-effect | LOW | 1 | 3 min |
| B7 | Boot RAF double-fire | LOW | 1 | 5 min |
| C1 | Voice history contamination | HIGH | 2 | 5 min |
| C2 | voice_ws security | HIGH | 1 | 10 min |
| C3 | STT delegation crash | MEDIUM | 1 | 5 min |
| C4 | Wake word mode | MEDIUM | 1 | 5 min |
| D1 | SemanticMemory persistence | HIGH | 1 | 15 min |
| D2 | MultiDB D1/sync | HIGH | 1 | 15 min |
| E1 | Capability fail-open | HIGH | 1 | 3 min |
| E2 | LoopGuard connection | MEDIUM | 1 | 5 min |
| E3 | dir() bug | LOW | 1 | 2 min |
| E4 | Ghost persistence DRY | HIGH | 1 | 3 min |
| F1 | VoiceConfig fields | LOW | 1 | 3 min |
| F2 | Dead code removal | LOW | 1 | 2 min |
| F3 | gTTS temp leak | LOW | 1 | 3 min |
| F4 | ServiceLocator dup | MEDIUM | 1 | 5 min |
| F5 | MemoryTree logging | LOW | 1 | 3 min |
| G1-G4 | Commit working tree | — | ~650 | 20 min |
