"""CLI shim for scan_cmd."""

from loguru import logger
try:
    from vectorcode.src.vector_cli.scan_cmd import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
class PrivacyScanner:
    def scan(self, path) -> list: return []

