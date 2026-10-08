# OD-43 ChannelAgent Production Wiring Plan

## Goal

Make explicitly addressed chat-channel requests reach a named VECTOR city agent without bypassing the Permission Gateway or HP accounting, and replace `ChannelAgent`'s private thread pool with asyncio-owned tasks.

## Confirmed baseline

- `ChannelAgent` currently registers `self._handle_message` and calls `self._agent.run(msg.content)` directly inside its own `ThreadPoolExecutor`.
- That call does not use `core.city.governor.Governor.dispatch`, `PermissionGateway`, or the city HP lifecycle.
- Registered production chat platforms converge on `GatewayRunner._handle_message(MessageEvent)`.
- `core.city.a2a_bus.A2ABus` already supports pinning a named live agent while delivering through `Governor.dispatch`; Governor supplies permission classification, dispatch timeout, audit/event handling, and HP accounting.

## Trigger contract

Use `/agent <agent-id-or-name> <task-type> <request>`.

The explicit task type is required so the existing Permission Gateway vocabulary can classify the requested action before the named agent runs. Unmatched messages remain on the existing gateway conversation path.

## Steps

1. Add regression tests for the gateway-to-ChannelAgent construction site, named-agent delivery through the real A2A/Governor path, real HP credit, and real permission refusal.
2. Convert `ChannelAgent` to asyncio task ownership, supporting both synchronous and awaitable agent/channel implementations without creating a private executor.
3. Add a small governed invoker backed by `A2ABus` and response normalization.
4. Construct `ChannelAgent` in `GatewayRunner`, intercept the explicit command after user authorization, and drain owned tasks during shutdown.
5. Prove the new tests fail with implementation files stashed, restore the implementation, then run targeted compilation and tests.

## Risks and controls

- Command collision: only the exact `/agent` prefix is intercepted.
- Governance bypass: the production invoker never calls a city agent directly; it uses `A2ABus.ask`, which calls `Governor.dispatch`.
- Shutdown leaks: `ChannelAgent.shutdown()` cancels and awaits all tasks it owns.
- Invalid/missing agents and malformed commands: return a concise usage/refusal response and do not enter the ordinary chat path.
