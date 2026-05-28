FROM python:3.11-slim AS builder
WORKDIR /app

# Install tini for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

# Deps layer
COPY requirements.txt ./
RUN pip install --no-cache-dir --no-deps -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 vector
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy worker source + shared VECTOR packages
COPY core/ ./core/
COPY vectorcode/ ./vectorcode/
COPY districts/ ./districts/
COPY cloud/agent_workers/workers.py ./workers.py
COPY cloud/agent_workers/scheduler.py ./scheduler.py

USER vector

ENTRYPOINT ["tini", "--"]
CMD ["python", "workers.py"]
