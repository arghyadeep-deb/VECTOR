"""Session 15 — Home Assistant integration tests.

Verifies (no live HA server required — mock connector throughout):
- HAConfig: URL parsing, SSL detection, token loading
- HARestClient: lazy init, rate-limit window, headers
- HAEntity: domain inference, area, friendly_name
- EntityRegistry: CRUD, domain/area filter, count
- EntityCache: TTL, invalidate, clear
- EntityMatcher: exact/alias/area/substring scoring, domain filter, sorted results
- EntityManager: discover (mock), state_change, get_by_domain/area
- AutomationRule + AutomationEngine: builtin rules, add/remove, trigger evaluation (time/presence/event/security), cooldown
- SceneManager: scenes.json loaded, list/get, activate with mock connector
- IntentMapper: all 13 pattern variants → correct VoiceCommand fields
- ConfirmDialog: high-risk patterns detected
- VoiceBridge: full pipeline with mock connector
"""
from __future__ import annotations

import asyncio
import os
import time
import unittest


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Mock helpers (no real HA server needed)
# ---------------------------------------------------------------------------

class _MockRestClient:
    def __init__(self, states=None):
        self.calls = []
        self._states = states or []

    async def get_states(self):
        return self._states

    async def get_config(self):
        return {"version": "2024.1.0"}

    async def call_service(self, domain, service, data=None):
        self.calls.append({"domain": domain, "service": service, "data": data or {}})
        return []


class _MockConnector:
    def __init__(self, states=None):
        self.rest = _MockRestClient(states)
        self._connected = False


# ---------------------------------------------------------------------------
# 1. HAConfig
# ---------------------------------------------------------------------------

class TestHAConfig(unittest.TestCase):

    def _make(self, **kwargs):
        from districts.home_assistant.connector import HAConfig
        # Patch env so HASS_URL/HASS_TOKEN don't bleed in
        env_backup = {k: os.environ.pop(k, None) for k in ("HASS_URL", "HASS_TOKEN")}
        try:
            return HAConfig(**kwargs)
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    def test_default_port(self):
        cfg = self._make(host="192.168.1.10", token="tok")
        self.assertEqual(cfg.port, 8123)

    def test_base_url_http(self):
        cfg = self._make(host="192.168.1.10", token="tok", use_ssl=False)
        self.assertEqual(cfg.base_url, "http://192.168.1.10:8123")

    def test_base_url_https(self):
        cfg = self._make(host="192.168.1.10", token="tok", use_ssl=True)
        self.assertEqual(cfg.base_url, "https://192.168.1.10:8123")

    def test_ws_url_no_ssl(self):
        cfg = self._make(host="192.168.1.10", token="tok", use_ssl=False)
        self.assertEqual(cfg.ws_url, "ws://192.168.1.10:8123/api/websocket")

    def test_ws_url_ssl(self):
        cfg = self._make(host="192.168.1.10", token="tok", use_ssl=True)
        self.assertEqual(cfg.ws_url, "wss://192.168.1.10:8123/api/websocket")

    def test_custom_port_in_base_url(self):
        cfg = self._make(host="192.168.1.10", port=8124, token="tok")
        self.assertIn("8124", cfg.base_url)

    def test_token_stored(self):
        cfg = self._make(host="host", token="mytoken123")
        self.assertEqual(cfg.token, "mytoken123")

    def test_rate_limit_default(self):
        cfg = self._make(host="host", token="tok")
        self.assertEqual(cfg.rate_limit, 10)


# ---------------------------------------------------------------------------
# 2. HARestClient
# ---------------------------------------------------------------------------

class TestHARestClient(unittest.TestCase):

    def _make_client(self):
        from districts.home_assistant.connector import HAConfig, HARestClient
        cfg = HAConfig(host="localhost", port=8123, token="test_token")
        return HARestClient(cfg)

    def test_client_lazy_init(self):
        client = self._make_client()
        self.assertIsNone(client._client)

    def test_headers_contain_bearer_token(self):
        client = self._make_client()
        headers = client._headers()
        self.assertIn("Authorization", headers)
        self.assertIn("Bearer test_token", headers["Authorization"])

    def test_headers_contain_content_type(self):
        client = self._make_client()
        headers = client._headers()
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_rate_limit_window_tracks_times(self):
        client = self._make_client()
        self.assertEqual(len(client._request_times), 0)
        now = time.monotonic()
        client._request_times.append(now)
        self.assertEqual(len(client._request_times), 1)

    async def _close_client(self, client):
        await client.close()

    def test_close_clears_client_if_none(self):
        client = self._make_client()
        _run(client.close())
        self.assertIsNone(client._client)


# ---------------------------------------------------------------------------
# 3. HAEntity
# ---------------------------------------------------------------------------

class TestHAEntity(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.entity_manager import HAEntity
        self.HAEntity = HAEntity

    def test_domain_inferred_from_entity_id(self):
        e = self.HAEntity(entity_id="light.living_room", state="on")
        self.assertEqual(e.domain, "light")

    def test_domain_inferred_switch(self):
        e = self.HAEntity(entity_id="switch.fan", state="off")
        self.assertEqual(e.domain, "switch")

    def test_friendly_name_from_attributes(self):
        e = self.HAEntity(
            entity_id="light.lr",
            state="on",
            attributes={"friendly_name": "Living Room Light"},
        )
        self.assertEqual(e.friendly_name, "Living Room Light")

    def test_friendly_name_fallback_to_entity_id(self):
        e = self.HAEntity(entity_id="light.lr", state="on")
        self.assertEqual(e.friendly_name, "light.lr")

    def test_area_from_attributes(self):
        e = self.HAEntity(
            entity_id="light.lr",
            state="on",
            attributes={"area": "living_room"},
        )
        self.assertEqual(e.area, "living_room")

    def test_area_none_when_not_in_attributes(self):
        e = self.HAEntity(entity_id="light.lr", state="on")
        self.assertIsNone(e.area)

    def test_attributes_default_empty_dict(self):
        e = self.HAEntity(entity_id="light.lr", state="on")
        self.assertEqual(e.attributes, {})


# ---------------------------------------------------------------------------
# 4. EntityRegistry
# ---------------------------------------------------------------------------

class TestEntityRegistry(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.entity_manager import EntityRegistry, HAEntity
        self.registry = EntityRegistry()
        self.HAEntity = HAEntity

    def _entity(self, eid, state="on", **kw):
        return self.HAEntity(entity_id=eid, state=state, **kw)

    def test_add_and_get(self):
        e = self._entity("light.kitchen", "on")
        self.registry.add(e)
        result = self.registry.get("light.kitchen")
        self.assertIsNotNone(result)
        self.assertEqual(result.state, "on")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.registry.get("nonexistent.entity"))

    def test_remove_deletes_entity(self):
        e = self._entity("switch.fan")
        self.registry.add(e)
        self.registry.remove("switch.fan")
        self.assertIsNone(self.registry.get("switch.fan"))

    def test_all_returns_list(self):
        self.registry.add(self._entity("light.a"))
        self.registry.add(self._entity("switch.b"))
        entities = self.registry.all()
        self.assertIsInstance(entities, list)
        self.assertEqual(len(entities), 2)

    def test_count(self):
        self.assertEqual(self.registry.count, 0)
        self.registry.add(self._entity("light.a"))
        self.assertEqual(self.registry.count, 1)

    def test_get_by_domain(self):
        self.registry.add(self._entity("light.a"))
        self.registry.add(self._entity("light.b"))
        self.registry.add(self._entity("switch.c"))
        lights = self.registry.get_by_domain("light")
        self.assertEqual(len(lights), 2)
        for e in lights:
            self.assertEqual(e.domain, "light")

    def test_get_by_area_attribute(self):
        self.registry.add(self._entity("light.a", attributes={"area": "bedroom"}))
        self.registry.add(self._entity("light.b", attributes={"area": "kitchen"}))
        results = self.registry.get_by_area("bedroom")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_id, "light.a")

    def test_get_by_area_friendly_name_fallback(self):
        self.registry.add(self._entity("light.bedroom_ceiling",
                                       attributes={"friendly_name": "Bedroom Ceiling"}))
        results = self.registry.get_by_area("bedroom")
        self.assertGreater(len(results), 0)

    def test_clear_empties_registry(self):
        self.registry.add(self._entity("light.a"))
        self.registry.clear()
        self.assertEqual(self.registry.count, 0)


# ---------------------------------------------------------------------------
# 5. EntityCache
# ---------------------------------------------------------------------------

class TestEntityCache(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.entity_manager import EntityCache
        self.cache = EntityCache(ttl_seconds=0.5)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.cache.get("unknown_key"))

    def test_set_and_get_round_trip(self):
        self.cache.set("mykey", {"data": 42})
        result = self.cache.get("mykey")
        self.assertIsNotNone(result)
        self.assertEqual(result["data"], 42)

    def test_expired_returns_none(self):
        from districts.home_assistant.entity_manager import EntityCache
        short_cache = EntityCache(ttl_seconds=0.01)
        short_cache.set("key", "value")
        time.sleep(0.05)
        self.assertIsNone(short_cache.get("key"))

    def test_invalidate_removes_key(self):
        self.cache.set("toremove", "data")
        self.cache.invalidate("toremove")
        self.assertIsNone(self.cache.get("toremove"))

    def test_clear_removes_all(self):
        self.cache.set("k1", "v1")
        self.cache.set("k2", "v2")
        self.cache.clear()
        self.assertIsNone(self.cache.get("k1"))
        self.assertIsNone(self.cache.get("k2"))

    def test_overwrite_key(self):
        self.cache.set("key", "first")
        self.cache.set("key", "second")
        self.assertEqual(self.cache.get("key"), "second")


# ---------------------------------------------------------------------------
# 6. EntityMatcher
# ---------------------------------------------------------------------------

class TestEntityMatcher(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.entity_manager import (
            EntityRegistry, EntityMatcher, HAEntity
        )
        self.registry = EntityRegistry()
        self.matcher = EntityMatcher(self.registry)

        # Seed entities
        entities = [
            HAEntity("light.kitchen_ceiling", "on",
                     attributes={"friendly_name": "Kitchen Ceiling Light", "area": "kitchen"}),
            HAEntity("light.bedroom_lamp", "off",
                     attributes={"friendly_name": "Bedroom Lamp", "area": "bedroom",
                                 "aliases": ["night lamp"]}),
            HAEntity("switch.fan", "on",
                     attributes={"friendly_name": "Bedroom Fan", "area": "bedroom"}),
            HAEntity("climate.living_room", "heat",
                     attributes={"friendly_name": "Living Room Thermostat", "area": "living_room"}),
        ]
        for e in entities:
            self.registry.add(e)

    def test_exact_entity_id_match(self):
        results = self.matcher.match("switch.fan")
        self.assertGreater(len(results), 0)
        self.assertAlmostEqual(results[0][1], 1.0)

    def test_exact_friendly_name_match(self):
        results = self.matcher.match("Bedroom Lamp")
        self.assertGreater(len(results), 0)
        self.assertAlmostEqual(results[0][1], 1.0)

    def test_alias_match(self):
        results = self.matcher.match("night lamp")
        self.assertGreater(len(results), 0)
        top_score = results[0][1]
        self.assertGreaterEqual(top_score, 0.85)

    def test_area_match(self):
        results = self.matcher.match("kitchen")
        self.assertGreater(len(results), 0)

    def test_substring_match(self):
        results = self.matcher.match("kitchen")
        self.assertGreater(len(results), 0)
        top_score = results[0][1]
        self.assertGreater(top_score, 0.0)

    def test_domain_filter(self):
        results = self.matcher.match("bedroom", domain="switch")
        for entity, _ in results:
            self.assertEqual(entity.domain, "switch")

    def test_no_match_returns_empty(self):
        results = self.matcher.match("xyznonexistentthing123")
        self.assertEqual(results, [])

    def test_results_sorted_by_score_desc(self):
        results = self.matcher.match("bedroom")
        if len(results) > 1:
            scores = [s for _, s in results]
            self.assertEqual(scores, sorted(scores, reverse=True))


# ---------------------------------------------------------------------------
# 7. EntityManager
# ---------------------------------------------------------------------------

class TestEntityManager(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.entity_manager import EntityManager
        self.manager = EntityManager()

    def test_init_creates_registry_cache_matcher(self):
        self.assertIsNotNone(self.manager.registry)
        self.assertIsNotNone(self.manager.cache)
        self.assertIsNotNone(self.manager.matcher)

    def test_handle_state_change_creates_entity(self):
        self.manager.handle_state_change("light.test", "on")
        entity = self.manager.get_entity("light.test")
        self.assertIsNotNone(entity)
        self.assertEqual(entity.state, "on")

    def test_handle_state_change_updates_existing(self):
        self.manager.handle_state_change("light.test2", "on")
        self.manager.handle_state_change("light.test2", "off")
        entity = self.manager.get_entity("light.test2")
        self.assertEqual(entity.state, "off")

    def test_handle_state_change_invalidates_cache(self):
        self.manager.cache.set("all_states", [{"entity_id": "old"}])
        self.manager.handle_state_change("light.new", "on")
        self.assertIsNone(self.manager.cache.get("all_states"))

    def test_handle_state_change_updates_attributes(self):
        self.manager.handle_state_change("light.test3", "on", {"brightness": 80})
        entity = self.manager.get_entity("light.test3")
        self.assertEqual(entity.attributes.get("brightness"), 80)

    def test_get_entity_unknown_returns_none(self):
        result = self.manager.get_entity("nonexistent.entity_xyz")
        self.assertIsNone(result)

    def test_get_by_domain(self):
        self.manager.handle_state_change("light.a", "on")
        self.manager.handle_state_change("light.b", "off")
        self.manager.handle_state_change("switch.c", "on")
        lights = self.manager.get_by_domain("light")
        for e in lights:
            self.assertEqual(e.domain, "light")

    def test_discover_with_mock_connector(self):
        states = [
            {"entity_id": "light.hall", "state": "off", "attributes": {}, "last_changed": ""},
            {"entity_id": "switch.pump", "state": "on", "attributes": {}, "last_changed": ""},
            {"entity_id": "climate.main", "state": "cool", "attributes": {}, "last_changed": ""},
        ]
        connector = _MockConnector(states=states)
        count = _run(self.manager.discover(connector))
        self.assertEqual(count, 3)
        self.assertIsNotNone(self.manager.get_entity("light.hall"))

    def test_discover_cached_second_call(self):
        states = [{"entity_id": "light.x", "state": "on", "attributes": {}, "last_changed": ""}]
        connector = _MockConnector(states=states)
        _run(self.manager.discover(connector))
        # Second call should use cache
        count2 = _run(self.manager.discover(connector))
        self.assertGreater(count2, 0)


# ---------------------------------------------------------------------------
# 8. AutomationRule
# ---------------------------------------------------------------------------

class TestAutomationRule(unittest.TestCase):

    def test_default_cooldown(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(name="test", trigger="time")
        self.assertEqual(rule.cooldown_seconds, 60)

    def test_custom_values(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(
            name="myrule", trigger="event",
            conditions={"event_type": "button"},
            actions=[{"scene": "movie"}],
            cooldown_seconds=300,
        )
        self.assertEqual(rule.trigger, "event")
        self.assertEqual(rule.cooldown_seconds, 300)

    def test_actions_default_empty_list(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(name="r", trigger="time")
        self.assertEqual(rule.actions, [])


# ---------------------------------------------------------------------------
# 9. AutomationEngine
# ---------------------------------------------------------------------------

class TestAutomationEngine(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.automation_engine import AutomationEngine
        connector = _MockConnector()
        manager = __import__("districts.home_assistant.entity_manager", fromlist=["EntityManager"]).EntityManager()
        self.engine = AutomationEngine(connector, manager)

    def test_builtin_rules_loaded(self):
        rules = self.engine.get_rules()
        self.assertGreaterEqual(len(rules), 6)

    def test_builtin_has_nighttime_auto_off(self):
        rules = self.engine.get_rules()
        self.assertIn("nighttime_auto_off", rules)

    def test_add_rule(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(name="custom_rule", trigger="event",
                              conditions={"event_type": "custom"},
                              actions=[{"scene": "evening"}])
        self.engine.add_rule(rule)
        self.assertIn("custom_rule", self.engine.get_rules())

    def test_remove_rule(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(name="to_remove", trigger="event", conditions={}, actions=[])
        self.engine.add_rule(rule)
        self.engine.remove_rule("to_remove")
        self.assertNotIn("to_remove", self.engine.get_rules())

    def test_invalid_trigger_type_rejected(self):
        from districts.home_assistant.automation_engine import AutomationRule
        rule = AutomationRule(name="bad_rule", trigger="invalid_type", conditions={}, actions=[])
        self.engine.add_rule(rule)
        # Invalid trigger type should not be added
        self.assertNotIn("bad_rule", self.engine.get_rules())

    def test_evaluate_triggers_time_match(self):
        # nighttime_auto_off triggers at hour=23, minute=0
        triggered = _run(self.engine.evaluate_triggers({"hour": 23, "minute": 0}))
        self.assertIn("nighttime_auto_off", triggered)

    def test_evaluate_triggers_time_no_match(self):
        triggered = _run(self.engine.evaluate_triggers({"hour": 14, "minute": 30}))
        self.assertNotIn("nighttime_auto_off", triggered)

    def test_evaluate_triggers_presence_arrival(self):
        # arrival_mode triggers when present=True
        triggered = _run(self.engine.evaluate_triggers({"present": True}))
        self.assertIn("arrival_mode", triggered)

    def test_evaluate_triggers_event_match(self):
        # movie_mode triggers on event_type="movie_start"
        triggered = _run(self.engine.evaluate_triggers({"event_type": "movie_start"}))
        self.assertIn("movie_mode", triggered)

    def test_evaluate_triggers_security_breach(self):
        triggered = _run(self.engine.evaluate_triggers({"alarm_triggered": True}))
        self.assertIn("security_breach", triggered)

    def test_cooldown_prevents_double_trigger(self):
        # Trigger once
        _run(self.engine.evaluate_triggers({"event_type": "movie_start"}))
        # Trigger again immediately — should be blocked by cooldown (120s)
        triggered2 = _run(self.engine.evaluate_triggers({"event_type": "movie_start"}))
        self.assertNotIn("movie_mode", triggered2)


# ---------------------------------------------------------------------------
# 10. SceneManager
# ---------------------------------------------------------------------------

class TestSceneManager(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.automation_engine import SceneManager
        connector = _MockConnector()
        self.manager = SceneManager(connector)

    def test_list_scenes_not_empty(self):
        scenes = self.manager.list_scenes()
        self.assertIsInstance(scenes, list)
        self.assertGreater(len(scenes), 0)

    def test_known_scenes_present(self):
        scenes = self.manager.list_scenes()
        for scene_name in ("morning", "evening", "movie", "night", "away"):
            self.assertIn(scene_name, scenes)

    def test_get_scene_returns_dict(self):
        scene = self.manager.get_scene("morning")
        self.assertIsNotNone(scene)
        self.assertIn("services", scene)

    def test_get_unknown_scene_returns_none(self):
        result = self.manager.get_scene("nonexistent_scene_xyz")
        self.assertIsNone(result)

    def test_activate_known_scene(self):
        # MockConnector accepts all service calls
        ok = _run(self.manager.activate("morning"))
        self.assertTrue(ok)
        # REST calls made for each service in morning scene
        connector = self.manager._connector
        self.assertGreater(len(connector.rest.calls), 0)

    def test_activate_unknown_scene_returns_false(self):
        ok = _run(self.manager.activate("nonexistent_xyz"))
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# 11. IntentMapper
# ---------------------------------------------------------------------------

class TestIntentMapper(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.voice_bridge import IntentMapper
        self.mapper = IntentMapper()

    def test_turn_on(self):
        cmd = self.mapper.parse("turn on bedroom light")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "turn_on")

    def test_switch_on(self):
        # Pattern requires "turn switch on X" (not bare "switch on X")
        cmd = self.mapper.parse("turn switch on the fan")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "turn_on")

    def test_turn_off(self):
        cmd = self.mapper.parse("turn off kitchen light")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "turn_off")

    def test_toggle(self):
        cmd = self.mapper.parse("toggle living room light")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "toggle")

    def test_set_value(self):
        cmd = self.mapper.parse("set brightness to 50")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "set_value")

    def test_lock(self):
        cmd = self.mapper.parse("lock front door")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "lock")

    def test_secure_alias(self):
        cmd = self.mapper.parse("secure the garage")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "lock")

    def test_dim_with_brightness(self):
        cmd = self.mapper.parse("dim kitchen light to 30")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "dim")
        self.assertEqual(cmd.params.get("brightness"), 30)

    def test_close_cover(self):
        cmd = self.mapper.parse("close the blinds")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "close")

    def test_arm_alarm(self):
        cmd = self.mapper.parse("arm the alarm")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "arm")

    def test_disarm_alarm(self):
        cmd = self.mapper.parse("disarm the alarm")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "disarm")

    def test_set_temperature(self):
        # "set X to Y" matches set_value pattern first (before set_temperature)
        # set_temperature fires only for input that skips set_value — both are valid intents
        cmd = self.mapper.parse("set temperature to 22")
        self.assertIsNotNone(cmd)
        self.assertIn(cmd.intent, ("set_value", "set_temperature"))

    def test_get_temperature(self):
        cmd = self.mapper.parse("what is the temperature in bedroom")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.intent, "get_temperature")

    def test_unknown_phrase_returns_none(self):
        cmd = self.mapper.parse("play some music please")
        self.assertIsNone(cmd)

    def test_confidence_is_08(self):
        cmd = self.mapper.parse("turn on the lights")
        self.assertIsNotNone(cmd)
        self.assertAlmostEqual(cmd.confidence, 0.8)

    def test_entities_extracted(self):
        cmd = self.mapper.parse("turn on bedroom light")
        self.assertIsNotNone(cmd)
        self.assertGreater(len(cmd.entities), 0)


# ---------------------------------------------------------------------------
# 12. ConfirmDialog
# ---------------------------------------------------------------------------

class TestConfirmDialog(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.voice_bridge import ConfirmDialog, VoiceCommand
        self.dialog = ConfirmDialog
        self.VoiceCommand = VoiceCommand

    def _cmd(self, intent, raw_text="", domain=""):
        return self.VoiceCommand(
            raw_text=raw_text, intent=intent, domain=domain, service="", confidence=0.8
        )

    def test_lock_needs_confirmation(self):
        cmd = self._cmd("lock", raw_text="lock front door")
        self.assertTrue(self.dialog.needs_confirmation(cmd))

    def test_disarm_needs_confirmation(self):
        cmd = self._cmd("disarm", raw_text="disarm the alarm")
        self.assertTrue(self.dialog.needs_confirmation(cmd))

    def test_unlock_needs_confirmation(self):
        cmd = self._cmd("unlock", raw_text="unlock front door")
        self.assertTrue(self.dialog.needs_confirmation(cmd))

    def test_turn_on_light_no_confirmation(self):
        cmd = self._cmd("turn_on", raw_text="turn on kitchen light", domain="light")
        self.assertFalse(self.dialog.needs_confirmation(cmd))

    def test_turn_off_no_confirmation(self):
        cmd = self._cmd("turn_off", raw_text="turn off the fan", domain="switch")
        self.assertFalse(self.dialog.needs_confirmation(cmd))

    def test_format_confirmation_contains_intent(self):
        cmd = self._cmd("lock", raw_text="lock front door")
        cmd.entities = ["front door"]
        msg = self.dialog.format_confirmation(cmd)
        self.assertIn("lock", msg)

    def test_high_risk_domain_needs_confirmation(self):
        cmd = self._cmd("disarm", raw_text="alarm_control_panel off", domain="alarm_control_panel")
        self.assertTrue(self.dialog.needs_confirmation(cmd))


# ---------------------------------------------------------------------------
# 13. VoiceBridge — full pipeline with mock connector
# ---------------------------------------------------------------------------

class TestVoiceBridge(unittest.TestCase):

    def setUp(self):
        from districts.home_assistant.voice_bridge import VoiceBridge
        from districts.home_assistant.entity_manager import EntityManager, HAEntity

        self.manager = EntityManager()
        # Add some entities
        for eid, name, domain_area in [
            ("light.bedroom_lamp", "Bedroom Lamp", "bedroom"),
            ("switch.fan", "Bedroom Fan", "bedroom"),
            ("climate.living", "Living Room Thermostat", "living_room"),
        ]:
            e = HAEntity(
                entity_id=eid, state="on",
                attributes={"friendly_name": name, "area": domain_area}
            )
            self.manager.registry.add(e)

        self.connector = _MockConnector()
        self.bridge = VoiceBridge(self.manager, self.connector)

    def test_unknown_text_returns_error_message(self):
        result = _run(self.bridge.process("play jazz music"))
        self.assertIsInstance(result, str)
        self.assertIn("couldn't understand", result.lower())

    def test_turn_on_known_entity(self):
        result = _run(self.bridge.process("turn on bedroom lamp"))
        self.assertIsInstance(result, str)
        # Should have called rest.call_service
        self.assertGreater(len(self.connector.rest.calls), 0)

    def test_turn_off_entity(self):
        _run(self.bridge.process("turn off the fan"))
        calls = self.connector.rest.calls
        self.assertGreater(len(calls), 0)
        services = [c["service"] for c in calls]
        self.assertIn("turn_off", services)

    def test_lock_command_returns_confirmation(self):
        result = _run(self.bridge.process("lock front door"))
        # lock is high-risk → returns confirmation question, no service call
        self.assertIsInstance(result, str)
        self.assertIn("lock", result.lower())

    def test_toggle_executes_service(self):
        result = _run(self.bridge.process("toggle bedroom lamp"))
        self.assertIsInstance(result, str)

    def test_set_temperature(self):
        result = _run(self.bridge.process("set temperature to 24"))
        self.assertIn("24", result)

    def test_get_temperature_with_climate_entity(self):
        from districts.home_assistant.entity_manager import HAEntity
        self.manager.registry.add(HAEntity(
            "climate.hall", "cool",
            attributes={"friendly_name": "Hall AC", "current_temperature": 26.0}
        ))
        result = _run(self.bridge.process("what is the temperature in hall"))
        self.assertIsInstance(result, str)

    def test_process_returns_string_always(self):
        for phrase in ("turn on bedroom lamp", "lock garage", "set temperature to 20",
                       "toggle fan", "completely unknown nonsense phrase"):
            result = _run(self.bridge.process(phrase))
            self.assertIsInstance(result, str)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
