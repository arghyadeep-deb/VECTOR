"""Prometheus-style metrics for circuit breaker states and bulkhead utilization."""

from __future__ import annotations

import json
from typing import Any


class ResilienceMetrics:
    def __init__(self):
        self._circuit_breaker_states: dict[str, dict[str, Any]] = {}
        self._bulkhead_stats: dict[str, dict[str, Any]] = {}
        self._failover_events: list[dict[str, Any]] = []
        self._degradation_events: list[dict[str, Any]] = []
        self._chaos_experiments: list[dict[str, Any]] = []

    def record_circuit_breaker(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self._circuit_breaker_states = snapshots

    def record_bulkheads(self, stats: dict[str, dict[str, Any]]) -> None:
        self._bulkhead_stats = stats

    def record_failover(self, event: dict[str, Any]) -> None:
        self._failover_events.append(event)
        if len(self._failover_events) > 100:
            self._failover_events.pop(0)

    def record_degradation(self, event: dict[str, Any]) -> None:
        self._degradation_events.append(event)
        if len(self._degradation_events) > 100:
            self._degradation_events.pop(0)

    def record_chaos_experiment(self, result: dict[str, Any]) -> None:
        self._chaos_experiments.append(result)
        if len(self._chaos_experiments) > 100:
            self._chaos_experiments.pop(0)

    def get_health_summary(self) -> dict[str, Any]:
        open_cbs = sum(1 for s in self._circuit_breaker_states.values() if s.get("state") == "open")
        half_open_cbs = sum(1 for s in self._circuit_breaker_states.values() if s.get("state") == "half_open")
        total_rejected = sum(s.get("total_rejected", 0) for s in self._bulkhead_stats.values())
        total_errors = sum(s.get("total_errors", 0) for s in self._bulkhead_stats.values())

        return {
            "circuit_breakers": {
                "total": len(self._circuit_breaker_states),
                "open": open_cbs,
                "half_open": half_open_cbs,
                "closed": len(self._circuit_breaker_states) - open_cbs - half_open_cbs,
            },
            "bulkheads": {
                "total": len(self._bulkhead_stats),
                "rejected_count": total_rejected,
                "error_count": total_errors,
            },
            "failover": {
                "total_events": len(self._failover_events),
                "last_event": self._failover_events[-1] if self._failover_events else None,
            },
            "degradation": {
                "current_tier": self._degradation_events[-1].get("new_tier") if self._degradation_events else "full",
                "total_events": len(self._degradation_events),
            },
            "chaos": {
                "experiments_run": len(self._chaos_experiments),
                "pass_rate": self._chaos_pass_rate(),
            },
        }

    def _chaos_pass_rate(self) -> float | None:
        # None (not 1.0) when nothing has run -- "no chaos experiments yet"
        # is not the same as "100% pass rate", and chaos.enabled defaults
        # to False so this is the common case, not an edge case.
        if not self._chaos_experiments:
            return None
        passed = sum(1 for e in self._chaos_experiments if e.get("passed", False))
        return passed / len(self._chaos_experiments)

    def to_json(self) -> str:
        return json.dumps(self.get_health_summary(), indent=2, default=str)
