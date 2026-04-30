# Commands

## Daily Development
```bash
# Start VECTOR
cd C:\Users\Arghyadeep\Projects\VECTOR
.venv\Scripts\activate
python run_vector.py

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
# Python environment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Verify CUDA
nvidia-smi

# Install AirLLM
pip install airllm

# Install OpenMythos (verify train.py exists before Month 2)
pip install open-mythos

# WSL2 for Hermes (PowerShell Admin)
wsl --install
# After restart in WSL2:
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
ollama launch hermes --model kimi-k2.6:cloud
```

## Ollama Model Management
```bash
# Pull all at once
ollama pull gemma4:e2b && ollama pull gemma4:e4b && ollama pull qwen3:8b && ollama pull qwen3:14b && ollama pull nomic-embed-text && ollama pull gemma4:26b && ollama pull gemma4:31b && ollama pull kimi-k2.6:cloud && ollama pull glm-5.1:cloud

# Build custom models
ollama create vector-ambient -f modelfiles\vector-ambient.modelfile
ollama create vector-focus -f modelfiles\vector-focus.modelfile
ollama create vector-multilingual -f modelfiles\vector-multilingual.modelfile
ollama create vector-reasoning -f modelfiles\vector-reasoning.modelfile
ollama create vector-coder -f modelfiles\vector-coder.modelfile

# Build all at once
ollama create vector-ambient -f modelfiles\vector-ambient.modelfile && ollama create vector-focus -f modelfiles\vector-focus.modelfile && ollama create vector-multilingual -f modelfiles\vector-multilingual.modelfile && ollama create vector-reasoning -f modelfiles\vector-reasoning.modelfile && ollama create vector-coder -f modelfiles\vector-coder.modelfile
```

## Cloud Deployment (Phase 3)
```bash
# Cloudflare Workers
cd api && npx wrangler deploy

# Fly.io
fly launch && fly deploy

# Vercel
cd dashboard && vercel --prod
```

## End-of-Day Pass Conditions
```
Day 1:  python run_vector.py → JSON response + SQLite row exists
Day 2:  debug mode → 4 candidates with scores + policy table has rows
Day 3:  "Hey VECTOR" → terminal: WAKE → TRANSCRIBE → THINK → SPEAK
Day 4:  face ID returns name + pyautogui moves cursor + ADB screenshot
Day 5:  GmailAgent reads + KIIT schedule + git log shows auto-commit
Day 6:  fly.dev/status → 200 + old phone ambient running + Obsidian note
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