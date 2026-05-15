"""WebSocket transport for VectorCode gateway — real-time streaming."""
import sys
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode pkg parent

from loguru import logger


@dataclass
class WSMessage:
    type: str   # "token" | "tool_call" | "tool_result" | "done" | "error"
    content: str
    metadata: Optional[dict] = None


class VectorWSHandler:
    """
    WebSocket handler that bridges a VectorAgent session to a WebSocket connection.

    Protocol (JSON messages):
    Client → Server:
      {"type": "run",       "input": "...", "model": "...", "session_id": "..."}
      {"type": "interrupt"}
      {"type": "approve",   "action_id": "...", "approved": true}

    Server → Client:
      {"type": "token",       "content": "...", "session_id": "..."}
      {"type": "tool_call",   "name": "...", "args": {...}, "call_id": "..."}
      {"type": "tool_result", "content": "...", "call_id": "..."}
      {"type": "done",        "response": "...", "session_id": "..."}
      {"type": "error",       "message": "..."}
    """

    _APPROVAL_TIMEOUT: float = 30.0  # seconds before auto-reject

    def __init__(self, websocket: Any, session_id: str = "") -> None:
        self.ws = websocket
        self.session_id = session_id
        self._interrupted = False
        self._pending_approvals: dict[str, asyncio.Future] = {}

    # ── Main handler loop ─────────────────────────────────────────────────────

    async def handle(self) -> None:
        """
        Main handler loop — receives JSON messages from the client,
        dispatches 'run', 'interrupt', and 'approve' types.

        Runs until the WebSocket is closed or an unrecoverable error occurs.
        """
        logger.info(f"[WS] session={self.session_id} handler started")
        try:
            while True:
                raw = await self.ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError as exc:
                    await self.send_error(f"Invalid JSON: {exc}")
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "run":
                    await self._handle_run(msg)

                elif msg_type == "interrupt":
                    self._interrupted = True
                    logger.info(f"[WS] session={self.session_id} interrupted by client")

                elif msg_type == "approve":
                    action_id = msg.get("action_id", "")
                    approved = bool(msg.get("approved", False))
                    fut = self._pending_approvals.get(action_id)
                    if fut and not fut.done():
                        fut.set_result(approved)
                    else:
                        logger.warning(
                            f"[WS] session={self.session_id} approve for unknown "
                            f"action_id={action_id}"
                        )

                else:
                    await self.send_error(f"Unknown message type: {msg_type!r}")

        except Exception as exc:
            # WebSocket disconnect raises various exceptions depending on the
            # framework; treat all unhandled errors as normal closure.
            logger.info(f"[WS] session={self.session_id} closed: {exc}")

    # ── Run dispatcher ────────────────────────────────────────────────────────

    async def _handle_run(self, msg: dict) -> None:
        """Handle a 'run' message: execute the task and stream the response."""
        user_input = msg.get("input", "")
        model_id = msg.get("model", "ollama/vector-focus")
        self._interrupted = False

        if not user_input:
            await self.send_error("'input' field is required for type='run'")
            return

        logger.info(
            f"[WS] session={self.session_id} run: model={model_id} "
            f"input_len={len(user_input)}"
        )

        try:
            from engine.agent_loop import VectorAgent

            # NOTE: VectorAgent.run_conversation() is currently synchronous.
            # Real token-level streaming would require refactoring the transport
            # layer to yield partial responses from the model provider.
            # For now, the full response is obtained in a thread executor and
            # sent as a single "token" message followed by "done".
            loop = asyncio.get_event_loop()
            agent = VectorAgent(model_id=model_id, project_dir=".")

            if self._interrupted:
                await self.send_error("Run interrupted before execution")
                return

            result = await loop.run_in_executor(
                None, agent.run_conversation, user_input
            )

            response = result.get("response", "") if isinstance(result, dict) else str(result)

            # Deliver tool_call / tool_result events from the result metadata
            tool_calls = result.get("tool_calls", []) if isinstance(result, dict) else []
            for tc in tool_calls:
                if self._interrupted:
                    break
                call_id = tc.get("id", "")
                await self.send_tool_call(
                    name=tc.get("name", ""),
                    args=tc.get("args", {}),
                    call_id=call_id,
                )
                tool_output = tc.get("output", "")
                if tool_output:
                    await self.send_tool_result(content=str(tool_output), call_id=call_id)

            if not self._interrupted:
                await self.send_token(response)
                await self.send_done(response)
            else:
                await self.send_error("Run was interrupted")

        except Exception as exc:
            logger.error(f"[WS] session={self.session_id} run error: {exc}")
            await self.send_error(str(exc))

    # ── Send helpers ──────────────────────────────────────────────────────────

    async def send_token(self, content: str) -> None:
        """Send a token chunk to the client."""
        await self._send({"type": "token", "content": content, "session_id": self.session_id})

    async def send_tool_call(self, name: str, args: dict, call_id: str) -> None:
        """Notify client of a tool call."""
        await self._send(
            {
                "type": "tool_call",
                "name": name,
                "args": args,
                "call_id": call_id,
                "session_id": self.session_id,
            }
        )

    async def send_tool_result(self, content: str, call_id: str) -> None:
        """Notify client of a tool result."""
        await self._send(
            {
                "type": "tool_result",
                "content": content,
                "call_id": call_id,
                "session_id": self.session_id,
            }
        )

    async def send_done(self, response: str) -> None:
        """Send completion signal to client."""
        await self._send(
            {"type": "done", "response": response, "session_id": self.session_id}
        )

    async def send_error(self, message: str) -> None:
        """Send an error message to the client."""
        await self._send({"type": "error", "message": message, "session_id": self.session_id})

    async def request_approval(self, action_id: str, action_desc: str) -> bool:
        """
        Send an approval request to the client and await their response.
        Times out after _APPROVAL_TIMEOUT seconds (returns False on timeout).
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_approvals[action_id] = fut

        await self._send(
            {
                "type": "approval_request",
                "action_id": action_id,
                "description": action_desc,
                "session_id": self.session_id,
            }
        )

        try:
            return await asyncio.wait_for(fut, timeout=self._APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                f"[WS] session={self.session_id} approval timeout for action_id={action_id}"
            )
            return False
        finally:
            self._pending_approvals.pop(action_id, None)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _send(self, payload: dict) -> None:
        """Serialize payload to JSON and send over the WebSocket."""
        try:
            await self.ws.send_text(json.dumps(payload))
        except Exception as exc:
            logger.warning(f"[WS] send failed session={self.session_id}: {exc}")


# ── FastAPI route registration ────────────────────────────────────────────────

def create_ws_route(app: Any, path: str = "/ws") -> None:
    """
    Add a WebSocket route to a FastAPI app.

    Usage:
        from gateway.ws import create_ws_route
        create_ws_route(app, path="/ws")

    Client connects: ws://host:port/ws?session_id=<id>
    """
    try:
        from fastapi import WebSocket
    except ImportError:
        logger.error("[WS] FastAPI not installed — cannot register WebSocket route")
        return

    @app.websocket(path)
    async def ws_endpoint(websocket: WebSocket, session_id: str = ""):
        handler = VectorWSHandler(websocket, session_id)
        await websocket.accept()
        logger.info(f"[WS] client connected session_id={session_id!r}")
        await handler.handle()

    logger.info(f"[WS] WebSocket route registered at {path}")


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # WSMessage dataclass
    m = WSMessage(type="token", content="hello")
    assert m.type == "token"
    assert m.content == "hello"
    assert m.metadata is None

    m2 = WSMessage(type="done", content="finished", metadata={"latency": 0.3})
    assert m2.metadata["latency"] == 0.3

    # VectorWSHandler instantiation with mock websocket=None
    handler = VectorWSHandler(websocket=None, session_id="test-session")
    assert handler.session_id == "test-session"
    assert handler._interrupted is False
    assert handler._pending_approvals == {}

    # create_ws_route import (FastAPI optional)
    try:
        from fastapi import FastAPI
        test_app = FastAPI()
        create_ws_route(test_app, "/ws")
        logger.info("[WS] FastAPI available — route registered")
    except ImportError:
        logger.warning("[WS] FastAPI not installed — create_ws_route skipped")

    logger.info("✅ gateway/ws.py OK")
