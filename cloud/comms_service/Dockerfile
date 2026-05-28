FROM python:3.11-slim AS builder
WORKDIR /app

# Install tini for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

# Deps layer — copy only requirements so Docker cache is not busted by source changes
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

# Copy service source + shared VECTOR packages
COPY core/ ./core/
COPY vectorcode/ ./vectorcode/
COPY districts/ ./districts/
COPY cloud/comms_service/service.py ./service.py

ENV PORT=8001 BIND_HOST=0.0.0.0

USER vector
EXPOSE 8001

ENTRYPOINT ["tini", "--"]
CMD ["python", "service.py"]
