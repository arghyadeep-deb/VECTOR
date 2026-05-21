from __future__ import annotations

import pytest
from loguru import logger

from districts.health.wearable_connector import (
    AppleHealthConnector,
    BaseConnector,
    GarminConnector,
    GoogleFitConnector,
    OuraConnector,
    PhoneSensorConnector,
    WearableConnector,
    WhoopConnector,
)


class TestConnectorFactory:
    def test_all_connectors_registered(self):
        wc = WearableConnector()
        assert wc._connectors["apple_health"] is not None
        assert wc._connectors["google_fit"] is not None
        assert wc._connectors["oura"] is not None
        assert wc._connectors["garmin"] is not None
        assert wc._connectors["whoop"] is not None
        assert wc._connectors["phone_sensor"] is not None

    def test_get_connector(self):
        wc = WearableConnector()
        conn = wc.get_connector("apple_health")
        assert isinstance(conn, AppleHealthConnector)
        assert conn is wc._connectors["apple_health"]

    def test_get_connector_unknown(self):
        wc = WearableConnector()
        assert wc.get_connector("nonexistent") is None

    def test_source_abstract(self):
        assert issubclass(AppleHealthConnector, BaseConnector)
        assert issubclass(GoogleFitConnector, BaseConnector)
        assert issubclass(OuraConnector, BaseConnector)
        assert issubclass(GarminConnector, BaseConnector)
        assert issubclass(WhoopConnector, BaseConnector)
        assert issubclass(PhoneSensorConnector, BaseConnector)

    def test_all_have_source_name(self):
        connectors = [AppleHealthConnector(), GoogleFitConnector(), OuraConnector(), GarminConnector(), WhoopConnector(), PhoneSensorConnector()]
        for c in connectors:
            assert c.source_name is not None
            assert c.source_name != "base"


class TestPhoneSensorConnector:
    @pytest.mark.asyncio
    async def test_authenticate_returns_bool(self):
        conn = PhoneSensorConnector()
        result = await conn.authenticate()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_fetch_metrics_returns_dict_or_none(self):
        conn = PhoneSensorConnector()
        result = await conn.fetch_metrics()
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_poll_sensors_returns_dict(self):
        conn = PhoneSensorConnector()
        result = await conn.poll_sensors()
        assert isinstance(result, dict)


class TestConnectorAuth:
    @pytest.mark.asyncio
    async def test_apple_health_auth_no_pyhealth(self):
        conn = AppleHealthConnector()
        result = await conn.authenticate()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_google_fit_auth_no_key(self):
        conn = GoogleFitConnector()
        authed = await conn.authenticate()
        metrics = await conn.fetch_metrics()
        if not authed:
            assert metrics is None
