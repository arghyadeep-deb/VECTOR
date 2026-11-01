"""Foreground-visible asyncio workers owned by one terminal bridge."""

from __future__ import annotations

import asyncio
import copy
import re
from collections import OrderedDict
from pathlib import Path

from core.config import CONFIG

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


def _bounded_result(value):
    text = str(value)
    limit = CONFIG["vectorcode"]["worker_result_max_chars"]
    if len(text) <= limit:
        return text
    suffix = "\n[Result truncated; see saved transcript if autosave succeeded.]"
    return text[: limit - len(suffix)] + suffix


class TerminalWorkers:
    def __init__(self, bridge):
        self.bridge = bridge
        self.records = OrderedDict()
        self.session_ids = set()
        self.sequence = 0
        self.root_model = None
        self.root_mode = None

    @property
    def active_count(self):
        return sum(record["state"] in {"running", "stopping"} for record in self.records.values())

    def start(self, request):
        from vectorcode.src.session import VectorCodeSession
        from vectorcode.src.terminal_bridge import TerminalBridge

        raw = str(request.get("input", "")).strip()
        argument = raw[len("/spawn") :].strip()
        if re.match(r"^--name(?:\s|$)", argument):
            pieces = argument.split(maxsplit=2)
            if len(pieces) < 3:
                raise ValueError("Usage: /spawn [--name <id>] <task>")
            name, argument = pieces[1], pieces[2]
            if not _NAME.fullmatch(name):
                raise ValueError(
                    "Worker name must start with a letter and contain at most 32 "
                    "letters, digits, underscores or hyphens."
                )
        else:
            self.sequence += 1
            name = f"worker-{self.sequence}"
            while name in self.records:
                self.sequence += 1
                name = f"worker-{self.sequence}"
        if not argument or argument.startswith("--"):
            raise ValueError("Usage: /spawn [--name <id>] <task>")
        if name in self.records:
            raise ValueError(f"Worker name already exists: {name}")
        if len(self.records) >= CONFIG["vectorcode"]["worker_max_retained"]:
            raise ValueError("Worker history limit reached; start a new terminal session.")
        if self.active_count >= CONFIG["vectorcode"]["worker_max_active"]:
            raise ValueError("Worker limit reached; wait for an active worker to finish.")
        project = Path(request.get("projectDir") or self.bridge.project).resolve()
        if not project.is_dir():
            raise ValueError("Project directory does not exist.")
        if self.active_count and project != self.bridge.project:
            raise ValueError("Project cannot change while workers are active.")
        if self.bridge.active:
            raise ValueError("Wait for the active turn before starting a worker.")
        self.bridge.project = project
        self.bridge.cancelled = False
        parent_session = VectorCodeSession.get()
        session = VectorCodeSession(
            mode=request.get("mode") or parent_session.mode,
            current_model=request.get("model") or parent_session.current_model,
            repo_path=str(project),
            local_images=parent_session.local_images,
        )
        session.set_mode(session.mode)
        if not self.active_count:
            self.root_model, self.root_mode = session.current_model, session.mode
        child = TerminalBridge(self.bridge.output)
        child.parent = self.bridge
        child.worker_name = name
        child.loop = self.bridge.loop
        child.project = project
        child.history = copy.deepcopy(self.bridge.history)
        child.system_prompt = self.bridge.system_prompt
        record = {
            "name": name,
            "state": "running",
            "result": "",
            "session": session,
            "bridge": child,
            "model": session.current_model,
            "task": None,
        }
        self.records[name] = record
        self.session_ids.add(session.session_id)
        self.bridge._activity_enter()
        self._emit(record)
        record["task"] = asyncio.create_task(self._run(record, dict(request, input=argument)))
        return name

    def _emit(self, record):
        event = {
            "type": "worker_status",
            "workerName": record["name"],
            "workerState": record["state"],
            "activeWorkers": self.active_count,
            "model": record["model"],
        }
        if "inputTokens" in record:
            event["inputTokens"] = record["inputTokens"]
            event["outputTokens"] = record["outputTokens"]
        if record["result"]:
            event["result"] = record["result"]
        if record.get("message"):
            event["message"] = record["message"]
        self.bridge.emit(event)

    async def _run(self, record, request):
        from vectorcode.src.session import VectorCodeSession

        child, session = record["bridge"], record["session"]
        with VectorCodeSession.scope(session):
            try:
                result = await child.execute_async(request)
                response = result.get("response", "")
                final_state = "failed" if response.startswith("[VECTOR error:") else "completed"
                full_result = response
                record["result"] = _bounded_result(response)
            except asyncio.CancelledError:
                final_state = "cancelled"
                full_result = "Stopped; completed actions have not been undone."
                record["result"] = full_result
            except Exception as exc:
                final_state = "failed"
                full_result = str(exc)
                record["result"] = _bounded_result(exc)
                if not any(m.get("role") == "user" and m.get("content") == request["input"] for m in child.history):
                    child.history.append({"role": "user", "content": request["input"]})
            if final_state in {"failed", "cancelled"}:
                child.history.append({"role": "assistant", "content": f"[Worker {final_state}: {full_result}]"})
            try:
                saved = await child.checkpoint()
                if not saved:
                    record["message"] = "Worker transcript autosave failed; the result is not durably saved."
                    if final_state == "completed":
                        final_state = "failed"
            except Exception as exc:
                record["message"] = f"Worker transcript autosave failed: {type(exc).__name__}"
                if final_state == "completed":
                    final_state = "failed"
            finally:
                record["state"] = final_state
                record["inputTokens"] = session.token_usage.prompt_tokens
                record["outputTokens"] = session.token_usage.completion_tokens
                self.bridge._activity_exit()
                self._emit(record)
                record["bridge"] = None
                record["session"] = None

    def stop(self):
        for record in self.records.values():
            if record["state"] == "running":
                record["bridge"].cancelled = True
                record["state"] = "stopping"
                self._emit(record)

    async def drain(self):
        tasks = [record["task"] for record in self.records.values() if record["task"] and not record["task"].done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def listing(self):
        if not self.records:
            return "No workers in this terminal session."
        return "\n".join(
            f"{item['name']}: {item['state']}" + (f" — {item['result']}" if item["result"] else "")
            for item in self.records.values()
        )


if __name__ == "__main__":
    assert _NAME.fullmatch("worker-1")
