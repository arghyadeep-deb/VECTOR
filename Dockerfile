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
