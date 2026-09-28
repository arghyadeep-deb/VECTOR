# Commands

## Daily Development
```bash
# Start VECTOR
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
# no .venv in the repo — system Python 3.13 is used
python run_vector.py
# `run_vector.py loop` (autonomous loop) and `run_vector.py api` (FastAPI on :8000) are separate processes.
# START_VECTOR.bat runs a smoke test, then launches the API in its own window and the loop in the current one;
# START_API_ONLY.bat launches only the API.

# Test a single module
python core\memory\episodic.py
python core\city\agent_base.py
python core\loop\decision_engine.py

# Check Ollama
ollama list
ollama run vector-focus "Hello VECTOR"

# Git — commit every day
git add .
git commit -m "[T1.5] episodic.py: FTS5 + 5 tables complete"
git push
```

## Setup (run once)
```bash
# Python environment (current machine uses system Python 3.13, no .venv; create one only if you want isolation)
pip install -r requirements.txt

# Verify CUDA
nvidia-smi

# Install AirLLM
pip install airllm

# Install OpenMythos (verify train.py exists before Month 2)
pip install open-mythos

# vectorcode comms layer (replaces Hermes — fully absorbed)
# All channels via vectorcode/src/channels/ — no separate install needed
# Use: from vectorcode.src.vc_agents.agent_registry import vc_agents
```

## Ollama Model Management
```bash
# Pull all at once
ollama pull gemma4:e2b && ollama pull gemma4:e4b && ollama pull qwen3:8b && ollama pull qwen3:14b && ollama pull nomic-embed-text && ollama pull gemma4:26b && ollama pull gemma4:31b && ollama pull kimi-k2.6:cloud && ollama pull glm-5.1:cloud

# Build custom models (individually)
ollama create vector-ambient -f modelfiles\vector-ambient.modelfile
ollama create vector-focus -f modelfiles\vector-focus.modelfile
ollama create vector-multilingual -f modelfiles\vector-multilingual.modelfile
ollama create vector-reasoning -f modelfiles\vector-reasoning.modelfile
ollama create vector-coder -f modelfiles\vector-coder.modelfile
ollama create vector-deep -f modelfiles\vector-deep.modelfile
ollama create vector-chairman -f modelfiles\vector-chairman.modelfile
ollama create vector-r1 -f modelfiles\vector-r1.modelfile
ollama create vector-dev -f modelfiles\vector-dev.modelfile
ollama create vector-fast -f modelfiles\vector-fast.modelfile

# Build all at once (10 models)
ollama create vector-ambient -f modelfiles\vector-ambient.modelfile && ollama create vector-focus -f modelfiles\vector-focus.modelfile && ollama create vector-multilingual -f modelfiles\vector-multilingual.modelfile && ollama create vector-reasoning -f modelfiles\vector-reasoning.modelfile && ollama create vector-coder -f modelfiles\vector-coder.modelfile && ollama create vector-deep -f modelfiles\vector-deep.modelfile && ollama create vector-chairman -f modelfiles\vector-chairman.modelfile && ollama create vector-r1 -f modelfiles\vector-r1.modelfile && ollama create vector-dev -f modelfiles\vector-dev.modelfile && ollama create vector-fast -f modelfiles\vector-fast.modelfile
```

## Cloud Deployment (Phase 3)
```bash
# Cloudflare Worker (live)
cd api && npx wrangler deploy

# Fly.io — dropped (owner declined the card requirement; cloud/brain_server/ removed)
# Vercel dashboard — not applicable: dashboard/ does not exist; the frontend/ HUD is served by the API at /hud/
```

## End-of-Day Pass Conditions
```
Day 1:  python run_vector.py → JSON response + SQLite row exists
Day 2:  debug mode → 4 candidates with scores + policy table has rows
Day 3:  "Hey VECTOR" → terminal: WAKE → TRANSCRIBE → THINK → SPEAK
Day 4:  face ID returns name + pyautogui moves cursor + ADB screenshot
Day 5:  GmailAgent reads + KIIT schedule + git log shows auto-commit
Day 6:  Cloudflare Worker /status → 200 (Fly.io dropped) + old phone ambient running + Obsidian note
Day 7:  all 4 end-to-end scenarios pass without manual intervention
```

## Useful Checks
```bash
# Verify env vars
echo %OLLAMA_MAX_LOADED_MODELS%
echo %OLLAMA_FLASH_ATTENTION%
echo %OLLAMA_HOST%

# Count Python files
dir /s /b *.py | find /c ".py"

# Check SQLite memory
sqlite3 vector_memory.db "SELECT COUNT(*) FROM episodic_memory"

# Test API connection
python -c "import anthropic; print(anthropic.Anthropic().models.list())"
```