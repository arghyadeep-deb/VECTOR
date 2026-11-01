"""
VectorCode Event Bus Hooks — replaces Claude Code hook scripts.
These fire on VECTOR's internal event bus instead of Claude Code's hook system.

Replaces:
- ~/.claude/hooks/session_start_hook.py  → fires on VECTOR startup/session init
- ~/.claude/hooks/suggest_compact_hook.py → fires on every agent action
"""
import asyncio
from loguru import logger

from vectorcode.src.bootstrap import ensure_paths

ensure_paths()


async def on_session_start(event: dict) -> None:
    """
    Fires when VECTOR session initializes — injects context.
    Replaces ~/.claude/hooks/session_start_hook.py
    """
    try:
        from core.memory.reasoning_memory import ReasoningMemory
        from core.brain.goal_system import GoalSystem

        context_lines = ["[VECTOR SESSION START]"]

        # Recent reasoning
        try:
            mem = ReasoningMemory()
            recent = mem.get_recent(limit=5) if hasattr(mem, 'get_recent') else []
            if recent:
                context_lines.append("Recent reasoning:")
                for r in recent[:3]:
                    context_lines.append(f"  - {str(r)[:120]}")
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

        # Active goals
        try:
            gs = GoalSystem()
            goals = gs.get_active_goals()
            if goals:
                context_lines.append("Active goals:")
                for g in goals[:5]:
                    context_lines.append(
                        f"  [{g.get('horizon', '?')}] {g.get('description', '?')[:100]}"
                    )
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

        # Available commands
        try:
            from vectorcode.src.command_registry import get_command_registry
            reg = get_command_registry()
            cmds = list(reg.load().keys())[:10]
            if cmds:
                context_lines.append(f"Available commands: {', '.join(cmds)}")
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

        logger.info("[VECTOR][hooks] Session start:\n{}", "\n".join(context_lines))
    except Exception as e:
        logger.debug("[VECTOR][hooks] on_session_start error: {}", e)


_tool_call_count = 0
_COMPACT_WARN_THRESHOLD = 40


async def on_pre_tool_use(event: dict) -> None:
    """
    Fires before each agent tool use — warns about context size.
    Replaces ~/.claude/hooks/suggest_compact_hook.py
    """
    global _tool_call_count
    _tool_call_count += 1

    if _tool_call_count >= _COMPACT_WARN_THRESHOLD:
        try:
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            if hasattr(ctx, 'is_context_near_limit') and ctx.is_context_near_limit():
                logger.warning(
                    "[VECTOR][hooks] Context near limit ({} tool calls) — consider compacting",
                    _tool_call_count,
                )
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass


def register_hooks() -> None:
    """Register all hooks on the VECTOR event bus."""
    try:
        from core.event_bus.bus import get_event_bus
        from core.event_bus.types import EventType

        bus = get_event_bus()

        # Session start equivalent — fires when a new task is scheduled (session init)
        if hasattr(EventType, 'TASK_SCHEDULED'):
            bus.subscribe(EventType.TASK_SCHEDULED, on_session_start)

        # Pre-tool-use — fire on every agent state change
        if hasattr(EventType, 'AGENT_STATE_CHANGED'):
            bus.subscribe(EventType.AGENT_STATE_CHANGED, on_pre_tool_use)

        logger.info("[VECTOR][hooks] Event bus hooks registered")
    except Exception as e:
        logger.warning("[VECTOR][hooks] Could not register event bus hooks: {}", e)


if __name__ == "__main__":
    register_hooks()
    print("✅ event_bus_hooks OK")