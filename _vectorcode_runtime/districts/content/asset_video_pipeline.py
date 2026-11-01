"""Asset-aware storyboard planner for VECTOR content videos."""
from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase

__all__ = ["AssetDescriptor", "AssetScene", "AssetStoryboard", "AssetVideoPipelineAgent"]


@dataclass
class AssetDescriptor:
    path: str
    kind: str
    name: str
    size_bytes: int
    prompt_hint: str


@dataclass
class AssetScene:
    index: int
    title: str
    narration: str
    duration_sec: float
    asset_path: str
    render_vars: dict[str, Any]


@dataclass
class AssetStoryboard:
    title: str
    intent: str
    orientation: str
    duration_sec: float
    assets: list[AssetDescriptor]
    scenes: list[AssetScene]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "intent": self.intent,
            "orientation": self.orientation,
            "duration_sec": self.duration_sec,
            "assets": [asdict(a) for a in self.assets],
            "scenes": [asdict(s) for s in self.scenes],
        }


class AssetVideoPipelineAgent(AgentBase):
    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "AssetVideoPipelineAgent", "content")
        self.capabilities = ["asset", "content", "pipeline", "video"]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][asset_video] initialized")

    def analyze_assets(self, assets: list[str | Path]) -> list[AssetDescriptor]:
        descriptors: list[AssetDescriptor] = []
        for asset in assets:
            path = Path(asset).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"asset not found: {path}")
            mime, _ = mimetypes.guess_type(str(path))
            kind = "video" if (mime or "").startswith("video/") else "image" if (mime or "").startswith("image/") else "file"
            descriptors.append(AssetDescriptor(
                path=str(path),
                kind=kind,
                name=path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
                size_bytes=path.stat().st_size,
                prompt_hint=f"{kind} asset named {path.stem}",
            ))
        return descriptors

    def build_storyboard(
        self,
        assets: list[str | Path],
        intent: str,
        duration: float = 30.0,
        title: str = "VECTOR Asset Story",
        orientation: str = "9:16",
        bgm_path: str = "",
    ) -> AssetStoryboard:
        descriptors = self.analyze_assets(assets)
        if not descriptors:
            raise ValueError("at least one asset is required")
        per_scene = max(3.0, float(duration) / len(descriptors))
        scenes = [
            AssetScene(
                index=i + 1,
                title=f"{title} - moment {i + 1}",
                narration=f"Show {asset.name} as evidence for {intent}.",
                duration_sec=round(per_scene, 2),
                asset_path=asset.path,
                render_vars={
                    "asset_kind": asset.kind,
                    "asset_name": asset.name,
                    "orientation": orientation,
                    "bgm_path": bgm_path,
                },
            )
            for i, asset in enumerate(descriptors)
        ]
        return AssetStoryboard(
            title=title,
            intent=intent,
            orientation=orientation,
            duration_sec=round(per_scene * len(scenes), 2),
            assets=descriptors,
            scenes=scenes,
        )

    async def run(self, task: dict | None = None) -> dict:
        params = (task or {}).get("params", task or {})
        try:
            storyboard = self.build_storyboard(
                assets=list(params.get("assets", [])),
                intent=str(params.get("intent", "tell a concise story")),
                duration=float(params.get("duration", 30.0)),
                title=str(params.get("title", "VECTOR Asset Story")),
                orientation=str(params.get("orientation", "9:16")),
                bgm_path=str(params.get("bgm_path", "")),
            )
            return {"status": "ok", "storyboard": storyboard.to_dict(), "render_engine": "core.video.vector_composer"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
