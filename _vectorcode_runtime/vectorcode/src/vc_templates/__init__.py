# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Agent template system — pre-configured agent manifests."""

from vectorcode.src.vc_templates.agent_templates import (
    AgentTemplate,
    discover_templates,
    load_template,
)

__all__ = ["AgentTemplate", "discover_templates", "load_template"]
