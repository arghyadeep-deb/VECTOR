"""Channels router — /channels/status."""

import sys

__all__ = [
    "channels_status",
    "router",
]


from fastapi import APIRouter
from loguru import logger

from core.api.schemas import ChannelsStatusResponse

router = APIRouter(prefix="/channels", tags=["channels"])

@router.get("/status", response_model=ChannelsStatusResponse)
async def channels_status():
    try:
        active = []
        recent_count = 0
        # FLAG FOR OWNER: neither candidate data source for "active channels"
        # has ever actually provided it. The removed first attempt imported
        # a nonexistent vectorcode.src.channels.channel_directory.ChannelDirectory
        # (real file is vectorcode/src/gateway/channel_directory.py, module-level
        # functions only, no such class) -- confirmed via import, it raised
        # every single call, silently swallowed by the handler below.
        # ChannelRuntime (this path) has no active_channels() method either
        # (confirmed: only submit_sync()/stop() exist) -- the hasattr() guard
        # makes this degrade quietly instead of raising, but it has also never
        # returned real data. This endpoint has always reported
        # active_channels=[] / status="inactive" regardless of real channel
        # state. A real fix needs an owner call on the actual intended data
        # source (vectorcode/src/gateway/channel_directory.py's real
        # load_directory() is the most plausible candidate, un-verified here).
        try:
            from core.engine.channels.runtime import ChannelRuntime
            runtime = ChannelRuntime()
            active = [ch.name for ch in runtime.active_channels()] if hasattr(runtime, 'active_channels') else []
        except Exception as e:
            logger.warning("[VECTOR][api][channels] ChannelRuntime lookup failed: {}", e)
        try:
            from core.memory.episodic import EpisodicMemory
            recent = EpisodicMemory().recall("channel message", limit=1, event_type="channel_message")
            recent_count = len(recent)
        except Exception:
            recent_count = 0
        return ChannelsStatusResponse(
            active_channels=active,
            recent_messages=recent_count,
            status="active" if active else "inactive",
        )
    except Exception as e:
        logger.warning(f"[VECTOR][api][channels] status failed: {e}")
        return ChannelsStatusResponse(
            active_channels=[], recent_messages=0, status=str(e),
        )

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ channels.py OK")
