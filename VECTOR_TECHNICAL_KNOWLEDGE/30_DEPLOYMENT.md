# Deployment

**Purpose:** Local, cloud, CI/CD, service installation
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR deploys locally as a Windows service, with cloud components on Cloudflare Workers, Supabase, and optional Fly.io.

**Key Properties:**
- **Local service** — NSSM Windows service
- **Cloudflare Worker** — remote API (deployed)
- **Supabase** — cloud database (configured)
- **Cloudflare D1/R2/KV** — remote storage (deployed)
- **GitHub Actions** — CI/CD pipeline
- **Manual steps** — Ollama setup, phone ADB

**Files:**
- `scripts/install_service.ps1` (NSSM)
- `api/wrangler.toml` (Cloudflare)
- `.github/workflows/ci.yml` (CI/CD)

**Status:** ✅ IMPLEMENTED, partially deployed

---

## Local Deployment

### Windows Service (NSSM)

**File:** `scripts/install_service.ps1`
**Status:** ✅ IMPLEMENTED

```powershell
# Install VECTOR as Windows service
# Run as Administrator

$nssm = "C:\Program Files\nssm-2.24\win64\nssm.exe"
$python = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\.venv\Scripts\python.exe"
$script = "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\run_vector.py"

# Install service
& $nssm install "VECTOR" $python $script

# Configure service
& $nssm set "VECTOR" AppDirectory "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R"
& $nssm set "VECTOR" AppStopMethodConsole 1  # Graceful shutdown
& $nssm set "VECTOR" AppRestartDelay 5000
& $nssm set "VECTOR" AppExit Default Restart
& $nssm set "VECTOR" DisplayName "VECTOR Autonomous AI"
& $nssm set "VECTOR" Description "Darwinian multi-agent autonomous AI system"

# Start service
& $nssm start "VECTOR"

Write-Host "✅ VECTOR service installed and started"
```

### Manual Start

```bash
# Activate environment
cd C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R
.venv\Scripts\activate

# Start VECTOR
python run_vector.py
```

---

## Cloud Deployment

### Cloudflare Worker

**File:** `api/wrangler.toml`
**Status:** ✅ DEPLOYED

```toml
name = "vector-api"
main = "src/router.ts"
compatibility_date = "2024-01-01"

# D1 database
[[d1_databases]]
binding = "DB"
database_name = "vector-db"
database_id = "xxx"

# KV namespace
[[kv_namespaces]]
binding = "KV"
id = "xxx"

# R2 bucket
[[r2_buckets]]
binding = "R2"
bucket_name = "vector-storage"

# Environment variables
[vars]
VECTOR_API_KEY = "your_key_here"
```

### Deploy Command

```bash
cd api
npx wrangler deploy
```

### Supabase

**File:** `deploy/supabase_schema.sql`
**Status:** ✅ CONFIGURED

```sql
-- Create tables
CREATE TABLE episodic_memory (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB,
    timestamp DOUBLE PRECISION,
    embedding VECTOR(1536)
);

CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT,
    hp INTEGER,
    status TEXT,
    district TEXT
);

CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    title TEXT,
    horizon TEXT,
    progress DOUBLE PRECISION,
    status TEXT
);

-- Enable RLS
ALTER TABLE episodic_memory ENABLE ROW LEVEL SECURITY;

-- Create indexes
CREATE INDEX idx_episodic_timestamp ON episodic_memory(timestamp DESC);
CREATE INDEX idx_agents_district ON agents(district);
```

### Apply Schema

```bash
# Via Supabase dashboard SQL editor
# Or via CLI
supabase db push
```

---

## CI/CD

### GitHub Actions

**File:** `.github/workflows/ci.yml`
**Status:** ✅ IMPLEMENTED

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run unit tests
        run: |
          pytest tests/ -v --tb=short
      
      - name: Run smoke tests
        run: |
          python scripts/smoke_test.py
      
      - name: Run integration tests
        run: |
          python scripts/integration_check.py
```

---

## Manual Setup Steps

### Ollama Models

```bash
# Pull all models
ollama pull gemma4:e2b
ollama pull gemma4:e4b
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama pull gemma4:26b
ollama pull gemma4:31b

# Build custom models
ollama create vector-ambient -f modelfiles/vector-ambient.modelfile
ollama create vector-focus -f modelfiles/vector-focus.modelfile
ollama create vector-multilingual -f modelfiles/vector-multilingual.modelfile
ollama create vector-reasoning -f modelfiles/vector-reasoning.modelfile
ollama create vector-coder -f modelfiles/vector-coder.modelfile
ollama create vector-deep -f modelfiles/vector-deep.modelfile
ollama create vector-chairman -f modelfiles/vector-chairman.modelfile
ollama create vector-r1 -f modelfiles/vector-r1.modelfile
ollama create vector-dev -f modelfiles/vector-dev.modelfile
ollama create vector-fast -f modelfiles/vector-fast.modelfile
```

### Phone ADB

```bash
# Enable USB debugging on phone
# Connect via USB
adb devices  # Verify connection

# Test screenshot
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png

# Install Termux (for ambient node)
# Download from F-Droid
# Run setup script
bash phone_node/setup.sh
```

### Python Dependencies

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: GPU acceleration
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# Optional: Voice cloning
pip install chatterbox-tts

# Optional: Face recognition
pip install face-recognition mediapipe
```

---

## Deployment Status

| Component | Status | Notes |
|-----------|--------|-------|
| Local service | ✅ Code ready | NSSM script exists |
| Cloudflare Worker | ✅ Deployed | Live, authenticated |
| Supabase | ✅ Configured | Schema applied |
| Cloudflare D1 | ✅ Deployed | 7 tables |
| Cloudflare KV | ✅ Deployed | Active |
| Cloudflare R2 | ✅ Deployed | Active |
| Phone ADB | ✅ Connected | Oppo A31 |
| Ollama models | ✅ Installed | 10 custom models |
| CI/CD | ✅ Configured | GitHub Actions |

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Local service start | 5-15s | Model loading |
| Cloudflare deploy | 10-30s | Build + upload |
| Supabase schema | 1-5s | Network |
| Ollama model pull | 1-10min | Network |
| Custom model build | 5-30min | GPU |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `04_RUNTIME_AND_BOOT.md` — Boot sequence
- `22_FRONTEND.md` — HUD interface
- `23_BACKEND_API.md` — API endpoints

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
