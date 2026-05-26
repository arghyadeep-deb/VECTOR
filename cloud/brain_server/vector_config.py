"""Minimal standalone CONFIG for cloud/brain_server — no VECTOR codebase dependency.

Used when the full VECTOR core/ is not available (Docker build without project root).
Values are read from environment variables; sensible defaults are provided.
"""
from __future__ import annotations

import os

CONFIG: dict = {
    "system_name": os.environ.get("VECTOR_SYSTEM_NAME", "VECTOR"),
    "version": os.environ.get("VECTOR_VERSION", "1.0.0"),
    "env": os.environ.get("VECTOR_ENV", "production"),
    "allowed_origins": [
        o.strip()
        for o in os.environ.get("VECTOR_ALLOWED_ORIGINS", "*").split(",")
        if o.strip()
    ],
}
