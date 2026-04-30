# 05 — Edge Cases and Error Handling

## Autonomous Loop

| Edge Case | Expected Behaviour | Implementation |
|-----------|-------------------|----------------|
| Ollama crashes during inference | Catch OllamaError. Fall back to next model. Notify owner once. | `try/except` every `ollama.chat()`. Chain: focus→reasoning→glm-5.1:cloud |
| All models unavailable | Return cached last response. Notify once. Do not spam. | CachedResponseManager stores last 10. `alert_sent` flag prevents repeat. |
| Coroutine crashes | Catch exception. Log traceback. Sleep 5s. Restart that coroutine only. | `while True` + `try/except` in every coroutine. Never kill the `gather()`. |
| VRAM OOM | Catch CUDA OOM. Force unload. Retry after 5s. | ResourceMonitor checks VRAM before every load. Refuse if < 1GB headroom. |
| Session hydration exceeds context | Truncate oldest episodes first. Always keep: goals + last 24h + active tasks. | `session_hydration_prompt()` enforces 4096 token max. |
| Clock drift between devices | All timestamps UTC ISO. Never local time in storage. | `datetime.utcnow().isoformat()` everywhere. |
| SQLite lock contention | WAL mode. Retry exponential backoff (100ms→200ms→400ms, max 3). | `PRAGMA journal_mode=WAL`. Write queue for high-frequency. |

## Voice Pipeline

| Edge Case | Expected Behaviour | Implementation |
|-----------|-------------------|----------------|
| Wake word false positive | Activate, listen 5s. No speech → return to ambient. No response. | VAD after wake word. Silence > 1s in first 3s = false positive. |
| Whisper fails mid-transcription | Fall to text input mode silently. Log once per session. | `try/except` on `whisper.transcribe()`. Degrade gracefully. |
| Kokoro TTS silent | Print to terminal. Log warning. Do not crash loop. | `sounddevice.play()` in `try/except`. Text fallback always available. |
| Language detection wrong | Use detected. If user corrects → update `semantic_memory.preferred_language`. | langdetect confidence < 0.85 → default to last used language. |
| Audio extremely noisy | Whisper attempts. Confidence < 0.6 → ask repeat once only. | Word-level confidence check. One retry maximum. |
| Wake word while VECTOR is speaking | Queue activation. Finish current response. Then activate. | `activation_queue` asyncio.Queue. Process after TTS completes. |

## Agent HP System

| Edge Case | Expected Behaviour | Implementation |
|-----------|-------------------|----------------|
| All agents in district die | District inactive. Notify owner. Governor routes to Research District. | `district_health_monitor` checks alive agents > 0 every 30 min. |
| HP oscillates near death (49→51 repeatedly) | After 5 oscillations in 24h → freeze HP at 50, flag for review. | `hp_oscillation_counter` in semantic_memory. |
| Ghost memory corrupt or empty | Spawn with empty ghost_memory. Log warning. Agent starts fresh. | `ghost_memory` is Optional. Null check before inheritance. |
| Agent generation > 100 | Archive all ghost memory to `data/training/`. Reset counter. | `generation > 100` triggers archival. High-value training signal. |
| Multiple agents claim same task | Mutex lock. First claimant wins. Others notified. | `asyncio.Lock` per task_type in task_router.py. |

## Permission Gateway

| Edge Case | Expected Behaviour | Implementation |
|-----------|-------------------|----------------|
| RED action during sleep (1–8AM) | Queue. Do not wake unless urgency > 0.9. Include in morning brief. | `timing_score` check. RED + urgency < 0.9 = overnight queue. |
| Owner doesn't respond to RED in 30s | Abort. Log timed_out. Morning brief. Never auto-retry. | `asyncio.wait_for(confirm_event, timeout=30)`. |
| Action type not in matrix | Default to RED. Log unknown_action. Never assume GREEN. | Gateway fallback: unknown → RED. Append to unknown_actions log. |
| Audit log > 10GB | Archive logs > 30 days to Cloudflare R2, encrypted. | APScheduler monthly. Local log rotates at 1GB. |
| 3 RED rejections same action in 24h | Flag as persistently_blocked. Remove from candidate generation. | `policy.update_from_outcome()` reward=-1.0 × 3 → blocks. |

## Memory and Database

| Edge Case | Expected Behaviour | Implementation |
|-----------|-------------------|----------------|
| Supabase unreachable | Write to local SQLite. Queue sync for when it returns. | `multi_db_manager` health check per write. Local always available. |
| DB sync conflict (same key, different values) | Last-write-wins on `updated_at`. Log conflict. | `sync_all()` compares `updated_at` across all 4 DBs. |
| Obsidian vault path missing on startup | Create directory. Log warning. Continue — never crash. | `vault_path.mkdir(parents=True, exist_ok=True)` on startup. |
| reasoning_chains > 1GB | Archive chains > 90 days to `data/training/`. Keep recent 90 days. | APScheduler weekly archival. Archived = LLM training data. |