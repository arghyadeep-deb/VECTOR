# 03 — API Contracts

## FastAPI Endpoints

### `POST /command`
```json
// Request
{ "text": "string", "source": "voice|text|api", "priority": "normal|urgent" }

// 200 OK
{ "response": "string", "action_taken": "string|null",
  "candidates_evaluated": 4, "winner_score": 0.0,
  "memory_updated": true, "processing_ms": 0 }

// 429
{ "error": "rate_limited", "retry_after_ms": 0 }

// 503
{ "error": "model_unavailable", "fallback_used": "string" }
```

### `GET /status`
```json
{ "loop_running": true, "uptime_seconds": 0,
  "models": { "focus": "loaded|unloaded" },
  "memory": { "episodic_rows": 0, "policy_rows": 0 },
  "agents": { "alive": 0, "dead": 0, "top_hp": 0 },
  "last_reflect": "ISO timestamp|null" }
```

### `POST /voice`
```
Request:  multipart/form-data { audio: wav/mp3 max 30s }
Response: { "transcript": "string", "response": "string",
            "language_detected": "en|hi|bn|as|ja", "audio_url": "string" }
```

### `POST /agent/award`
```json
// Request
{ "agent_id": "string", "points": 0, "reason": "string" }
// Response
{ "new_hp": 0, "status": "alive|weakened|critical", "model_upgraded": false }
```

### `POST /council`
```json
// Request
{ "question": "string", "stakes": "medium|high|critical" }
// Response
{ "session_id": "string", "chairman_decision": "string",
  "confidence": 0.0, "winning_model": "string",
  "stored_as_training_data": true }
```

## Ollama Model Contracts

| Model | Input | Output Contract | On Failure |
|-------|-------|----------------|------------|
| vector-ambient | 5s transcript | JSON only: `{actionable, intent, confidence, action_type}` | Return `{actionable:false, confidence:0}` |
| vector-focus | text + hydration | British tone, no reasoning visible | Fall back to vector-reasoning |
| vector-coder | task + mode | Code first, explanation after | Fall back to qwen3:14b |
| vector-multilingual | any language text | Same language back, VECTOR personality | Fall back to vector-focus |
| vector-reasoning | complex task | Step-by-step with explicit uncertainty | Fall back to glm-5.1:cloud |

## Memory System Contracts

| Function | Contract | On Error |
|----------|----------|----------|
| `episodic.store(type, content, tags)` | row_id:int. Persists < 100ms. FTS5 indexed. | Write local SQLite. Never block. |
| `episodic.recall(query, limit=5)` | list[{timestamp, content}]. Max 500ms. | Return empty list. Log, never raise. |
| `policy.get_score(action, situation)` | float 0.0-1.0. Returns 0.5 if no history. Max 50ms. | Return 0.5. Never block decision. |
| `policy.update_from_outcome(...)` | Updates avg_reward. Async, non-blocking. | Queue if DB unavailable. Apply later. |
| `reasoning_memory.start_chain(...)` | chain_id:str. Context snapshot stored. | Local UUID, store in memory until DB available. |
| `multi_db_manager.sync_all()` | Syncs 4 DBs. Last-write-wins per record. | Partial sync OK. Log failures. Never block. |

## Permission Gateway Contract

| Level | Examples | Behaviour | User Experience |
|-------|----------|-----------|-----------------|
| GREEN | read_calendar, play_music, search_web | Execute immediately. Log. Soft notify after. | Silent. Dashboard activity feed. |
| YELLOW | send_message_routine, commit_code, download_file | Execute. Pushover priority 1 immediately. | Phone buzz. 30s undo window. |
| RED | send_email, delete_files, push_github, deploy | STOP. Ask owner. Wait 30s. Abort if no response. | Critical alert. Dashboard confirm. |

> **Hard rule: LLM has ZERO direct access. Ever. No exceptions.**