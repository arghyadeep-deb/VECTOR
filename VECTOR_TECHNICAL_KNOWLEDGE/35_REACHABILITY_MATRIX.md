# Reachability Matrix

**Purpose:** How to reach VECTOR from outside
**Level:** System Level (Level 1)

---

## Overview

This matrix documents all ways to interact with VECTOR from external systems.

**Key Properties:**
- **Local HTTP** — FastAPI server
- **Remote HTTP** — Cloudflare Worker
- **MCP protocol** — Model Context Protocol
- **Communication platforms** — 30+ messaging apps
- **Pushover** — Owner notifications
- **HUD** — Web interface

---

## Local Access

### FastAPI Server

**Endpoint:** `http://localhost:8000`
**Auth:** API key required
**Status:** ✅ IMPLEMENTED

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | VECTOR status |
| `/health` | GET | Health check |
| `/heartbeat` | GET | Heartbeat |
| `/api/command` | POST | Execute command |
| `/api/memory/recent` | GET | Recent memories |
| `/api/memory/search` | GET | Search memory |
| `/api/agents` | GET | List agents |
| `/api/agents/{id}` | GET | Agent details |
| `/api/goals` | GET | Active goals |
| `/hud/` | GET | HUD interface |

**Example:**
```bash
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "What is my next goal?", "key": "your_api_key"}'
```

---

## Remote Access

### Cloudflare Worker API

**Endpoint:** `https://vector-api.workers.dev`
**Auth:** API key (query param)
**Status:** ✅ DEPLOYED

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | VECTOR status |
| `/health` | GET | Health check |
| `/heartbeat` | GET | Heartbeat |
| `/command` | POST | Queue command |
| `/memory/recent` | GET | Recent memories |
| `/agents` | GET | List agents |
| `/goals` | GET | Active goals |

**Example:**
```bash
curl "https://vector-api.workers.dev/command?key=your_api_key" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"command": "Check my schedule"}'
```

---

## MCP Protocol

### Model Context Protocol

**Endpoint:** Local MCP server
**Auth:** None (local only)
**Status:** ✅ IMPLEMENTED

**Tools:**
- `file_read` — Read file
- `file_write` — Write file
- `shell_exec` — Execute shell command
- `memory_store` — Store memory
- `memory_query` — Query memory
- `collection_list` — List collections
- `collection_query` — Query collection
- `collection_record_create` — Create record
- `browser_prune_dom` — Prune DOM
- `browser_list_auth_profiles` — List auth profiles
- ... (100+ tools)

**Usage:**
```python
from mcp.client import Client

client = Client("vector")
result = await client.call_tool("memory_query", {"query": "goals", "limit": 10})
```

---

## Communication Platforms

### 30+ Platforms

**Direction:** Inbound + Outbound
**Status:** ✅ IMPLEMENTED

| Platform | Inbound | Outbound | Auth |
|----------|---------|----------|------|
| Telegram | ✅ | ✅ | Bot token |
| WhatsApp | ✅ | ✅ | Cloud API |
| WhatsApp Business | ✅ | ✅ | Cloud API |
| Discord | ✅ | ✅ | Bot token |
| Slack | ✅ | ✅ | OAuth |
| Gmail | ✅ | ✅ | OAuth |
| Signal | ✅ | ✅ | Phone number |
| Instagram | ❌ | ✅ | instagrapi |
| YouTube | ❌ | ✅ | OAuth |
| Twitter/X | ❌ | ✅ | OAuth 1.0a |
| LinkedIn | ❌ | ✅ | OAuth |
| Reddit | ❌ | ✅ | OAuth |
| GitHub | ✅ | ✅ | OAuth |
| Matrix | ✅ | ✅ | Access token |
| IRC | ✅ | ✅ | Nick |
| SMS | ✅ | ✅ | Twilio |
| Pushover | ❌ | ✅ | User + token |
| Email (SMTP) | ❌ | ✅ | SMTP creds |
| Webhook | ✅ | ✅ | HMAC |
| RSS | ✅ | ❌ | Feed URL |
| Mastodon | ✅ | ✅ | Access token |
| Bluesky | ✅ | ✅ | DID + key |
| Nostr | ✅ | ✅ | Private key |
| XMPP | ✅ | ✅ | JID + password |
| Mattermost | ✅ | ✅ | Token |
| Rocket.Chat | ✅ | ✅ | Token |
| Zulip | ✅ | ✅ | API key |
| Microsoft Teams | ✅ | ✅ | OAuth |
| Google Chat | ✅ | ✅ | OAuth |

**Example (Telegram):**
```python
from vectorcode.src.channels.gateway import ChannelGateway

gateway = ChannelGateway()
await gateway.send("telegram", "Hello from VECTOR!", "user_id")
```

---

## Push Notifications

### Pushover

**Direction:** Outbound only
**Purpose:** Owner notifications
**Status:** ✅ IMPLEMENTED

**Usage:**
```python
from core.notifications.pushover import send_notification

await send_notification(
    title="VECTOR Alert",
    message="High-stakes decision requires approval",
    priority=1  # 0=normal, 1=high
)
```

---

## Web Interface

### HUD

**Endpoint:** `http://localhost:8000/hud/`
**Auth:** None (local only)
**Status:** ✅ IMPLEMENTED

**Features:**
- Command box — send commands
- Agent grid — live agent status
- Goal panel — active goals
- Memory list — recent memories
- Status indicator — loop health

---

## Phone Access

### ADB

**Direction:** VECTOR → Phone
**Purpose:** Phone control
**Status:** ✅ IMPLEMENTED

**Usage:**
```python
from core.control.phone_controller import PhoneController

phone = PhoneController()
screenshot = await phone.screenshot()
await phone.tap(500, 1000)
await phone.type_text("Hello")
```

---

## Reachability Summary

| Method | Direction | Auth | Latency |
|--------|-----------|------|---------|
| Local HTTP | Bidirectional | API key | 10-100ms |
| Remote HTTP | Bidirectional | API key | 50-200ms |
| MCP | Bidirectional | None (local) | 10-500ms |
| Telegram | Bidirectional | Bot token | 100ms-2s |
| WhatsApp | Bidirectional | Cloud API | 100ms-2s |
| Discord | Bidirectional | Bot token | 100ms-2s |
| Pushover | Outbound | User+token | 100ms-1s |
| HUD | Inbound | None (local) | 100-500ms |
| ADB | VECTOR→Phone | None (USB) | 50-2000ms |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `23_BACKEND_API.md` — API endpoints
- `17_COMMUNICATIONS.md` — Communications
- `22_FRONTEND.md` — HUD interface

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
