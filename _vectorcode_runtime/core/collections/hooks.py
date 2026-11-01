"""Per-collection CRUD hooks for the VECTOR collections engine.

Python reimplementation of PocketBase's record event hooks (core/events.go, tools/hook/):
before/after create|update|delete handlers with priority ordering. `before` handlers may
mutate the incoming data or cancel the operation; `after` handlers are notifications. Each
fired event is also broadcast onto VECTOR's existing AsyncEventBus (RECORD_CREATED /
RECORD_UPDATED / RECORD_DELETED) so the rest of the system can react — best-effort and
non-blocking, so a missing/idle event loop never breaks synchronous CRUD.
"""

from __future__ import annotations

import sys

__all__ = [
    "HookContext",
    "CollectionHooks",
    "HookCancelled",
    "get_hooks",
    "HOOK_EVENTS",
]


import asyncio
from dataclasses import dataclass, field

from loguru import logger
from core.config import CONFIG  # noqa: F401

HOOK_EVENTS = {
    "before_create", "after_create",
    "before_update", "after_update",
    "before_delete", "after_delete",
}

# Maps an after-event to the AsyncEventBus EventType broadcast on the system bus.
_BUS_EVENT = {
    "after_create": "RECORD_CREATED",
    "after_update": "RECORD_UPDATED",
    "after_delete": "RECORD_DELETED",
}


class HookCancelled(Exception):
    """Raised internally when a before-hook cancels an operation."""


@dataclass
class HookContext:
    collection: str
    action: str                 # create | update | delete
    phase: str                  # before | after
    record_id: str | None = None
    data: dict | None = None    # mutable payload for before-hooks
    record: dict | None = None  # resulting record for after-hooks
    cancelled: bool = False
    cancel_reason: str = ""

    def cancel(self, reason: str = "") -> None:
        self.cancelled = True
        self.cancel_reason = reason


@dataclass(order=True)
class _Handler:
    priority: int
    seq: int
    fn: object = field(compare=False)
    collection: str | None = field(default=None, compare=False)


class CollectionHooks:
    """Synchronous before/after hook registry + best-effort system-bus broadcast."""

    def __init__(self, bus=None, publish_events: bool = True):
        self._handlers: dict[str, list[_Handler]] = {e: [] for e in HOOK_EVENTS}
        self._seq = 0
        self._bus = bus
        self.publish_events = publish_events

    # ── registration ────────────────────────────────────────────────────────
    def on(self, event: str, fn, *, collection: str | None = None, priority: int = 0):
        if event not in HOOK_EVENTS:
            raise ValueError(f"unknown hook event {event!r}; valid: {sorted(HOOK_EVENTS)}")
        self._seq += 1
        self._handlers[event].append(_Handler(priority, self._seq, fn, collection))
        self._handlers[event].sort()   # lower priority first, then registration order
        return fn

    # convenience decorators/registrars
    def before_create(self, fn=None, *, collection=None, priority=0):
        return self._reg("before_create", fn, collection, priority)

    def after_create(self, fn=None, *, collection=None, priority=0):
        return self._reg("after_create", fn, collection, priority)

    def before_update(self, fn=None, *, collection=None, priority=0):
        return self._reg("before_update", fn, collection, priority)

    def after_update(self, fn=None, *, collection=None, priority=0):
        return self._reg("after_update", fn, collection, priority)

    def before_delete(self, fn=None, *, collection=None, priority=0):
        return self._reg("before_delete", fn, collection, priority)

    def after_delete(self, fn=None, *, collection=None, priority=0):
        return self._reg("after_delete", fn, collection, priority)

    def _reg(self, event, fn, collection, priority):
        if fn is None:
            def _wrap(f):
                self.on(event, f, collection=collection, priority=priority)
                return f
            return _wrap
        return self.on(event, fn, collection=collection, priority=priority)

    def clear(self):
        for e in self._handlers:
            self._handlers[e].clear()

    # ── firing ────────────────────────────────────────────────────────────────
    def fire(self, event: str, ctx: HookContext) -> HookContext:
        """Run all handlers for `event` (filtered by collection) in priority order.
        before-handlers may mutate ctx or call ctx.cancel(). after-handlers also trigger
        a best-effort system-bus broadcast."""
        if event not in HOOK_EVENTS:
            raise ValueError(f"unknown hook event {event!r}")
        for h in list(self._handlers[event]):
            if h.collection is not None and h.collection != ctx.collection:
                continue
            try:
                h.fn(ctx)
            except HookCancelled:
                ctx.cancel("handler raised HookCancelled")
            except Exception as e:
                # A misbehaving hook must not crash the CRUD path (RULE 2 spirit).
                logger.error(f"[VECTOR][collections] hook {event} for {ctx.collection} failed: {e}")
            if ctx.cancelled and ctx.phase == "before":
                logger.info(f"[VECTOR][collections] {event} cancelled: {ctx.cancel_reason}")
                break
        if event in _BUS_EVENT and not ctx.cancelled and self.publish_events:
            self._broadcast(event, ctx)
        return ctx

    def _broadcast(self, event: str, ctx: HookContext):
        try:
            from core.event_bus import get_event_bus, Event, EventType
            bus = self._bus or get_event_bus()
            evt = Event(
                event_type=EventType[_BUS_EVENT[event]],
                data={"collection": ctx.collection, "record_id": ctx.record_id,
                      "record": ctx.record},
                source="collections",
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bus.publish(evt))      # fire-and-forget when a loop exists
            except RuntimeError:
                pass  # no running loop (sync context) — skip broadcast, hooks already ran
        except Exception as e:
            logger.debug(f"[VECTOR][collections] event broadcast skipped: {e}")


_DEFAULT_HOOKS: CollectionHooks | None = None


def get_hooks() -> CollectionHooks:
    global _DEFAULT_HOOKS
    if _DEFAULT_HOOKS is None:
        _DEFAULT_HOOKS = CollectionHooks()
    return _DEFAULT_HOOKS


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    hooks = CollectionHooks(publish_events=False)
    order = []

    # priority ordering (lower first), then registration order
    hooks.before_create(lambda c: order.append("p10"), priority=10)
    hooks.before_create(lambda c: order.append("p0a"), priority=0)
    hooks.before_create(lambda c: order.append("p0b"), priority=0)
    ctx = HookContext(collection="notes", action="create", phase="before", data={"x": 1})
    hooks.fire("before_create", ctx)
    assert order == ["p0a", "p0b", "p10"], order

    # before-hook can mutate data
    hooks.clear()
    hooks.before_create(lambda c: c.data.update(slug="auto"))
    ctx = HookContext(collection="notes", action="create", phase="before", data={"title": "Hi"})
    hooks.fire("before_create", ctx)
    assert ctx.data["slug"] == "auto"

    # before-hook can cancel (stops the chain)
    hooks.clear()
    hit = []
    hooks.before_delete(lambda c: c.cancel("nope"), priority=0)
    hooks.before_delete(lambda c: hit.append("ran"), priority=1)
    ctx = HookContext(collection="notes", action="delete", phase="before", record_id="r1")
    hooks.fire("before_delete", ctx)
    assert ctx.cancelled and ctx.cancel_reason == "nope" and hit == []

    # collection-scoped handler only fires for its collection
    hooks.clear()
    seen = []
    hooks.after_create(lambda c: seen.append(c.collection), collection="notes")
    hooks.fire("after_create", HookContext(collection="other", action="create", phase="after"))
    hooks.fire("after_create", HookContext(collection="notes", action="create", phase="after"))
    assert seen == ["notes"], seen

    # a throwing hook does not break the fire loop
    hooks.clear()
    survived = []
    hooks.after_update(lambda c: (_ for _ in ()).throw(RuntimeError("boom")), priority=0)
    hooks.after_update(lambda c: survived.append("ok"), priority=1)
    hooks.fire("after_update", HookContext(collection="n", action="update", phase="after"))
    assert survived == ["ok"]

    # bus broadcast under a running loop delivers the event
    async def _bus_test():
        from core.event_bus import AsyncEventBus, EventType
        bus = AsyncEventBus()
        await bus.start()
        got = []
        bus.subscribe(EventType.RECORD_CREATED, lambda e: got.append(e))
        h = CollectionHooks(bus=bus, publish_events=True)
        h.fire("after_create", HookContext(collection="notes", action="create",
                                           phase="after", record_id="r9",
                                           record={"id": "r9"}))
        await asyncio.sleep(0.2)
        await bus.stop()
        return got

    delivered = asyncio.run(_bus_test())
    assert len(delivered) == 1 and delivered[0].data["record_id"] == "r9", delivered

    print("✅ hooks.py OK" if ok else "❌ FAILED")
