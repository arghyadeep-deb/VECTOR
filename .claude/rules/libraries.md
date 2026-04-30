# Preferred Libraries

## Core Stack (always use these, never substitute)
```
fastapi + uvicorn    — API server
anthropic            — Claude API (build sessions only, never VECTOR runtime)
ollama               — local model inference
langchain + langgraph — agent orchestration
loguru               — logging (never print in production)
python-dotenv        — env vars
pydantic             — data validation
httpx                — async HTTP
```

## Memory & Storage
```
sqlcipher3           — SQLite with AES-256 encryption (primary local DB)
chromadb             — vector embeddings
lightrag             — upgraded RAG system (replaces ChromaDB-only)
supabase             — primary cloud DB
keyring              — API key storage (never store in .env files on server)
watchdog             — file system monitoring for Obsidian sync
```

## Voice Pipeline
```
openai-whisper       — STT, local only, audio never leaves device (start: "base", prod: "large-v3")
kokoro               — TTS primary (bf_emma 0.85x = VECTOR voice)
sounddevice          — audio capture + playback
openwakeword         — wake word detection
langdetect           — language auto-detection
```

## Vision & Control
```
opencv-python        — camera, face detection
face-recognition     — identity verification
mediapipe            — fatigue scoring (eye aspect ratio)
mss                  — screen capture
pytesseract          — OCR
pyautogui            — PC control (vision-guided)
playwright           — browser automation (KIIT scraper)
```

## AI Extensions
```
airllm               — 70B inference on RTX 5070 Ti (overnight tasks)
open-mythos          — RDT architecture for custom LLM (verify training code exists first)
unsloth              — fastest LoRA fine-tuning on consumer GPUs
```

## Integrations
```
gitpython + PyGithub — GitHub automation
yt-dlp               — any video download (YouTube/Coursera/any URL)
instagrapi           — Instagram upload
google-api-python-client — Gmail + Calendar
apscheduler          — scheduled tasks (2AM reflect, daily KIIT scrape)
slowapi              — FastAPI rate limiting
pushover             — notifications to phone
```

## DO NOT USE
```
requests             — use httpx (async)
flask                — use fastapi
threading            — use asyncio
pickle               — use json/msgpack (security)
print()              — use loguru
```