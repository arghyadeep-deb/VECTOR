"""Regression for three more vc_security classes that called
get_rust_module().<Thing>() unconditionally: when the Rust extension isn't
built, get_rust_module() returns None (confirmed on this machine), so each
of these classes could never even be constructed, let alone used.

- CapabilityPolicy (capabilities.py): the RBAC policy gating tool
  dispatch. grant()/deny()/check() had the same unconditional
  self._rust_impl.* calls.
- RateLimiter (rate_limiter.py): check()/reset() had the same shape;
  reset() additionally had dead Python fallback code stranded after an
  unconditional early `return`.
- SecretScanner / PIIScanner (scanner.py): neither had ANY Python
  fallback at all, despite complete, ready-to-use PATTERNS regex dicts
  sitting unused in the same file.
"""
from __future__ import annotations

from unittest import mock

import pytest

from vectorcode.src.vc_security.capabilities import CapabilityPolicy
from vectorcode.src.vc_security.rate_limiter import RateLimitConfig, RateLimiter
from vectorcode.src.vc_security.scanner import PIIScanner, SecretScanner


def _no_rust():
    return mock.patch(
        "vectorcode.src._rust_bridge.get_rust_module", return_value=None
    )


def test_capability_policy_constructs_and_checks_without_rust():
    with _no_rust():
        policy = CapabilityPolicy(default_deny=True)
        policy.grant("agent1", "file:read")
        assert policy.check("agent1", "file:read") is True
        assert policy.check("agent1", "file:write") is False


def test_capability_policy_explicit_deny_overrides_grant_without_rust():
    with _no_rust():
        policy = CapabilityPolicy(default_deny=False)
        policy.grant("agent1", "file:*")
        policy.deny("agent1", "file:write")
        assert policy.check("agent1", "file:write") is False
        assert policy.check("agent1", "file:read") is True


@pytest.mark.asyncio
async def test_rate_limiter_enforces_burst_limit_without_rust():
    with _no_rust():
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60, burst_size=2))
        allowed1, _ = await limiter.check("k1")
        allowed2, _ = await limiter.check("k1")
        allowed3, wait = await limiter.check("k1")
    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is False
    assert wait > 0


@pytest.mark.asyncio
async def test_rate_limiter_reset_clears_bucket_without_rust():
    with _no_rust():
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60, burst_size=1))
        await limiter.check("k1")
        blocked, _ = await limiter.check("k1")
        assert blocked is False
        await limiter.reset("k1")
        allowed_after_reset, _ = await limiter.check("k1")
    assert allowed_after_reset is True


def test_secret_scanner_detects_and_redacts_without_rust():
    with _no_rust():
        scanner = SecretScanner()
        text = "key=sk-abcdefghijklmnopqrstuvwxyz123456"
        result = scanner.scan(text)
        redacted = scanner.redact(text)
    assert any(f.pattern_name == "openai_key" for f in result.findings)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in redacted


def test_pii_scanner_detects_email_and_ssn_without_rust():
    with _no_rust():
        scanner = PIIScanner()
        result = scanner.scan("contact me at foo@example.com or 123-45-6789")
    names = {f.pattern_name for f in result.findings}
    assert "email" in names
    assert "us_ssn" in names
