# Owner-Gated Runtime Flags

Last checked: 2026-06-27.

These flags intentionally keep live services, model calls, hardware, or mutable
production resources out of default local tests. A feature behind one of these
flags is not "fully proven in production" unless the owner supplies the needed
service/device/account and runs the live proof.

| Flag | Default | Enables |
|---|---:|---|
| `VECTOR_LIVE_TESTS=1` | off | Live network/model integration proofs in `tests/integration/test_capability_live.py`. |
| `VECTOR_RESEARCH_LLM_DESIGN=1` | off | Ollama-backed research experiment design in `core/research_engine/experiment_designer.py`; otherwise rule-based design is used. |
| `VECTOR_TRAINING_REAL=1` | off | Real PEFT/Unsloth LoRA training in `core/training/lora_trainer.py`; otherwise adapter manifests are simulated/dry-run. |
| `VECTOR_PREDICTIVE_USE_MEMORY=1` | off | Predictive analytics mining of live episodic memory history. |
| `VECTOR_DB_RECOVERY_CHECK=1` | off | Live memory DB integrity check and recovery playbook. Keep off unless the DB is backed up and the owner wants inspection. |
| `VECTOR_OBSIDIAN_RAG_QUERY=1` | off | Obsidian/LightRAG query during context hydration. |
| `VECTOR_FASTAPI_REVIEW_LLM=1` | off | LLM-backed FastAPI code review. |
| `VECTOR_PYTHON_REVIEW_LLM=1` | off | LLM-backed Python code review. |
| `VECTOR_SECURITY_REVIEW_LLM=1` | off | LLM-backed security review. |
| `VECTOR_SEO_LLM=1` | off | LLM-backed SEO synthesis/schema/keyword work. |
| `VECTOR_GOOGLE_ADS_LLM=1` | off | LLM-backed Google Ads audit/copy/landing-page reasoning. |
| `VECTOR_FEEDBACK_LLM=1` | off | LLM-backed interview feedback analysis. |
| `VECTOR_STYLE_LLM=1` | off | Ollama-backed persona style rewrites. |
| `VECTOR_WEB_SCOUT_LLM=1` | off | LLM-backed WebScout research summaries. |
| `VECTOR_REDDIT_MINER_LLM=1` | off | LLM-backed RedditMiner opportunity extraction. |
| `VECTOR_SKILLS_LLM=1` | off | LLM-backed skills gap analysis, prioritization, and learning path generation. |

Owner-gated **work items** (cloud deploys, hardware, wake-word training, etc.)
are tracked in `OPEN_ISSUES.md`, not here — this doc is only the catalog of
runtime *config flags*. See `OPEN_ISSUES.md` §B/§C for the deploy/device actions.
