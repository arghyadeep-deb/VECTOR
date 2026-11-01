"""Single point of contact between Python and the Rust ``vectorcode.src_rust`` module.

Gap 13 fix: The compiled Rust extension (.pyd) does not exist in this repo.
All callers now get a graceful Python fallback instead of a hard ImportError.
RUST_AVAILABLE is False; callers should check it before using Rust-specific paths.
"""

from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    import types as _types


@functools.lru_cache(maxsize=1)
def get_rust_module() -> "_types.ModuleType | None":
    """Return the ``vectorcode.src_rust`` module, or None if not compiled."""
    try:
        import vectorcode.src_rust  # type: ignore[import-untyped]
        return vectorcode.src_rust
    except ImportError:
        return None


RUST_AVAILABLE: bool = get_rust_module() is not None


# ---------------------------------------------------------------------------
# JSON -> Python dataclass converters (pure-Python, no Rust required)
# ---------------------------------------------------------------------------


def scan_result_from_json(json_str: str) -> object:
    from vectorcode.src.security.types import ScanFinding, ScanResult, ThreatLevel
    data = json.loads(json_str)
    findings: List[ScanFinding] = []
    for f in data.get("findings", []):
        findings.append(ScanFinding(
            pattern_name=f.get("pattern_name", ""),
            matched_text=f.get("matched_text", ""),
            threat_level=ThreatLevel(f.get("threat_level", "low").lower()),
            start=f.get("start", 0), end=f.get("end", 0),
            description=f.get("description", ""),
        ))
    return ScanResult(findings=findings)


def injection_result_from_json(json_str: str) -> object:
    from vectorcode.src.security.injection_scanner import InjectionScanResult
    from vectorcode.src.security.types import ScanFinding, ThreatLevel
    data = json.loads(json_str)
    findings: List[ScanFinding] = []
    for f in data.get("findings", []):
        findings.append(ScanFinding(
            pattern_name=f.get("pattern_name", ""),
            matched_text=f.get("matched_text", ""),
            threat_level=ThreatLevel(f.get("threat_level", "low").lower()),
            start=f.get("start", 0), end=f.get("end", 0),
            description=f.get("description", ""),
        ))
    try:
        threat = ThreatLevel(data.get("threat_level", "low").lower())
    except ValueError:
        threat = ThreatLevel.LOW
    return InjectionScanResult(
        is_clean=data.get("is_clean", True), findings=findings, threat_level=threat,
    )


def retrieval_results_from_json(json_str: str) -> list:
    from vectorcode.src.tools.storage._abc import RetrievalResult
    items = json.loads(json_str)
    results: List[RetrievalResult] = []
    for item in items:
        meta = item.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        results.append(RetrievalResult(
            content=item.get("content", ""), score=float(item.get("score", 0.0)),
            source=item.get("source", ""), metadata=meta,
        ))
    return results


def optimization_store_from_rust(path: str = ":memory:") -> object | None:
    mod = get_rust_module()
    if mod is None:
        return None
    try:
        return mod.OptimizationStore(path)
    except Exception:
        return None


def trial_result_from_json(json_str: str) -> dict:
    return json.loads(json_str)


def optimization_run_from_json(json_str: str) -> dict:
    return json.loads(json_str)


def generate_result_from_json(json_str: str) -> dict:
    data = json.loads(json_str)
    return {
        "content": data.get("content", ""),
        "model": data.get("model", ""),
        "finish_reason": data.get("finish_reason", "stop"),
        "usage": data.get("usage", {}),
        "tool_calls": data.get("tool_calls"),
        "ttft": data.get("ttft", 0.0),
        "cost_usd": data.get("cost_usd", 0.0),
        "metadata": data.get("metadata", {}),
    }


__all__ = [
    "RUST_AVAILABLE", "generate_result_from_json", "get_rust_module",
    "injection_result_from_json", "optimization_run_from_json",
    "optimization_store_from_rust", "retrieval_results_from_json",
    "scan_result_from_json", "trial_result_from_json",
]
