# External Integrations

**Purpose:** Third-party APIs, OAuth, webhooks
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR integrates with 80+ external services via OAuth, webhooks, and direct API calls.

**Key Properties:**
- **80+ OAuth providers** — YAML registry
- **Webhook signing** — HMAC-SHA256
- **Bulk messaging** — rate-limited sending
- **WhatsApp Business** — templates, media, reactions
- **Google APIs** — Gmail, Calendar, YouTube
- **Social platforms** — Instagram, Twitter, LinkedIn

**Files:**
- `core/engine/oauth/` (providers, flows, server)
- `core/engine/webhook/` (HMAC signing)
- `vectorcode/src/channels/` (platform adapters)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## OAuth System

### Provider Registry

**File:** `core/engine/oauth/providers.yaml`
**Status:** ✅ IMPLEMENTED

```yaml
providers:
  # Dev Tools
  github:
    auth_mode: oauth2
    authorize_url: https://github.com/login/oauth/authorize
    token_url: https://github.com/login/oauth/access_token
    scopes: ["repo", "user"]
  
  gitlab:
    auth_mode: oauth2
    authorize_url: https://gitlab.com/oauth/authorize
    token_url: https://gitlab.com/oauth/token
    scopes: ["read_user", "api"]
  
  # Productivity
  google:
    auth_mode: oauth2
    authorize_url: https://accounts.google.com/o/oauth2/v2/auth
    token_url: https://oauth2.googleapis.com/token
    scopes: ["openid", "email", "profile"]
  
  microsoft:
    auth_mode: oauth2
    authorize_url: https://login.microsoftonline.com/common/oauth2/v2.0/authorize
    token_url: https://login.microsoftonline.com/common/oauth2/v2.0/token
    scopes: ["openid", "email", "profile"]
  
  # Communication
  slack:
    auth_mode: oauth2
    authorize_url: https://slack.com/oauth/v2/authorize
    token_url: https://slack.com/api/oauth.v2.access
    scopes: ["channels:read", "chat:write"]
  
  discord:
    auth_mode: oauth2
    authorize_url: https://discord.com/api/oauth2/authorize
    token_url: https://discord.com/api/oauth2/token
    scopes: ["identify", "email"]
  
  # Social
  twitter:
    auth_mode: oauth1
    request_token_url: https://api.twitter.com/oauth/request_token
    authorize_url: https://api.twitter.com/oauth/authorize
    access_token_url: https://api.twitter.com/oauth/access_token
  
  # ... (80+ providers total)
```

### OAuth Flow Manager

**File:** `core/engine/oauth/flows.py`
**Status:** ✅ IMPLEMENTED

```python
class OAuthFlowManager:
    """Manage OAuth flows."""
    
    async def get_authorization_url(self, provider: str) -> str:
        """Get authorization URL."""
        config = self._get_provider_config(provider)
        
        if config.auth_mode == "oauth2":
            return self._oauth2_authorize_url(config)
        elif config.auth_mode == "oauth1":
            return await self._oauth1_authorize_url(config)
    
    async def complete_authorization(self, provider: str, code: str) -> dict:
        """Complete OAuth flow."""
        config = self._get_provider_config(provider)
        
        if config.auth_mode == "oauth2":
            token = await self._oauth2_exchange(config, code)
        elif config.auth_mode == "oauth1":
            token = await self._oauth1_access_token(config, code)
        
        # Store token
        await self._store_token(provider, token)
        
        return {"success": True, "token": token}
    
    async def get_token(self, provider: str) -> dict:
        """Get stored token, refresh if expired."""
        token = await self._load_token(provider)
        
        if not token:
            return None
        
        # Check expiry
        if self._is_expired(token, buffer_minutes=5):
            # Auto-refresh
            token = await self._refresh_token(provider, token)
            await self._store_token(provider, token)
        
        return token
    
    def _is_expired(self, token: dict, buffer_minutes: int = 5) -> bool:
        """Check if token is expired."""
        if "expires_at" not in token:
            return False
        
        expires_at = datetime.fromisoformat(token["expires_at"])
        now = datetime.utcnow()
        
        return now >= expires_at - timedelta(minutes=buffer_minutes)
    
    async def _refresh_token(self, provider: str, token: dict) -> dict:
        """Refresh expired token."""
        config = self._get_provider_config(provider)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token["refresh_token"],
                    "client_id": config.client_id,
                    "client_secret": config.client_secret
                }
            )
            
            data = response.json()
            
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", token["refresh_token"]),
                "expires_at": self._expires_at_from_seconds(data.get("expires_in"))
            }
```

---

## Webhook Signing

### HMAC-SHA256

**File:** `core/engine/webhook/hmac_signer.py`
**Status:** ✅ IMPLEMENTED

```python
import hmac
import hashlib

class WebhookSigner:
    """Sign webhooks with HMAC-SHA256."""
    
    def sign(self, body: bytes, secret: str) -> str:
        """Sign webhook body."""
        signature = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def verify(self, body: bytes, signature: str, secret: str) -> bool:
        """Verify webhook signature."""
        expected = self.sign(body, secret)
        
        # Constant-time comparison
        return hmac.compare_digest(expected, signature)
    
    def signed_headers(self, body: bytes, secret: str) -> dict:
        """Get signed headers."""
        import uuid
        from datetime import datetime
        
        return {
            "X-Signature-256": self.sign(body, secret),
            "X-Delivery-Id": str(uuid.uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat()
        }
```

---

## Bulk Messaging

### Rate-Limited Sending

**File:** `vectorcode/src/channels/bulk_sender.py`
**Status:** ✅ IMPLEMENTED

```python
class BulkSender:
    """Send bulk messages with rate limiting."""
    
    RATE_LIMITS = {
        "whatsapp": 80,  # msg/s
        "telegram": 30,
        "slack": 1,
        "discord": 5
    }
    
    async def send_bulk(self, channel: str, messages: list, dry_run: bool = False) -> dict:
        """Send bulk messages."""
        rate_limit = self.RATE_LIMITS.get(channel, 2)
        
        sent = 0
        failed = 0
        skipped = 0
        
        for message in messages:
            if dry_run:
                skipped += 1
                continue
            
            try:
                await self._send_with_rate_limit(channel, message, rate_limit)
                sent += 1
            except Exception as e:
                logger.error(f"[VECTOR][bulk] Send failed: {e}")
                failed += 1
        
        elapsed = time.time() - start_time
        success_rate = sent / (sent + failed) if (sent + failed) > 0 else 0
        
        return {
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "success_rate": success_rate,
            "elapsed_seconds": elapsed
        }
    
    async def _send_with_rate_limit(self, channel: str, message: dict, rate_limit: int):
        """Send with rate limiting."""
        # Wait for rate limit
        await asyncio.sleep(1.0 / rate_limit)
        
        # Send
        from vectorcode.src.channels.gateway import ChannelGateway
        gateway = ChannelGateway()
        await gateway.send(channel, message["content"], message["recipient"])
```

---

## WhatsApp Business Extensions

### Templates, Media, Reactions

**File:** `vectorcode/src/channels/whatsapp_business.py`
**Status:** ✅ IMPLEMENTED

```python
class WhatsAppBusinessChannel(WhatsAppChannel):
    """WhatsApp Business Cloud API extensions."""
    
    async def send_template(self, recipient: str, template_name: str, params: list):
        """Send HSM template."""
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params]
                    }
                ]
            }
        }
        
        await self._api_call("messages", payload)
    
    async def send_image(self, recipient: str, image_url: str, caption: str = ""):
        """Send image."""
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption
            }
        }
        
        await self._api_call("messages", payload)
    
    async def send_reaction(self, recipient: str, message_id: str, emoji: str):
        """Send reaction."""
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "reaction",
            "reaction": {
                "message_id": message_id,
                "emoji": emoji
            }
        }
        
        await self._api_call("messages", payload)
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| OAuth authorize | 1-5s | User interaction |
| Token exchange | 500ms-2s | API latency |
| Token refresh | 200ms-1s | API latency |
| Webhook sign | <1ms | HMAC computation |
| Bulk send (100 msgs) | 5-30s | Rate limits |
| WhatsApp template | 200ms-1s | API latency |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `17_COMMUNICATIONS.md` — Communications
- `16_TOOL_SYSTEM.md` — Tool system

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
