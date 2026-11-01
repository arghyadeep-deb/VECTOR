# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py (run_conversation)
"""The main think→act→observe loop."""
import asyncio
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .tool_exec import _should_parallelize_tool_batch, execute_tool_calls_sequential, execute_tool_calls_concurrent
from .safety import _sanitize_surrogates

if TYPE_CHECKING:
    from .agent import AIAgent


async def run_conversation_loop(agent: "AIAgent", user_message: str) -> Dict[str, Any]:
    """Core think→act→observe loop.

    1. Append user message to history
    2. Call model
    3. If model returns tool_calls → execute → append results → goto 2
    4. If model returns text → return final response
    5. If budget exhausted → call _handle_max_iterations
    """
    from .max_iter import handle_max_iterations

    # Sanitize input
    user_message = _sanitize_surrogates(user_message)

    # Prefetch memory if available
    if agent.memory_manager is not None:
        try:
            await _maybe_prefetch_memory(agent, user_message)
        except Exception as e:
            logger.warning(f"Memory prefetch failed: {e}")

    # Memory cadence — track turn count for periodic memory review
    if not hasattr(agent, "_user_turn_count"):
        agent._user_turn_count = 0
    agent._user_turn_count += 1

    # Plugin pre-LLM hook — invoke before model call so plugins can inject context
    plugin_context_extras = []
    try:
        from vectorcode.plugins import init_plugins  # lazy
        for plugin_mod in getattr(agent, "_plugins", []) or []:
            hook = getattr(plugin_mod, "pre_llm_call", None)
            if callable(hook):
                try:
                    extras = hook(agent, user_message)
                    if extras:
                        plugin_context_extras.append(str(extras))
                except Exception as e:
                    logger.warning(f"Plugin pre_llm_call hook failed: {e}")
    except Exception as _sve:
        logger.debug("[VECTOR][engine.conversation] suppressed Exception: {}", _sve)

    # If plugins added context, inject it before the user message
    if plugin_context_extras:
        user_message = "\n\n".join(plugin_context_extras) + "\n\n" + user_message

    # Append user turn
    agent._history.append({"role": "user", "content": user_message})

    # Record in session DB
    if agent.session_db is not None:
        try:
            agent.session_db.add_message(
                session_id=agent.session_id,
                role="user",
                content=user_message,
            )
        except Exception as e:
            logger.warning(f"session_db.add_message failed: {e}")

    final_text = ""
    tool_calls_total = 0

    while True:
        # Check budget
        if not agent.budget.consume():
            logger.warning(f"Iteration budget exhausted ({agent.budget.max_total})")
            return await handle_max_iterations(agent, final_text)

        # Build system prompt on first call
        if agent._system_prompt is None:
            agent._system_prompt = _build_system_prompt(agent)

        # Call model
        try:
            response = await _call_model(agent)
        except Exception as e:
            logger.error(f"Model call failed: {e}")
            # Try credential rotation
            from .recovery import recover_on_error
            response = await recover_on_error(agent, e)
            if response is None:
                return {"status": "error", "error": str(e), "text": final_text}

        # Parse response
        content = _extract_content(response)
        tool_calls = _extract_tool_calls(response)

        if content:
            final_text = content

        if not tool_calls:
            # Model is done — no more tool calls
            break

        tool_calls_total += len(tool_calls)
        logger.debug(f"Executing {len(tool_calls)} tool call(s) (total so far: {tool_calls_total})")

        # Execute tools — use VectorCode model_tools.handle_function_call if available
        try:
            from model_tools import handle_function_call as _vector_dispatch
            def dispatch_fn(name, args, ctx):
                return _vector_dispatch(name, args)
        except Exception:
            registry = agent._get_registry()
            if registry and hasattr(registry, "get_entry"):
                def dispatch_fn(name, args, ctx):
                    entry = registry.get_entry(name)
                    if entry is None:
                        return f"Error: tool {name!r} not registered"
                    try:
                        return entry.handler(**args)
                    except Exception as e:
                        return f"Error: {e}"
            else:
                dispatch_fn = _noop_dispatch

        if _should_parallelize_tool_batch(tool_calls):
            results = execute_tool_calls_concurrent(tool_calls, dispatch_fn, agent)
        else:
            results = execute_tool_calls_sequential(tool_calls, dispatch_fn, agent)

        # Append assistant turn with tool calls
        agent._history.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": tool_calls,
        })

        # Append tool results
        for res in results:
            result_content = res.get("result", "")
            if not isinstance(result_content, str):
                result_content = json.dumps(result_content)
            agent._history.append({
                "role": "tool",
                "tool_call_id": res.get("id", ""),
                "name": res.get("name", ""),
                "content": result_content,
            })

        # Small delay between iterations
        if agent.tool_delay > 0:
            await asyncio.sleep(agent.tool_delay)

    # Append final assistant turn
    if final_text:
        agent._history.append({"role": "assistant", "content": final_text})
        if agent.session_db is not None:
            try:
                agent.session_db.add_message(
                    session_id=agent.session_id,
                    role="assistant",
                    content=final_text,
                )
            except Exception as e:
                logger.warning(f"session_db.add_message failed: {e}")

    # Sync memory after turn
    if agent.memory_manager is not None:
        try:
            await _maybe_sync_memory(agent, final_text)
        except Exception as e:
            logger.warning(f"Memory sync failed: {e}")

    # Plugin post-LLM hook — invoke after model finishes so plugins can react
    try:
        for plugin_mod in getattr(agent, "_plugins", []) or []:
            hook = getattr(plugin_mod, "post_llm_call", None)
            if callable(hook):
                try:
                    hook(agent, final_text, tool_calls_total)
                except Exception as e:
                    logger.warning(f"Plugin post_llm_call hook failed: {e}")
    except Exception as _sve:
        logger.debug("[VECTOR][engine.conversation] suppressed Exception: {}", _sve)

    # Memory review cadence — every N turns, write a summary memory
    cadence = getattr(agent, "_memory_nudge_interval", 10)
    if cadence > 0 and agent._user_turn_count % cadence == 0 and agent.memory_manager:
        try:
            mm = agent.memory_manager
            if hasattr(mm, "review"):
                review_result = mm.review(agent._user_turn_count)
                if hasattr(review_result, "__await__"):
                    await review_result
        except Exception as e:
            logger.warning(f"Memory review failed: {e}")

    return {
        "status": "ok",
        "text": final_text,
        "tool_calls_total": tool_calls_total,
        "iterations_used": agent.budget.used,
    }


def _build_system_prompt(agent: "AIAgent") -> str:
    """Build the system prompt for this agent."""
    from core.loop.context_engine import ContextEngine

    hydration = ContextEngine().session_hydration_prompt(
        {"session_id": agent.session_id, "model": agent.model}
    )
    if agent.ephemeral_system_prompt:
        purpose_prompt = agent.ephemeral_system_prompt
    else:
        try:
            from vectorcode.context.prompt_builder import build_system_prompt
            purpose_prompt = build_system_prompt(agent)
        except Exception:
            purpose_prompt = "You are VectorCode, an autonomous coding agent."
    return f"{hydration}\n\n{purpose_prompt}" if hydration else purpose_prompt


async def _call_model(agent: "AIAgent") -> Any:
    """Call the model with current history."""
    provider = agent._get_provider()
    if provider is None:
        # Fallback: try direct Ollama
        return await _call_ollama_direct(agent)

    messages = []
    if agent._system_prompt:
        messages.append({"role": "system", "content": agent._system_prompt})
    messages.extend(agent._history)

    registry = agent._get_registry()

    # Get tool definitions via model_tools (VectorCode API)
    tools = []
    try:
        from model_tools import get_tool_definitions
        tools = get_tool_definitions(
            enabled_toolsets=[agent.toolset] if agent.toolset != "full" else None,
            disabled_toolsets=None,
            quiet_mode=True,
        )
    except Exception:
        # Fallback: build from registry entries directly
        if registry:
            for entry in registry._snapshot_entries() if hasattr(registry, "_snapshot_entries") else []:
                tools.append({"type": "function", "function": {
                    "name": entry.name,
                    "description": entry.description or "",
                    "parameters": entry.schema if isinstance(entry.schema, dict) else {},
                }})

    return await provider.chat(
        model=agent.model,
        messages=messages,
        tools=tools,
    )


async def _call_ollama_direct(agent: "AIAgent") -> Any:
    """Direct Ollama fallback when provider router not available."""
    import httpx
    base_url = agent.base_url or "http://localhost:11434"
    messages = []
    if agent._system_prompt:
        messages.append({"role": "system", "content": agent._system_prompt})
    messages.extend(agent._history)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{base_url}/api/chat",
            json={"model": agent.model or "qwen2.5-coder:7b", "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data


def _extract_content(response: Any) -> str:
    """Extract text content from a model response."""
    if isinstance(response, dict):
        # Ollama format
        msg = response.get("message", {})
        return msg.get("content", "") or response.get("content", "")
    # OpenAI SDK object
    try:
        return response.choices[0].message.content or ""
    except Exception:
        return str(response)


def _extract_tool_calls(response: Any) -> list:
    """Extract tool calls from a model response."""
    if isinstance(response, dict):
        msg = response.get("message", {})
        return msg.get("tool_calls", [])
    try:
        tcs = response.choices[0].message.tool_calls
        return tcs or []
    except Exception:
        return []


def _noop_dispatch(name: str, args: dict, context: Any) -> str:
    return f"[tool {name!r} not registered]"


async def _maybe_prefetch_memory(agent: "AIAgent", text: str) -> None:
    mm = agent.memory_manager
    if hasattr(mm, "prefetch_all"):
        result = mm.prefetch_all(text)
        if hasattr(result, "__await__"):
            await result


async def _maybe_sync_memory(agent: "AIAgent", text: str) -> None:
    mm = agent.memory_manager
    if hasattr(mm, "sync_all"):
        result = mm.sync_all()
        if hasattr(result, "__await__"):
            await result
