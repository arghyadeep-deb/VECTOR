"""BiometricsAggregator — pulls Apple Health + Oura + Strava via absorbed
VectorCode connectors and writes structured biometric records to
episodic_memory. Other Health-district agents (SleepTracker, FatigueMonitor,
ExerciseLogger) opportunistically read these enriched records.

Runs once per day at 06:00 (when configured via the durable scheduler).

Failure modes are silent — if a connector is unavailable, that source is
skipped without crashing the loop.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import uuid


from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync


class BiometricsAggregator(AgentBase):
    """Aggregate sleep / heart rate / activity / readiness from external sources.

    Sources (each guarded by its own try/except):
      • Apple Health — via vectorcode.src.connectors.apple_health
      • Oura          — via vectorcode.src.connectors.oura
      • Strava        — via vectorcode.src.connectors.strava

    Writes one record per source per day to episodic_memory with:
      event_type = "biometrics"
      content    = JSON dump of normalized payload
      tags       = ["biometrics", "<source>", "auto"]

    Optionally writes a daily summary to Obsidian under Health/.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="BiometricsAggregator",
            district="health",
            generation=generation,
        )
        self.capabilities = ["biometrics", "get_daily_summary", "get_recent_activities", "get_recent_summary", "health", "metrics", "source"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        try:
            self._obsidian: ObsidianSync | None = ObsidianSync()
        except Exception:
            self._obsidian = None
        logger.info(f"[VECTOR][biometrics] ready gen={generation}")

    # ── Sources ──────────────────────────────────────────────────────────────

    async def _pull_apple_health(self) -> dict | None:
        try:
            from vectorcode.src.connectors.apple_health import (  # type: ignore
                AppleHealthConnector,
            )
        except Exception as exc:
            logger.debug(f"[VECTOR][biometrics] apple_health unavailable: {exc}")
            return None
        try:
            connector = AppleHealthConnector()
            for name in ("get_recent_summary", "today_summary", "summary",
                         "fetch_today", "snapshot"):
                fn = getattr(connector, name, None)
                if callable(fn):
                    raw = fn()
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if not raw:
                        continue
                    return self._normalize(raw, source="apple_health")
        except Exception as exc:
            logger.warning(f"[VECTOR][biometrics] apple_health fetch failed: {exc}")
        return None

    async def _pull_oura(self) -> dict | None:
        try:
            from vectorcode.src.connectors.oura import OuraConnector  # type: ignore
        except Exception as exc:
            logger.debug(f"[VECTOR][biometrics] oura unavailable: {exc}")
            return None
        try:
            connector = OuraConnector()
            for name in ("get_daily_summary", "today_summary", "summary",
                         "fetch_today", "snapshot", "get_readiness"):
                fn = getattr(connector, name, None)
                if callable(fn):
                    raw = fn()
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if not raw:
                        continue
                    return self._normalize(raw, source="oura")
        except Exception as exc:
            logger.warning(f"[VECTOR][biometrics] oura fetch failed: {exc}")
        return None

    async def _pull_strava(self) -> dict | None:
        try:
            from vectorcode.src.connectors.strava import StravaConnector  # type: ignore
        except Exception as exc:
            logger.debug(f"[VECTOR][biometrics] strava unavailable: {exc}")
            return None
        try:
            connector = StravaConnector()
            for name in ("get_recent_activities", "recent_activities", "today_activities",
                         "fetch_recent", "snapshot"):
                fn = getattr(connector, name, None)
                if callable(fn):
                    raw = fn()
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if not raw:
                        continue
                    return self._normalize(raw, source="strava")
        except Exception as exc:
            logger.warning(f"[VECTOR][biometrics] strava fetch failed: {exc}")
        return None

    @staticmethod
    def _normalize(raw: object, source: str) -> dict:
        """Coerce arbitrary connector output into a flat dict + raw blob.

        Pulls these well-known keys when present:
          sleep_hours, deep_sleep_hours, rem_sleep_hours,
          steps, active_minutes, heart_rate_avg, heart_rate_resting,
          hrv_ms, readiness, calories
        """
        keys = {
            "sleep_hours", "deep_sleep_hours", "rem_sleep_hours",
            "steps", "active_minutes",
            "heart_rate_avg", "heart_rate_resting", "hrv_ms",
            "readiness", "calories", "stress_score", "spo2",
        }
        flat: dict = {"source": source}
        if isinstance(raw, dict):
            for k in keys:
                if k in raw:
                    flat[k] = raw[k]
            # Some Apple Health adapters nest under 'metrics' or 'today'
            for nested_key in ("metrics", "today", "summary", "data"):
                nested = raw.get(nested_key)
                if isinstance(nested, dict):
                    for k in keys:
                        if k in nested and k not in flat:
                            flat[k] = nested[k]
            flat["raw"] = raw
        else:
            flat["raw"] = raw
        return flat

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist(self, payload: dict) -> None:
        try:
            self._memory.store(
                event_type="biometrics",
                content=json.dumps(payload, default=str)[:4000],
                tags=["biometrics", payload.get("source", "unknown"), "auto"],
                source="biometrics_aggregator",
            )
        except Exception as exc:
            logger.warning(f"[VECTOR][biometrics] persist failed: {exc}")

    def _write_obsidian(self, all_payloads: list[dict]) -> None:
        if not self._obsidian or not all_payloads:
            return
        try:
            today = datetime.date.today().isoformat()
            lines = [f"# Biometrics — {today}", ""]
            for p in all_payloads:
                src = p.get("source", "unknown")
                lines.append(f"## {src}")
                for k, v in p.items():
                    if k in ("source", "raw"):
                        continue
                    lines.append(f"- **{k}**: {v}")
                lines.append("")
            self._obsidian.write_note(
                folder="Health",
                title=f"{today} biometrics",
                content="\n".join(lines),
            )
        except Exception as exc:
            logger.warning(f"[VECTOR][biometrics] obsidian write failed: {exc}")

    # ── Entry points ─────────────────────────────────────────────────────────

    async def run(self, task: dict | None = None) -> dict:
        """Pull every source, persist results, return summary.

        Task params (all optional):
          sources: list[str]  — restrict to subset of {"apple_health","oura","strava"}
          obsidian: bool      — write a daily note to Health/ (default True)
        """
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- sources/
        # obsidian below were read straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged.
        task = task or {}
        task = {**task, **(task.get("params") or {})}
        wanted = set(task.get("sources") or ["apple_health", "oura", "strava"])
        write_md = bool(task.get("obsidian", True))

        results: list[dict] = []
        sources_attempted: list[str] = []

        if "apple_health" in wanted:
            sources_attempted.append("apple_health")
            payload = await self._pull_apple_health()
            if payload:
                self._persist(payload)
                results.append(payload)

        if "oura" in wanted:
            sources_attempted.append("oura")
            payload = await self._pull_oura()
            if payload:
                self._persist(payload)
                results.append(payload)

        if "strava" in wanted:
            sources_attempted.append("strava")
            payload = await self._pull_strava()
            if payload:
                self._persist(payload)
                results.append(payload)

        if write_md:
            self._write_obsidian(results)

        return {
            # Zero successful sources is not a successful health scan. It can
            # mean missing configuration or connector failure, but never
            # evidence of a healthy/clean state.
            "status": "ok",
            "assessment_status": "complete" if results else "unavailable",
            "sources_attempted": sources_attempted,
            "sources_succeeded": [p["source"] for p in results],
            "records": len(results),
        }

    async def run_forever(self) -> None:
        """Cron-style daily pull at 06:00 local. Never crashes."""
        last_run_date: datetime.date | None = None
        while True:
            try:
                now = datetime.datetime.now()
                if now.hour >= 6 and last_run_date != now.date():
                    await self.run()
                    last_run_date = now.date()
            except Exception as exc:
                logger.error(f"[VECTOR][biometrics] run_forever tick failed: {exc}")
            await asyncio.sleep(600)  # check every 10 min


# Public alias matching the rest of the agent registry conventions
__all__ = ["BiometricsAggregator"]
