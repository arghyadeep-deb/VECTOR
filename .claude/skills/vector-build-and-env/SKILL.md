---
name: vector-build-and-env
description: Load when setting up VECTOR's environment from scratch, debugging a dependency/interpreter issue, or confused about which Python/torch/CUDA is in use. Triggers: "install deps", "environment", "which python", "venv", "torch cuda", "setup", "requirements", "module not found".
---

# VECTOR Build & Environment

Recreate and understand VECTOR's runtime environment. Ground truth 2026-07-07,
Windows 11 + RTX 5070 Ti. Verify before relying.

## When NOT to use this skill
For running the app after setup use `vector-run-and-operate`.

## Critical env facts (these trip people up)
- **There is NO `.venv`.** VECTOR runs on the SYSTEM Python 3.13
  (`C:\Users\Arghyadeep\AppData\Local\Programs\Python\Python313\python.exe`).
  Do not assume a virtualenv. `python` on PATH is the right interpreter.
- **torch is CUDA (cu128), GPU-resident:** `torch 2.11.0+cu128`,
  `torch.cuda.is_available() == True`. (It was silently CPU-only once — if
  Whisper/ComfyUI run slow, re-check the CUDA wheel.)
- **`OLLAMA_MAX_LOADED_MODELS=1`** — one local model in 12GB VRAM at a time.
- Ollama models live locally (`ollama list`): vector-focus/ambient/reasoning/
  coder/deep/chairman/r1/dev/fast + base qwen3/gemma4/deepseek-r1/devstral +
  qwen2.5vl:7b (vision) + nomic-embed-text.

## Setup from scratch
```
# 1. deps
python -m pip install -r requirements.txt
# 2. verify CUDA
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# 3. verify config loads
python core/config.py    # expect: config.py OK
# 4. Ollama models
ollama list              # pull missing ones per .claude/rules/commands.md
# 5. smoke
python scripts/smoke_test.py   # expect 38/38 PASS
```

## Known env traps
- **Windows cp1252 console** → non-ASCII prints crash. Use `PYTHONUTF8=1` for
  scripts that print unicode (or reconfigure stdout).
- **Repo path has a literal space** (`V.E.C.T.O.R. Codebase`) → `workerd`
  (Cloudflare Worker tests) can't resolve modules locally. Runs in CI (Linux)
  or a space-free clone path. Not a code bug.
- **`test_tmp/` is ACL-locked** — read-only pytest shard dirs survive
  takeown/icacls; needs an admin shell (`rmdir /s /q test_tmp`) or reboot.
- **dlib** (face_recognition) is blocked by a Windows Application Control policy
  — an OS setting, not a missing package. Camera falls back to neutral.
- Some ML deps have load-order landmines (torchvision before openwakeword — see
  `vector-debugging-playbook`).

## Provenance and maintenance
Dated 2026-07-07. Re-verify: `python -c "import sys,torch; print(sys.version.split()[0], torch.__version__, torch.cuda.is_available())"`.
Deps: `requirements.txt` (pinned). Ollama env in `.claude/rules/models.md`.
