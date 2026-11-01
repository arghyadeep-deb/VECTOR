"""Explicit terminal shortcuts over existing configuration, tools and session stores."""

import json
import subprocess

NAMES = {
    "fast",
    "reasoning",
    "platforms",
    "copy",
    "paste",
    "skin",
    "statusbar",
    "verbose",
    "debug",
    "branch",
    "queue",
    "fork",
    "browser",
    "cron",
    "reload-mcp",
}


def execute(adapter, name, argument):
    from vectorcode.src.session import VectorCodeSession

    bridge = adapter.bridge
    session = VectorCodeSession.get()
    result = adapter._result
    if name in {"fast", "reasoning"}:
        from vectorcode.src.config import VectorConfig

        if argument:
            raise ValueError(f"Usage: /{name} (select the configured model alias).")
        config = VectorConfig(bridge.project)
        session.current_model = (
            config.fast_model
            if name == "fast"
            else "ollama/" + config.get("models", "reasoning", default="vector-reasoning")
        )
        return result("Selected " + session.current_model + ". No priority-processing billing option is enabled.")
    if name == "platforms":
        from vectorcode.src.vector_cli.platforms import PLATFORMS

        return result(
            "Registered messaging platforms (registration is not a live connection check):\n"
            + "\n".join(f"{key}: {info.label}" for key, info in PLATFORMS.items())
        )
    if name in {"copy", "paste"}:
        import pyperclip

        if argument:
            raise ValueError(f"Usage: /{name}")
        if name == "paste":
            text = pyperclip.paste()
            return result("Clipboard text inserted into the draft; review it before submitting.", composerText=text)
        response = next(
            (
                m.get("content", "")
                for m in reversed(bridge.history)
                if m.get("role") == "assistant" and m.get("content")
            ),
            "",
        )
        if not response:
            return result("No assistant response to copy.")
        pyperclip.copy(response)
        return result("Copied the last assistant response to the clipboard.")
    if name == "skin":
        from vectorcode.src.vector_cli.skin_engine import list_skins, set_active_skin

        skins = list_skins()
        if not argument:
            return result("\n".join(item["name"] + ": " + item["description"] for item in skins))
        if argument not in {item["name"] for item in skins}:
            raise ValueError("Unknown skin. Use /skin to list installed skins.")
        skin = set_active_skin(argument)
        return result("Skin: " + skin.name, display={"colors": skin.colors})
    if name in {"statusbar", "verbose", "debug"}:
        if argument:
            raise ValueError(f"Usage: /{name} (toggle)")
        settings = getattr(bridge, "display_settings", {"statusbar": True, "verbose": False, "debug": False})
        settings[name] = not settings[name]
        bridge.display_settings = settings
        if name == "debug" and getattr(bridge, "log_sink", None) is not None:
            import sys

            from loguru import logger

            logger.remove(bridge.log_sink)
            bridge.log_sink = logger.add(sys.stderr, level="DEBUG" if settings[name] else "WARNING")
        return result(f"{name}: {'on' if settings[name] else 'off'}", display=dict(settings))
    if name == "queue":
        if argument:
            raise ValueError("Usage: /queue (inspect only; this terminal has no background prompt executor).")
        return result("No pending queued messages. This terminal executes one foreground turn at a time.")
    if name == "fork":
        import uuid

        from vectorcode.src.terminal_sessions import checkpoint

        if argument:
            raise ValueError("Usage: /fork")
        checkpoint(bridge)
        session.session_id = str(uuid.uuid4())
        checkpoint(bridge)
        return result(
            "Forked conversation: " + session.session_id + ". Future tools still require approval.",
            history=bridge.history,
        )
    if name == "branch":
        import os
        import shlex

        from vectorcode.src.tools.environments.local import _sanitize_subprocess_env

        args = ["git", "branch", "--list", "--no-color"]
        if argument:
            # Pass branch names as argv, never shell code or an option.
            names = shlex.split(argument)
            if len(names) != 1 or names[0].startswith("-"):
                raise ValueError("Usage: /branch [existing-local-branch]")
            local = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", "refs/heads/" + names[0]],
                cwd=bridge.project, capture_output=True, text=True, timeout=15,
                env=_sanitize_subprocess_env(dict(os.environ)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if local.returncode:
                raise ValueError("Choose an existing local branch; use /branch to list them.")
            if not _approve(bridge, session, "git_switch", {"branch": names[0]}):
                return result("Command denied; no branch was switched.")
            args = ["git", "switch", names[0]]
        completed = subprocess.run(
            args,
            cwd=bridge.project,
            capture_output=True,
            text=True,
            timeout=15,
            env=_sanitize_subprocess_env(dict(os.environ)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            raise ValueError((completed.stderr or "Git command failed.").strip())
        return result((completed.stdout + completed.stderr).strip() or "No local branches.")
    if name in {"browser", "cron"}:
        from vectorcode.src.tools.registry import ToolRouter

        router = ToolRouter(
            project_dir=bridge.project, enabled_toolsets=["browser" if name == "browser" else "cronjob"]
        )
        schemas = router.get_schemas()
        available = {schema["function"]["name"] for schema in schemas}
        if not available:
            return result(
                f"/{name} tools are unavailable in this environment; check the existing backend requirements."
            )
        if not argument:
            return result(
                "Explicit tools (every execution asks approval):\n"
                + json.dumps(schemas, ensure_ascii=True, indent=2)
                + (
                    "\nUsage: /browser <tool-name> {JSON arguments}"
                    if name == "browser"
                    else '\nUsage: /cron {"action":"list"}'
                )
            )
        if name == "browser":
            parts = argument.split(maxsplit=1)
            tool = parts[0]
            args = json.loads(parts[1] if len(parts) > 1 else "{}")
        else:
            tool = "cronjob"
            args = json.loads(argument)
        if tool not in available or not isinstance(args, dict):
            raise ValueError("Select an available tool and a JSON object from /" + name + ".")
        if not _approve(bridge, session, tool, args):
            return result("Command denied; no tool was executed.")
        return result(router.execute(tool, args))
    if name == "reload-mcp":
        from vectorcode.src.tools.mcp_tool import discover_mcp_tools, shutdown_mcp_servers

        if argument:
            raise ValueError("Usage: /reload-mcp")
        if not _approve(bridge, session, "reload_mcp", {"project": str(bridge.project)}):
            return result("Command denied; no MCP connections were changed.")
        shutdown_mcp_servers()
        names = discover_mcp_tools()
        return result(f"MCP reload finished: {len(names)} registered tools. No terminal restart.")
    raise ValueError("Unsupported terminal shortcut.")


def _approve(bridge, session, name, args):
    if session.mode == "read-only":
        raise ValueError(f"{name} is unavailable in read-only mode.")
    return bridge.approve_tool("slash_command", name, args)


if __name__ == "__main__":
    assert {"fork", "browser", "cron"} <= NAMES
