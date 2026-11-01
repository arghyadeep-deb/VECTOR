"""
Module: core/sensing/health_monitor.py
HealthMonitor: aggregates fatigue (camera EAR), system load (psutil),
and a wearable stub (planned for T6).
RULE 5 — all health data stays local, never transmitted externally.
"""

import sys

from datetime import datetime, timezone
from loguru import logger

from core.config import CONFIG


class HealthMonitor:
    """Aggregates owner health signals into a single snapshot dict.

    Signals collected:
        - fatigue_score  (0-10) via camera EAR from FatigueMonitor
        - energy_level   ("high" / "medium" / "low") derived from fatigue
        - system_load    {cpu_percent, ram_percent} via psutil
        - wearable       stub — API integration planned for T6

    All error paths return safe neutral values; this class must never raise.
    """

    _ENERGY_MAP = {
        range(0,  4): "high",    # fatigue 0-3 → high energy
        range(4,  7): "medium",  # fatigue 4-6 → medium energy
        range(7, 11): "low",     # fatigue 7-10 → low energy
    }

    def __init__(self) -> None:
        self._fatigue_monitor = None    # FatigueMonitor, lazy
        self._psutil = None             # psutil module, lazy
        self._wearable_connector = None # WearableConnector, lazy

    # ── private helpers ───────────────────────────────────────────────────────

    def _get_fatigue_monitor(self):
        """Lazy-load FatigueMonitor to avoid circular import at module level."""
        if self._fatigue_monitor is None:
            try:
                from core.sensing.camera import FatigueMonitor
                self._fatigue_monitor = FatigueMonitor()
                logger.debug("[VECTOR][health] FatigueMonitor loaded")
            except Exception as exc:
                logger.warning(
                    f"[VECTOR][health] FatigueMonitor unavailable: {exc}"
                )
        return self._fatigue_monitor

    def _get_psutil(self):
        """Lazy-load psutil."""
        if self._psutil is None:
            try:
                import psutil
                self._psutil = psutil
            except ImportError as exc:
                logger.warning(f"[VECTOR][health] psutil unavailable: {exc}")
        return self._psutil

    @staticmethod
    def _fatigue_to_energy(fatigue: float) -> str:
        """Map fatigue score 0-10 to energy level string."""
        fi = int(fatigue)
        if fi <= 3:
            return "high"
        if fi <= 6:
            return "medium"
        return "low"

    # ── public API ─────────────────────────────────────────────────────────────

    def get_fatigue_score(self) -> float:
        """Return fatigue score 0-10 from camera. Falls back to 5.0."""
        try:
            mon = self._get_fatigue_monitor()
            if mon is None:
                return 5.0
            score = mon.get_fatigue_score()
            logger.debug(f"[VECTOR][health] fatigue_score={score}")
            return score
        except Exception as exc:
            logger.error(f"[VECTOR][health] get_fatigue_score error: {exc}")
            return 5.0

    def get_system_load(self) -> dict:
        """Return current CPU and RAM usage percentages.

        Returns {cpu_percent: float, ram_percent: float}.
        Falls back to 0.0 / 0.0 on any error.
        """
        try:
            ps = self._get_psutil()
            if ps is None:
                return {"cpu_percent": 0.0, "ram_percent": 0.0}

            cpu = float(ps.cpu_percent(interval=0.2))
            ram = float(ps.virtual_memory().percent)
            logger.debug(f"[VECTOR][health] cpu={cpu}% ram={ram}%")
            return {"cpu_percent": cpu, "ram_percent": ram}

        except Exception as exc:
            logger.error(f"[VECTOR][health] get_system_load error: {exc}")
            return {"cpu_percent": 0.0, "ram_percent": 0.0}

    def _get_wearable_data(self) -> dict:
        """Pull wearable metrics from external connector sources without recursion.

        The default phone sensor connector derives its data from HealthMonitor, so
        invoking it from here recursively creates HealthMonitor instances. Keep
        this snapshot path synchronous and offline-safe; async callers can poll
        WearableConnector directly.
        """
        try:
            from districts.health.wearable_connector import WearableConnector
            import asyncio

            if self._wearable_connector is None:
                self._wearable_connector = WearableConnector()
            if not hasattr(self._wearable_connector, 'poll_all'):
                return {"available": False, "note": "poll_all not available"}

            enabled = [
                source for source in getattr(self._wearable_connector, "enabled_sources", [])
                if source != "phone_sensor"
            ]
            if not enabled:
                return {"available": False, "note": "no external wearable sources configured"}

            try:
                asyncio.get_running_loop()
                return {"available": False, "note": "wearable poll skipped in active event loop"}
            except RuntimeError:
                pass

            original_sources = list(self._wearable_connector.enabled_sources)
            self._wearable_connector.enabled_sources = enabled
            try:
                result = asyncio.run(self._wearable_connector.poll_all())
            finally:
                self._wearable_connector.enabled_sources = original_sources

            if result:
                return {"available": True, "data": result, "note": "connector poll"}
            return {"available": False, "note": "wearable poll returned empty"}
        except Exception as exc:
            logger.warning(f"[VECTOR][health] wearable data unavailable: {exc}")
        return {"available": False, "note": "wearable unavailable"}

    def get_health_snapshot(self) -> dict:
        ts = datetime.now(timezone.utc).isoformat()

        fatigue = self.get_fatigue_score()
        energy  = self._fatigue_to_energy(fatigue)
        sysload = self.get_system_load()
        wearable = self._get_wearable_data()

        snapshot = {
            "fatigue_score": fatigue,
            "energy_level":  energy,
            "system_load":   sysload,
            "wearable":      wearable,
            "timestamp": ts,
        }

        logger.info(
            f"[VECTOR][health] snapshot — fatigue={fatigue} "
            f"energy={energy} cpu={sysload['cpu_percent']}% "
            f"ram={sysload['ram_percent']}%"
        )
        return snapshot


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    ok = True

    try:
        monitor = HealthMonitor()

        # system_load (no camera needed)
        load = monitor.get_system_load()
        assert isinstance(load, dict),                  "get_system_load must return dict"
        assert "cpu_percent" in load,                   "missing cpu_percent"
        assert "ram_percent" in load,                   "missing ram_percent"
        assert isinstance(load["cpu_percent"], float),  "cpu_percent must be float"

        # full snapshot
        snap = monitor.get_health_snapshot()
        assert isinstance(snap, dict),                    "snapshot must be dict"
        assert "fatigue_score"  in snap,                  "missing fatigue_score"
        assert "energy_level"   in snap,                  "missing energy_level"
        assert "system_load"    in snap,                  "missing system_load"
        assert "wearable"       in snap,                  "missing wearable"
        assert "timestamp"      in snap,                  "missing timestamp"
        assert snap["energy_level"] in ("high", "medium", "low"), \
            "energy_level must be high/medium/low"
        assert snap["wearable"]["available"] is False,    "wearable stub must be False"

        # energy mapping edge cases
        assert HealthMonitor._fatigue_to_energy(0.0) == "high"
        assert HealthMonitor._fatigue_to_energy(3.9) == "high"
        assert HealthMonitor._fatigue_to_energy(4.0) == "medium"
        assert HealthMonitor._fatigue_to_energy(6.9) == "medium"
        assert HealthMonitor._fatigue_to_energy(7.0) == "low"
        assert HealthMonitor._fatigue_to_energy(10.0) == "low"

        logger.info(
            f"[VECTOR][health] HealthMonitor OK — "
            f"energy={snap['energy_level']} "
            f"cpu={snap['system_load']['cpu_percent']}%"
        )
    except Exception as exc:
        logger.error(f"[VECTOR][health] HealthMonitor smoke test FAILED: {exc}")
        ok = False

    print("✅ health_monitor.py OK" if ok else "❌ health_monitor.py FAILED")
