# Claude Code Remaining Issues

Use this as the next cleanup/hardening handoff. The earlier broken wiring and focused failing tests have been fixed; these are the remaining production-readiness items.

Current 24/7 target architecture:

```text
Daily phone / browser / any device
  -> Cloudflare Pages or simple client UI
  -> Cloudflare Worker secure API
  -> Cloudflare D1/KV command queue and state
  -> Old OPPO A31 Termux node as always-on lightweight executor
  -> Legion VECTOR node as heavy executor when online
```

Do not deploy private AI provider keys in frontend code. Keep laptop-only keys in the laptop `.env`; put only the keys needed for 24/7 lightweight assistant work into Cloudflare Worker Secrets or a minimal Termux-only config.

## 1. Fixed: optional `fastmcp` / `beartype` dependency break

**Status:** Fixed in repo wiring. `core/__init__.py` no longer eagerly imports optional MCP packages during normal package import, and `beartype>=0.20.0,<0.23.0` is now explicitly pinned beside `fastmcp`.

**Problem:** `python run_vector.py smoke` and `python run_vector.py doctor` pass, but startup logs show an optional dependency import failure:

```text
ImportError: cannot import name 'BeartypeConf' from 'beartype'
```

This comes through `fastmcp -> key_value -> beartype`.

**Impact:** FastMCP/MCP functionality may silently degrade even though core startup succeeds.

**What to do:**
- Find the compatible `fastmcp`, `key-value`, and `beartype` versions.
- Pin or update dependencies in the appropriate requirements/pyproject file.
- Verify import no longer logs the optional dependency failure.

**Acceptance checks:**
- `python run_vector.py smoke`
- `python run_vector.py doctor`
- No `BeartypeConf` import error appears in startup logs.

## 2. Resolve doctor degraded sidecar warnings

**Problem:** `python run_vector.py doctor` has `required_failed: 0`, but status is still `degraded` because:

- `VECTOR_LIBRECHAT_PATH` is not configured.
- ComfyUI health check at `http://127.0.0.1:8188/system_stats` is unreachable.

**Impact:** Optional sidecar services are not production-ready or not intentionally disabled.

**What to do:**
- Decide whether LibreChat and ComfyUI are required for this deployment.
- If required, configure paths/URLs and startup instructions.
- If optional, make doctor output clearly distinguish “disabled by choice” from “misconfigured”.

**Acceptance checks:**
- `python run_vector.py doctor`
- Doctor either reports sidecars as healthy or clearly reports them as intentionally disabled.

## 3. Run and stabilize live capability tests

**Problem:** `tests/integration/test_capability_live.py` contains real network/Ollama/live-service tests. They timed out in the current environment.

**Impact:** The live proofs for scraper, research, FinAgent, and WebScout capability paths are not verified in this pass.

**What to do:**
- Run live tests only when network, Ollama, and required local services are intentionally available.
- Add clear skip conditions or timeout handling for missing live prerequisites.
- Keep deterministic non-live tests separate from live proofs.

**Acceptance checks:**
- `python -m pytest -q tests/integration/test_capability_live.py -m live`
- Or a documented skip result when live prerequisites are absent.

## 4. Review and stage untracked source additions

**Problem:** Many real source additions remain untracked. They should be classified intentionally instead of left as noise.

Important untracked groups:

- `core/brain/anticipation.py`
- `core/brain/person_model.py`
- `core/brain/suggestion_queue.py`
- `core/runtime/tls.py`
- `core/security/secrets_manager.py`
- `core/security/secrets_providers.py`
- `core/prompts/shared/**`
- `districts/*/prompts/**`
- `frontend/sw.js`
- `frontend/js/offline.js`
- new tests under `tests/backend`, `tests/unit`, and `tests/loop`

**Impact:** Important code may be missing from commits/releases, while unrelated generated files may be mixed in.

**What to do:**
- Classify each group as `commit`, `ignore`, or `remove`.
- Keep source code and tests tracked.
- Keep generated/runtime/private artifacts ignored.
- Make sure prompt packs are either intentionally committed or documented as external assets.

**Acceptance checks:**
- `git status --short --untracked-files=all`
- No unexplained source-like untracked files remain.

## 5. Confirm deleted files and replacement paths

**Problem:** Several tracked files are deleted. Some are expected because Fly.io was replaced by Cloudflare, but one deletion still needs product confirmation.

Deleted Fly brain files:

- `cloud/brain_server/main.py`
- `cloud/brain_server/requirements.txt`
- `cloud/brain_server/vector_config.py`

Likely OK if Cloudflare Worker is now the only cloud brain.

Deleted control file:

- `core/control/vision_controller.py`

This still needs confirmation. If computer-vision/GUI control remains part of VECTOR, it needs a replacement path or the file should not be removed.

**What to do:**
- Confirm Cloudflare fully replaces Fly brain.
- Confirm whether `vision_controller.py` is obsolete.
- If obsolete, remove stale references/docs/tests.
- If not obsolete, restore or replace it.

**Acceptance checks:**
- `rg -n "vision_controller|VisionController|cloud/brain_server|brain_server" core districts tests docs README.md DEPLOY.md`
- Any remaining references are either intentional docs or valid replacement paths.

## 6. Strengthen Cloudflare Worker parity tests

**Problem:** Python-side Cloudflare config tests pass, but Worker/D1/KV behavior still needs stronger parity coverage after replacing Fly.

Areas needing tests:

- `GET /status`
- `GET /health`
- `POST /heartbeat`
- command delivery from D1 queue
- `POST /command`
- `GET /command/:id`
- Bearer auth enforcement
- rate limiting behavior
- missing D1/KV/Supabase graceful degradation

**Impact:** The architecture migration from Fly to Cloudflare is plausible, but not fully proven at the Worker behavior level.

**What to do:**
- Add Worker tests using the repo’s TypeScript/Cloudflare test setup, or document and add a minimal local `wrangler dev` verification script.
- Preserve Python tests for local config/autonomous loop polling.
- Ensure remote commands remain permission-gated on the laptop side.

**Acceptance checks:**
- Worker tests or documented `wrangler dev` checks cover heartbeat and command queue flow.
- Python tests still pass:

```powershell
python -m pytest -q tests/integration/test_phase_e1_cloud_brain.py
```

## 7. Build the 24/7 Cloudflare command queue

**Problem:** The desired production shape is a 24/7 assistant reachable from any device while the Legion laptop is off. The current Cloudflare migration is not yet proven as a complete command queue and result channel.

**Impact:** Termux can stay online, but it cannot reliably receive commands from any device, return results, or hand off heavy work to Legion without a durable cloud queue.

**What to do:**
- Cloudflare Worker routes now include the existing `/command` path plus node polling/result paths. Verify them against a real `wrangler dev` or deployed Worker:
  - authenticated command submission
  - command polling by registered nodes
  - command result posting
  - command status lookup
  - node heartbeat
- Back the queue with D1 or KV. Prefer D1 for queryable command history and KV for simple transient state.
- Add per-device node IDs such as `termux-room-node`, `legion-heavy-node`, and `daily-phone-client`.
- Ensure commands can be marked as `lightweight`, `requires_legion`, `deferred`, `running`, `done`, or `failed`.
- Ensure commands from the daily-use phone can target the correct executor:
  - `daily-phone-client` submits commands.
  - `termux-room-node` handles lightweight commands.
  - `legion-heavy-node` handles heavy commands when awake/online.

**Acceptance checks:**
- A command submitted from a phone/browser can be picked up by Termux.
- Termux can post the result back without the Legion being online.
- A Legion-only command remains queued until Legion reconnects.
- A heavy command submitted from the daily phone is routed to Legion when Legion is online.
- All routes reject missing or invalid auth.

## 8. Upgrade Termux from ambient node to lightweight primary node

**Problem:** `phone_node/ambient_server.py` currently behaves mostly as an ambient companion: status, alerts, heartbeat, and simple classification. The target is an always-on lightweight VECTOR node on the OPPO A31 that can process everyday assistant work while the laptop is off.

**Impact:** The phone can be online 24/7, but it is not yet a true primary executor for everyday API-backed tasks.

**What to do:**
- The basic Termux polling loop now exists in `phone_node/ambient_server.py`; validate it against the deployed Cloudflare Worker.
- Add a lightweight task router for everyday work:
  - chat/question answering through AI APIs
  - notes/reminders/task capture
  - summaries/drafts
  - command queue updates
  - notification replies
- Keep heavy tasks deferred to Legion:
  - PC control
  - local files/apps
  - GPU/local-model work
  - browser automation on the laptop
- Add watchdog/boot behavior suitable for 24/7 use:
  - Termux:Boot startup
  - log rotation or bounded logs
  - crash restart loop
  - clear battery optimization instructions

**Acceptance checks:**
- OPPO A31 can process a simple assistant command while the Legion is off.
- OPPO A31 can queue a Legion-only command and report that it is deferred.
- Rebooting the OPPO restarts the node through Termux:Boot.

## 9. Harden cloud and local secret handling

**Problem:** API keys are currently stored on the laptop `.env`. That is safe for laptop-only work, but it cannot support 24/7 cloud/Termux execution while the laptop is off.

**Impact:** If secrets are copied carelessly into frontend code, committed files, logs, or broad device configs, the project risks leaking AI provider keys.

**What to do:**
- Keep private keys out of all frontend bundles.
- Use Cloudflare Worker Secrets for keys needed by the 24/7 cloud relay.
- Use a minimal Termux config only for secrets the OPPO node truly needs.
- Keep laptop-only secrets in the laptop `.env`.
- Add separate project-specific provider keys with billing limits where possible.
- Add auth between every device and Worker:
  - `VECTOR_API_KEY` or signed request token for clients
  - per-node tokens for Termux and Legion
  - no unauthenticated `/alert`, `/classify`, command, or result endpoints
- Ensure logs never print full secrets.

**Acceptance checks:**
- `rg -n "OPENAI_API_KEY|GEMINI_API_KEY|GROQ_API_KEY|ANTHROPIC_API_KEY|VECTOR_API_KEY" . --glob "!*.env" --glob "!data/**"` finds no real key values.
- Frontend code has no provider API keys.
- Worker routes reject unauthenticated requests.
- Termux local mutating HTTP endpoints require auth when `VECTOR_API_KEY` is configured.

## 10. Add Cloudflare-first deployment documentation

**Problem:** The project discussion has considered Vercel frontend plus Render backend, but the current best fit is Cloudflare-first: Pages for UI, Workers for API, D1/KV for queue/state, Worker Secrets for API keys.

**Impact:** Without a clear deployment doc, the system may split across unnecessary platforms and create more secret-management and uptime risk.

**What to do:**
- Document the recommended deployment:
  - Cloudflare Pages for frontend/mobile web UI
  - Cloudflare Worker for secure backend relay
  - Cloudflare D1/KV for queue/state
  - Cloudflare Worker Secrets for AI keys and VECTOR tokens
  - Termux OPPO A31 as always-on lightweight executor
  - Legion as optional heavy executor
- Document when Render is appropriate:
  - only for a paid always-on Python service or workloads that cannot fit Workers
- Document when Vercel is appropriate:
  - only if a Next.js/Vercel frontend is specifically needed
- Add setup commands for Worker secrets and D1/KV bindings once the actual Worker layout is confirmed.

**Acceptance checks:**
- A new setup doc exists for the 24/7 Cloudflare + Termux architecture.
- `docs/TERMUX_SETUP.md` clearly distinguishes current ambient setup from the target primary-node setup.

## 11. Add Legion wake/resume support for heavy commands

**Problem:** Heavy commands from the daily phone should run on the Legion when it is available. The current code can drain Cloudflare commands while VECTOR is awake and running, but there is no Wake-on-LAN, sleep-resume, or Windows power-management path in the codebase.

Existing relevant code:

- `api/src/router.ts` stores commands in D1 and delivers queued commands through `/heartbeat`.
- `api/src/router.ts` now also supports `/nodes/:node_id/poll` and `/commands/:id/result` for node-specific polling and result reporting.
- `core/loop/autonomous_loop.py` has `command_poll_loop()` and routes remote commands through the permission gateway.
- `core/control/pc_controller.py` can control the PC only after Windows and VECTOR are already awake.
- `core/control/wake_on_lan.py` can build/send Wake-on-LAN magic packets.
- `core/control/legion_wake.py` reads `CONFIG["wake"]` and sends the configured Legion wake packet.
- `phone_node/ambient_server.py` has a local Wake-on-LAN sender and authenticated `/wake_legion` endpoint for the OPPO Termux node.

Missing:

- End-to-end Cloudflare/Termux deployed validation for the Wake-on-LAN sender.
- BIOS/UEFI and Windows network-adapter setup documentation.
- Automatic heavy-command orchestration that queues/dispatches a `wake_legion` command before Legion-only work.
- Node status model that distinguishes `online`, `asleep`, `offline`, and `unknown`.
- Resume flow that waits for Legion heartbeat before assigning heavy commands.

**Impact:** If the Legion is asleep, it will not run Python, poll Cloudflare, or execute heavy commands until something wakes it. If it is fully shut down or hibernated, wake may not work unless hardware/BIOS/network settings support it.

**What to do:**
- Use the existing Wake-on-LAN utility from `core/control/wake_on_lan.py`.
- Wire equivalent config fields into the Termux/Cloudflare flow:
  - `LEGION_WIFI_MAC`
  - `LEGION_ETHERNET_MAC`
  - `LEGION_WAKE_BROADCAST`
  - `LEGION_NODE_ID=legion-heavy-node`
- Use current discovered values as defaults/examples:
  - `LEGION_WIFI_MAC=14-B5-CD-3C-EC-99`
  - `LEGION_ETHERNET_MAC=E8-97-44-2E-A9-3C`
  - `LEGION_WAKE_BROADCAST=10.208.79.255`
- Add a `wake_legion` command type in the Cloudflare/Termux command flow.
- When a daily-phone command is marked `requires_legion`, Termux should:
  - send Wake-on-LAN on the local WiFi/LAN
  - keep the heavy command queued/deferred
  - wait for Legion heartbeat
  - allow Legion to drain and execute the command through the existing permission gateway
- Document required Windows setup:
  - enable Wake-on-LAN in BIOS/UEFI
  - enable wake capability on the network adapter
  - allow wake from sleep
  - avoid full shutdown/hibernate if wake is unreliable
  - keep charger connected

**Acceptance checks:**
- With the Legion awake, a heavy command from the daily phone is executed by Legion.
- With the Legion asleep, Termux sends Wake-on-LAN and the command remains queued until heartbeat resumes.
- With the Legion offline/unwakeable, the command status reports `deferred_requires_legion` instead of failing silently.
