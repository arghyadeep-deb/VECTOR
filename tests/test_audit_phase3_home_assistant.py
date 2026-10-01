"""Phase-3 audit regression tests for districts/home_assistant (no real network)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from districts.home_assistant import automation_engine as ae_mod
from districts.home_assistant.automation_engine import AutomationEngine, SceneManager
from districts.home_assistant.connector import HAConfig, HAConnector, HARestClient, HAWebSocketClient
from districts.home_assistant.entity_manager import EntityManager, HAEntity
from districts.home_assistant.voice_bridge import IntentMapper, VoiceBridge

FAIL = "Sorry, I couldn't execute"


def _bridge(*entities):
    mgr = EntityManager()
    for eid, name, state, attrs in entities:
        mgr.registry.add(HAEntity(entity_id=eid, state=state, attributes={"friendly_name": name, **attrs}))
    conn = MagicMock()
    conn.rest.call_service = AsyncMock(return_value=[])
    return VoiceBridge(mgr, conn), conn


# ---------------------------------------------------------------- connector
def test_https_url_selects_tls_and_default_port(monkeypatch):
    monkeypatch.setenv("HASS_URL", "https://ha.example.com")
    cfg = HAConfig(token="t")
    assert cfg.use_ssl is True and cfg.host == "ha.example.com" and cfg.port == 443
    assert cfg.base_url == "https://ha.example.com:443"


def test_https_url_with_port_and_trailing_path(monkeypatch):
    monkeypatch.setenv("HASS_URL", "https://ha.example.com:8443/")
    cfg = HAConfig(token="t")
    assert (cfg.use_ssl, cfg.host, cfg.port) == (True, "ha.example.com", 8443)


@pytest.mark.asyncio
async def test_get_state_rejects_path_traversal_entity_id():
    client = HARestClient(HAConfig(host="h", token="t"))
    client._request = AsyncMock()
    for bad in ("../config", "light.x/../../config", "", "light"):
        with pytest.raises(ValueError):
            await client.get_state(bad)
    client._request.assert_not_called()


@pytest.mark.asyncio
async def test_call_service_rejects_path_injection():
    client = HARestClient(HAConfig(host="h", token="t"))
    client._request = AsyncMock()
    with pytest.raises(ValueError):
        await client.call_service("../config", "turn_on", {})
    with pytest.raises(ValueError):
        await client.call_service("light", "turn_on/../../x", {})
    client._request.assert_not_called()


@pytest.mark.asyncio
async def test_ws_call_service_failure_raises():
    ws = HAWebSocketClient(HAConfig(host="h", token="t"))
    ws._send = AsyncMock(return_value={"success": False, "error": {"code": "not_found"}})
    with pytest.raises(RuntimeError):
        await ws.call_service("lock", "lock", {"entity_id": "lock.front"})


@pytest.mark.asyncio
async def test_connect_false_when_ha_unreachable_and_ws_not_attempted():
    conn = HAConnector(HAConfig(host="h", token="t"))
    conn.rest.get_config = AsyncMock(side_effect=ConnectionError("down"))
    conn.ws.connect = AsyncMock(return_value=True)
    assert await conn.connect() is False
    conn.ws.connect.assert_not_called()


@pytest.mark.asyncio
async def test_connect_does_not_hang_on_endless_ws_retry():
    conn = HAConnector(HAConfig(host="h", token="t"))
    conn.rest.get_config = AsyncMock(return_value={"version": "1"})

    async def forever():
        await asyncio.sleep(3600)

    conn.ws.connect = forever
    orig = asyncio.wait_for
    asyncio.wait_for = lambda coro, timeout: orig(coro, 0.05)  # shrink the 15s bound
    try:
        assert await conn.connect() is True  # REST-only
    finally:
        asyncio.wait_for = orig
    assert (await conn.health())["ws"] is False


@pytest.mark.asyncio
async def test_health_reports_rest_down_and_ws_down():
    conn = HAConnector(HAConfig(host="h", token="t"))
    conn.rest.get_config = AsyncMock(side_effect=ConnectionError("down"))
    conn._connected = True  # REST-only "connected" must not read as ws up
    h = await conn.health()
    assert h["rest"] is False and h["ws"] is False


# ------------------------------------------------------------- voice bridge
def test_unlock_and_disarm_are_not_parsed_as_lock_and_arm():
    m = IntentMapper()
    assert m.parse("unlock the front door").intent == "unlock"
    assert m.parse("disarm the alarm").intent == "disarm"
    assert m.parse("open the blinds living room").intent == "open_cover"
    assert m.parse("set the thermostat to 21").intent == "set_temperature"


@pytest.mark.asyncio
async def test_unresolved_device_is_not_executed_or_reported_success():
    bridge, conn = _bridge()
    reply = await bridge.process("turn on kitchen lamp")
    conn.rest.call_service.assert_not_called()
    assert reply.startswith("I couldn't understand")  # gateway maps this to "rejected"


@pytest.mark.asyncio
async def test_lock_never_resolves_to_non_lock_entity():
    bridge, conn = _bridge(("binary_sensor.front_door", "Front Door", "off", {}))
    reply = await bridge.process("lock front door")
    conn.rest.call_service.assert_not_called()
    assert "Locked" not in reply


@pytest.mark.asyncio
async def test_open_blinds_does_not_call_lock_unlock():
    bridge, conn = _bridge(("cover.living_room", "Living Room", "closed", {}))
    reply = await bridge.process("open the blinds living room")
    conn.rest.call_service.assert_awaited_once_with("cover", "open_cover", {"entity_id": "cover.living_room"})
    assert reply.startswith("Opened")


@pytest.mark.asyncio
async def test_garage_cover_requires_confirmation_and_does_not_execute():
    bridge, conn = _bridge(("cover.garage", "Garage", "open", {"device_class": "garage"}))
    reply = await bridge.process("close garage")
    assert reply.startswith("Are you sure")
    conn.rest.call_service.assert_not_called()


@pytest.mark.asyncio
async def test_dim_actually_calls_service():
    bridge, conn = _bridge(("light.lamp", "Lamp", "on", {}))
    reply = await bridge.process("dim lamp to 30")
    conn.rest.call_service.assert_awaited_once_with("light", "turn_on", {"entity_id": "light.lamp", "brightness_pct": 30})
    assert not reply.startswith(FAIL)


@pytest.mark.asyncio
async def test_unsupported_intent_is_failure_not_executed_claim():
    bridge, conn = _bridge(("light.lamp", "Lamp", "on", {}))
    reply = await bridge.process("toggle lamp")
    conn.rest.call_service.assert_not_called()
    assert reply.startswith(FAIL) and "Executed" not in reply


@pytest.mark.asyncio
async def test_set_value_on_non_light_is_refused():
    bridge, conn = _bridge(("cover.blind", "Blind", "open", {}))
    reply = await bridge.process("set blind to 50")
    conn.rest.call_service.assert_not_called()
    assert reply.startswith(FAIL)


@pytest.mark.asyncio
async def test_set_temperature_targets_climate_entity_not_the_number():
    bridge, conn = _bridge(("climate.hall", "Hall", "heat", {}))
    reply = await bridge.process("set the thermostat to 21")
    conn.rest.call_service.assert_awaited_once_with(
        "climate", "set_temperature", {"entity_id": "climate.hall", "temperature": 21}
    )
    assert "21" in reply


@pytest.mark.asyncio
async def test_set_temperature_without_single_climate_does_not_call():
    bridge, conn = _bridge()
    reply = await bridge.process("set the thermostat to 21")
    conn.rest.call_service.assert_not_called()
    assert not reply.startswith("Temperature set")


@pytest.mark.asyncio
async def test_failed_temperature_read_is_not_reported_as_a_reading():
    bridge, _ = _bridge(("climate.hall", "Hall", "unavailable", {}))
    reply = await bridge.process("the temperature in hall")
    assert reply.startswith(FAIL) and "unknown degrees" not in reply


@pytest.mark.asyncio
async def test_service_exception_is_failure():
    bridge, conn = _bridge(("light.lamp", "Lamp", "on", {}))
    conn.rest.call_service = AsyncMock(side_effect=ConnectionError("down"))
    assert (await bridge.process("turn off lamp")).startswith(FAIL)


# ------------------------------------------------------------- automations
@pytest.mark.asyncio
async def test_scene_activate_false_when_service_calls_fail():
    conn = MagicMock()
    conn.rest.get_states = AsyncMock(return_value=[])
    conn.rest.call_service = AsyncMock(side_effect=ConnectionError("down"))
    assert await SceneManager(conn).activate("night") is False


@pytest.mark.asyncio
async def test_scene_restore_uses_valid_services_per_domain():
    conn = MagicMock()
    conn.rest.get_states = AsyncMock(return_value=[
        {"entity_id": "cover.a", "state": "open"},
        {"entity_id": "climate.b", "state": "heat"},
        {"entity_id": "light.c", "state": "unavailable"},
        {"entity_id": "lock.d", "state": "locked"},
    ])
    conn.rest.call_service = AsyncMock(return_value=[])
    mgr = SceneManager(conn)
    await mgr.activate("morning")
    conn.rest.call_service.reset_mock()
    assert await mgr.deactivate("morning") is True
    calls = [c.args for c in conn.rest.call_service.await_args_list]
    assert ("cover", "open_cover", {"entity_id": "cover.a"}) in calls
    assert ("climate", "set_hvac_mode", {"entity_id": "climate.b", "hvac_mode": "heat"}) in calls
    assert len(calls) == 2  # unavailable light and lock are not touched


@pytest.mark.asyncio
async def test_absent_does_not_trigger_arrival_mode():
    eng = AutomationEngine(MagicMock(), MagicMock())
    eng._execute_rule = AsyncMock()
    fired = await eng.evaluate_triggers({"present": False, "absent_seconds": 2000})
    assert "away_mode" in fired and "arrival_mode" not in fired


@pytest.mark.asyncio
async def test_never_triggered_rule_not_on_cooldown_shortly_after_boot(monkeypatch):
    monkeypatch.setattr(ae_mod.time, "monotonic", lambda: 10.0)
    eng = AutomationEngine(MagicMock(), MagicMock())
    eng._execute_rule = AsyncMock()
    assert "nighttime_auto_off" in await eng.evaluate_triggers({"hour": 23, "minute": 0})


# -------------------------------------------------------------------- agent
def _agent():
    from districts.home_assistant.agent import HomeAssistantAgent
    a = HomeAssistantAgent()
    a._ensure_ready = AsyncMock(return_value=None)
    return a


@pytest.mark.asyncio
async def test_ha_status_error_when_rest_down():
    a = _agent()
    a._connector.health = AsyncMock(return_value={"rest": False, "ws": False})
    r = await a.run({"type": "ha_status"})
    assert r["status"] == "error"


@pytest.mark.asyncio
async def test_run_accepts_params_text_and_gates(monkeypatch):
    from core.loop import permission_gateway as pg
    seen = {}

    async def fake_execute(self, action):
        seen["a"] = action
        return pg.GatewayResult(True, "YELLOW", True, {"status": "ok", "message": "Turned on x"}, "")

    monkeypatch.setattr(pg.PermissionGateway, "execute", fake_execute)
    r = await _agent().run({"type": "home_control", "params": {"text": "turn on x"}})
    assert seen["a"].action_type == "home_control" and seen["a"].params == {"text": "turn on x"}
    assert r["status"] == "ok"
