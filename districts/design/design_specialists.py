"""Evidence-based Design specialists created by the self-development program.

These agents deliberately return bounded, in-memory briefs.  They do not claim
to verify subjective or cultural facts from a language-model response: a brief
is ready only when the caller supplies the persona-specific evidence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine


@dataclass(frozen=True)
class SpecialistProfile:
    """The bounded, independently checkable contract for one design persona."""

    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str


class DesignSpecialist(AgentBase):
    """Base class for read-only, evidence-aware Design personas."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="design",
            generation=generation,
        )
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][design_specialists] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return an auditable report based only on submitted evidence fields."""
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.evidence_fields if supplied.get(field)]
        missing = [field for field in self.profile.evidence_fields if not supplied.get(field)]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
        }

    def synthesize_suggestions(self, query: str, report: dict[str, Any]) -> str:
        """Offer clearly non-evidentiary suggestions through the approved LLM path."""
        hydration = ContextEngine().session_hydration_prompt({"query": query})
        prompt = (
            f"{hydration}\n\nYou are {self.name}, a VECTOR Design specialist. "
            "Suggest next steps only; do not assert that missing evidence has been "
            "verified and do not make cultural, accessibility, safety, or user-study "
            f"claims without supplied evidence.\n\nBrief report: {report}\n\nRequest: {query}"
        )
        return chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
            district="design",
            domain="vision",
        ).strip()

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }

        try:
            report = self.build_evidence_report(task.get("evidence"))
            response: dict[str, Any] = {"status": "ok", "report": report}
            query = str(task.get("query", "")).strip()
            if query:
                suggestion = await asyncio.to_thread(self.synthesize_suggestions, query, report)
                if suggestion:
                    response["suggestion"] = suggestion
                    response["suggestion_is_evidence"] = False
            self.award_points(20, f"{self.profile.primary_action}_brief_created")
            return response
        except Exception as exc:
            logger.error("[VECTOR][design_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "design_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


class BrandGuardian(DesignSpecialist):
    profile = SpecialistProfile("BrandGuardian", "brand_guardian_001", "brand_identity", "brand_consistency", ("brand_purpose", "audience", "existing_assets"), "brand identity brief")


class InclusiveVisualsSpecialist(DesignSpecialist):
    profile = SpecialistProfile("InclusiveVisualsSpecialist", "inclusive_visuals_specialist_001", "inclusive_visual_review", "inclusive_prompt", ("audience", "representation_requirements", "reviewer"), "inclusive visual review")


class UXArchitect(DesignSpecialist):
    profile = SpecialistProfile("UXArchitect", "ux_architect_001", "ux_architecture", "information_architecture", ("user_goals", "content_inventory", "constraints"), "UX architecture brief")


class VisualStoryteller(DesignSpecialist):
    profile = SpecialistProfile("VisualStoryteller", "visual_storyteller_001", "visual_storyboard", "visual_narrative", ("audience", "message", "channels"), "visual narrative storyboard")


class WhimsyInjector(DesignSpecialist):
    profile = SpecialistProfile("WhimsyInjector", "whimsy_injector_001", "whimsy_design", "microinteraction_audit", ("brand_voice", "user_context", "reduced_motion_plan"), "purposeful delight brief")


class LevelDesigner(DesignSpecialist):
    profile = SpecialistProfile("LevelDesigner", "level_designer_001", "level_design", "level_flow", ("player_goal", "progression", "constraints"), "level flow brief")


class NarrativeDesigner(DesignSpecialist):
    profile = SpecialistProfile("NarrativeDesigner", "narrative_designer_001", "narrative_design", "narrative_arc", ("audience", "conflict", "desired_outcome"), "narrative arc brief")


class TechnicalArtist(DesignSpecialist):
    profile = SpecialistProfile("TechnicalArtist", "technical_artist_001", "technical_art", "asset_pipeline", ("target_platform", "asset_budget", "rendering_constraints"), "technical art pipeline brief")


class VisionOSSpatialEngineer(DesignSpecialist):
    profile = SpecialistProfile("VisionOSSpatialEngineer", "visionos_spatial_engineer_001", "spatial_design", "spatial_comfort", ("spatial_goal", "comfort_constraints", "input_method"), "spatial experience brief")


class XRImmersiveDeveloper(DesignSpecialist):
    profile = SpecialistProfile("XRImmersiveDeveloper", "xr_immersive_developer_001", "immersive_design", "immersive_flow", ("user_goal", "device_constraints", "safety_constraints"), "immersive flow brief")


class XRInterfaceArchitect(DesignSpecialist):
    profile = SpecialistProfile("XRInterfaceArchitect", "xr_interface_architect_001", "xr_interface", "xr_interaction", ("interaction_goal", "input_method", "accessibility_requirements"), "XR interface brief")


class CulturalIntelligenceStrategist(DesignSpecialist):
    profile = SpecialistProfile("CulturalIntelligenceStrategist", "cultural_intelligence_strategist_001", "cultural_review", "cultural_brief", ("locale", "audience", "local_reviewer"), "cultural intelligence brief")


SPECIALIST_CLASSES: tuple[type[DesignSpecialist], ...] = (
    BrandGuardian,
    InclusiveVisualsSpecialist,
    UXArchitect,
    VisualStoryteller,
    WhimsyInjector,
    LevelDesigner,
    NarrativeDesigner,
    TechnicalArtist,
    VisionOSSpatialEngineer,
    XRImmersiveDeveloper,
    XRInterfaceArchitect,
    CulturalIntelligenceStrategist,
)


if __name__ == "__main__":
    async def _smoke() -> None:
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            result = await specialist.run({"type": specialist.capabilities[0], "evidence": {}})
            assert result["status"] == "ok"
            assert result["report"]["missing_evidence"]
        logger.info("[VECTOR][design_specialists] smoke check passed")

    asyncio.run(_smoke())
