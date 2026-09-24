---
name: vector-run-and-operate
description: Load when running, starting, deploying, or operating VECTOR — which mode to run, how to install it as a service, where output lands. Triggers: "run vector", "start vector", "run_vector.py", "install service", "how do I launch", "autonomous mode", "deploy".
---

# VECTOR Run & Operate

How to actually run and operate VECTOR. Ground truth 2026-07-07.

## When NOT to use this skill
For environment setup use `vector-build-and-env`; for config use `vector-config-and-flags`.

## Running: `python run_vector.py --mode X`
Valid modes (argparse choices — anything else is rejected):
`loop | api | smoke | doctor | readiness-check | memory-repair`. Default `loop`.
- **`loop`** — THE autonomous observe→think→act→reflect loop. Runs until
  interrupted. (Historical gotcha: `install_service.ps1` passed the INVALID
  `--mode autonomous` and would never start — fixed to `loop`.)
- **`api`** — FastAPI server (HUD at `/hud/`, ~85 routers).
- **`smoke`** — quick self-test.
- **`doctor` / `readiness-check` / `memory-repair`** — diagnostics/maintenance.

## Installing as a Windows service (the #1 operational gap)
```
# From an ADMIN PowerShell (requires elevation):
powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1
```
The script auto-downloads NSSM (cached at `data/tools/nssm.exe`), installs
VECTOR as an auto-restart service running `run_vector.py --mode loop`, with log
rotation and graceful CTRL+C shutdown. **VECTOR is NOT currently running as a
service** — this is the single highest-leverage operational step. Everything
else (feature flags, trust ladder, loops) only matters once it runs.

## Where output lands
- Logs: `data/logs/` (loguru, rotating).
- Generated media: `~/.vector/media/`, `renders/` (gitignored).
- Memory DB: `vector_memory.db` (SQLCipher, gitignored).
- Metering/quota: `~/.vector_ca/metering/` (budgets.json, provider_quota.json).
- Obsidian vault output: `brain/` (junction to V.E.C.T.O.R Brain).

## Verifying a running/changed system (the evidence gate)
```
python scripts/smoke_test.py         # expect 38/38 PASS
python scripts/integration_check.py  # expect 51/51 PASS
```
Cloud health: `python core/memory/multi_db_manager.py` (expect fully_healthy 4/4
when Supabase/Turso/D1 reachable).

## Cloud footprint (live)
- Cloudflare Worker: `https://vector-api.arghyadeepdeb020703.workers.dev`
  (`/health`, `/status`, D1 command queue). Deploy: `cd api && npx wrangler deploy`.
- Supabase + Turso: live (memory sync). Set via .env keys.

## Local free media servers (optional, for video)
- ComfyUI at `http://127.0.0.1:8188` (images; folder at `../ComfyUI`, has SD1.5).
- Wan2GP server + `CONFIG["media"]["wan2gp_url"]` (free local text/img-to-video:
  ltx-video/wan2.2/hunyuan). GPU processes — start manually.

## Provenance and maintenance
Dated 2026-07-07. Re-verify modes: `grep -n "choices=" run_vector.py`.
Re-verify service script: `Get-Service VECTOR` (after install).
