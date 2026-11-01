from __future__ import annotations

import asyncio
import datetime
import random
from abc import ABC, abstractmethod
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG

class BaseConnector(ABC):
    source_name: str = "base"

    @abstractmethod
    async def authenticate(self) -> bool:
        ...

    @abstractmethod
    async def fetch_metrics(self) -> dict[str, Any] | None:
        ...

class AppleHealthConnector(BaseConnector):
    source_name = "apple_health"

    async def authenticate(self) -> bool:
        try:
            import pyhealth
            return True
        except ImportError:
            logger.debug("[VECTOR][wearable] pyhealth not installed — Apple Health unavailable")
            return False

    async def fetch_metrics(self) -> dict[str, Any] | None:
        try:
            import pyhealth
            from pyhealth.apple_health import AppleHealthConnector as AH
            connector = AH()
            data = connector.get_recent_summary()
            if data:
                return {
                    "heart_rate": data.get("heart_rate"),
                    "hrv": data.get("hrv"),
                    "resting_heart_rate": data.get("resting_heart_rate"),
                    "steps": data.get("steps"),
                    "active_calories": data.get("active_calories"),
                    "sleep_hours": data.get("sleep_hours"),
                    "sleep_quality": data.get("sleep_quality"),
                    "spo2": data.get("spo2"),
                    "skin_temperature": data.get("temperature"),
                    "exercise_minutes": data.get("exercise_minutes"),
                    "timestamp": datetime.datetime.now().isoformat(),
                }
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] apple_health fetch error: {exc}")
        return None

class GoogleFitConnector(BaseConnector):
    source_name = "google_fit"

    def __init__(self) -> None:
        self._api_key = CONFIG.get("api_keys", {}).get("google_fit_key", "")

    async def authenticate(self) -> bool:
        return bool(self._api_key)

    async def fetch_metrics(self) -> dict[str, Any] | None:
        if not self._api_key:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                now = int(datetime.datetime.now().timestamp() * 1_000_000_000)
                hour_ago = now - 3_600_000_000_000
                body = {
                    "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
                    "bucketByTime": {"durationMillis": 3_600_000},
                    "startTimeMillis": hour_ago // 1_000_000,
                    "endTimeMillis": now // 1_000_000,
                }
                headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
                resp = await client.post(
                    "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate",
                    json=body, headers=headers,
                )
                if resp.is_success:
                    data = resp.json()
                    return {"heart_rate": data.get("heart_rate"), "timestamp": datetime.datetime.now().isoformat()}
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] google_fit error: {exc}")
        return None

class OuraConnector(BaseConnector):
    source_name = "oura"

    def __init__(self) -> None:
        self._token = CONFIG.get("api_keys", {}).get("oura_token", "")

    async def authenticate(self) -> bool:
        return bool(self._token)

    async def fetch_metrics(self) -> dict[str, Any] | None:
        if not self._token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"Bearer {self._token}"}
                resp = await client.get("https://api.ouraring.com/v2/usercollection/daily_readiness", headers=headers)
                if resp.is_success:
                    data = resp.json()
                    return {
                        "hrv": data.get("hrv"),
                        "resting_heart_rate": data.get("resting_heart_rate"),
                        "skin_temperature": data.get("temperature"),
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] oura error: {exc}")
        return None

class GarminConnector(BaseConnector):
    source_name = "garmin"

    def __init__(self) -> None:
        self._email = CONFIG.get("api_keys", {}).get("garmin_email", "")
        self._password = CONFIG.get("api_keys", {}).get("garmin_password", "")

    async def authenticate(self) -> bool:
        return bool(self._email and self._password)

    async def fetch_metrics(self) -> dict[str, Any] | None:
        if not self._email or not self._password:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post("https://connect.garmin.com/signin", data={"email": self._email, "password": self._password})
                resp = await client.get("https://connect.garmin.com/proxy/wellness-service/wellness/daily/")
                if resp.is_success:
                    data = resp.json()
                    return {
                        "steps": data.get("steps"),
                        "resting_heart_rate": data.get("restingHeartRate"),
                        "sleep_hours": (data.get("sleepTimeSeconds", 0) / 3600) if data.get("sleepTimeSeconds") else None,
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] garmin error: {exc}")
        return None

class WhoopConnector(BaseConnector):
    source_name = "whoop"

    def __init__(self) -> None:
        self._token = CONFIG.get("api_keys", {}).get("whoop_token", "")

    async def authenticate(self) -> bool:
        return bool(self._token)

    async def fetch_metrics(self) -> dict[str, Any] | None:
        if not self._token:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"Bearer {self._token}"}
                resp = await client.get("https://api.prod.whoop.com/v1/recovery", headers=headers)
                if resp.is_success:
                    data = resp.json()
                    return {
                        "resting_heart_rate": data.get("restingHeartRate"),
                        "hrv": data.get("hrv"),
                        "spo2": data.get("spo2"),
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] whoop error: {exc}")
        return None

class PhoneSensorConnector(BaseConnector):
    source_name = "phone_sensor"

    async def authenticate(self) -> bool:
        try:
            from core.sensing.health_monitor import HealthMonitor
            monitor = HealthMonitor()
            _ = monitor.get_health_snapshot()
            return True
        except Exception:
            return False

    async def fetch_metrics(self) -> dict[str, Any] | None:
        try:
            from core.sensing.health_monitor import HealthMonitor
            monitor = HealthMonitor()
            snapshot = monitor.get_health_snapshot()
            return {
                "heart_rate": snapshot.get("heart_rate"),
                "steps": snapshot.get("steps"),
                "skin_temperature": snapshot.get("temperature"),
                "stress_level": snapshot.get("stress_level"),
                "timestamp": datetime.datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.warning(f"[VECTOR][wearable] phone_sensor error: {exc}")
        return None

    async def poll_sensors(self) -> dict[str, Any]:
        return await self.fetch_metrics() or {}

class WearableConnector:
    def __init__(self) -> None:
        raw_sources: list[str] = CONFIG.get("health", {}).get("wearable_sources", ["phone_sensor"])
        self._connectors: dict[str, BaseConnector] = {
            "apple_health": AppleHealthConnector(),
            "google_fit": GoogleFitConnector(),
            "oura": OuraConnector(),
            "garmin": GarminConnector(),
            "whoop": WhoopConnector(),
            "phone_sensor": PhoneSensorConnector(),
        }
        self.enabled_sources: list[str] = []
        for s in raw_sources:
            if s in self._connectors:
                self.enabled_sources.append(s)
            else:
                logger.warning(f"[VECTOR][wearable] unknown source '{s}'")

    async def poll_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source_name in self.enabled_sources:
            connector = self._connectors[source_name]
            try:
                authed = await connector.authenticate()
                if not authed:
                    logger.debug(f"[VECTOR][wearable] {source_name} auth failed — skipping")
                    continue
                metrics = await connector.fetch_metrics()
                if metrics:
                    metrics["source"] = source_name
                    results.append(metrics)
            except Exception as exc:
                logger.warning(f"[VECTOR][wearable] {source_name} poll error: {exc}")
        return results

    async def poll_phone_sensors(self) -> dict[str, Any]:
        connector = self._connectors.get("phone_sensor")
        if connector:
            return await connector.poll_sensors()
        return {}

    def get_connector(self, source: str) -> BaseConnector | None:
        return self._connectors.get(source)
