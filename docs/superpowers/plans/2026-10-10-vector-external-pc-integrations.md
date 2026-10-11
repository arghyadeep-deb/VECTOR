# Plan: VECTOR external PC integrations

## Objective

Verify the owner-facing PC surfaces and represent unavailable external services
honestly.

## Files and surfaces

- `core/voice/stt.py`
- `core/voice/tts.py`
- `core/coding_assistant/core/tts/factory.py`
- `core/coding_assistant/core/transcribe/__init__.py`
- `core/coding_assistant/acp/acp_agent_loop.py`
- `core/control/pc_controller.py`
- camera/screenshot/control routes under `core/api/routers/`
- `frontend/VECTOR.html`
- `frontend/widgets.js`
- `frontend/demo.js`
- `scripts/capability_smoke.py`
- external mail/calendar/browser/sidecar adapters identified by the matrix

## Steps

1. Add offline tests for explicit legacy voice-stub and ACP availability states.
2. Add Gateway approval/denial tests for PC actions and file/media roots.
3. Run minimal local probes for STT, TTS, screenshot, app launch, browser/HUD,
   and media paths without claiming hardware success when unavailable.
4. Run owner-assisted voice/camera/microphone/browser checks on the real PC.
5. Record credential/device/service prerequisites as `NEEDS_CONFIG` when live
   proof is impossible.

## Verification

```powershell
python -m pytest -q tests -k "voice or tts or transcrib or acp or pc_controller or camera or browser" --timeout=120
python scripts/capability_smoke.py --help
python run_vector.py readiness-check
```

Browser/HUD verification requires the browser QA workflow after the local API
is running; static asset existence is insufficient.

## Gate

Every PC side effect has a Gateway path, a clear unavailable state, and a
recorded owner-run result where hardware or credentials are required.
