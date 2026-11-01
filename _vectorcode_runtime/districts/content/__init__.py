"""
Module: agents/content/__init__.py
V.E.C.T.O.R. Content District - Video creation and content generation agents
"""

import sys

from loguru import logger

from .script_generator import ScriptGenerator
from .video_generator import VideoGenerator
from .caption_generator import CaptionGenerator
from .uploader import Uploader
from .video_merger import VideoMerger
from .voice_generator import VoiceGenerator
from .comfyui_adapter import ComfyUIAdapter
from .media_studio_agent import MediaStudioAgent
from .analytics_retriever import AnalyticsRetriever, PostMetrics
from .blog_publisher import BlogPublisher, PublishResult
from .post_job import PostJobTracker, JobStatus
from .asset_video_pipeline import AssetVideoPipelineAgent
from .youtube_trends import YouTubeTrendScout

__all__ = [
    "ScriptGenerator",
    "VideoGenerator",
    "CaptionGenerator",
    "Uploader",
    "VideoMerger",
    "VoiceGenerator",
    "ComfyUIAdapter",
    "MediaStudioAgent",
    "AnalyticsRetriever",
    "PostMetrics",
    "BlogPublisher",
    "PublishResult",
    "PostJobTracker",
    "JobStatus",
    "AssetVideoPipelineAgent",
    "YouTubeTrendScout",
]

logger.info("[VECTOR][content] Content district loaded")


def get_agent(name: str):
    """Factory function to get content district agents."""
    agents = {
        "ScriptGenerator": ScriptGenerator,
        "VideoGenerator": VideoGenerator,
        "CaptionGenerator": CaptionGenerator,
        "Uploader": Uploader,
        "VideoMerger": VideoMerger,
        "VoiceGenerator": VoiceGenerator,
        "ComfyUIAdapter": ComfyUIAdapter,
        "MediaStudioAgent": MediaStudioAgent,
        "media_studio": MediaStudioAgent,
        "AnalyticsRetriever": AnalyticsRetriever,
        "BlogPublisher": BlogPublisher,
        "PostJobTracker": PostJobTracker,
        "AssetVideoPipelineAgent": AssetVideoPipelineAgent,
        "asset_video": AssetVideoPipelineAgent,
        "YouTubeTrendScout": YouTubeTrendScout,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    script_gen = ScriptGenerator()
    print(f"ScriptGenerator: {script_gen.name}")

    video_gen = VideoGenerator()
    print(f"VideoGenerator: {video_gen.name}")

    caption_gen = CaptionGenerator()
    print(f"CaptionGenerator: {caption_gen.name}")

    uploader = Uploader()
    print(f"Uploader: {uploader.name}")

    video_merger = VideoMerger()
    print(f"VideoMerger: {video_merger.name}")

    voice_gen = VoiceGenerator()
    print(f"VoiceGenerator: {voice_gen.name}")

    print("✅ content/__init__.py OK")
