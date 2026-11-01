"""Adapt the existing command registries to the active local terminal session."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import re
import tempfile
from pathlib import Path

_MAX_SESSION_TITLE_LENGTH = 120


class TerminalCommands:
    UI = {"new", "clear", "help", "quit", "model", "models", "mode", "connect", "redraw"}
    LEGACY = {
        "status",
        "skills",
        "tools",
        "memory",
        "cost",
        "diff",
        "comms",
        "usage",
        "persona",
        "save",
        "init",
        "notify",
        "search",
        "fetch",
        "undo",
        "commit",
    }
    ALIASES = {
        "q": "quit",
        "reload": "reload-mcp",
        "reload_mcp": "reload-mcp",
        "reset": "new",
        "exit": "quit",
        "provider": "model",
        "personality": "persona",
        "compress": "compact",
        "insights": "usage",
        "resume": "restore",
        "commands": "help",
        "snap": "snapshot",
    }
    CUSTOM = {
        "history", "restore", "compact", "config", "profile", "agents", "toolsets", "plugins",
        "sparc", "spawn", "workers", "retry", "rollback", "snapshot", "title", "stop", "image",
    }
    APPROVAL = {"save", "init", "notify", "search", "fetch", "commit", "snapshot"}

    def __init__(self, bridge):
        self.bridge = bridge
        self.repl = None
        self.entries = {}
        self.prompts = {}
        self._load()

    def _load(self):
        from vectorcode.src.terminal_extras import NAMES
        from vectorcode.src.command_registry import get_command_registry
        from vectorcode.src.repl import VectorREPL, _scan_skills
        from vectorcode.src.vector_cli.commands import COMMAND_REGISTRY

        supported = self.UI | self.LEGACY | self.CUSTOM | NAMES
        for definition in COMMAND_REGISTRY:
            if definition.gateway_only:
                continue
            for name in (definition.name, *definition.aliases):
                canonical = self.ALIASES.get(name, self.ALIASES.get(definition.name, definition.name))
                available = canonical in supported or definition.category == "VECTOR Skills"
                self.entries[name] = {
                    "name": name,
                    "canonical": canonical,
                    "description": definition.description,
                    "category": definition.category,
                    "takesArgument": bool(definition.args_hint),
                    "available": available,
                    "reason": ""
                    if available
                    else "No local terminal handler is implemented for this shared-catalog entry.",
                }
                if definition.category == "VECTOR Skills":
                    self.prompts[name] = Path(__file__).parent.parent / "commands" / (definition.name + ".md")
        for raw, description in VectorREPL.COMMANDS.items():
            name = raw.lstrip("/")
            canonical = self.ALIASES.get(name, name)
            entry = self.entries.setdefault(name, {"name": name, "canonical": canonical})
            entry.update(
                description=description,
                category="Terminal",
                available=canonical in supported,
                takesArgument=name
                in {"model", "mode", "connect", "commit", "spawn", "notify", "search", "fetch", "sparc"},
                reason=""
                if canonical in supported
                else "Background execution is not connected to local per-tool approvals.",
            )
        for definition in get_command_registry().load().values():
            if definition.name not in self.entries:
                self.prompts[definition.name] = definition.path
                self.entries[definition.name] = {
                    "name": definition.name,
                    "canonical": definition.name,
                    "description": definition.description,
                    "category": "Brain commands",
                    "takesArgument": True,
                    "available": True,
                    "reason": "",
                }
        skills = _scan_skills()
        for folder in (Path(__file__).resolve().parents[2] / ".claude" / "skills").glob("*/SKILL.md"):
            skills.setdefault(folder.parent.name, folder)
        for name, path in skills.items():
            if name not in self.entries:
                self.prompts[name] = path
                self.entries[name] = {
                    "name": name,
                    "canonical": name,
                    "description": "Run skill: " + name,
                    "category": "Skills",
                    "takesArgument": True,
                    "available": True,
                    "reason": "",
                }
        for name, canonical in self.ALIASES.items():
            self.entries.setdefault(
                name,
                {
                    "name": name,
                    "canonical": canonical,
                    "description": "Alias for /" + canonical,
                    "category": "Terminal",
                    "available": True,
                    "takesArgument": canonical in {"model", "persona", "restore"},
                    "reason": "",
                },
            )
        for name in self.CUSTOM:
            self.entries.setdefault(
                name,
                {
                    "name": name,
                    "canonical": name,
                    "description": name.replace("-", " ").capitalize(),
                    "category": "Terminal",
                    "available": True,
                    "takesArgument": name in {"restore", "sparc", "snapshot", "title"},
                    "reason": "",
                },
            )
        self.entries["commit"].update(
            description="Commit using an explicit message (asks approval)", takesArgument=True
        )
        self.entries["restore"].update(description="List saved sessions, or /restore <number>", takesArgument=False)
        self.entries["sparc"].update(
            description="/sparc <stage|full> <task> through the approved coding agent", available=True
        )
        self.entries["spawn"].update(
            description="/spawn [--name <id>] <task> — start a visible worker with tool approvals", available=True, reason=""
        )
        self.entries["workers"].update(description="List terminal workers and their results", available=True, reason="")
        self.entries["compact"].update(description="Prune older tool results while preserving conversation turns")
        self.entries["mode"].update(description="/mode cautious|standard|read-only; every tool asks approval")
        self.entries["model"].update(description="Select /model provider/model-id")
        self.entries["models"].update(description="Choose installed local models or configured cloud catalog models")
        for name in ("model", "mode", "help"):
            self.entries[name]["takesArgument"] = False
        self.entries["config"]["description"] = "Show configuration summary (editing is not implemented here)"
        self.entries["profile"]["description"] = "Show current profile (switching is not implemented here)"
        self.entries["tools"]["description"] = "List actual available tools, optionally filter: /tools web"
        self.entries["plugins"]["description"] = "List installed plugins (installation is not implemented here)"
        self.entries["retry"].update(description="Resend the last user message to the active session")
        self.entries["rollback"].update(description="Revert the last approved file write made this session")
        self.entries["snapshot"].update(
            description="/snapshot <name> — save a labelled transcript copy", takesArgument=True
        )
        self.entries["title"].update(
            description="/title <name> — set the current session display title", takesArgument=True
        )
        self.entries["stop"].update(description="Request the same cooperative stop as Escape")
        for name, canonical in self.ALIASES.items():
            self.entries[name]["description"] = "Alias for /" + canonical
            self.entries[name]["takesArgument"] = self.entries[canonical].get("takesArgument", False)
        for name, entry in self.entries.items():
            entry["kind"] = "unavailable" if not entry["available"] else "prompt" if name in self.prompts else "native"
        # The authorized terminal scope differs intentionally from the gateway's shared labels.
        descriptions = {
            'image': 'Attach an approved workspace PNG/JPEG for the next local vision prompt; /image clear detaches',
            'fast': 'Select the configured fast model alias',
            'reasoning': 'Select the configured local reasoning model alias',
            'paste': 'Paste clipboard text into the draft for review',
            'debug': 'Toggle local terminal debug details (no upload)',
            'verbose': 'Toggle tool activity display',
            'branch': 'List local git branches; /branch <name> asks approval to switch',
            'fork': 'Save an independent copy of this conversation',
            'queue': 'Inspect pending foreground messages',
            'browser': 'List browser tools; /browser <tool> {JSON} asks approval',
            'cron': 'List cron tool schema; /cron {JSON} asks approval',
            'reload-mcp': 'Reconnect configured MCP servers (asks approval)',
        }
        for name in NAMES:
            entry = self.entries[name]
            entry.update(available=True, kind='native', reason='', canonical=name,
                         description=descriptions.get(name, entry['description']))
            if name in {'fast', 'reasoning', 'platforms', 'copy', 'paste', 'statusbar', 'verbose',
                        'debug', 'queue', 'fork', 'reload-mcp'}:
                entry['takesArgument'] = False
        for name, canonical in self.ALIASES.items():
            self.entries[name].update(canonical=canonical, available=True, kind='native', reason='',
                                      description='Alias for /' + canonical,
                                      takesArgument=self.entries[canonical].get('takesArgument', False))
        if 'gateway' in self.entries:
            self.entries['gateway'].update(available=False, kind='unavailable',
                                           reason='Use the separate HTTP gateway server mode.')

    def catalog(self):
        priority = ["models", "model", "connect", "new", "mode", "help", "quit"]
        entries = sorted(
            self.entries.values(),
            key=lambda entry: (
                priority.index(entry["name"]) if entry["name"] in priority else len(priority),
                not entry["available"],
                entry["name"] in self.prompts,
                entry["category"],
                entry["name"],
            ),
        )
        return [
            dict(entry, description=("[unavailable] " if not entry["available"] else "") + entry["description"])
            for entry in entries
        ]

    def _view(self, request):
        from vectorcode.src.repl import VectorREPL
        from vectorcode.src.session import VectorCodeSession

        session = VectorCodeSession.get()
        mode = request.get("mode") or session.mode
        model = request.get("model") or session.current_model
        if self.repl is None:
            self.repl = VectorREPL(project_dir=self.bridge.project)
        session.set_mode(mode)
        session.current_model = model
        self.repl._project_dir = self.bridge.project
        self.repl._history = [{"role": "system", "content": self.bridge.system_prompt}] + list(self.bridge.history)
        self.repl._skills.update({name: path for name, path in self.prompts.items() if path.name == "SKILL.md"})
        writes = [call for call in session.tool_calls if call.get("name") in {"write_file", "edit_file", "apply_patch"}]
        if writes:
            self.repl._last_write = writes[-1].get("args", {}).get("path")
        return self.repl

    def execute(self, request):
        from vectorcode.src.session import VectorCodeSession

        raw = str(request.get("input", "")).strip()
        parts = raw.lstrip("/").split(maxsplit=1)
        name = parts[0] if parts else ""
        argument = parts[1] if len(parts) > 1 else ""
        entry = self.entries.get(name)
        if not entry:
            raise ValueError("Unknown slash command. Use /help.")
        if not entry["available"]:
            raise ValueError(entry["reason"])
        canonical = entry["canonical"]
        if argument and canonical in {
            "config", "profile", "history", "agents", "toolsets", "plugins", "compact", "retry", "rollback", "stop",
        }:
            raise ValueError(f"Usage: /{canonical} (display only; arguments are not supported). No changes were made.")
        self.bridge.project = Path(request.get("projectDir") or self.bridge.project).resolve()
        if not self.bridge.project.is_dir():
            raise ValueError("Project directory does not exist.")
        session = VectorCodeSession.get()
        session.set_mode(request.get("mode") or session.mode)
        session.current_model = request.get("model") or session.current_model
        from vectorcode.src.terminal_extras import NAMES, execute

        if canonical in NAMES:
            if session.mode == 'read-only' and canonical in {'browser', 'cron', 'reload-mcp'} and argument:
                raise ValueError(f'/{canonical} is unavailable in read-only mode.')
            return execute(self, canonical, argument)
        if name in self.prompts:
            content = self.prompts[name].read_text(encoding="utf-8")
            content = re.sub(r"^\s*<!--.*?-->\s*", "", content, count=1, flags=re.S)
            content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.S)
            content = content.replace("$ARGUMENTS", argument)
            return self.bridge.execute(dict(request, input=f"Command /{name}\n{content}\n\nUser arguments: {argument}"))
        if canonical == "snapshot" and not argument.strip():
            return self._result("Usage: /snapshot <name>")
        if canonical in self.APPROVAL:
            if session.mode == "read-only" and canonical not in {"save", "snapshot"}:
                raise ValueError(f"/{canonical} is unavailable in read-only mode.")
            if canonical == "commit" and not argument:
                return self._result("Usage: /commit <message>. No automatic unapproved model call is made.")
            if not self.bridge.approve_tool(
                "slash_command", "/" + canonical, {"command": raw, "project": str(self.bridge.project)}
            ):
                return self._result("Command denied; no action was executed.")
        if canonical == "history":
            from vectorcode.src.image_attachments import content_preview
            return self._result(
                "\n\n".join(
                    f"{message['role'].upper()}: {content_preview(message.get('content', ''))}"
                    for message in self.bridge.history
                )
                or "No conversation history."
            )
        if canonical == "image":
            return self._image(argument)
        if canonical == "tools":
            from vectorcode.src.tools.registry import ToolRouter

            router = ToolRouter(project_dir=self.bridge.project, approval_callback=self.bridge.approve_tool)
            names = sorted(schema["function"]["name"] for schema in router.get_schemas())
            found = [tool for tool in names if argument.strip().lower() in tool.lower()]
            return self._result(
                f"Available tools in {session.mode} mode ({len(found)}/{len(names)}):\n"
                + ("\n".join(found) if found else "No matching tools. Try /tools without a filter.")
            )
        if canonical == "retry":
            return self._retry(request)
        if canonical == "rollback":
            return self._rollback(session)
        if canonical == "snapshot":
            return self._snapshot(argument, session)
        if canonical == "title":
            title = self._sanitize_title(argument)
            if not title:
                return self._result("Usage: /title <name>")
            session.display_title = title
            return self._result(f"Session title set: {title}", title=title)
        if canonical == "stop":
            self.bridge.request_stop()
            return self._result("Stopping at the next safe boundary; an active tool may finish.")
        if canonical == "restore":
            return self._restore(argument)
        if canonical == "config":
            from vectorcode.src.config import VectorConfig

            config = VectorConfig(self.bridge.project)
            return self._result(
                f"Project: {self.bridge.project}\nDefault model: {config.default_model}\nMode: {session.mode}"
            )
        if canonical == "profile":
            import os

            return self._result("Profile: " + (os.environ.get("VECTOR_PROFILE") or "default"))
        if canonical == "agents":
            return self._result(
                json.dumps(session.active_agents, default=str, indent=2)
                if session.active_agents
                else "No active background agents in this session."
            )
        if canonical == "toolsets":
            from vectorcode.src.tools.registry import DEFAULT_AGENT_TOOLSETS

            return self._result("\n".join(DEFAULT_AGENT_TOOLSETS))
        if canonical == "plugins":
            from vectorcode.src.vector_cli.plugins import get_plugin_manager

            return self._result(json.dumps(get_plugin_manager().list_plugins(), default=str, indent=2))
        if canonical == "compact":
            return self._compact(request)
        # /fetch and /search fall through to the REPL handlers below: after the approval above they run the
        # web backend directly (no model call, no tool-choice) and record /fetch text in the shared history.
        if canonical == "sparc":
            return self._sparc(request, argument)
        if canonical == "spawn":
            if not argument:
                return self._result("Usage: /spawn <task>. Worker runs in the foreground with tool approvals.")
            from vectorcode.src.terminal_bridge import TerminalBridge

            worker = TerminalBridge(self.bridge.output)
            worker.loop = self.bridge.loop
            worker.controller = self.bridge
            worker.history = list(self.bridge.history)
            try:
                result = worker.execute(dict(request, input=argument))
            finally:
                self.bridge.history = worker.history
            response = "Worker completed (foreground):\n" + result["response"]
            return self._result(response, replyRole="assistant")
        view = self._view(request)
        if canonical not in self.LEGACY:
            raise ValueError("This command is handled by the terminal interface.")
        output = io.StringIO()
        original_model = view.session.current_model
        try:
            if canonical == "cost" and "/" not in original_model:
                view.session.current_model = "ollama/" + original_model
            with contextlib.redirect_stdout(output):
                result = view.handle_command("/" + canonical + (" " + argument if argument else ""))
        finally:
            view.session.current_model = original_model
        self.bridge.history = [message for message in view._history if message.get("role") != "system"]
        self.bridge.system_prompt = view._history[0]["content"]
        if result is None and not output.getvalue():
            raise ValueError(
                "This local handler does not accept those arguments. Use /" + canonical + " without arguments."
            )
        return self._result((result or "") + ("\n" + output.getvalue() if output.getvalue() else ""))

    def _result(self, response, **fields):
        from vectorcode.src.session import VectorCodeSession
        from vectorcode.src.image_attachments import content_preview

        session = VectorCodeSession.get()
        if "history" in fields:
            fields = dict(fields, history=[dict(message, content=content_preview(message.get("content", "")))
                                           for message in fields["history"]])
        return {
            "type": "command_result",
            "response": response,
            "status": {
                "model": session.current_model,
                "mode": session.mode,
                "inputTokens": session.token_usage.prompt_tokens,
                "outputTokens": session.token_usage.completion_tokens,
                "title": session.display_title or '',
                "localImages": session.local_images,
            },
            **fields,
            "imageAttachments": [image.metadata() for image in self.bridge.pending_images.values()],
        }

    def _restore(self, argument):
        from vectorcode.src.repl import _list_sessions
        from vectorcode.src.session import VectorCodeSession

        sessions = _list_sessions()
        if not argument:
            return self._result(
                "\n".join(
                    f"{index}. {item['model']} · {item['turns']} messages"
                    + (f" · snapshot: {item['label']}" if item.get("label") else "")
                    for index, item in enumerate(sessions, 1)
                )
                + "\nUse /restore <number>."
                if sessions
                else "No saved sessions."
            )
        if not argument.isdigit() or not 1 <= int(argument) <= len(sessions):
            raise ValueError("Select a session number from /restore.")
        data = json.loads(Path(sessions[int(argument) - 1]["path"]).read_text(encoding="utf-8"))
        return self._restore_data(data)

    def _restore_data(self, data):
        """Apply one already-selected snapshot; never re-resolve its positional list index."""
        from vectorcode.src.session import VectorCodeSession

        history = data.get("history", [])
        if not isinstance(history, list) or any(
            not isinstance(message, dict) or "role" not in message for message in history
        ):
            raise ValueError("Saved conversation history is invalid.")
        from vectorcode.src.image_attachments import saved_image_privacy
        image_private = saved_image_privacy(data)
        usage = {
            name: max(0, int(data.get(name, 0))) for name in ("prompt_tokens", "completion_tokens", "cache_read_tokens")
        }
        session = VectorCodeSession.get()
        session.set_mode(data.get("mode") or session.mode)
        session.reset()
        session.local_images = image_private
        self.bridge.pending_images.clear()
        import uuid
        # Manual restore branches the loaded transcript. Preserve both existing saves;
        # --resume explicitly selects its saved identity after this shared loader returns.
        session.session_id = str(uuid.uuid4())
        session.current_model = data.get("model") or session.current_model
        session.token_usage.add(
            prompt=usage["prompt_tokens"], completion=usage["completion_tokens"], cache_read=usage["cache_read_tokens"]
        )
        session.tool_calls = [{key: value for key, value in call.items() if key != 'rollback'}
                              for call in (data.get('tool_calls') or []) if isinstance(call, dict)]
        session.display_title = data.get('title') or None
        self.bridge.history = [message for message in history if message.get("role") != "system"]
        self.bridge.system_prompt = next(
            (message.get("content", "") for message in history if message.get("role") == "system"), ""
        )
        return self._result("Session restored.", history=self.bridge.history)

    def _retry(self, request):
        last_user_index = next(
            (index for index in range(len(self.bridge.history) - 1, -1, -1)
             if self.bridge.history[index].get("role") == "user"),
            None,
        )
        last_user = self.bridge.history[last_user_index].get("content", "") if last_user_index is not None else ""
        if not last_user:
            return self._result("No user message is available to retry.")
        # Retry replaces an answer only on success. Keep the old exchange on
        # failure, and also retain any replacement tool results: their approved
        # side effects cannot be undone by dropping the attempted transcript.
        original_history = self.bridge.history
        self.bridge.history = original_history[:last_user_index]

        def retain_failed_attempt():
            attempted = getattr(self.bridge, "last_turn_history", None) or self.bridge.history[last_user_index:]
            self.bridge.history = original_history + attempted if any(
                message.get("role") == "tool" for message in attempted
            ) else original_history

        try:
            result = self.bridge.execute(dict(request, input=last_user))
        except BaseException:
            retain_failed_attempt()
            raise
        if result.get('response', '').startswith('[VECTOR error:'):
            retain_failed_attempt()
        return self._result(result.get("response", ""), replyRole="assistant")


    def _image(self, argument):
        from core.config import CONFIG
        from vectorcode.src.image_attachments import capture_image, image_context_bytes
        pending = self.bridge.pending_images
        argument = argument.strip()
        if argument == "clear":
            pending.clear()
            return self._result("Pending images detached. Conversation privacy is unchanged.")
        if not argument:
            return self._result("\n".join(image.name for image in pending.values())
                                or "No pending images. Use /image <workspace-relative PNG/JPEG path>.")
        if len(pending) >= CONFIG["vectorcode"]["image_attachment_max_count"]:
            raise ValueError("Pending image limit reached. Submit or detach the current images first.")
        if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in {'"', "'"}:
            argument = argument[1:-1]
        image = capture_image(argument, self.bridge.project, self.bridge.approve_tool)
        if (image_context_bytes(self.bridge.history) + sum(len(item.data) for item in pending.values()) + len(image.data)
                > CONFIG["vectorcode"]["image_session_max_bytes"]):
            raise ValueError("Image conversation exceeds the configured retained-data limit.")
        pending[image.id] = image
        return self._result(f"Attached {image.name} ({image.width}x{image.height}, {len(image.data)} bytes). "
                            "Review it, select a local vision model, and enter your question. No inference has run.")

    def _snapshot(self, label, session):
        from vectorcode.src.repl import _save_session

        label = label.strip()
        if not label:
            return self._result("Usage: /snapshot <name>")
        usage = session.token_usage
        path = _save_session(
            [{"role": "system", "content": self.bridge.system_prompt}] + list(self.bridge.history),
            session.current_model,
            mode=session.mode,
            token_usage={
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
                "total": usage.total_tokens,
            },
            tool_calls=session.tool_calls,
            label=label,
            title=session.display_title,
        )
        return self._result(f"Snapshot saved ({label}) → {path}")


    def _rollback(self, session):
        if session.mode == "read-only":
            raise ValueError("/rollback is unavailable in read-only mode.")
        record = next((call for call in reversed(session.tool_calls) if call.get("file_write")), None)
        if record is None:
            return self._result("No approved file write is available to roll back this session.")
        if not record.get("approved") or not record.get("rollback"):
            return self._result("The last approved file write cannot be safely rolled back.")
        if record.get("rolled_back"):
            return self._result("The last approved file write has already been rolled back.")
        rollback = record["rollback"]
        path = Path(rollback["path"]).resolve()
        try:
            path.relative_to(self.bridge.project)
        except ValueError:
            return self._result("The recorded file write is outside the active project and cannot be rolled back.")
        from vectorcode.src.session import file_fingerprint

        current = file_fingerprint(path)
        if current != rollback.get("post_write"):
            return self._result("The file changed after the approved write; rollback was refused.")
        if not self.bridge.approve_tool("slash_command", "/rollback", {"path": str(path)}):
            return self._result("Command denied; no rollback was executed.")
        # Approval can wait for several minutes. Re-check after it resolves so
        # a later edit is never overwritten by this restoration.
        if file_fingerprint(path) != rollback.get("post_write"):
            return self._result("The file changed after the approved write; rollback was refused.")
        try:
            if rollback["existed"]:
                self._atomic_restore(path, base64.b64decode(rollback["content"]))
            elif path.exists():
                path.unlink()
        except (OSError, ValueError) as exc:
            return self._result(f"Rollback failed: {exc}")
        record["rolled_back"] = True
        return self._result(f"Rolled back {path.relative_to(self.bridge.project)}.")


    @staticmethod
    def _atomic_restore(path, content):
        """Restore existing file bytes without leaving a partial target on failure."""
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".rollback")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise


    @staticmethod
    def _sanitize_title(value):
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value).strip()
        return value[:_MAX_SESSION_TITLE_LENGTH]


    def _compact(self, request):
        from vectorcode.src.context.compactor import _prune_old_tool_results

        before = len(self.bridge.history)
        self.bridge.history, pruned = _prune_old_tool_results(self.bridge.history, protect_tail_tokens=1500)
        return self._result(
            f"Compacted {pruned} older tool results; {before} messages preserved. No summary model call.",
            history=self.bridge.history,
        )

    def _sparc(self, request, argument):
        from vectorcode.src.skills.builtin.sparc.coordinator import sparc_slash_command

        parts = argument.split(maxsplit=1)
        if len(parts) < 2:
            return self._result("Usage: /sparc <stage|full> <task>")
        bridge = self.bridge

        class ApprovedAgent:
            async def run_conversation(self, prompt):
                result = bridge.execute(dict(request, input=prompt))
                return {"text": result["response"]}

        return self._result(sparc_slash_command(parts[0], parts[1], ApprovedAgent()), replyRole="assistant")


if __name__ == "__main__":
    assert TerminalCommands.ALIASES["personality"] == "persona"
