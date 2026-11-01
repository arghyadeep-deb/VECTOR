"""
SwarmMonitor — complete reference real-time-monitor.ts + health-check.ts + diagnostics.ts absorption.

Absorbed from reference v2/src/monitoring/:
  - real-time-monitor.ts  → take_snapshot(), get_metrics(window_seconds)
  - health-check.ts       → run_health_check() → HealthReport
  - diagnostics.ts        → run_diagnostics() → DiagnosticsReport
  - per-agent metrics, per-channel statistics feed
  - alert thresholds: stall_seconds, low_hp_threshold, high_error_rate
"""
import time
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    from swarm import SwarmCoordinator
    from message_bus import MessageBus


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class AgentMetric:
    agent_id:    str
    agent_name:  str
    status:      str
    hp:          int
    tasks_completed: int
    tasks_failed:    int
    error_rate:  float   # tasks_failed / total tasks
    uptime_s:    float   # seconds since first task or spawn


@dataclass
class SwarmSnapshot:
    """Point-in-time swarm state — reference real-time-monitor snapshot."""
    ts:         float
    active:     int
    idle:       int
    busy:       int
    stalled:    int
    dead:       int
    total_completed: int
    total_failed:    int
    agents:     list     # [AgentMetric]
    topology:   str      = ""
    raft_leader: str      = ""


@dataclass
class HealthStatus:
    name:     str
    ok:       bool
    message:  str
    severity: str = "info"   # info / warning / critical


@dataclass
class HealthReport:
    """reference health-check.ts output — per-component status."""
    ts:       float
    healthy:  bool
    checks:   list   # [HealthStatus]
    summary:  str    = ""


@dataclass
class DiagnosticsReport:
    """reference diagnostics.ts output — deeper system analysis."""
    ts:                float
    total_agents:      int
    stalled_agents:    list   # [agent_id]
    low_hp_agents:     list   # [agent_id]
    high_error_agents: list   # [agent_id]
    dead_agents:       int
    avg_hp:            float
    bus_stats:         dict   # channel → stats
    recommendations:   list   # [str]
    alerts:            list   # [str]


# ── SwarmMonitor ──────────────────────────────────────────────────────────────

class SwarmMonitor:
    """
    Real-time swarm health monitoring absorbed from reference's monitoring/ module.
    Attach to a SwarmCoordinator (and optionally a MessageBus) to get
    live metrics, health checks, and diagnostic reports.
    """

    # Alert thresholds
    STALL_SECONDS       = 120.0   # busy > N seconds → stalled
    LOW_HP_THRESHOLD    = 100     # HP below this → low_hp alert
    HIGH_ERROR_RATE     = 0.30    # 30%+ failure rate → alert
    SNAPSHOT_BUFFER     = 500     # keep last N snapshots

    def __init__(self):
        self._snapshots: deque = deque(maxlen=self.SNAPSHOT_BUFFER)
        self._start_ts: float = time.time()

    # ── Snapshot (reference real-time-monitor.ts takeSnapshot) ────────────────────

    def take_snapshot(self, swarm: "SwarmCoordinator") -> SwarmSnapshot:
        """Capture a point-in-time swarm state."""
        report = swarm.report()
        now    = time.time()

        agents = []
        stalled = 0
        for info in report.get("agents", []):
            started = info.get("task_started_at", now)
            status  = info.get("status", "idle")
            completed = info.get("tasks_completed", 0)
            failed    = info.get("tasks_failed", 0)
            total     = completed + failed
            error_rate = round(failed / total, 3) if total > 0 else 0.0

            if status == "busy" and (now - started) > self.STALL_SECONDS:
                status = "stalled"
                stalled += 1

            agents.append(AgentMetric(
                agent_id=info.get("id", "?"),
                agent_name=info.get("name", "?"),
                status=status,
                hp=info.get("hp", 500),
                tasks_completed=completed,
                tasks_failed=failed,
                error_rate=error_rate,
                uptime_s=round(now - started if started else 0.0, 1),
            ))

        snap = SwarmSnapshot(
            ts=now,
            active=report.get("active", 0),
            idle=sum(1 for a in agents if a.status == "idle"),
            busy=sum(1 for a in agents if a.status == "busy"),
            stalled=stalled,
            dead=sum(1 for a in agents if a.status == "dead"),
            total_completed=sum(a.tasks_completed for a in agents),
            total_failed=sum(a.tasks_failed for a in agents),
            agents=agents,
            topology=report.get("topology", ""),
            raft_leader=report.get("raft_leader") or "",
        )
        self._snapshots.append(snap)
        return snap

    # ── Health check (reference health-check.ts) ──────────────────────────────────

    def run_health_check(self, swarm: "SwarmCoordinator", bus: Optional["MessageBus"] = None) -> HealthReport:
        """Run all health checks. Returns HealthReport."""
        checks: list[HealthStatus] = []
        now = time.time()
        snap = self.take_snapshot(swarm)

        # 1. Agent liveness
        if snap.active == 0:
            checks.append(HealthStatus("agent_liveness", False, "No agents in swarm", "critical"))
        else:
            checks.append(HealthStatus("agent_liveness", True, f"{snap.active} agents active"))

        # 2. Stall detection
        if snap.stalled > 0:
            checks.append(HealthStatus(
                "stall_detection", False,
                f"{snap.stalled} agent(s) stalled (>{self.STALL_SECONDS}s)", "warning"
            ))
        else:
            checks.append(HealthStatus("stall_detection", True, "No stalled agents"))

        # 3. HP health
        low_hp = [a for a in snap.agents if a.hp < self.LOW_HP_THRESHOLD]
        if low_hp:
            checks.append(HealthStatus(
                "hp_health", False,
                f"{len(low_hp)} agent(s) below HP {self.LOW_HP_THRESHOLD}: "
                f"{[a.agent_id for a in low_hp]}", "warning"
            ))
        else:
            checks.append(HealthStatus("hp_health", True, "All agents healthy HP"))

        # 4. Error rate
        high_err = [a for a in snap.agents if a.error_rate >= self.HIGH_ERROR_RATE]
        if high_err:
            checks.append(HealthStatus(
                "error_rate", False,
                f"{len(high_err)} agent(s) high error rate: "
                f"{[a.agent_id for a in high_err]}", "warning"
            ))
        else:
            checks.append(HealthStatus("error_rate", True, "Error rates within threshold"))

        # 5. MessageBus health
        if bus is not None:
            all_stats = bus.get_stats()
            total_denied = sum(v.get("acl_denied", 0) for v in all_stats.values())
            if total_denied > 100:
                checks.append(HealthStatus(
                    "bus_acl", False, f"High ACL denials: {total_denied}", "warning"
                ))
            else:
                checks.append(HealthStatus("bus_acl", True, f"Bus ACL OK ({total_denied} denials)"))

        healthy = all(c.ok for c in checks if c.severity != "info")
        summary = (
            f"{sum(1 for c in checks if c.ok)}/{len(checks)} checks passing"
        )
        report = HealthReport(ts=now, healthy=healthy, checks=checks, summary=summary)
        logger.info(f"[VECTOR][monitor] health: {summary} — {'OK' if healthy else 'ISSUES'}")
        return report

    # ── Diagnostics (reference diagnostics.ts) ────────────────────────────────────

    def run_diagnostics(self, swarm: "SwarmCoordinator", bus: Optional["MessageBus"] = None) -> DiagnosticsReport:
        """Deep diagnostics — identifies stalled agents, low HP, high error rates."""
        snap = self.take_snapshot(swarm)
        now  = time.time()

        stalled_ids    = [a.agent_id for a in snap.agents if a.status == "stalled"]
        low_hp_ids     = [a.agent_id for a in snap.agents if a.hp < self.LOW_HP_THRESHOLD]
        high_error_ids = [a.agent_id for a in snap.agents if a.error_rate >= self.HIGH_ERROR_RATE]
        avg_hp = float(
            statistics.mean(a.hp for a in snap.agents)
            if snap.agents else 0.0
        )

        bus_stats = bus.get_stats() if bus else {}

        recommendations = []
        alerts = []

        if stalled_ids:
            alerts.append(f"STALLED: {stalled_ids} — redecompose tasks")
            recommendations.append("Use QueenCoordinator.decompose() on stalled tasks")
        if low_hp_ids:
            alerts.append(f"LOW HP: {low_hp_ids}")
            recommendations.append("Spawn replacement agents for low-HP agents")
        if high_error_ids:
            alerts.append(f"HIGH ERROR RATE: {high_error_ids}")
            recommendations.append("Review task routing — consider topology change")
        if snap.dead > 0:
            alerts.append(f"DEAD AGENTS: {snap.dead}")
            recommendations.append("Ghost memory preserved — spawn successors")
        if avg_hp < 300:
            recommendations.append("Overall HP critically low — consider council review")

        report = DiagnosticsReport(
            ts=now,
            total_agents=snap.active,
            stalled_agents=stalled_ids,
            low_hp_agents=low_hp_ids,
            high_error_agents=high_error_ids,
            dead_agents=snap.dead,
            avg_hp=round(avg_hp, 1),
            bus_stats=bus_stats,
            recommendations=recommendations,
            alerts=alerts,
        )
        logger.info(
            f"[VECTOR][monitor] diagnostics: {snap.active} agents, "
            f"{len(alerts)} alerts, avg_hp={avg_hp:.0f}"
        )
        return report

    # ── Metrics window (reference per-agent metrics feed) ─────────────────────────

    def get_metrics(self, window_seconds: float = 300.0) -> dict:
        """
        Aggregate metrics over a rolling time window.
        reference real-time-monitor: emits per-agent and aggregate stats.
        """
        cutoff = time.time() - window_seconds
        window = [s for s in self._snapshots if s.ts >= cutoff]
        if not window:
            return {"window_seconds": window_seconds, "samples": 0}

        avg_active = statistics.mean(s.active for s in window)
        avg_busy   = statistics.mean(s.busy   for s in window)
        avg_idle   = statistics.mean(s.idle   for s in window)
        total_completed = window[-1].total_completed - window[0].total_completed
        total_failed    = window[-1].total_failed    - window[0].total_failed

        return {
            "window_seconds":    window_seconds,
            "samples":           len(window),
            "avg_active_agents": round(avg_active, 1),
            "avg_busy":          round(avg_busy, 1),
            "avg_idle":          round(avg_idle, 1),
            "tasks_completed":   total_completed,
            "tasks_failed":      total_failed,
            "throughput_per_min": round(total_completed / (window_seconds / 60), 2),
        }

    def snapshot_history(self, limit: int = 10) -> list[dict]:
        """Recent snapshots as plain dicts."""
        snaps = list(self._snapshots)[-limit:]
        return [
            {
                "ts": s.ts, "active": s.active, "idle": s.idle,
                "busy": s.busy, "stalled": s.stalled,
                "topology": s.topology, "raft_leader": s.raft_leader,
            }
            for s in snaps
        ]


if __name__ == "__main__":
    from swarm import SwarmCoordinator, Topology
    from message_bus import MessageBus

    sc = SwarmCoordinator(topology=Topology.HIERARCHICAL)
    sc.spawn("coder")
    sc.spawn("reviewer")

    monitor = SwarmMonitor()

    # Snapshot
    snap = monitor.take_snapshot(sc)
    assert snap.active == 2
    assert snap.topology == "hierarchical"
    assert len(snap.agents) == 2

    # Health check
    bus = MessageBus()
    health = monitor.run_health_check(sc, bus)
    assert isinstance(health.healthy, bool)
    assert len(health.checks) >= 4
    assert health.summary != ""

    # Diagnostics
    diag = monitor.run_diagnostics(sc, bus)
    assert diag.total_agents == 2
    assert isinstance(diag.avg_hp, float)
    assert isinstance(diag.recommendations, list)

    # Metrics window
    metrics = monitor.get_metrics(window_seconds=60)
    assert "samples" in metrics
    assert "avg_active_agents" in metrics

    # Snapshot history
    history = monitor.snapshot_history(limit=5)
    assert len(history) >= 1
    assert "ts" in history[0]

    print(f"monitoring.py OK — {len(health.checks)} health checks, {len(diag.alerts)} alerts")


