FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VECTOR_ENV=production \
    PORT=8001

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN test -d /app/core -a -d /app/vectorcode -a -f /app/cloud/comms_service/service.py

EXPOSE 8001
CMD ["python", "cloud/comms_service/service.py"]
