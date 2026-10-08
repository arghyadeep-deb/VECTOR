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


class SecurityInitializationError(RuntimeError):
    """Raised when an enabled security control cannot be initialized."""


def _initialization_error(control: str, exc: Exception) -> SecurityInitializationError:
    logger.opt(exception=True).critical(
        "[VECTOR][security] Mandatory {} initialization failed", control
    )
    return SecurityInitializationError(
        f"Security startup refused: mandatory {control} initialization failed"
    )

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

    # Scanner controls are mandatory when either scanner is configured on.
    # An individually disabled scanner is optional by explicit configuration.
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
                max_stream_buffer_chars=getattr(
                    config.security, "max_stream_buffer_chars", 1_048_576
                ),
                bus=bus,
            )
    except Exception as exc:
        raise _initialization_error("scanner controls", exc) from exc

    # Capability policy
    cap_policy = None
    # Capability enforcement is mandatory only when explicitly enabled.
    if config.security.capabilities.enabled:
        try:
            from vectorcode.src.vc_security.capabilities import CapabilityPolicy

            cap_policy = CapabilityPolicy(
                policy_path=config.security.capabilities.policy_path or None,
                default_deny=True,
            )
        except Exception as exc:
            raise _initialization_error("capability policy", exc) from exc

    # Audit is mandatory whenever the security subsystem is enabled. There is
    # currently no separate config switch declaring audit optional.
    try:
        audit = AuditLogger(
            db_path=config.security.audit_log_path,
            bus=bus,
        )
    except Exception as exc:
        raise _initialization_error("audit control", exc) from exc

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
    "SecurityInitializationError",
    "SecurityEvent",
    "SecurityEventType",
    "ThreatLevel",
    "check_ssrf",
    "filter_sensitive_paths",
    "is_private_ip",
    "is_sensitive_file",
    "setup_security",
]
