import time
import pytest
from unittest.mock import AsyncMock, patch

from districts.home_assistant.entity_manager import HAEntity, EntityRegistry, EntityCache, EntityMatcher, EntityManager


class TestEntityCache:
    def test_set_and_get(self):
        cache = EntityCache(ttl_seconds=60)
        cache.set("light.living_room", {"state": "on"})
        assert cache.get("light.living_room") == {"state": "on"}

    def test_expiry(self):
        cache = EntityCache(ttl_seconds=0.1)
        cache.set("test.key", "value")
        time.sleep(0.2)
        assert cache.get("test.key") is None

    def test_invalidate(self):
        cache = EntityCache(ttl_seconds=60)
        cache.set("test.key", "value")
        cache.invalidate("test.key")
        assert cache.get("test.key") is None

    def test_clear(self):
        cache = EntityCache(ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


class TestEntityMatcher:
    def setup_method(self):
        self.registry = EntityRegistry()
        self.registry.add(HAEntity(
            entity_id="light.living_room",
            state="on",
            attributes={"friendly_name": "Living Room Light", "aliases": ["main light"]},
            area="Living Room",
        ))
        self.registry.add(HAEntity(
            entity_id="sensor.temperature",
            state="22.5",
            attributes={"friendly_name": "Temperature Sensor"},
            domain="sensor",
        ))
        self.matcher = EntityMatcher(self.registry)

    def test_exact_name_match(self):
        results = self.matcher.match("Living Room Light")
        assert len(results) >= 1
        assert results[0][1] == 1.0

    def test_alias_match(self):
        results = self.matcher.match("main light")
        assert len(results) >= 1
        assert results[0][1] == 0.9

    def test_domain_filter(self):
        results = self.matcher.match("temperature", domain="sensor")
        assert len(results) >= 1

    def test_no_match(self):
        results = self.matcher.match("nonexistent_device_xyz")
        assert len(results) == 0


class TestEntityRegistry:
    def setup_method(self):
        self.reg = EntityRegistry()
        self.reg.add(HAEntity(entity_id="light.a", state="on", domain="light"))
        self.reg.add(HAEntity(entity_id="switch.b", state="off", domain="switch"))

    def test_get_by_domain(self):
        lights = self.reg.get_by_domain("light")
        assert len(lights) == 1
        assert lights[0].entity_id == "light.a"

    def test_get_by_area(self):
        self.reg.add(HAEntity(
            entity_id="light.kitchen",
            state="on",
            attributes={"friendly_name": "Kitchen Light"},
            area="Kitchen",
        ))
        results = self.reg.get_by_area("Kitchen")
        assert len(results) >= 1


class TestEntityManager:
    @pytest.mark.asyncio
    async def test_discover(self):
        mgr = EntityManager()
        mock_connector = AsyncMock()
        mock_connector.rest.get_states.return_value = [
            {"entity_id": "light.test", "state": "on", "attributes": {"friendly_name": "Test Light"}},
            {"entity_id": "sensor.temp", "state": "25", "attributes": {"friendly_name": "Temp"}},
        ]
        count = await mgr.discover(mock_connector)
        assert count == 2
        assert mgr.get_entity("light.test") is not None

    def test_handle_state_change_new(self):
        mgr = EntityManager()
        mgr.handle_state_change("light.new", "on", {"friendly_name": "New Light"})
        assert mgr.get_entity("light.new") is not None
        assert mgr.get_entity("light.new").state == "on"
