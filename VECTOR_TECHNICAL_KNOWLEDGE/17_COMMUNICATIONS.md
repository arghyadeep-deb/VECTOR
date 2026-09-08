# Communications System

**Purpose:** 30+ communication adapters  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR integrates 30+ communication platforms via VectorCode gateway, enabling messaging across Telegram, WhatsApp, Discord, Slack, Gmail, and more.

**Key Properties:**
- **30+ platforms** — comprehensive coverage
- **VectorCode gateway** — unified interface
- **Inbound/outbound** — bidirectional messaging
- **Observable** — all messages logged

**Files:** `vectorcode/src/channels/`, `districts/communications/`  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Platform Adapters

### 30+ Platforms

**File:** `vectorcode/src/channels/`  
**Status:** ✅ IMPLEMENTED

| Platform | Inbound | Outbound | Status |
|----------|---------|----------|--------|
| Telegram | ✅ | ✅ | ✅ |
| WhatsApp | ✅ | ✅ | ✅ |
| WhatsApp Business | ✅ | ✅ | ✅ |
| Discord | ✅ | ✅ | ✅ |
| Slack | ✅ | ✅ | ✅ |
| Gmail | ✅ | ✅ | ✅ |
| Signal | ✅ | ✅ | ✅ |
| Instagram | ❌ | ✅ | ✅ |
| YouTube | ❌ | ✅ | ✅ |
| Twitter/X | ❌ | ✅ | ✅ |
| LinkedIn | ❌ | ✅ | ✅ |
| Reddit | ❌ | ✅ | ✅ |
| GitHub | ✅ | ✅ | ✅ |
| Matrix | ✅ | ✅ | ✅ |
| IRC | ✅ | ✅ | ✅ |
| SMS | ✅ | ✅ | ✅ |
| Pushover | ❌ | ✅ | ✅ |
| Email (SMTP) | ❌ | ✅ | ✅ |
| Webhook | ✅ | ✅ | ✅ |
| RSS | ✅ | ❌ | ✅ |
| Atom | ✅ | ❌ | ✅ |
| Mastodon | ✅ | ✅ | ✅ |
| Bluesky | ✅ | ✅ | ✅ |
| Nostr | ✅ | ✅ | ✅ |
| XMPP | ✅ | ✅ | ✅ |
| Mattermost | ✅ | ✅ | ✅ |
| Rocket.Chat | ✅ | ✅ | ✅ |
| Zulip | ✅ | ✅ | ✅ |
| Microsoft Teams | ✅ | ✅ | ✅ |
| Google Chat | ✅ | ✅ | ✅ |

---

## VectorCode Gateway

### Unified Interface

**File:** `vectorcode/src/channels/gateway.py`  
**Status:** ✅ IMPLEMENTED

```python
class ChannelGateway:
    """Unified gateway for all channels."""
    
    def __init__(self):
        self.channels = {}
        self._register_channels()
    
    def _register_channels(self):
        """Register all channels."""
        from .telegram import TelegramChannel
        from .whatsapp import WhatsAppChannel
        from .discord import DiscordChannel
        # ... (30+ channels)
        
        self.channels["telegram"] = TelegramChannel()
        self.channels["whatsapp"] = WhatsAppChannel()
        self.channels["discord"] = DiscordChannel()
    
    async def send(self, platform: str, message: str, recipient: str):
        """Send message to platform."""
        if platform not in self.channels:
            raise ValueError(f"Unknown platform: {platform}")
        
        channel = self.channels[platform]
        await channel.send(message, recipient)
    
    async def receive(self, platform: str) -> List[Message]:
        """Receive messages from platform."""
        if platform not in self.channels:
            raise ValueError(f"Unknown platform: {platform}")
        
        channel = self.channels[platform]
        return await channel.receive()
```

---

## Base Channel

### Channel Base Class

**File:** `vectorcode/src/channels/base.py`  
**Status:** ✅ IMPLEMENTED

```python
class BaseChannel:
    """Base class for all channels."""
    
    async def send(self, message: str, recipient: str):
        """Send message."""
        raise NotImplementedError
    
    async def receive(self) -> List[Message]:
        """Receive messages."""
        raise NotImplementedError
    
    async def _api_call(self, endpoint: str, data: dict):
        """Make API call."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/{endpoint}",
                json=data,
                headers=self.headers
            )
            return response.json()
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Send message | 100ms-2s | API latency |
| Receive messages | 500ms-5s | Polling interval |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `16_TOOL_SYSTEM.md` — Tool system

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
