FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /sandbox

COPY sandbox_entrypoint.py /sandbox/sandbox_entrypoint.py

# No network, no VECTOR source tree, no writable layer beyond /sandbox --
# real isolation comes from `docker run --network none` + read-only mounts
# in core/sandbox/runner.py's ContainerRunner, not from anything in here.
ENTRYPOINT ["python3", "/sandbox/sandbox_entrypoint.py"]
