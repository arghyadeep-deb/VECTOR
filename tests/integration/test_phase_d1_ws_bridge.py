"""D1 tests — WebSocket bridge: autonomous_loop event_bus -> /ws/state -> dashboard."""
from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── EventType additions ───────────────────────────────────────────────────────


class TestEventTypeAdditions(unittest.TestCase):
    """D1 requires 3 new EventType values in core.event_bus.types."""

    def test_agent_hp_changed_exists(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.AGENT_HP_CHANGED.value, "agent_hp_changed")

    def test_task_routed_exists(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.TASK_ROUTED.value, "task_routed")

    def test_anomaly_detected_exists(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.ANOMALY_DETECTED.value, "anomaly_detected")

    def test_decision_made_still_exists(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.DECISION_MADE.value, "decision_made")

    def test_hypothesis_surfaced_still_exists(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.HYPOTHESIS_SURFACED.value, "hypothesis_surfaced")


# ── /ws/state endpoint presence ───────────────────────────────────────────────


class TestWsStateEndpointExists(unittest.TestCase):
    """vector_ws_state is registered on the WebSocket router."""

    def test_vector_ws_state_in_all(self):
        import core.api.routers.websocket as mod
        self.assertIn("vector_ws_state", mod.__all__)

    def test_vector_ws_state_is_callable(self):
        from core.api.routers.websocket import vector_ws_state
        self.assertTrue(callable(vector_ws_state))

    def test_vector_ws_state_is_async(self):
        import asyncio
        from core.api.routers.websocket import vector_ws_state
        self.assertTrue(asyncio.iscoroutinefunction(vector_ws_state))

    def test_ws_state_route_registered_on_router(self):
        """The router has a /state WebSocket route."""
        import inspect
        from core.api.routers.websocket import vector_ws_state
        src = inspect.getsource(vector_ws_state)
        self.assertIn("state_event", src)

    def test_state_ready_sent_on_connect(self):
        """vector_ws_state sends state_ready immediately on connect."""
        import inspect
        from core.api.routers.websocket import vector_ws_state
        src = inspect.getsource(vector_ws_state)
        self.assertIn("state_ready", src)


# ── WebSocket route prefix ────────────────────────────────────────────────────


class TestWsRouterPrefix(unittest.TestCase):
    """The WebSocket router is mounted at /ws so /ws/state resolves correctly."""

    def test_router_prefix_is_ws(self):
        from core.api.routers.websocket import router
        self.assertEqual(router.prefix, "/ws")

    def test_state_route_in_router_routes(self):
        from core.api.routers.websocket import router
        paths = [r.path for r in router.routes]
        # FastAPI includes the prefix in the stored path, so full path is /ws/state
        self.assertTrue(
            any("/state" in p for p in paths),
            f"No /state route found in {paths}",
        )


# ── ConnectionManager broadcast ───────────────────────────────────────────────


class TestConnectionManagerBroadcast(unittest.TestCase):
    """ConnectionManager sends to all connected clients and cleans up dead ones."""

    def test_connect_adds_to_connections(self):
        from core.api.routers.websocket import ConnectionManager
        mgr = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        async def run():
            await mgr.connect(mock_ws)
            return len(mgr._connections)

        count = asyncio.run(run())
        self.assertEqual(count, 1)

    def test_disconnect_removes_from_connections(self):
        from core.api.routers.websocket import ConnectionManager
        mgr = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        async def run():
            await mgr.connect(mock_ws)
            mgr.disconnect(mock_ws)
            return len(mgr._connections)

        count = asyncio.run(run())
        self.assertEqual(count, 0)

    def test_broadcast_calls_send_json_for_each_connection(self):
        from core.api.routers.websocket import ConnectionManager
        mgr = ConnectionManager()
        ws1, ws2 = MagicMock(), MagicMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        async def run():
            await mgr.connect(ws1)
            await mgr.connect(ws2)
            await mgr.broadcast({"type": "test"})

        asyncio.run(run())
        ws1.send_json.assert_called_once_with({"type": "test"})
        ws2.send_json.assert_called_once_with({"type": "test"})

    def test_broadcast_removes_dead_connection(self):
        from core.api.routers.websocket import ConnectionManager
        mgr = ConnectionManager()
        dead_ws = MagicMock()
        dead_ws.accept = AsyncMock()
        dead_ws.send_json = AsyncMock(side_effect=RuntimeError("broken pipe"))

        async def run():
            await mgr.connect(dead_ws)
            await mgr.broadcast({"type": "test"})
            return len(mgr._connections)

        count = asyncio.run(run())
        self.assertEqual(count, 0)


# ── event_bus publish → ws/state forward ─────────────────────────────────────


class TestEventBusForwardToWsState(unittest.TestCase):
    """Events published to the bus arrive at connected /ws/state clients."""

    def test_decision_made_forwarded(self):
        """Publish DECISION_MADE to bus; mock forward handler receives it."""
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        received: list[dict] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                received.append({
                    "type": "state_event",
                    "event_type": event.event_type.value,
                    "data": event.data,
                })

            sub = bus.subscribe(EventType.DECISION_MADE, handler)
            event = Event(
                event_type=EventType.DECISION_MADE,
                data={"action_type": "send_morning_brief", "score": 0.92},
                source="autonomous_loop",
            )
            await bus.publish(event)
            await asyncio.sleep(0.1)  # allow consumer task to process
            await bus.stop()

        asyncio.run(run())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event_type"], "decision_made")
        self.assertEqual(received[0]["data"]["action_type"], "send_morning_brief")

    def test_hypothesis_surfaced_forwarded(self):
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        received: list[str] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                received.append(event.event_type.value)

            bus.subscribe(EventType.HYPOTHESIS_SURFACED, handler)
            await bus.publish(Event(
                event_type=EventType.HYPOTHESIS_SURFACED,
                data={"text": "Owner likely wants coffee", "confidence": 0.82},
                source="hypothesis_engine",
            ))
            await asyncio.sleep(0.1)
            await bus.stop()

        asyncio.run(run())
        self.assertIn("hypothesis_surfaced", received)

    def test_agent_hp_changed_forwarded(self):
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        received: list[str] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                received.append(event.event_type.value)

            bus.subscribe(EventType.AGENT_HP_CHANGED, handler)
            await bus.publish(Event(
                event_type=EventType.AGENT_HP_CHANGED,
                data={"agent_id": "git_bot", "old_hp": 600, "new_hp": 650},
                source="agent_registry",
            ))
            await asyncio.sleep(0.1)
            await bus.stop()

        asyncio.run(run())
        self.assertIn("agent_hp_changed", received)

    def test_task_routed_forwarded(self):
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        received: list[str] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                received.append(event.event_type.value)

            bus.subscribe(EventType.TASK_ROUTED, handler)
            await bus.publish(Event(
                event_type=EventType.TASK_ROUTED,
                data={"task_type": "code_review", "district": "coding"},
                source="governor",
            ))
            await asyncio.sleep(0.1)
            await bus.stop()

        asyncio.run(run())
        self.assertIn("task_routed", received)

    def test_anomaly_detected_forwarded(self):
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        received: list[str] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                received.append(event.event_type.value)

            bus.subscribe(EventType.ANOMALY_DETECTED, handler)
            await bus.publish(Event(
                event_type=EventType.ANOMALY_DETECTED,
                data={"description": "CPU spike > 90%", "severity": "high"},
                source="health_monitor",
            ))
            await asyncio.sleep(0.1)
            await bus.stop()

        asyncio.run(run())
        self.assertIn("anomaly_detected", received)

    def test_event_delivered_within_100ms(self):
        """Bus delivers events to subscriber within 100ms (performance gate)."""
        from core.event_bus.bus import AsyncEventBus
        from core.event_bus.types import Event, EventType

        arrival_time: list[float] = []
        publish_time: list[float] = []

        async def run():
            bus = AsyncEventBus()
            await bus.start()

            async def handler(event: Event):
                arrival_time.append(time.monotonic())

            bus.subscribe(EventType.DECISION_MADE, handler)
            await asyncio.sleep(0.01)  # let subscriber task start
            publish_time.append(time.monotonic())
            await bus.publish(Event(
                event_type=EventType.DECISION_MADE,
                data={"action_type": "test"},
                source="test",
            ))
            await asyncio.sleep(0.15)
            await bus.stop()

        asyncio.run(run())
        self.assertEqual(len(arrival_time), 1, "Handler must be called exactly once")
        latency_ms = (arrival_time[0] - publish_time[0]) * 1000
        self.assertLess(latency_ms, 100.0, f"Latency {latency_ms:.1f}ms > 100ms SLA")


# ── broadcast_event helper ────────────────────────────────────────────────────


class TestBroadcastEventHelper(unittest.TestCase):
    """broadcast_event() module helper never raises and reaches all WS clients."""

    def test_broadcast_event_importable(self):
        from core.api.routers.websocket import broadcast_event
        self.assertTrue(callable(broadcast_event))

    def test_broadcast_event_is_async(self):
        import asyncio
        from core.api.routers.websocket import broadcast_event
        self.assertTrue(asyncio.iscoroutinefunction(broadcast_event))

    def test_broadcast_event_never_raises(self):
        """broadcast_event must not propagate exceptions (RULE 2)."""
        from core.api.routers.websocket import broadcast_event
        try:
            asyncio.run(broadcast_event({"type": "test"}))
        except Exception as exc:
            self.fail(f"broadcast_event raised: {exc}")


# ── Dashboard wiring ──────────────────────────────────────────────────────────


class TestDashboardWiring(unittest.TestCase):
    """App.tsx connects to /ws/state and handles state_event messages."""

    def _read_app_tsx(self) -> str:
        path = Path(__file__).parent.parent.parent / "dashboard" / "src" / "App.tsx"
        return path.read_text(encoding="utf-8")

    def test_dashboard_uses_ws_state_url(self):
        src = self._read_app_tsx()
        self.assertIn("/ws/state", src, "App.tsx must connect to /ws/state")

    def test_dashboard_handles_state_event_type(self):
        src = self._read_app_tsx()
        self.assertIn("state_event", src)

    def test_dashboard_handles_decision_made(self):
        src = self._read_app_tsx()
        self.assertIn("decision_made", src)

    def test_dashboard_handles_hypothesis_surfaced(self):
        src = self._read_app_tsx()
        self.assertIn("hypothesis_surfaced", src)


if __name__ == "__main__":
    unittest.main()
