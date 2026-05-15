"""CLI shim for scan_cmd."""
try:
    from vectorcode.src.vector_cli.scan_cmd import *
except ImportError:
    pass
class PrivacyScanner:
    def scan(self, path) -> list: return []

