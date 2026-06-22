FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VECTOR_ENV=production

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN test -d /app/core -a -d /app/districts -a -f /app/cloud/agent_workers/workers.py

CMD ["python", "cloud/agent_workers/workers.py"]
