# Models & Routing

## Hardware
```
GPU:  RTX 5070 Ti 12GB VRAM
RAM:  32GB DDR5
CPU:  Intel Core Ultra 9 275HX (24 cores)
```

## Ollama Environment (already set)
```
OLLAMA_MAX_LOADED_MODELS=1     ← NEVER load 2 simultaneously (KV cache overflow)
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_KEEP_ALIVE=30m
OLLAMA_HOST=127.0.0.1:11434
```

## Installed Models
```
vector-ambient      (gemma4:e2b)   — ambient JSON classifier, old phone
vector-focus        (gemma4:e4b)   — main voice + multimodal, permanent VRAM
vector-multilingual (qwen3:14b)    — HI/BN/AS/JA/EN auto-switch
vector-reasoning    (qwen3:14b)    — step-by-step, council member
vector-coder        (qwen3:14b)    — 2-mode: personal stack / SaaS stack
vector-deep        (gemma4:26b)    — overnight analysis, 65K context, document reading
vector-chairman    (gemma4:31b)    — council chairman, private reasoning, training data gen
nomic-embed-text                   — vector embeddings
qwen3:8b, qwen3:14b                — base models
qwen3:30b-a3b (MoE, 3B active)     — fast large-context reasoning, low VRAM for 30B class
gemma4:e2b, gemma4:e4b             — base models
gemma4:26b (MoE, 4B active)        — deep tasks, hybrid mode
gemma4:31b (Dense)                 — slow deep tasks, hybrid mode
deepseek-r1:14b                    — chain-of-thought reasoning, R1 style
devstral:24b                       — code-specialist (Mistral devstral), refactor + review
mistral-small3.1:latest            — fast general-purpose, low-latency fallback
kimi-k2.6:cloud                    — Council + Hermes brain
glm-5.1:cloud                      — Council Chairman (until your LLM ready)
```

## Model Routing (use this decision tree)
```
Real-time conversation   → vector-focus (permanent VRAM, 40+ tok/s)
Hindi/Bengali/Assamese  → vector-multilingual (load on demand)
Code generation         → vector-coder OR qwen3:14b (load on demand)
Council/reasoning       → vector-reasoning + kimi-k2.6 + glm-5.1
Deep overnight tasks    → gemma4:26b or gemma4:31b (hybrid, 3-6 tok/s)
70B tasks               → AirLLM (streams layers, slow but works)
YOUR build sessions     → Claude Sonnet 4.6 via Pro plan chat (unlimited)
YOUR complex planning   → Claude Opus 4.6 via Pro plan chat
```

## VECTOR Runtime Rule
```
Claude API is NEVER called during VECTOR's autonomous operation.
Local models handle ALL runtime decisions.
Claude API = your build sessions only = Pro plan chat = ₹0.
```

## Custom LLM Plan (OpenMythos RDT)
```
Week 7-8:  nanoGPT on your data (learning exercise)
Month 2:   LoRA fine-tune Qwen3 4B on RTX 5070 Ti (1-2 hours local)
Month 2-3: vector-chairman → Council Chairman (replaces glm-5.1:cloud)
Month 4-6: Pre-train OpenMythos 200M from scratch (weekend on Legion)
Year 2:    Full custom LLM trained on VECTOR's reasoning chains

WARNING: Verify OpenMythos has working train.py before Month 2.
Fallback:  karpathy/nanoGPT + LoRA on Colab (proven, no risk)
```

## Coder Model — Two Modes
```
MODE 1 (Personal/Skill Projects):
  Fixed stack: Python, FastAPI, LangGraph, LangChain, PyTorch, SQLite,
               RAG, MCP, Streamlit, Docker, TensorFlow, Keras, PowerBI
  Goal: resume-worthy, clean, demonstrable

MODE 2 (SaaS Products):
  Stack chosen per requirement. Analyse first.
  Defaults: FastAPI/Next.js + Supabase + Railway + Stripe + Cloudflare
  Ask: "Personal project or SaaS?" if unclear
```

## LLM Council
```
Trigger:  high-stakes decisions only (stakes = "high" or "critical")
Members:  kimi-k2.6:cloud + glm-5.1:cloud + qwen3:14b + vector-reasoning
Chairman: glm-5.1:cloud → your fine-tuned model (Month 2)
HP gate:  only agents >700 HP get council vote
Cost:     ~₹1.60/session, max 10/week
Sessions: stored in reasoning_chains → LLM training data
```