"""
Image Prompt Engineer — crafts detailed prompts for AI image generation.

Generates photography-grade prompts for ComfyUI/Stable Diffusion/Midjourney
optimized for VECTOR's content district. Translates visual concepts into
precise language with style, lighting, composition, and technical parameters.
"""

import asyncio
import json
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

_STYLE_PRESETS = {
    "cinematic": "cinematic lighting, 35mm film, anamorphic lens, depth of field, color grade",
    "technical": "clean white background, technical illustration, precise lines, professional",
    "cyberpunk": "neon lights, dark environment, holographic elements, futuristic city, rain",
    "minimal": "minimalist, white space, geometric shapes, flat design, clean composition",
    "photography": "DSLR photo, natural lighting, bokeh, sharp focus, realistic",
    "concept_art": "concept art, digital painting, dramatic lighting, detailed environment",
    "isometric": "isometric view, 3D render, clean colors, low poly, architectural",
}

_QUALITY_SUFFIX = (
    "8k resolution, ultra detailed, sharp focus, professional photography, "
    "masterpiece, best quality, highly detailed"
)

_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, extra limbs, bad anatomy, "
    "watermark, text, signature, low resolution, jpeg artifacts"
)

class ImagePromptEngineer(AgentBase):
    """
    AI image generation prompt specialist.
    Crafts precise prompts for ComfyUI, Stable Diffusion, Midjourney.
    """

    def __init__(self):
        super().__init__(agent_id="image_prompt_engineer_001",
                         name="ImagePromptEngineer", district="design")
        self.capabilities = ["build", "cinematic", "deconstruct", "design", "image", "prompt", "variations"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][image_prompt] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float) -> str:
        """Call the routed model with mandatory session hydration."""
        hydration = ContextEngine().session_hydration_prompt({"query": prompt})
        return chat(
            model=self._model,
            messages=[{"role": "user", "content": f"{hydration}\n\n{prompt}"}],
            timeout=timeout,
            district="design",
            domain="vision",
        )

    def build_prompt(self, subject: str, style: str = "cinematic",
                     mood: str = "professional", extras: str = "") -> dict:
        """Construct a complete image generation prompt with style, mood, quality."""
        style_tokens = _STYLE_PRESETS.get(style, _STYLE_PRESETS["cinematic"])
        prompt = f"{subject}, {style_tokens}, {mood} mood"
        if extras:
            prompt += f", {extras}"
        prompt += f", {_QUALITY_SUFFIX}"
        return {
            "positive_prompt": prompt,
            "negative_prompt": _NEGATIVE_PROMPT,
            "style": style,
            "mood": mood,
            "recommended_steps": 30 if style in ("cinematic", "concept_art") else 20,
            "recommended_cfg": 7.5,
            "recommended_sampler": "DPM++ 2M Karras",
            "recommended_size": "1024x1024" if style != "cinematic" else "1216x832",
        }

    def generate_variation_set(self, base_subject: str, count: int = 4) -> list[dict]:
        """Generate multiple style variations of the same subject."""
        styles = list(_STYLE_PRESETS.keys())[:count]
        return [self.build_prompt(base_subject, style=s) for s in styles]

    def deconstruct_image_description(self, description: str) -> dict:
        """Parse a natural language image description into prompt components."""
        components = {
            "subject": "",
            "environment": "",
            "lighting": "",
            "style": "",
            "mood": "",
            "camera": "",
            "color_palette": "",
        }
        # Simple keyword extraction heuristic
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["dark", "night", "shadow"]):
            components["lighting"] = "dramatic shadows, low-key lighting"
        elif any(w in desc_lower for w in ["bright", "sunny", "daylight"]):
            components["lighting"] = "golden hour, soft natural light"
        else:
            components["lighting"] = "studio lighting, balanced exposure"

        if any(w in desc_lower for w in ["city", "urban", "street"]):
            components["environment"] = "urban environment, city backdrop"
        elif any(w in desc_lower for w in ["nature", "forest", "outdoor"]):
            components["environment"] = "natural environment, organic textures"

        if any(w in desc_lower for w in ["tech", "ai", "robot", "digital", "cyber"]):
            components["style"] = "cyberpunk"
        elif any(w in desc_lower for w in ["clean", "minimal", "simple"]):
            components["style"] = "minimal"
        else:
            components["style"] = "cinematic"

        components["subject"] = description[:80]
        return components

    async def generate_prompt_from_concept(self, concept: str, use_case: str = "social_media") -> dict:
        """LLM-enhanced prompt generation from high-level concept."""
        size_map = {
            "social_media": "1080x1080",
            "banner": "1920x1080",
            "thumbnail": "1280x720",
            "portrait": "832x1216",
            "square": "1024x1024",
        }
        prompt_instruction = (
            f"Create a detailed Stable Diffusion prompt for: '{concept}'\n"
            f"Use case: {use_case}\n\n"
            f"Return JSON:\n"
            f'{{"positive_prompt": "detailed SD prompt", '
            f'"negative_prompt": "what to avoid", '
            f'"style_keywords": ["list"], '
            f'"photography_terms": ["aperture, lighting etc"], '
            f'"composition": "rule description"}}'
        )
        try:
            response = await asyncio.to_thread(self._llm, prompt_instruction, 20.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                result["recommended_size"] = size_map.get(use_case, "1024x1024")
                result["concept"] = concept
                return result
        except Exception as e:
            logger.warning("[VECTOR][image_prompt] LLM failed: {}", e)

        components = self.deconstruct_image_description(concept)
        prompt = self.build_prompt(concept, style=components["style"])
        prompt["concept"] = concept
        prompt["recommended_size"] = size_map.get(use_case, "1024x1024")
        return prompt

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 full-repo mechanical sweep finding): the real
        # governor dispatch shape is {"type": ..., "params": {...}} -- every
        # branch below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Capture task_type from the UNMERGED task first
        # (a nested params dict could carry its own "type" key -- see
        # districts/communications/email_agent.py's identical fix), then
        # flatten params into task once for every branch below.
        task_type = task.get("type", "build")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "build":
                result = self.build_prompt(
                    task.get("subject", "autonomous AI system visualization"),
                    task.get("style", "cyberpunk"),
                    task.get("mood", "futuristic"),
                    task.get("extras", ""),
                )
                self.award_points(15, "prompt_built")
                return {"status": "ok", "prompt": result}

            elif task_type == "variations":
                results = self.generate_variation_set(
                    task.get("subject", "AI neural network"), task.get("count", 4)
                )
                self.award_points(20, "variations_generated")
                return {"status": "ok", "variations": results, "count": len(results)}

            elif task_type == "deconstruct":
                result = self.deconstruct_image_description(task.get("description", ""))
                self.award_points(10, "description_deconstructed")
                return {"status": "ok", "components": result}

            else:  # concept
                result = await self.generate_prompt_from_concept(
                    task.get("concept", "VECTOR AI autonomous agent city"),
                    task.get("use_case", "social_media"),
                )
                self._get_memory().store(
                    event_type="image_prompt_generated",
                    content=f"Image prompt for: {task.get('concept', 'unknown')[:60]}",
                    tags=["design", "image", "comfyui"],
                    source="image_prompt_engineer",
                )
                self.award_points(20, "concept_prompt_generated")
                return {"status": "ok", "prompt": result}

        except Exception as e:
            logger.error("[VECTOR][image_prompt] {}", e)
            self.deduct_points(30, "prompt_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ImagePromptEngineer()
        prompt = agent.build_prompt("VECTOR AI city with glowing agents", "cyberpunk", "mysterious")
        print(f"[OK] build: {len(prompt['positive_prompt'])} char prompt, steps={prompt['recommended_steps']}")
        variations = agent.generate_variation_set("autonomous AI system", count=3)
        print(f"[OK] variations: {len(variations)} styles generated")
        components = agent.deconstruct_image_description("dark futuristic tech lab with AI holograms")
        print(f"[OK] deconstruct: style={components['style']} lighting={components['lighting'][:30]}")
        result = await agent.run({"type": "build", "subject": "neural network visualization", "style": "technical"})
        print(f"[OK] run: status={result['status']}")
        print("image_prompt_engineer.py OK")

    asyncio.run(_smoke())
