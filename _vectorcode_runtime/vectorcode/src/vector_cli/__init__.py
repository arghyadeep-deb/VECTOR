"""
VectorCode CLI - Unified command-line interface for VectorCode.

Provides subcommands for:
- vector chat          - Interactive chat (same as ./vector)
- vector gateway       - Run gateway in foreground
- vector gateway start - Start gateway service
- vector gateway stop  - Stop gateway service  
- vector setup         - Interactive setup wizard
- vector status        - Show status of all components
- vector cron          - Manage cron jobs
"""
from loguru import logger

__version__ = "0.11.0"
__release_date__ = "2026.4.23"

try:
    from vectorcode.src.vector_cli import kanban_db
except ImportError as e:
    logger.debug("[VECTOR][vector_cli] kanban_db unavailable: {}", e)
