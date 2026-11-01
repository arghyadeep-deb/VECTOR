"""
VECTOR Additional Channel Adapters — extends vectorcode's 30+ channels.

New adapters added from VECTOR absorption:
  MastodonAdapter  — federated microblogging (Mastodon.social, etc.)
  BlueskyAdapter   — AT Protocol decentralized social
  TwitchAdapter    — live streaming chat via IRC/WebSocket
  LinkedInAdapter  — professional networking posts and DMs
  YouTubeAdapter   — YouTube Data API v3 (search, comments, stats)

All adapters follow VECTOR's channel interface pattern from vectorcode.
"""
from vectorcode.src.channels.adapters.mastodon_adapter import MastodonAdapter
from vectorcode.src.channels.adapters.bluesky_adapter import BlueskyAdapter
from vectorcode.src.channels.adapters.twitch_adapter import TwitchAdapter
from vectorcode.src.channels.adapters.linkedin_adapter import LinkedInAdapter
from vectorcode.src.channels.adapters.youtube_adapter import YouTubeAdapter

__all__ = [
    "MastodonAdapter", "BlueskyAdapter", "TwitchAdapter",
    "LinkedInAdapter", "YouTubeAdapter",
]

ADAPTER_REGISTRY = {
    "mastodon":  MastodonAdapter,
    "bluesky":   BlueskyAdapter,
    "twitch":    TwitchAdapter,
    "linkedin":  LinkedInAdapter,
    "youtube":   YouTubeAdapter,
}
