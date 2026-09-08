# Configuration

**Purpose:** CONFIG dict, environment variables, secrets
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR uses a centralized CONFIG dict in `core/config.py` for all configurable values. Environment variables are loaded via python-dotenv. Secrets use SecretStr.

**Key Properties:**
- **Centralized config** — single CONFIG dict
- **No hardcoding** — all paths/keys in config
- **SecretStr** — secure secret handling
- **Pydantic validation** — type-safe config
- **Environment variables** — loaded from .env

**Files:**
- `core/config.py` (~300 lines)
- `.env` (secrets, not committed)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Config Structure

### Main Config

**File:** `core/config.py`
**Status:** ✅ IMPLEMENTED

```python
from pydantic import BaseModel, SecretStr
from dotenv import load_dotenv
import os

load_dotenv()

class DatabaseConfig(BaseModel):
    path: str = "vector_memory.db"
    key: SecretStr = SecretStr(os.getenv("VECTOR_DB_KEY", ""))
    backup_path: str = "backups/"

class InferenceConfig(BaseModel):
    ollama_host: str = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
    max_loaded_models: int = 1
    flash_attention: bool = True
    kv_cache_type: str = "q8_0"
    keep_alive: str = "30m"

class APIConfig(BaseModel):
    anthropic_key: SecretStr = SecretStr(os.getenv("ANTHROPIC_API_KEY", ""))
    openai_key: SecretStr = SecretStr(os.getenv("OPENAI_API_KEY", ""))
    gemini_key: SecretStr = SecretStr(os.getenv("GEMINI_API_KEY", ""))
    groq_key: SecretStr = SecretStr(os.getenv("GROQ_API_KEY", ""))
    deepseek_key: SecretStr = SecretStr(os.getenv("DEEPSEEK_API_KEY", ""))
    # ... (27 providers)

class VectorConfig(BaseModel):
    version: str = "1.0.0"
    owner: str = "Arghyadeep Deb"
    db: DatabaseConfig = DatabaseConfig()
    inference: InferenceConfig = InferenceConfig()
    api: APIConfig = APIConfig()
    
    # Paths
    brain_path: str = r"C:\Users\Arghyadeep\V.E.C.T.O.R Brain"
    obsidian_path: str = r"C:\Users\Arghyadeep\V.E.C.T.O.R Brain"
    
    # Cloud
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: SecretStr = SecretStr(os.getenv("SUPABASE_KEY", ""))
    cloudflare_account_id: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    cloudflare_api_token: SecretStr = SecretStr(os.getenv("CLOUDFLARE_API_TOKEN", ""))
    
    # Notifications
    pushover_user: str = os.getenv("PUSHOVER_USER", "")
    pushover_token: SecretStr = SecretStr(os.getenv("PUSHOVER_TOKEN", ""))
    
    # Voice
    kokoro_model: str = "models/kokoro/kokoro-v1.0.fp16-gpu.onnx"
    whisper_model: str = "base"  # "large-v3" for production
    wake_word: str = "hey_vector"
    
    # Security
    api_key: SecretStr = SecretStr(os.getenv("VECTOR_API_KEY", ""))
    virustotal_key: SecretStr = SecretStr(os.getenv("VIRUSTOTAL_KEY", ""))

# Global config instance
CONFIG = VectorConfig()
```

---

## Environment Variables

### Required .env

```bash
# Database
VECTOR_DB_KEY=your_encryption_key_here

# LLM Providers (at least one)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROQ_API_KEY=gsk_...
DEEPSEEK_API_KEY=...
OPENROUTER_API_KEY=...
MISTRAL_API_KEY=...
# ... (27 providers total)

# Cloud
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...

# Notifications
PUSHOVER_USER=...
PUSHOVER_TOKEN=...

# Security
VECTOR_API_KEY=your_api_key_here
VIRUSTOTAL_KEY=...

# Ollama (already set system-wide)
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_KEEP_ALIVE=30m
```

---

## Config Convention

### Rule: Never Hardcode

```python
# ❌ WRONG — never do this
db_path = "vector_memory.db"
api_key = "sk-ant-..."

# ✅ CORRECT — always use CONFIG
from core.config import CONFIG

db_path = CONFIG.db.path
api_key = CONFIG.api.anthropic_key.get_secret_value()
```

---

## Config Sections

### Sub-Configs

```python
# Browser config
CONFIG.browser = {
    "dom_pruner_enabled": True,
    "pii_scrub_enabled": True,
    "auth_profiles_path": "browser_profiles/"
}

# Voice config
CONFIG.voice = {
    "kokoro_model": "models/kokoro/kokoro-v1.0.fp16-gpu.onnx",
    "whisper_model": "base",
    "wake_word": "hey_vector",
    "prefer_local_voice": True
}

# Collections config
CONFIG.collections = {
    "max_fields": 50,
    "max_collections": 100,
    "storage_backend": "local"  # "local" | "s3"
}
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Config load | 10-50ms | File I/O |
| Env var access | <1ms | Memory |
| Secret retrieval | <1ms | Memory |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `29_CONFIGURATION.md` — this document
- `04_RUNTIME_AND_BOOT.md` — Boot sequence

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
