"""Skill type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MatchedSkill:
    """A skill returned by SkillManager.match() with a confidence score."""

    name: str
    description: str = ""
    confidence: float = 0.0
    skill_id: str = ""
    category: str = ""
    triggers: List[str] = field(default_factory=list)

@dataclass(slots=True)
class SkillStep:
    """A single step in a skill pipeline."""

    tool_name: str = ""
    skill_name: str = ""  # invoke another skill instead of a tool
    arguments_template: str = "{}"  # Jinja2-style template
    output_key: str = ""  # Key to store result in context

@dataclass(slots=True)
class SkillManifest:
    """Manifest describing a reusable skill."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    steps: List[SkillStep] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    signature: str = ""  # Base64-encoded Ed25519 signature
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    depends: List[str] = field(default_factory=list)
    user_invocable: bool = True
    disable_model_invocation: bool = False
    markdown_content: str = ""  # loaded from SKILL.md

    def manifest_bytes(self) -> bytes:
        """Serialize the manifest (excluding signature) for signing/verification.

        FLAGGED, not fixed: manifest_bytes() has zero callers anywhere in the
        repo (confirmed via grep) -- like security.py's capability gate, the
        signature field and this method are fully data-plumbed but entirely
        unwired at runtime. Separately: this serialization excludes
        markdown_content (the actual SKILL.md body executed/followed by the
        agent). If signing is ever wired up, excluding markdown_content would
        make the signature meaningless -- an attacker could swap out a
        validly-signed skill's real instructions while the signature still
        verifies. Whoever wires this up needs to include markdown_content (or
        a hash of it) in the signed bytes; not fixed here since there is no
        live verification path yet to regression-test against.
        """
        import json

        data = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "skill_name": s.skill_name,
                    "arguments_template": s.arguments_template,
                    "output_key": s.output_key,
                }
                for s in self.steps
            ],
            "required_capabilities": self.required_capabilities,
            "tags": self.tags,
            "depends": self.depends,
        }
        return json.dumps(data, sort_keys=True).encode()

__all__ = ["SkillManifest", "SkillStep"]

# SkillType enum added for VECTOR compatibility
from enum import Enum

class SkillType(str, Enum):
    FUNCTION = 'function'
    COMMAND = 'command'
    WORKFLOW = 'workflow'
    AGENT = 'agent'
    BUILT_IN = 'built_in'
    EXTERNAL = 'external'
