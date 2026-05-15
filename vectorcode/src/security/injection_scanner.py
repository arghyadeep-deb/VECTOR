"""Injection scanner shim — re-exports from vc_security.injection_scanner."""
try:
    from vectorcode.src.vc_security.injection_scanner import *
    from vectorcode.src.vc_security.injection_scanner import InjectionScanner
except ImportError:
    class InjectionScanner:
        def scan(self, text: str) -> list: return []

from vectorcode.src.security.types import InjectionScanResult
