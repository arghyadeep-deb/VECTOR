"""Compatibility shim; ``vectorcode.src.vc_security`` is canonical."""

from vectorcode.src.vc_security.injection_scanner import (
    InjectionScanner,
    InjectionScanResult,
)

__all__ = ["InjectionScanner", "InjectionScanResult"]
