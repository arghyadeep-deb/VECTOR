# VECTOR Frontend/Backend Feature Coverage

Date: 2026-06-04

Scope excludes cloud deployment, phone nodes, and Home Assistant/smart-home features.

## What Is Mounted In The Main API

The main FastAPI app mounts these backend feature groups:

- Core runtime: status, system health, loop, scheduler, providers, tools, network, metering, sandbox, MCP.
- Brain and agency: command, agents, A2A, council, brain goals, hypotheses, epistemic state, reasoning chains, persons, governance, chief, agency.
- Memory and knowledge: memory, knowledge graph/merge/scan, collections, migration.
- Safety and approvals: security, gateway approvals, keys, privacy, audit, queue.
- Voice and communication: voice, voice studio, email, calls, notifications, websocket command/voice.
- Local control and sensing: PC control, camera, location, gesture, sensing. Phone control exists but is excluded from this milestone.
- Coding and engineering: vectorcode, code-intel, coding, QA, documentation, projects, Karpathy experiments.
- Finance and investment: personal finance, market ticker/news, investment analysis, DCF, alpha, backtest request, geopolitics, hedge, portfolio, market status.
- Intelligence: public-signal layers for flights, vessels, satellites, conflicts, fires, outages, CCTV, reports, pins, and Shadowbroker summary/layers/commands.
- Content and growth: content scheduler, ads, SEO, startups, news, research, scraper, design.
- Personal operating system: health, learning, interview prep, languages, patterns, reflection, relationships, skills.
- Media/video currently mounted in the main API: media model catalog and video composition list.

## Side Systems Or Partial Main-API Integrations

- ComfyUI exists as `districts/content/comfyui_adapter.py` and is used by the media stack, but the main API currently exposes only `/media/models`. Rich generation/status endpoints live in `core/video/studio_server.py` under `/api/media/*`, which is a separate Studio server.
- Hyperframes exists through `core/video/vector_composer.py` and falls back when unavailable. The main API only lists `/video/compositions`; render control belongs to the Studio server.
- The deeper backtest swarm server exists under `districts/investment/vector_backtest/api_server.py`. The main API has `/investment/backtest`, but not the whole swarm/session API.
- `frontend/js/city3d.js` implements a city widget, but it was not listed in the terminal command registry.

## Existing Frontend Panels Before This Pass

Existing first-class panels:

- chat, music, map, webcam, telemetry, market, goals, goalplanner, districts, council, security, memory, approvals, finance, contentscheduler, answerengine, voicestudio, codegraph, librechat, openwebui.

Coverage gap:

- Many mounted backend domains had no explicit panel/command at all, so the user could not open them by name even though backend endpoints existed.

## Integration Direction

This pass adds backend feature launch coverage without forcing final UI design:

- Add a feature index panel for backend domains.
- Add generic endpoint/status panels for mounted domains.
- Keep existing bespoke panels where they already exist.
- Label side systems honestly as Studio/sidecar integrations until the main API exposes full control endpoints.

## Implemented Frontend Coverage

- `frontend/js/widgets.js` now contains a `FEATURE_REGISTRY` with 27 feature entries:
  - feature index
  - core systems
  - agents/A2A
  - brain/reasoning
  - knowledge graph
  - code intel
  - VectorCode
  - trading
  - backtest
  - Hedgebot
  - intelligence
  - ShadowBroker
  - media studio
  - ComfyUI
  - Hyperframes
  - content ops
  - design
  - research
  - PC control
  - camera
  - health
  - learning
  - workflow/projects
  - privacy/keys
  - analytics
  - personal OS
  - platform
- Each feature panel is opened on demand through the existing widget system.
- Each backend feature panel now has a bespoke mission-board layout:
  - domain mode header
  - feature focus chips
  - live readout tiles
  - linked tool buttons
  - safe endpoint surface
  - guarded action rail for mutation/sidecar operations
- Terminal commands can open every feature panel by name.
- Voice/chat local command matching can open domain panels when the user asks to open/show/launch them.
- The visible dock now includes a backend feature index button.
- The Director dev widget list now includes the backend feature panels, not only the older bespoke widgets.
- Side systems are labeled with `studio:`, `sidecar:`, or `comfyui:` prefixes instead of being presented as main-API endpoints.
- Action endpoints are displayed but disabled in generic panels unless they are explicitly safe/read-only; bespoke panels still own their real mutations.

## Frontend Verification

Passed:

- `node --check frontend/js/widgets.js`
- `node --check frontend/js/demo.js`
- `python -m pytest -q tests/frontend/test_feature_registry.py`
- `python -m pytest -q tests/backend/test_control_gateway.py tests/frontend/test_feature_registry.py`
- Playwright render smoke:
  - loaded `frontend/VECTOR.html`
  - opened `features`, `trading`, `corepanel`, and `pccontrol`
  - confirmed all four rendered as visible widgets
  - confirmed `VectorFeatureRegistry` exposed 27 entries
- Playwright all-feature render smoke:
  - opened all 26 backend feature panels from `VectorFeatureRegistry`
  - confirmed each panel rendered with either the bespoke mission-board layout or the dedicated core-system layout
  - failures: `0`

## Remaining Frontend Notes

- This is now bespoke mission-board UX for every mounted backend feature domain, with reusable structure so the UI stays maintainable as VECTOR grows.
- Some domains still intentionally expose guarded actions instead of one-click mutation forms. That is a safety choice for PC control, key/privacy operations, trading/backtest requests, and sidecar execution.
- Deep controls for ComfyUI, Hyperframes, and media generation remain honestly marked as Studio/sidecar areas until those controls are mounted in the main API.
- Phone, cloud deployment, and Home Assistant/smart features remain excluded from this milestone.
