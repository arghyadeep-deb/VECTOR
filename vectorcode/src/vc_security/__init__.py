# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Security guardrails — scanners, engine wrapper, audit, SSRF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from vectorcode.src.vc_core.events import EventBus
from vectorcode.src.vc_security._abc import BaseScanner
from vectorcode.src.vc_security.audit import AuditLogger
from vectorcode.src.vc_security.file_policy import (
    DEFAULT_SENSITIVE_PATTERNS,
    filter_sensitive_paths,
    is_sensitive_file,
)
from vectorcode.src.vc_security.guardrails import GuardrailsEngine, SecurityBlockError
from vectorcode.src.vc_security.scanner import PIIScanner, SecretScanner
from vectorcode.src.vc_security.ssrf import check_ssrf, is_private_ip
from vectorcode.src.vc_security.types import (
    RedactionMode,
    ScanFinding,
    ScanResult,
    SecurityEvent,
    SecurityEventType,
    ThreatLevel,
)

@dataclass
class SecurityContext:
    """Result of setup_security() — wrapped engine, policy, audit."""

    engine: Any
    capability_policy: Any = None
    audit_logger: Any = None

def setup_security(
    config: Any,
    engine: Any,
    bus: Optional[EventBus] = None,
) -> SecurityContext:
    """Apply security guardrails to an engine based on config.

    Returns a SecurityContext. No-ops if config.security.enabled is False.
    """
    if not config.security.enabled:
        return SecurityContext(engine=engine)

    # Scanners + engine wrapping
    try:
        scanners: list[BaseScanner] = []
        if config.security.secret_scanner:
            scanners.append(SecretScanner())
        if config.security.pii_scanner:
            scanners.append(PIIScanner())

        if scanners:
            mode = RedactionMode(config.security.mode)
            engine = GuardrailsEngine(
                engine,
                scanners=scanners,
                mode=mode,
                scan_input=config.security.scan_input,
                scan_output=config.security.scan_output,
                bus=bus,
            )
    except Exception as exc:
        logger.debug("Failed to set up security scanners: {}", exc)

    # Capability policy
    cap_policy = None
    if config.security.capabilities.enabled:
        try:
            from vectorcode.src.vc_security.capabilities import CapabilityPolicy

            cap_policy = CapabilityPolicy(
                policy_path=config.security.capabilities.policy_path or None,
            )
        except Exception as exc:
            logger.debug("Failed to set up capability policy: {}", exc)

    # Audit logger
    audit = None
    try:
        audit = AuditLogger(
            db_path=config.security.audit_log_path,
            bus=bus,
        )
    except Exception as exc:
        logger.debug("Failed to set up audit logger: {}", exc)

    return SecurityContext(
        engine=engine,
        capability_policy=cap_policy,
        audit_logger=audit,
    )

__all__ = [
    "AuditLogger",
    "BaseScanner",
    "DEFAULT_SENSITIVE_PATTERNS",
    "GuardrailsEngine",
    "PIIScanner",
    "RedactionMode",
    "ScanFinding",
    "ScanResult",
    "SecretScanner",
    "SecurityBlockError",
    "SecurityContext",
    "SecurityEvent",
    "SecurityEventType",
    "ThreatLevel",
    "check_ssrf",
    "filter_sensitive_paths",
    "is_private_ip",
    "is_sensitive_file",
    "setup_security",
]
