# Wave 7 — Packaging + Release

**Goal:** Make VectorCode installable via `pip`, runnable via `docker`, distributable via PyPI + GitHub releases. Add `vector self-update`.

**Dependencies:** Waves 0–6 complete and CI green.

**Est effort:** 1 session (~500 lines).

---

## Read before coding

1. `00-MASTER-PLAN.md`
2. `vectorcode/package.json` (existing TS scaffolding — archive)
3. `GitHub/NousResearch_hermes-agent/repo/pyproject.toml`
4. `GitHub/NousResearch_hermes-agent/repo/Dockerfile`
5. `GitHub/NousResearch_hermes-agent/repo/setup-hermes.sh`

---

## Deliverables

### 1. `pyproject.toml`

At repo root. Replaces ad-hoc `requirements.txt`.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vectorcode"
version = "0.1.0"
description = "Autonomous coding agent — Hermes + Ruflo absorbed into Python"
readme = "vectorcode/README.md"
authors = [{ name = "Arghyadeep Deb" }]
license = { text = "MIT" }
requires-python = ">=3.11"
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Code Generators",
]

dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.7.0",
    "loguru>=0.7.2",
    "typer>=0.9.0",
    "httpx>=0.27.0",
    "rich>=13.0.0",
    "ollama>=0.3.0",
    "anthropic>=0.40.0",
    "openai>=1.50.0",
    "google-generativeai>=0.8.0",
    "boto3>=1.34.0",
    "websockets>=12.0",
    "jsonschema>=4.0.0",
    "tomli>=2.0; python_version<'3.11'",
    "playwright>=1.40.0",
    "sentence-transformers>=3.0.1",
    "faiss-cpu>=1.8.0",
    "supabase>=2.0.0",
    "redis>=5.0.0",
    "aiosqlite>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "ruff>=0.5",
    "black>=24.0",
    "mypy>=1.10",
]
voice = ["sounddevice", "soundfile", "openai-whisper"]
vision = ["pillow", "opencv-python-headless"]
all = ["vectorcode[dev,voice,vision]"]

[project.scripts]
vector = "vectorcode.cli.main:main"
vectorcode = "vectorcode.cli.main:main"

[project.entry-points."vectorcode.plugins"]
# (third-party plugins register here)

[tool.hatch.build.targets.wheel]
packages = ["vectorcode/python/vectorcode"]

[tool.hatch.build.targets.sdist]
include = [
    "vectorcode/python/vectorcode/**",
    "vectorcode/skills/**",
    "vectorcode/docs/**",
    "vectorcode/README.md",
    "pyproject.toml",
    "LICENSE",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.mypy]
python_version = "3.11"
strict = false
warn_unused_ignores = true
warn_redundant_casts = true
```

### 2. `Dockerfile`

Multi-stage; final image <500 MB.

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY vectorcode/ ./vectorcode/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl ripgrep git tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
RUN useradd -m -u 1000 vector
USER vector
WORKDIR /home/vector
ENV VECTOR_HOME=/home/vector/.vectorcode \
    PYTHONUNBUFFERED=1 \
    VECTOR_LOG_JSON=1
EXPOSE 8123
ENTRYPOINT ["tini", "--", "vector"]
CMD ["gateway", "start", "--host", "0.0.0.0", "--port", "8123"]
```

`docker-compose.yml` for local dev with Ollama + Redis sidecars.

### 3. `vector self-update`

New command `cli/self_update.py`:

```python
import sys, subprocess, importlib.metadata
import httpx

def cmd_self_update(args):
    current = importlib.metadata.version("vectorcode")
    latest = httpx.get("https://pypi.org/pypi/vectorcode/json").json()["info"]["version"]
    if current == latest:
        print(f"vectorcode is up to date ({current})")
        return 0
    print(f"updating vectorcode {current} → {latest}")
    return subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", "vectorcode"])
```

Register in `cli/main.py` argparse: `vector self-update`.

For Docker: `vector self-update --docker` pulls `ghcr.io/<user>/vectorcode:latest`.

### 4. GitHub Actions release pipeline

`.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install build hatchling
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish-pypi:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1

  publish-docker:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/vectorcode:latest
            ghcr.io/${{ github.repository_owner }}/vectorcode:${{ github.ref_name }}

  github-release:
    needs: [build, publish-pypi, publish-docker]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
```

### 5. Install scripts

`packaging/install.sh` (Unix one-liner):

```bash
#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --user --upgrade vectorcode
echo "vectorcode installed. Run: vector setup"
```

`packaging/install.ps1` (Windows):

```powershell
$ErrorActionPreference = "Stop"
python -m pip install --user --upgrade vectorcode
Write-Host "vectorcode installed. Run: vector setup"
```

`README.md` Install section:

```bash
# from PyPI
pip install vectorcode

# from source
git clone https://github.com/<you>/vectorcode.git
cd vectorcode
pip install -e ".[dev]"

# docker
docker run --rm -p 8123:8123 ghcr.io/<you>/vectorcode:latest

# one-liner (Unix)
curl -fsSL https://raw.githubusercontent.com/<you>/vectorcode/main/packaging/install.sh | bash
```

### 6. systemd / launchd unit files

`packaging/systemd/vector-gateway.service`:

```ini
[Unit]
Description=VectorCode Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=%i
ExecStart=/usr/bin/vector gateway start --host 127.0.0.1 --port 8123
Restart=on-failure
RestartSec=5
EnvironmentFile=-%h/.vectorcode/env

[Install]
WantedBy=default.target
```

`packaging/systemd/vector-cron.service` — mirrors above for `vector cron daemon start`.

`packaging/launchd/vector.plist` — macOS equivalent.

---

## Acceptance

1. `pip install vectorcode` from a fresh venv installs and runs `vector --help`
2. `pip install -e ".[dev]"` from source repo + `pytest` runs full suite
3. `docker build -t vectorcode .` produces image; `docker run vectorcode --help` works
4. `docker compose up` brings up gateway + ollama + redis stack
5. `vector self-update` detects new PyPI version, upgrades, restarts cleanly
6. Pushing tag `v0.1.0` triggers release workflow → PyPI + GHCR + GitHub release
7. `systemctl --user start vector-gateway` runs gateway as service
8. README install snippets all work end-to-end on a clean machine

---

## Documentation deliverables

| File | Purpose |
|------|---------|
| `vectorcode/README.md` | Quickstart, install, basic usage |
| `vectorcode/docs/architecture.md` | System overview, ADRs |
| `vectorcode/docs/api/` | Auto-generated API docs (mkdocs or pydoc) |
| `vectorcode/docs/troubleshooting.md` | Common errors + fixes |
| `vectorcode/docs/plugins-howto.md` | Writing your own plugin |
| `vectorcode/docs/skills-howto.md` | Writing skills |
| `CHANGELOG.md` | Per-version changes |
| `CONTRIBUTING.md` | PR process |

---

## Final acceptance — 100% absorption complete

After Wave 7:

- [ ] `pip install vectorcode` works on Linux/Mac/Windows
- [ ] All 8 waves tagged in git: `absorption-wave-N-complete`
- [ ] Master plan status table shows all `[DONE]`
- [ ] CI green on Python 3.11 / 3.12 / 3.13
- [ ] Coverage ≥80%
- [ ] PyPI page live: `pypi.org/project/vectorcode/`
- [ ] Docker image pulls + runs: `ghcr.io/<user>/vectorcode:latest`
- [ ] `vector --version` reports `0.1.0` matching git tag
- [ ] README install + run flow validated by clean-machine test
- [ ] All Hermes + Ruflo capabilities reachable from `vector` CLI

Tag: `git tag v0.1.0` → triggers release workflow.

🎉 **Absorption complete.**
