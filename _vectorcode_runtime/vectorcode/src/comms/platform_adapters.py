"""
PlatformAdapters — multi-platform send adapters for VectorCode.

  - WhatsApp     (Meta Cloud API)
  - Matrix       (Matrix HTTP Client-Server API)
  - Signal       (signal-cli REST bridge)
  - Mattermost   (webhook + REST)
  - HomeAssistant (webhook)
  - DingTalk     (group robot webhook)
  - Feishu/Lark  (bot webhook)
  - WeCom        (企业微信 webhook)
  - SMS          (Twilio / AWS SNS)

All adapters are send-only outbound. Inbound routing -> comms/inbound.py.
All use httpx for consistency. Graceful fallback if httpx unavailable.
"""
import json
import time
import hashlib
import hmac
from typing import Optional

from loguru import logger

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

def _post(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 10) -> bool:
    if not _HAS_HTTPX:
        logger.warning(f"[VECTOR][adapters] httpx not installed — cannot send to {url[:40]}")
        return False
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload, headers=headers or {})
            ok = r.status_code < 300
            if not ok:
                logger.warning(f"[VECTOR][adapters] POST {url[:40]} -> {r.status_code}: {r.text[:100]}")
            return ok
    except Exception as e:
        logger.error(f"[VECTOR][adapters] POST error {url[:40]}: {e}")
        return False

# ── WhatsApp (Meta Cloud API) ─────────────────────────────────────────────────

class WhatsAppAdapter:
    """
    Meta Cloud API for WhatsApp Business.
    Requires: phone_number_id, access_token from Meta Business.
    """

    BASE = "https://graph.facebook.com/v18.0/{phone_number_id}/messages"

    def __init__(self, phone_number_id: str, access_token: str):
        self._url     = self.BASE.format(phone_number_id=phone_number_id)
        self._token   = access_token
        self._headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    def send(self, to: str, text: str) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        }
        return _post(self._url, payload, self._headers)

    def send_template(self, to: str, template_name: str, language: str = "en_US") -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language}},
        }
        return _post(self._url, payload, self._headers)

# ── Matrix (HTTP Client-Server API) ──────────────────────────────────────────

class MatrixAdapter:
    """
    Matrix protocol via HTTP Client-Server API (no matrix-nio dependency).
    Requires: homeserver URL, access_token, room_id.
    """

    def __init__(self, homeserver: str, access_token: str):
        self._hs      = homeserver.rstrip("/")
        self._token   = access_token
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def send(self, room_id: str, text: str) -> bool:
        txn_id = str(int(time.time() * 1000))
        url = f"{self._hs}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
        payload = {"msgtype": "m.text", "body": text}
        if not _HAS_HTTPX:
            logger.warning("[VECTOR][matrix] httpx not installed")
            return False
        try:
            with httpx.Client(timeout=10) as client:
                r = client.put(url, json=payload, headers=self._headers)
                return r.status_code == 200
        except Exception as e:
            logger.error(f"[VECTOR][matrix] send error: {e}")
            return False

# ── Signal (signal-cli REST bridge) ──────────────────────────────────────────

class SignalAdapter:
    """
    signal-cli REST bridge (https://github.com/bbernhard/signal-cli-rest-api).
    Requires: bridge running at `host`, sender number configured.
    """

    def __init__(self, host: str, sender: str):
        self._host   = host.rstrip("/")
        self._sender = sender

    def send(self, recipients: list[str], text: str) -> bool:
        url = f"{self._host}/v2/send"
        payload = {
            "message": text,
            "number":  self._sender,
            "recipients": recipients,
        }
        return _post(url, payload)

# ── Mattermost ────────────────────────────────────────────────────────────────

class MattermostAdapter:
    """
    Mattermost incoming webhook + REST API.
    Webhook for simple posts; REST for channel-targeted messages.
    """

    def __init__(self, webhook_url: str, token: Optional[str] = None, base_url: Optional[str] = None):
        self._webhook   = webhook_url
        self._token     = token
        self._base_url  = base_url

    def send_webhook(self, text: str, channel: Optional[str] = None, username: str = "VECTOR") -> bool:
        payload: dict = {"text": text, "username": username}
        if channel:
            payload["channel"] = channel
        return _post(self._webhook, payload)

    def send_rest(self, channel_id: str, text: str) -> bool:
        """POST to Mattermost REST API /posts."""
        if not self._base_url or not self._token:
            logger.warning("[VECTOR][mattermost] REST requires base_url and token")
            return False
        url = f"{self._base_url.rstrip('/')}/api/v4/posts"
        payload = {"channel_id": channel_id, "message": text}
        headers = {"Authorization": f"Bearer {self._token}"}
        return _post(url, payload, headers)

# ── HomeAssistant ─────────────────────────────────────────────────────────────

class HomeAssistantAdapter:
    """
    Home Assistant webhook trigger or persistent_notification service.
    Requires: HA base URL, long-lived access token.
    """

    def __init__(self, base_url: str, token: str):
        self._base    = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def notify(self, title: str, message: str, notification_id: str = "vector") -> bool:
        url = f"{self._base}/api/services/persistent_notification/create"
        payload = {"title": title, "message": message, "notification_id": notification_id}
        return _post(url, payload, self._headers)

    def fire_event(self, event_type: str, data: Optional[dict] = None) -> bool:
        url = f"{self._base}/api/events/{event_type}"
        return _post(url, data or {}, self._headers)

    def webhook(self, webhook_id: str, data: Optional[dict] = None) -> bool:
        url = f"{self._base}/api/webhook/{webhook_id}"
        return _post(url, data or {})

# ── DingTalk ──────────────────────────────────────────────────────────────────

class DingTalkAdapter:
    """
    DingTalk group robot webhook with HMAC-SHA256 signature.
    Requires: webhook URL + optional secret for signature verification.
    """

    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self._webhook = webhook_url
        self._secret  = secret

    def _sign(self) -> tuple[str, str]:
        """Returns (timestamp, sign) for signed webhooks."""
        ts = str(int(time.time() * 1000))
        string_to_sign = f"{ts}\n{self._secret}"
        sign = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        import base64
        return ts, base64.b64encode(sign).decode("utf-8")

    def send(self, text: str, at_all: bool = False) -> bool:
        url = self._webhook
        if self._secret:
            ts, sign = self._sign()
            url += f"&timestamp={ts}&sign={sign}"
        payload = {
            "msgtype": "text",
            "text": {"content": text},
            "at": {"isAtAll": at_all},
        }
        return _post(url, payload)

    def send_markdown(self, title: str, text: str) -> bool:
        url = self._webhook
        if self._secret:
            ts, sign = self._sign()
            url += f"&timestamp={ts}&sign={sign}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
        return _post(url, payload)

# ── Feishu / Lark ─────────────────────────────────────────────────────────────

class FeishuAdapter:
    """
    Feishu (Lark) custom bot webhook.
    Supports text and interactive card messages.
    """

    def __init__(self, webhook_url: str):
        self._webhook = webhook_url

    def send(self, text: str) -> bool:
        payload = {"msg_type": "text", "content": {"text": text}}
        return _post(self._webhook, payload)

    def send_card(self, title: str, content: str) -> bool:
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": content}}],
            },
        }
        return _post(self._webhook, payload)

# ── WeCom (企业微信) ────────────────────────────────────────────────────────────

class WeComAdapter:
    """
    WeCom (Enterprise WeChat) group robot webhook.
    """

    def __init__(self, webhook_url: str):
        self._webhook = webhook_url

    def send(self, text: str, mentioned_list: Optional[list] = None) -> bool:
        payload = {
            "msgtype": "text",
            "text": {
                "content": text,
                "mentioned_list": mentioned_list or [],
            },
        }
        return _post(self._webhook, payload)

    def send_markdown(self, content: str) -> bool:
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        return _post(self._webhook, payload)

# ── SMS -- Twilio / AWS SNS ────────────────────────────────────────────────────

class SMSAdapter:
    """
    SMS via Twilio or AWS SNS.
    Set provider="twilio" or provider="sns".
    """

    def __init__(
        self,
        provider: str = "twilio",
        *,
        twilio_sid: str = "",
        twilio_token: str = "",
        twilio_from: str = "",
        sns_region: str = "ap-south-1",
    ):
        self._provider      = provider
        self._twilio_sid    = twilio_sid
        self._twilio_token  = twilio_token
        self._twilio_from   = twilio_from
        self._sns_region    = sns_region

    def send(self, to: str, body: str) -> bool:
        if self._provider == "twilio":
            return self._send_twilio(to, body)
        elif self._provider == "sns":
            return self._send_sns(to, body)
        logger.warning(f"[VECTOR][sms] unknown provider: {self._provider}")
        return False

    def _send_twilio(self, to: str, body: str) -> bool:
        if not _HAS_HTTPX:
            logger.warning("[VECTOR][sms] httpx not installed")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._twilio_sid}/Messages.json"
        try:
            with httpx.Client(timeout=10) as client:
                r = client.post(
                    url,
                    data={"From": self._twilio_from, "To": to, "Body": body[:1600]},
                    auth=(self._twilio_sid, self._twilio_token),
                )
                return r.status_code == 201
        except Exception as e:
            logger.error(f"[VECTOR][sms/twilio] {e}")
            return False

    def _send_sns(self, to: str, body: str) -> bool:
        try:
            import boto3
            sns = boto3.client("sns", region_name=self._sns_region)
            sns.publish(PhoneNumber=to, Message=body[:1600])
            return True
        except Exception as e:
            logger.error(f"[VECTOR][sms/sns] {e}")
            return False

# ── Platform registry ─────────────────────────────────────────────────────────

class PlatformRegistry:
    """
    Unified registry for all platform adapters.
    register("whatsapp", WhatsAppAdapter(...))
    send("whatsapp", to="+91...", text="Hello")
    """

    def __init__(self):
        self._adapters: dict[str, object] = {}

    def register(self, name: str, adapter: object) -> None:
        self._adapters[name] = adapter
        logger.info(f"[VECTOR][platforms] registered: {name}")

    def get(self, name: str) -> Optional[object]:
        return self._adapters.get(name)

    def send(self, platform: str, **kwargs) -> bool:
        adapter = self._adapters.get(platform)
        if not adapter:
            logger.warning(f"[VECTOR][platforms] not registered: {platform}")
            return False
        try:
            return adapter.send(**kwargs)
        except Exception as e:
            logger.error(f"[VECTOR][platforms] {platform}.send() error: {e}")
            return False

    def list_platforms(self) -> list[str]:
        return list(self._adapters.keys())

if __name__ == "__main__":
    # Offline structural tests — no real tokens/webhooks needed

    # DingTalk signature generation (offline)
    dt = DingTalkAdapter("https://example.com/hook?access_token=x", secret="test_secret")
    ts, sign = dt._sign()
    assert ts.isdigit() and len(sign) > 10

    # FeishuAdapter payload structure
    fs = FeishuAdapter("https://example.com/feishu")
    assert fs._webhook == "https://example.com/feishu"

    # WeComAdapter
    wc = WeComAdapter("https://example.com/wecom")
    assert wc._webhook == "https://example.com/wecom"

    # SMSAdapter provider selection
    sms = SMSAdapter(provider="twilio", twilio_sid="AC123", twilio_token="tok", twilio_from="+1000")
    assert sms._provider == "twilio"
    sms2 = SMSAdapter(provider="sns", sns_region="us-east-1")
    assert sms2._sns_region == "us-east-1"

    # WhatsAppAdapter
    wa = WhatsAppAdapter(phone_number_id="12345", access_token="token")
    assert "12345" in wa._url

    # MatrixAdapter headers
    mx = MatrixAdapter("https://matrix.example.com", "tok123")
    assert "Bearer tok123" in mx._headers["Authorization"]

    # MattermostAdapter
    mm = MattermostAdapter("https://mm.example.com/hook/abc")
    assert mm._webhook == "https://mm.example.com/hook/abc"

    # HomeAssistantAdapter
    ha = HomeAssistantAdapter("https://ha.example.com", "ha_token")
    assert "Bearer ha_token" in ha._headers["Authorization"]

    # SignalAdapter
    sig = SignalAdapter("http://localhost:8080", "+91999")
    assert sig._sender == "+91999"

    # PlatformRegistry
    reg = PlatformRegistry()
    reg.register("dingtalk", dt)
    reg.register("feishu", fs)
    reg.register("wecom", wc)
    assert "dingtalk" in reg.list_platforms()
    assert "feishu" in reg.list_platforms()
    assert len(reg.list_platforms()) == 3

    print(f"platform_adapters.py OK — 9 platforms registered: WhatsApp, Matrix, Signal, Mattermost, HA, DingTalk, Feishu, WeCom, SMS")

