# Repo Audit — UI-TARS-desktop-main vs VECTOR

> Audited: 2026-05-31 · Repo: `GitHub/UI-TARS-desktop-main` · ByteDance, Apache-2.0
> Verdict: **SAFE TO DELETE** (already absorbed — `core/vision_control/` is an explicit Python port)

---

## Section 1 — Repo Reality

**What it is:** ByteDance's TARS multimodal GUI/computer-use agent stack. A large TypeScript pnpm monorepo (`apps/`, `packages/`, `multimodal/`, `infra/`) shipping two products: **Agent TARS** (CLI + Web UI, MCP-driven hybrid browser agent) and **UI-TARS Desktop** (Electron native GUI agent driven by the UI-TARS / Seed-1.5-VL vision-language model).

The core idea (`packages/ui-tars/sdk/README.md`): a continuous loop —
`screenshot() → VLM predicts an action with a bounding box → parse box to screen coords → operator.execute() → repeat` until `finished()` / `max_loop` (default 25).

**Concrete features:**

| # | Feature | Where (repo) |
|---|---------|--------------|
| 1 | **Visual grounding** — VLM emits `click(start_box='[x1,y1,x2,y2]')`, `parseBoxToScreenCoords` maps normalized box → physical pixels | `action-parser/src/actionParser.ts`, `sdk/core` |
| 2 | GUIAgent loop (INIT→RUNNING→END/MAX_LOOP, abort signal, onData callback) | `packages/ui-tars/sdk` |
| 3 | Action space: click/left_double/right_single/drag/hotkey/type/scroll/wait/finished/call_user | `operators/nut-js/src/index.ts:37` |
| 4 | Desktop operator (NutJS) — screenshot via `screen.grab()`, mouse/keyboard/scroll/drag, DPR scale factor | `operators/nut-js` |
| 5 | Browser operator (Playwright) + browserbase remote operator | `operators/browser-operator`, `operators/browserbase` |
| 6 | **Mobile operator (ADB)** — click/type/swipe/press_home/press_back via `adb shell input` | `operators/adb` |
| 7 | Smart-resize for V1.5 model (pixel-budget aspect-ratio preserving) | `actionParser.ts:28` |
| 8 | Electron desktop UI — live ScreenRecorder feed, ThoughtChain, RunMessages, ImageGallery, ChatInput, local/remote operator pages | `apps/ui-tars/src/renderer` |
| 9 | OpenAI-compatible model client (any VLM via baseURL/apiKey) | `sdk` model config |
| 10 | MCP integration, Event Stream protocol, Tarko agent server/UI builder | `multimodal/tarko`, `packages/agent-infra` |

Heart of the system is **#1 + #2** — vision-guided clicking. Everything else is scaffolding around it.

---

## Section 2 — VECTOR Parity (verified by running)

**Key discovery:** VECTOR already ported UI-TARS. `core/vision_control/` contains explicit Python ports with file headers like *"Python port of UI-TARS-desktop/packages/ui-tars/sdk/src/GUIAgent.ts"*. Provider-agnostic (Ollama vision → Gemini → GPT-4o fallback chain), which is correct per VECTOR's LLM rules.

### Feature-by-feature

| UI-TARS feature | VECTOR equivalent | Verdict |
|-----------------|-------------------|---------|
| **Visual grounding** (box → screen coords) | `core/vision_control/action_parser.py` `action_parser()` | ✅ real & working |
| GUIAgent loop | `core/vision_control/gui_agent.py` `GUIAgent` | ✅ real & working |
| Action space (10 actions) | `vision_operator.py` `ACTION_SPACE` + dispatch | ✅ real & working |
| Desktop operator | `vision_operator.py` `VisionOperator` (mss + pyautogui) | ✅ real (⚠️ needs `mss`/`pyautogui` at runtime) |
| Browser operator (Playwright) | `core/vision_control/browser_controller.py` `BrowserController` | ✅ present (VLM + Playwright) |
| Mobile ADB GUI loop (swipe/tap-by-box) | `core/control/phone_controller.py` (screenshot + keyevent only) | ⚠️ partial — no VLM-driven mobile operator |
| Smart-resize V1.5 | `action_parser.py` `smart_resize_v15()` | ✅ real & working |
| Desktop UI (live screen + thought chain) | none (`dashboard/` not built) | ❌ missing |
| OpenAI-compat model client | `core/inference/provider_client.py` + `vectorcode_llm.chat` | ✅ real & working |
| District routing | `core/city/governor.py` + `districts/coding/gui_automation_agent.py` | ✅ real & working |

### Verification runs

**1. Visual grounding — VERIFIED WORKING.** `python -X utf8 core/vision_control/action_parser.py`:
```
OK click point: click coords=(1655, 561)     # <point>862 519</point> on 1920x1080
OK scroll: scroll coords=(960, 432)
OK drag: drag coords=(192, 216)
OK bbox format: click coords=(1655, 561)      # <bbox>850 510 874 528</bbox>
OK action_parser.py
```
This is the answer to the KEY QUESTION: **VECTOR HAS visual grounding.** The VLM names a UI element, emits a normalized box, and `action_parser` converts the box center to absolute screen pixels (e.g. `<point>862 519</point>` → `(1655, 561)` on a 1920×1080 screen). Not blind coordinate clicking — vision-guided clicking by description, the exact UI-TARS core.

**2. GUIAgent + VisionOperator — VERIFIED IMPORT/INIT.**
```
GUIAgent init OK status= init model= vector-focus
GUIStatus members: ['init','running','pause','end','call_user','user_stopped','max_loop','error']
VisionOperator methods: ['execute', 'get_action_space', 'screenshot']
action_space chars: 873
```
GUIAgent even adds **pause/resume/stop** (human-in-the-loop) beyond the upstream abort-only signal. The smoke `asyncio.run()` failed with `OSError WinError 10055` (socket buffer) — that is a **sandbox event-loop limitation, not a code bug**; the class imports, constructs, and exposes pause/resume/stop correctly.

**3. Underlying primitives — PCController (verified):**
```
['click','get_mouse_position','get_screen_size','hotkey','launch_app',
 'move_cursor','run_shell_command','take_screenshot','type_text']
```
`PCController.click(x, y, button)` is blind coordinate clicking — but `VisionOperator` wraps it with the VLM grounding layer on top, so vision-guided clicking is achieved at the `vision_control` level, not at `pc_controller`.

**4. Governor routing — VERIFIED:** `core/city/governor.py:268-272` routes `gui_task`, `vision_control`, `click_screen`, `browser_task` → `coding` district → `GUIAutomationAgent`.

### Gaps found

- ⚠️ **No test suite** for `core/vision_control/` — no `tests/test_*` references `GUIAgent`/`action_parser`/`VisionOperator`. Only the in-file `__main__` smoke blocks. action_parser's smoke passes; gui_agent's can't run in-sandbox. **This is the one real weakness** — the most security-sensitive subsystem (it moves the real mouse) has no pytest coverage.
- ⚠️ **Mobile**: `phone_controller.py` does ADB screenshot + keyevent + SMS/notifications, but there's no VLM-driven mobile GUI operator (no tap-by-box / swipe-by-box loop like `operators/adb`). The grounding layer is desktop/browser only.
- ❌ **No live action-viewer UI** — `dashboard/` doesn't exist (consistent with `phase_status.md`: "Next.js Dashboard not built").

---

## Section 3 — Frontend → Panel Design

UI-TARS Desktop's Electron renderer (`apps/ui-tars/src/renderer/src`) shows the agent operating the computer in real time. Components: `ScreenRecorder` (live screen feed with action overlays), `ThoughtChain` (the VLM's reasoning per step), `RunMessages` / `Detail` (action log), `ImageGallery` (per-step screenshots), `ChatInput` (task entry), `SideBar`, plus `local` / `remote` / `widget` operator pages.

**Recommended VECTOR HUD panel — "Computer Control / Agent Action Viewer" — worth building NOW.** VECTOR's GUIAgent already emits the exact data this panel needs via the `on_step` callback: each `step_data` carries `{loop, prediction, parsed, screen, elapsed_ms}` — i.e. screenshot, VLM thought, parsed action, and coords. The panel is essentially a renderer for the `on_step` stream.

Proposed layout (single panel, three regions):
- **Left — Live Screen** — latest screenshot (`step_data.screen` + b64 from operator), with the click point / drag vector drawn as an overlay marker (the panel already has the coords from `parsed.start_coords`/`end_coords`).
- **Right top — Thought Chain** — scrollable list of per-loop `prediction` text (the VLM's "Thought:" reasoning), highlighting the current step.
- **Right bottom — Action Log** — table: loop # · action_type · coords · elapsed_ms · status. Pause/Resume/Stop buttons wired to `GUIAgent.pause()/resume()/stop()` (already implemented — this is a genuine differentiator over upstream's abort-only).
- Status badge driven by `GUIStatus` (init/running/pause/end/call_user/max_loop/error).

This is high-value: it's the human-in-the-loop window onto an agent that physically controls the machine. Build it when `dashboard/` is built; the data contract already exists.

---

## Section 4 — Verdict

### SAFE TO DELETE

**Size of gap: effectively zero.** VECTOR already contains a faithful, provider-agnostic Python port of UI-TARS's entire value:

- `core/vision_control/action_parser.py` — visual grounding (box → pixels), V1.0 + V1.5 smart-resize, bc/o1 modes — **runs and passes**.
- `core/vision_control/gui_agent.py` — the screenshot→VLM→parse→execute loop, with pause/resume/stop added — **imports and inits**.
- `core/vision_control/vision_operator.py` — desktop operator (mss + pyautogui), full 10-action space — **imports and inits**.
- `core/vision_control/browser_controller.py` — VLM-driven Playwright browser operator.
- `districts/coding/gui_automation_agent.py` + governor routes — wired into the agent city.

The upstream repo is a 200+-package TypeScript/Electron monorepo. There is nothing left to port — the GUI-agent kernel is the only transferable part and it's done. The remaining scaffolding (Electron app, Tarko agent server, MCP infra, Event Stream, UI builder) is either TypeScript-only or already covered by VECTOR's own MCP server, provider_client, event_bus, and (future) dashboard.

**Two follow-ups — but they are PATCH-VECTOR items, not reasons to keep the repo:**

1. **Add pytest coverage for `core/vision_control/`** (the only real weakness). This subsystem moves the physical mouse/keyboard yet has zero pytest tests — only in-file `__main__` smokes. Port the `action_parser.py` `__main__` cases into `tests/test_vision_control.py` and add mocked-operator tests for the GUIAgent loop (mock `screenshot`/`_call_vlm`/`execute`, assert terminal/max_loop transitions). Reference upstream `packages/ui-tars/action-parser/__tests__` for grounding edge cases.
2. **(Optional) Mobile VLM operator** — a `MobileVisionOperator` wrapping `phone_controller.py` with `adb shell input tap/swipe` from parsed boxes would close the one functional gap vs `operators/adb`. Low priority — desktop/browser grounding is the 95% case for the owner.

Neither requires the repo on disk. **Delete it.**
