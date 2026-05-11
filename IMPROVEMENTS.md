# V.E.C.T.O.R Codebase Improvements

This document lists code improvements identified during the codebase review. Claude Code should use this as a task list to refactor and fix the existing modules.

## 🔴 High Priority (Bug Risks & Concurrency)

### ✅ [COMPLETED] 1. Blocking the Event Loop in FastAPI Endpoints
**Location:** `core/main.py`
**Problem:** The `/command` and `/council` FastAPI routes are defined as `async def`, but they call the synchronous `ollama.chat()` method from the `ollama` Python client. Since this is a blocking HTTP request, the entire FastAPI event loop freezes while waiting for the LLM response, rendering VECTOR unresponsive to other requests (e.g., `/health`).
**Fix:** Switch to the asynchronous client `ollama.AsyncClient().chat(...)` or offload the call using `await asyncio.to_thread(ollama.chat, ...)`.

### ✅ [COMPLETED] 2. Blocking the Event Loop in Voice Pipeline (Phase 3)
**Location:** `core/voice/ambient_listener.py` and `core/voice/wake_word.py`
**Problem:** The `handle_voice_input()` coroutine calls `self._stt.record_and_transcribe()` and `self._tts.speak()` directly, which use blocking calls like `sd.rec()`, `sd.wait()`, and `sd.play()`. This blocks the entire asyncio event loop for 5+ seconds. Similarly, `WakeWordDetector.listen_for_wake()` loops over blocking `stream.read()` calls.
**Fix:** Offload synchronous audio recording, inference, and playback to a thread pool using `await asyncio.to_thread(...)` or use `sounddevice.AsyncInputStream`.

### ✅ [COMPLETED] 3. Blocking the Event Loop in Malware Scanning (Phase 4)
**Location:** `core/control/security/malware_detector.py`
**Problem:** The `scan_file` method is `async def` but makes synchronous calls to `self.file_hash()` and `self.check_lgbm()`, both of which perform synchronous file I/O (reading potentially large executables chunk by chunk). This will block the event loop if the file is large.
**Fix:** Wrap the synchronous file I/O operations (`file_hash` and `_extract_features`) in `await asyncio.to_thread(...)`.

---

## 🟡 Medium Priority (Robustness & Security)

### ✅ [COMPLETED] 4. Missing Timezone Awareness
**Location:** Widespread (e.g., `core/loop/autonomous_loop.py`, `core/memory/episodic.py`)
**Problem:** Most `datetime.datetime.now()` or `utcnow()` calls are naive and lack proper timezone context. Some files still use `datetime.datetime.now().isoformat()`.
**Fix:** Standardize on `datetime.datetime.now(datetime.timezone.utc)` everywhere to prevent subtle timezone scheduling bugs.

### ✅ [COMPLETED] 5. Hardcoded Host and Missing Fallback in Voice Pipeline (Phase 3)
**Location:** `core/voice/ambient_listener.py`
**Problem:** `_classify_intent` hardcodes `http://127.0.0.1:11434` instead of using `get_ollama_host()`. Additionally, if intent classification fails, it defaults to `search_web` instead of a conversational fallback or polite failure message.
**Fix:** Use `CONFIG["ollama_host"]` or `core.main.get_ollama_host()`. Implement a safer fallback like `{"action_type": "respond", "params": {"message": "I didn't catch that."}}`.

### ✅ [COMPLETED] 6. Missing Resource Cleanup in Error Paths (Phase 4)
**Location:** `core/sensing/camera.py`
**Problem:** In `capture_and_scan` and `get_fatigue_score`, `cap = self._cv2.VideoCapture(...)` is initialized, but if an exception occurs before `cap.release()`, the camera handle is leaked.
**Fix:** Wrap the camera capture in a `try...finally` block to ensure `cap.release()` is always called.

---

## 🟢 Low Priority (Clean Code)

### ✅ [COMPLETED] 7. Lazy Loading Overhead in Camera Sensing (Phase 4)
**Location:** `core/sensing/camera.py`
**Problem:** `_load_known_faces` reads images from disk and encodes them every time the class is initialized. This adds significant overhead.
**Fix:** Pickle or cache the face encodings so they don't have to be recomputed on every run.

---

## 🟡 Medium Priority (Architecture)

### ✅ [COMPLETED] 11. `multi_db_manager.py` is a Stub
**Location:** `core/memory/multi_db_manager.py`
**Problem:** Only contains `run(*args, **kwargs)` returning a stub dict.
**Fix:** Implement 4-DB sync with Supabase, Turso, SQLite, and Cloudflare D1.
**Status:** ✅ COMPLETED — fully implemented with write_local, write_cloud, write_all, sync_all, health_check, get_stats. Last-write-wins strategy with deque retry queue (maxlen=10000).

---

## 🟠 Pending Deployment & Setup Tasks

### ⏳ [PENDING] 1. Deploy Brain Server to Fly.io
**Location:** `cloud/brain_server/`
**Problem:** Brain server code is complete but not deployed to production.
**Fix:** Run `fly launch` in the brain_server directory and follow prompts.
**Status:** ⏳ PENDING — HIGH priority

### ⏳ [PENDING] 2. Deploy Cloudflare Worker API
**Location:** `api/`
**Problem:** API worker code is complete but not deployed to Cloudflare Workers.
**Fix:** Run `wrangler deploy` in the api directory.
**Status:** ⏳ PENDING — HIGH priority

### ⏳ [PENDING] 3. Deploy Dashboard to Vercel
**Location:** `dashboard/`
**Problem:** Dashboard code is complete but not deployed to Vercel.
**Fix:** Run `vercel --prod` in the dashboard directory.
**Status:** ⏳ PENDING — MEDIUM priority

### ⏳ [PENDING] 4. Download Kokoro TTS Model
**Location:** `core/voice/tts.py`
**Problem:** Kokoro TTS model (~300MB) not downloaded for primary TTS engine.
**Fix:** Download model from kokoro-onnx releases.
**Status:** ⏳ PENDING — MEDIUM priority

### ⏳ [PENDING] 5. Train Custom Wake Word
**Location:** `core/voice/wake_word.py`
**Problem:** Using placeholder "hey_jarvis" wake word instead of custom "Hey VECTOR".
**Fix:** Train custom wake word model using openwakeword.
**Status:** ⏳ PENDING — LOW priority

### ⏳ [PENDING] 6. Install Optional Dependencies
**Location:** Various sensing modules
**Problem:** Optional dependencies not installed for enhanced functionality.
**Fix:** 
- Install face_recognition: `pip install face-recognition`
- Install mediapipe: `pip install mediapipe`  
- Install Tesseract OCR: Install binary + `pip install pytesseract`
**Status:** ⏳ PENDING — LOW priority

### ⏳ [PENDING] 7. Setup Phone Ambient Node
**Location:** `phone_node/`
**Problem:** Phone node not set up on Termux for mobile extension.
**Fix:** Run `phone_node/setup.sh` on Termux device.
**Status:** ⏳ PENDING — LOW priority (requires physical phone)
