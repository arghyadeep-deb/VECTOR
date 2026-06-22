FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VECTOR_ENV=production \
    VECTOR_SERVICE=comms \
    PORT=8001

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN test -d /app/core -a -d /app/vectorcode -a -d /app/districts \
    -a -f /app/cloud/comms_service/service.py \
    -a -f /app/cloud/agent_workers/workers.py

EXPOSE 8001

CMD ["python", "-c", "import os, runpy; runpy.run_path('cloud/agent_workers/workers.py' if os.environ.get('VECTOR_SERVICE') == 'workers' else 'cloud/comms_service/service.py', run_name='__main__')"]
