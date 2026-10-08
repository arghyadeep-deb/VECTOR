# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""RBAC capability system — fine-grained permission model for tool dispatch."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

class Capability(str, Enum):
    """Fine-grained capability labels."""

    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK_FETCH = "network:fetch"
    CODE_EXECUTE = "code:execute"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    CHANNEL_SEND = "channel:send"
    TOOL_INVOKE = "tool:invoke"
    SCHEDULE_CREATE = "schedule:create"
    SYSTEM_ADMIN = "system:admin"

@dataclass(slots=True)
class CapabilityGrant:
    """A single capability grant for an agent."""

    capability: str  # Capability value or glob pattern
    pattern: str = "*"  # resource glob pattern

@dataclass(slots=True)
class AgentPolicy:
    """Policy for a specific agent."""

    agent_id: str
    grants: List[CapabilityGrant] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)  # explicit denials

class CapabilityPolicy:
    """RBAC capability policy for tool dispatch.

    Checks whether an agent has the required capability to invoke a tool.
    Policy can be loaded from a JSON file or configured programmatically.

    Policies deny by default. Callers that deliberately need legacy open
    behavior must opt into it explicitly with ``default_deny=False``.
    """

    def __init__(
        self,
        *,
        policy_path: Optional[str] = None,
        default_deny: bool = True,
    ) -> None:
        self._policies: Dict[str, AgentPolicy] = {}
        self._default_deny = default_deny

        # Previously called get_rust_module().CapabilityPolicy(...)
        # unconditionally -- when the Rust extension isn't built,
        # get_rust_module() returns None (confirmed on this machine), so
        # __init__ itself raised AttributeError and this RBAC policy class
        # -- which gates every tool dispatch -- could never be constructed
        # at all. grant()/deny()/check() had the same unconditional
        # self._rust_impl.* calls. Now guards for a None Rust impl and
        # falls back to the pure-Python state (self._policies) that was
        # already being maintained in parallel regardless of Rust.
        try:
            from vectorcode.src._rust_bridge import get_rust_module

            _rust = get_rust_module()
        except ImportError:
            _rust = None
        self._rust_impl = (
            _rust.CapabilityPolicy(default_deny=default_deny)
            if _rust is not None
            else None
        )

        if policy_path:
            self._load_file(Path(policy_path))

    def grant(self, agent_id: str, capability: str, pattern: str = "*") -> None:
        """Grant a capability to an agent."""
        policy = self._policies.setdefault(
            agent_id,
            AgentPolicy(agent_id=agent_id),
        )
        policy.grants.append(CapabilityGrant(capability=capability, pattern=pattern))
        if self._rust_impl is not None:
            self._rust_impl.grant(agent_id, capability, pattern)

    def deny(self, agent_id: str, capability: str) -> None:
        """Explicitly deny a capability to an agent."""
        policy = self._policies.setdefault(
            agent_id,
            AgentPolicy(agent_id=agent_id),
        )
        policy.deny.append(capability)
        if self._rust_impl is not None:
            self._rust_impl.deny(agent_id, capability)

    def check(self, agent_id: str, capability: str, resource: str = "") -> bool:
        """Check whether *agent_id* has *capability* for *resource*.

        Returns True if allowed, False if denied.
        """
        if self._rust_impl is not None:
            return self._rust_impl.check(agent_id, capability, resource)
        return self._check_python(agent_id, capability, resource)

    def _check_python(self, agent_id: str, capability: str, resource: str = "") -> bool:
        """Pure-Python check -- used when the Rust backend is unavailable."""
        policy = self._policies.get(agent_id)
        if policy is None:
            # No explicit policy — use default
            return not self._default_deny

        # Explicit denials take precedence
        for denied in policy.deny:
            if fnmatch.fnmatch(capability, denied):
                return False

        # Check grants
        for grant in policy.grants:
            if fnmatch.fnmatch(capability, grant.capability):
                if resource and grant.pattern != "*":
                    if fnmatch.fnmatch(resource, grant.pattern):
                        return True
                else:
                    return True

        # No matching grant found
        return not self._default_deny

    def list_grants(self, agent_id: str) -> List[CapabilityGrant]:
        """List all grants for an agent."""
        policy = self._policies.get(agent_id)
        return list(policy.grants) if policy else []

    def list_agents(self) -> List[str]:
        """List all agents with explicit policies."""
        return list(self._policies.keys())

    def _load_file(self, path: Path) -> None:
        """Load a configured policy file, rejecting missing/malformed input."""
        if not path.exists():
            raise FileNotFoundError(f"Capability policy file does not exist: {path}")
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("agents"), list):
                raise ValueError("capability policy must contain an 'agents' list")
            for agent_data in data["agents"]:
                if not isinstance(agent_data, dict):
                    raise ValueError("each capability policy agent must be an object")
                agent_id = agent_data["agent_id"]
                if not isinstance(agent_id, str) or not agent_id:
                    raise ValueError("capability policy agent_id must be non-empty")
                for grant_data in agent_data.get("grants", []):
                    if not isinstance(grant_data, dict):
                        raise ValueError("capability grants must be objects")
                    self.grant(
                        agent_id,
                        grant_data["capability"],
                        grant_data.get("pattern", "*"),
                    )
                for denied in agent_data.get("deny", []):
                    if not isinstance(denied, str):
                        raise ValueError("capability denials must be strings")
                    self.deny(agent_id, denied)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Malformed capability policy file {path}: {exc}") from exc

    def save(self, path: Path) -> None:
        """Save policy to a JSON file."""
        agents = []
        for agent_id, policy in self._policies.items():
            agents.append(
                {
                    "agent_id": agent_id,
                    "grants": [
                        {"capability": g.capability, "pattern": g.pattern}
                        for g in policy.grants
                    ],
                    "deny": policy.deny,
                }
            )
        path.write_text(json.dumps({"agents": agents}, indent=2))

# Default capability requirements for built-in tools
DEFAULT_TOOL_CAPABILITIES: Dict[str, List[str]] = {
    "file_read": [Capability.FILE_READ],
    "web_search": [Capability.NETWORK_FETCH],
    "code_interpreter": [Capability.CODE_EXECUTE],
    "memory_store": [Capability.MEMORY_WRITE],
    "memory_retrieve": [Capability.MEMORY_READ],
    "memory_search": [Capability.MEMORY_READ],
    "memory_index": [Capability.MEMORY_WRITE],
    "schedule_task": [Capability.SCHEDULE_CREATE],
    "channel_send": [Capability.CHANNEL_SEND],
}

__all__ = [
    "AgentPolicy",
    "Capability",
    "CapabilityGrant",
    "CapabilityPolicy",
    "DEFAULT_TOOL_CAPABILITIES",
]
