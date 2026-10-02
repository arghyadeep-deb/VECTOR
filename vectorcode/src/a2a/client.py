# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""A2A client — discover and call external A2A agents."""

from __future__ import annotations

from typing import Any, Optional

from vectorcode.src.a2a.protocol import A2ARequest, A2ATask, AgentCard

class A2AClient:
    """Client for calling external A2A-compatible agents.

    Discovers agent capabilities via /.well-known/agent.json and
    sends tasks via /a2a/tasks.
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0, allow_private: bool = False) -> None:
        # base_url is caller-supplied and every method below makes a real
        # outbound httpx call to it -- an SSRF primitive with zero
        # confinement before this fix (same class of gap fixed in
        # core/browser/ and core/vision_control/browser_controller.py this
        # cycle). allow_private defaults to False (same convention as
        # SSRFGuard's own flag and browser_controller.py's
        # allow_private_navigation) since a legitimate local/LAN-deployed
        # A2A agent is a real, plausible use case for this client,
        # unlike an arbitrary-page navigator.
        from core.security.ssrf_guard import SSRFGuard
        result = SSRFGuard(resolve_dns=True, allow_private=allow_private).check_url(base_url)
        if not result.safe:
            raise ValueError(f"A2AClient base_url blocked by SSRF guard: {result.reason}")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._card: Optional[AgentCard] = None

    def discover(self) -> AgentCard:
        """Fetch the agent card from /.well-known/agent.json."""
        import httpx

        resp = httpx.get(
            f"{self._base_url}/.well-known/agent.json",
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self._card = AgentCard(
            name=data.get("name", ""),
            description=data.get("description", ""),
            url=data.get("url", self._base_url),
            version=data.get("version", ""),
            capabilities=data.get("capabilities", []),
            skills=data.get("skills", []),
        )
        return self._card

    def send_task(self, input_text: str, **kwargs: Any) -> A2ATask:
        """Send a task to the remote agent and return the result."""
        import httpx

        request = A2ARequest(
            method="tasks/send",
            params={
                "message": {
                    "role": "user",
                    "parts": [{"text": input_text}],
                },
            },
        )
        resp = httpx.post(
            f"{self._base_url}/a2a/tasks",
            json=request.to_dict(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return A2ATask(
            task_id=result.get("id", ""),
            state=result.get("state", "unknown"),
            input_text=result.get("input", input_text),
            output_text=result.get("output", ""),
            history=result.get("history", []),
        )

    def get_task(self, task_id: str) -> A2ATask:
        """Get the status of a previously submitted task."""
        import httpx

        request = A2ARequest(
            method="tasks/get",
            params={"id": task_id},
        )
        resp = httpx.post(
            f"{self._base_url}/a2a/tasks",
            json=request.to_dict(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return A2ATask(
            task_id=result.get("id", task_id),
            state=result.get("state", "unknown"),
            output_text=result.get("output", ""),
        )

    def cancel_task(self, task_id: str) -> A2ATask:
        """Cancel a running task."""
        import httpx

        request = A2ARequest(
            method="tasks/cancel",
            params={"id": task_id},
        )
        resp = httpx.post(
            f"{self._base_url}/a2a/tasks",
            json=request.to_dict(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return A2ATask(
            task_id=result.get("id", task_id),
            state=result.get("state", "canceled"),
        )

__all__ = ["A2AClient"]
