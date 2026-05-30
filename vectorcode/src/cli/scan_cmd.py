from loguru import logger
"""CLI shim for scan_cmd."""
try:
    from vectorcode.src.vector_cli.scan_cmd import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
class PrivacyScanner:
    def scan(self, path) -> list: return []

