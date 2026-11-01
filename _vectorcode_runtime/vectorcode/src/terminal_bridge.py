"""Private local stdio adapter for the terminal UI and canonical coding engine."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import uuid
from pathlib import Path

from loguru import logger


class TerminalBridge:
    def __init__(self, output=None):
        self.output = output or sys.stdout
        self.history = []
        self.pending_images = {}
        self.active = None
        self.approvals = {}
        self.cancelled = False
        self.project = Path.cwd()
        self.loop = None
        self.system_prompt = ""
        self.command_adapter = None
        self.worker_name = None
        self.parent = None
        self._approval_lock = asyncio.Lock()
        self._activity_count = 0
        from vectorcode.src.terminal_workers import TerminalWorkers
        self.workers = TerminalWorkers(self)

    def commands(self):
        if self.command_adapter is None:
            from vectorcode.src.terminal_commands import TerminalCommands

            self.command_adapter = TerminalCommands(self)
        return self.command_adapter

    def emit(self, event):
        if self.worker_name:
            event = dict(event, workerName=self.worker_name)
        self.output.write(json.dumps(event, ensure_ascii=True) + "\n")
        self.output.flush()

    def worker_emit(self, event):
        if self.worker_name:
            event = dict(event, workerName=self.worker_name)
        if self.loop is None or self.loop.is_closed():
            self.emit(event)
        else:
            self.loop.call_soon_threadsafe(self.emit, event)

    async def approval(self, name, args, worker=None):
        owner = worker or self
        if owner.cancelled or self.cancelled:
            return False
        async with self._approval_lock:
            if owner.cancelled or self.cancelled:
                return False
            approval_id = uuid.uuid4().hex
            future = self.loop.create_future()
            self.approvals[approval_id] = future
            event = {"type": "approval", "id": approval_id, "name": name, "args": args}
            if owner.worker_name:
                event["workerName"] = owner.worker_name
            self.emit(event)
            try:
                return await asyncio.wait_for(future, 600)
            except (TimeoutError, asyncio.CancelledError):
                return False
            finally:
                self.approvals.pop(approval_id, None)

    def approve_tool(self, event, name, args):
        root = self.parent or self
        if self.cancelled or root.cancelled:
            return False
        return asyncio.run_coroutine_threadsafe(root.approval(name, args, self), root.loop).result()

    def _activity_enter(self):
        from core.sensing.stuck_detector import write_session_marker
        if self._activity_count == 0:
            write_session_marker(str(self.project))
        self._activity_count += 1

    def _activity_exit(self):
        from core.sensing.stuck_detector import clear_session_marker
        self._activity_count -= 1
        if self._activity_count == 0:
            clear_session_marker()

    def request_stop(self):
        """Request the same cooperative stop used by Escape/cancel."""
        self.cancelled = True

        def deny_pending():
            self.workers.stop()
            for future in list(self.approvals.values()):
                if not future.done():
                    future.set_result(False)

        if self.loop is not None:
            self.loop.call_soon_threadsafe(deny_pending)
        else:
            deny_pending()

    def _prepare_agent(self, request):
        self.last_turn_history = []
        from vectorcode.src.engine.agent_loop import VectorAgent
        from vectorcode.src.session import VectorCodeSession

        session = VectorCodeSession.get()
        control = getattr(self, "controller", None) or self
        session.set_mode(request.get("mode") or "standard")
        session.current_model = request.get("model") or session.current_model
        self.project = Path(request.get("projectDir") or self.project).resolve()
        if not self.project.is_dir():
            raise ValueError("Project directory does not exist.")

        def started(name, preview):
            self.worker_emit({"type": "tool_call", "name": name, "args": {"preview": preview}})

        def finished(name, preview, duration):
            self.worker_emit({"type": "tool_result", "name": name, "result": preview, "durationMs": duration})

        def delta(text):
            if not control.cancelled:
                self.worker_emit({'type': 'token', 'content': text})

        agent = VectorAgent(
            model_id=session.current_model,
            project_dir=self.project,
            session_id=session.session_id,
            quiet_mode=True,
            save_trajectories=False,
            approval_callback=control.approve_tool,
            tool_start_callback=started,
            tool_complete_callback=finished,
            stop_requested_callback=lambda: control.cancelled,
            stream_delta_callback=delta,
            notice_callback=lambda message: self.worker_emit({"type": "notice", "message": message}),
        )
        return session, control, agent

    def _finish_turn(self, session, control, result, previous_history):
        self.history = result.get("messages", self.history)
        self.last_turn_history = result.get("turn_messages", [])
        if control.cancelled or result.get("cancelled"):
            if self.last_turn_history:
                self.history = previous_history + self.last_turn_history
            raise asyncio.CancelledError()
        usage = session.token_usage
        return {
            "type": "done",
            "response": result["response"],
            "iterations": result.get("iterations", 0),
            "status": {
                "model": session.current_model,
                "mode": session.mode,
                "inputTokens": usage.prompt_tokens,
                "outputTokens": usage.completion_tokens,
                "title": session.display_title or '',
                "localImages": session.local_images,
            },
        }

    def _turn_input(self, request):
        question = request["input"]
        if "editorContext" in request:
            from vectorcode.src.editor_context import editor_turn
            question = editor_turn(question, request["editorContext"], self.project)
        images = request.get("_imageSnapshots", ())
        if not images:
            return question
        from vectorcode.src.image_attachments import ImageAttachment, image_content
        from vectorcode.src.session import VectorCodeSession
        if any(not isinstance(image, ImageAttachment) or self.pending_images.get(image.id) is not image
               or Path(image.project) != self.project for image in images):
            raise ValueError("Image attachment is no longer pending in this project.")
        content = image_content(question, images)
        VectorCodeSession.get().local_images = True
        for image in images:
            self.pending_images.pop(image.id)
        self.worker_emit({"type": "image_attachments", "imageAttachments": [
            image.metadata() for image in self.pending_images.values()], "status": {"localImages": True}})
        return content

    def execute(self, request):
        session, control, agent = self._prepare_agent(request)
        previous_history = self.history
        result = agent.run_conversation(
            self._turn_input(request), conversation_history=self.history,
            system_message=self.system_prompt
            or (f"You are VectorCode, working in {self.project}. Read files with tools; never invent results."),
        )
        return self._finish_turn(session, control, result, previous_history)

    async def execute_async(self, request):
        session, control, agent = self._prepare_agent(request)
        previous_history = self.history
        result = await agent.run_conversation_async(
            self._turn_input(request), conversation_history=self.history,
            system_message=self.system_prompt
            or (f"You are VectorCode, working in {self.project}. Read files with tools; never invent results."),
        )
        return self._finish_turn(session, control, result, previous_history)

    async def run_turn(self, request):
        self.emit({"type": "start"})
        self._activity_enter()
        try:
            event = await asyncio.to_thread(self.execute, request)
            await self.checkpoint()
            if event.get("response", "").startswith("[VECTOR error:"):
                self.emit({"type": "error", "message": event["response"]})
            else:
                self.emit(event)
        except asyncio.CancelledError:
            await self.checkpoint()
            self.emit({"type": "cancelled"})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self._activity_exit()
            self.active = None

    async def run_command(self, request):
        self.emit({"type": "start"})
        self._activity_enter()
        try:
            result = await asyncio.to_thread(lambda: self.commands().execute(request))
            if self.history:
                await self.checkpoint()
            if result.get("type") == "done":
                result["replyRole"] = "assistant"
            result["type"] = "command_result"
            self.emit(result)
        except asyncio.CancelledError:
            if self.history:
                await self.checkpoint()
            self.emit({"type": "cancelled"})
        except Exception as exc:
            self.emit({"type": "error", "message": str(exc)})
        finally:
            self._activity_exit()
            self.active = None

    async def checkpoint(self):
        from vectorcode.src.terminal_sessions import checkpoint

        try:
            return bool(await asyncio.to_thread(checkpoint, self))
        except Exception:
            logger.exception("[VECTOR][terminal] conversation checkpoint failed")
            self.emit({"type": "notice", "message": "Autosave failed. Use /save before closing this conversation."})
            return False

    async def handle(self, request):
        command = request.get("command")
        if self.pending_images and command in {"run", "slash", "editor_context", "resume"}:
            if Path(request.get("projectDir") or self.project).resolve() != self.project:
                self.emit({"type": "error", "message": "Clear pending image attachments before changing the project."})
                return
        if self.workers.active_count:
            requested_project = Path(request.get("projectDir") or self.project).resolve()
            if requested_project != self.project:
                if command == "slash":
                    self.emit({"type": "command_result", "response": "Project cannot change while workers are active."})
                else:
                    self.emit({"type": "error" if command == "run" else "notice",
                               "message": "Project cannot change while workers are active."})
                return
            if command in {"reset", "resume", "connect"}:
                self.emit({"type": "notice", "message": "Stop or finish workers before changing the session."})
                return
        if command == "editor_context" and not self.active:
            from vectorcode.src.editor_context import load_editor_envelope

            try:
                project = Path(request.get("projectDir") or self.project).resolve()
                context, question = load_editor_envelope(request.get("file"), project)
                self.project = project
                self.emit({"type": "editor_context", "editorContext": context, "question": question})
            except (ValueError, OSError):
                self.emit({"type": "error", "message": "Editor context could not be attached. Check the envelope, limits and workspace."})
        elif command == "resume" and not self.active:
            from vectorcode.src.terminal_sessions import resume

            self.project = Path(request.get("projectDir") or self.project).resolve()
            try:
                self.emit(await asyncio.to_thread(resume, self, request.get("session") or "latest"))
            except (ValueError, OSError, TypeError):
                self.emit({"type": "notice", "message": "No valid saved session for this project. Use /restore to list sessions."})
        elif command == "commands":
            catalog = await asyncio.to_thread(lambda: self.commands().catalog())
            self.emit({"type": "commands", "commands": catalog})
        elif command == "slash":
            raw = str(request.get("input", "")).strip()
            if raw == "/stop":
                self.request_stop()
                self.emit(
                    {"type": "cancelling", "message": "Stopping at the next safe boundary; an active tool may finish."}
                )
                return
            if raw == "/workers":
                if self.active:
                    self.emit({"type": "notice", "message": self.workers.listing()})
                else:
                    self.emit({"type": "command_result", "response": self.workers.listing()})
                return
            if raw.split(maxsplit=1)[0:1] == ["/spawn"]:
                if self.active:
                    self.emit({"type": "notice", "message": "Wait for the active turn before starting a worker."})
                    return
                try:
                    name = self.workers.start(request)
                    self.emit({"type": "command_result", "response": f"Worker {name} started."})
                except ValueError as exc:
                    self.emit({"type": "command_result", "response": str(exc)})
                return
            if self.workers.active_count:
                self.emit({"type": "command_result", "response": "Stop or finish workers before changing the session."})
                return
            if self.active:
                self.emit({"type": "notice", "message": "Wait for the active turn before running another command."})
                return
            self.cancelled = False
            self.project = Path(request.get("projectDir") or self.project).resolve()
            self.active = asyncio.create_task(self.run_command(request))
        elif command == "approve":
            future = self.approvals.get(request.get("id"))
            if future and not future.done():
                future.set_result(request.get("allow") is True)
        elif command == "cancel":
            self.request_stop()
            self.emit(
                {"type": "cancelling", "message": "Stopping at the next safe boundary; an active tool may finish."}
            )
        elif command == "run":
            if self.active:
                self.emit({"type": "notice", "message": "A turn is already running."})
                return
            if self.workers.active_count:
                if ((request.get("model") and request["model"] != self.workers.root_model) or
                        (request.get("mode") and request["mode"] != self.workers.root_mode)):
                    self.emit({"type": "error", "message": "Stop or finish workers before changing the session model or mode."})
                    return
            if not str(request.get("input", "")).strip():
                return
            project = Path(request.get("projectDir") or self.project).resolve()
            try:
                from core.config import CONFIG
                from vectorcode.src.image_attachments import image_context_bytes
                from vectorcode.src.providers.router import split_model_id
                from vectorcode.src.session import VectorCodeSession
                ids = request.get("imageIds", [])
                if (not isinstance(ids, list) or len(ids) > CONFIG["vectorcode"]["image_attachment_max_count"]
                        or any(not isinstance(item, str) or item not in self.pending_images for item in ids)
                        or len(set(ids)) != len(ids) or "_imageSnapshots" in request):
                    raise ValueError("Select valid pending image attachments for this turn.")
                images = tuple(self.pending_images[item] for item in ids)
                if any(Path(image.project) != project for image in images):
                    raise ValueError("Image attachment belongs to another project.")
                session = VectorCodeSession.get()
                if (images or session.local_images) and split_model_id(request.get("model") or session.current_model)[0] != "ollama":
                    raise ValueError("Image conversations require a local Ollama model. Choose a vision model before submitting.")
                if image_context_bytes(self.history) + sum(len(image.data) for image in images) > CONFIG["vectorcode"]["image_session_max_bytes"]:
                    raise ValueError("Image conversation exceeds the configured retained-data limit.")
                request = dict(request, _imageSnapshots=images)
            except (ValueError, TypeError):
                self.emit({"type": "error", "message": "Image request is invalid or requires a local Ollama model. Pending attachments were retained."})
                return
            if "editorContext" in request:
                from vectorcode.src.editor_context import validate_editor_context

                try:
                    request = dict(request, editorContext=validate_editor_context(request["editorContext"], project))
                except ValueError as exc:
                    self.emit({"type": "error", "message": str(exc)})
                    return
            self.cancelled = False
            self.project = project
            self.active = asyncio.create_task(self.run_turn(request))
        elif command == "reset" and not self.active:
            from vectorcode.src.session import VectorCodeSession

            session = VectorCodeSession.get()
            session.reset()
            if request.get("model"):
                session.current_model = str(request["model"])
            if request.get("mode"):
                session.set_mode(request["mode"])
            session.session_id = str(uuid.uuid4())
            self.history = []
            self.pending_images.clear()
            await self.checkpoint()
            self.emit(
                {
                    "type": "notice",
                    "message": "New conversation started.",
                    "imageAttachments": [],
                    "status": {
                        "model": session.current_model,
                        "mode": session.mode,
                        "inputTokens": 0,
                        "outputTokens": 0,
                        "localImages": False,
                    },
                }
            )
        elif command == "connect" and not self.active:
            try:
                from vectorcode.src.cli.auth import AuthManager
                from vectorcode.src.providers.coding_catalog import get_coding_provider as get_provider

                provider = str(request.get("provider", "")).strip().lower()
                definition = get_provider(provider)
                key = str(request.get("key", "")).strip()
                if (
                    not definition
                    or definition.driver not in {"openai_compat", "anthropic", "gemini"}
                    or not key
                    or any(character.isspace() for character in key)
                ):
                    raise ValueError("Unsupported provider or empty key.")
                AuthManager().add(provider, provider, key, require_keyring=True)
                self.emit({"type": "notice", "message": f"{provider} key saved to the system keyring."})
            except Exception:
                self.emit(
                    {"type": "notice", "message": "Key setup failed. Check provider and system keyring availability."}
                )
        elif command == "models":
            from core.inference.llm_providers import PROVIDERS
            from vectorcode.src.cli.auth import AuthManager

            models = []
            try:
                import ollama

                def installed_models():
                    with ollama.Client(timeout=3) as client:
                        return client.list()

                response = await asyncio.to_thread(installed_models)
                models.extend("ollama/" + model.model for model in response.models)
            except Exception:
                pass
            try:
                entries = AuthManager().list_credentials()
            except Exception:
                entries = []
                self.emit({"type": "notice", "message": "Stored credentials could not be listed."})
            for entry in entries:
                if entry.provider == "freellmapi":
                    models.extend(await self.freellmapi_choices(entry.name))
                    continue
                provider = PROVIDERS.get(entry.provider)
                if provider:
                    models.extend(entry.provider + "/" + model for model in provider.models)
            self.emit({"type": "models", "models": list(dict.fromkeys(models))})

    async def freellmapi_choices(self, credential_name):
        """Router choices plus live discovery; discovery failure keeps the choices, marked unverified."""
        from vectorcode.src.cli.auth import AuthManager
        from vectorcode.src.providers.coding_catalog import freellmapi_models

        try:
            key = await asyncio.to_thread(AuthManager().get, credential_name)
            found = await asyncio.to_thread(freellmapi_models, key)
        except Exception:
            found = await asyncio.to_thread(freellmapi_models, None)
            self.emit(
                {
                    "type": "notice",
                    "message": "FreeLLMAPI discovery unavailable; showing router choices (readiness not verified).",
                }
            )
        return ["freellmapi/" + model for model in found]

    async def serve(self):
        self.loop = asyncio.get_running_loop()
        self.emit({"type": "ready"})
        try:
            while line := await asyncio.to_thread(sys.stdin.readline):
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object.")
                    await self.handle(request)
                except (ValueError, TypeError):
                    self.emit({"type": "notice", "message": "Invalid UI request."})
        finally:
            self.request_stop()
            if self.active:
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(self.active)
            await self.workers.drain()
            from tools.terminal_tool import clear_task_env_overrides, cleanup_vm
            for session_id in self.workers.session_ids:
                await asyncio.to_thread(cleanup_vm, session_id)
                clear_task_env_overrides(session_id)


def main():
    output = sys.stdout
    sys.stdout = sys.stderr
    logger.remove()
    bridge = TerminalBridge(output)
    bridge.log_sink = logger.add(sys.stderr, level="WARNING")
    asyncio.run(bridge.serve())


if __name__ == "__main__":
    main()
