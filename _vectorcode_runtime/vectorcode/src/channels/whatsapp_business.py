"""
WhatsAppBusinessChannel — Meta WhatsApp Business Cloud API extensions.

Extends the base WhatsAppChannel with Business-specific features:
  - Template messages (HSM — pre-approved structured messages)
  - Media messages (image, video, audio, document, sticker)
  - Reaction messages (emoji on a specific message)
  - Interactive messages (button replies, list pickers)
  - WhatsApp Channels / Newsletter API (broadcast to subscribers)

Inspired by OpenWA's Business API module (reimplemented for Meta's official API).
Requires: WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID env vars.

Usage:
    ch = WhatsAppBusinessChannel()
    ch.connect()
    ch.send_template("919876543210", "hello_world", language="en_US")
    ch.send_image("919876543210", "https://example.com/img.jpg", caption="Look!")
    ch.send_reaction("919876543210", message_id="wamid.xxx", emoji="👍")
    ch.send_interactive_buttons("919876543210",
        body="Pick one:", buttons=[("Yes", "yes"), ("No", "no")])
"""
from __future__ import annotations

__all__ = ["WhatsAppBusinessChannel"]

import os
from typing import Any

from loguru import logger

from vectorcode.src.channels.whatsapp import WhatsAppChannel
from vectorcode.src.core.registry import ChannelRegistry

_API_VERSION = "v21.0"
_BASE = "https://graph.facebook.com"


@ChannelRegistry.register("whatsapp_business")
class WhatsAppBusinessChannel(WhatsAppChannel):
    """
    WhatsApp Business Cloud API — extends WhatsAppChannel with structured
    message types that require a verified Business account and approved templates.

    All methods return True on success, False on failure (never raise).
    """

    channel_id = "whatsapp_business"

    # ── Template messages ──────────────────────────────────────────────────────

    def send_template(
        self,
        to: str,
        template_name: str,
        *,
        language: str = "en_US",
        components: list[dict[str, Any]] | None = None,
    ) -> bool:
        """
        Send a pre-approved HSM template message.

        Args:
            to:            Recipient phone number in E.164 format (e.g. "919876543210").
            template_name: Approved template name (e.g. "hello_world").
            language:      BCP-47 language code (default "en_US").
            components:    Template variable components (header/body/button params).
        """
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            payload["template"]["components"] = components
        return self._post_message(payload)

    # ── Media messages ─────────────────────────────────────────────────────────

    def send_image(self, to: str, url: str, *, caption: str = "") -> bool:
        """Send an image message (JPEG/PNG, max 5MB)."""
        return self._send_media(to, "image", url=url, caption=caption)

    def send_video(self, to: str, url: str, *, caption: str = "") -> bool:
        """Send a video message (MP4/3GPP, max 16MB)."""
        return self._send_media(to, "video", url=url, caption=caption)

    def send_audio(self, to: str, url: str) -> bool:
        """Send an audio message (AAC/MP4/OGG/AMR, max 16MB)."""
        return self._send_media(to, "audio", url=url)

    def send_document(self, to: str, url: str, *, filename: str = "", caption: str = "") -> bool:
        """Send a document (PDF/DOCX/XLSX etc., max 100MB)."""
        media: dict[str, str] = {"link": url}
        if caption:
            media["caption"] = caption
        if filename:
            media["filename"] = filename
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": media,
        })

    def send_sticker(self, to: str, url: str) -> bool:
        """Send a sticker (WebP, max 100KB static / 500KB animated)."""
        return self._send_media(to, "sticker", url=url)

    # ── Reaction messages ──────────────────────────────────────────────────────

    def send_reaction(self, to: str, *, message_id: str, emoji: str) -> bool:
        """
        React to a message with an emoji.

        Args:
            to:         Recipient phone.
            message_id: The wamid of the message to react to.
            emoji:      Unicode emoji character (e.g. "👍").
        """
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        })

    def remove_reaction(self, to: str, *, message_id: str) -> bool:
        """Remove a reaction from a message (send empty emoji)."""
        return self.send_reaction(to, message_id=message_id, emoji="")

    # ── Interactive messages ───────────────────────────────────────────────────

    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[tuple[str, str]],
        *,
        header: str = "",
        footer: str = "",
    ) -> bool:
        """
        Send a button interactive message (max 3 buttons).

        Args:
            to:      Recipient phone.
            body:    Message body text.
            buttons: List of (title, payload_id) tuples.
            header:  Optional header text.
            footer:  Optional footer text.
        """
        action = {
            "buttons": [
                {"type": "reply", "reply": {"id": pid, "title": title[:20]}}
                for title, pid in buttons[:3]
            ]
        }
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": action,
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        })

    def send_interactive_list(
        self,
        to: str,
        body: str,
        button_label: str,
        sections: list[dict[str, Any]],
        *,
        header: str = "",
        footer: str = "",
    ) -> bool:
        """
        Send a list picker interactive message.

        Args:
            to:           Recipient phone.
            body:         Message body text.
            button_label: Label for the list-open button (max 20 chars).
            sections:     List of section dicts with 'title' and 'rows' keys.
                          Each row: {"id": "...", "title": "...", "description": "..."}
            header:       Optional header text.
            footer:       Optional footer text.
        """
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_label[:20],
                "sections": sections,
            },
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        })

    # ── WhatsApp Channels / Newsletter API ─────────────────────────────────────

    def send_channel_message(
        self,
        channel_id: str,
        content: str,
        *,
        media_url: str = "",
        media_type: str = "image",
    ) -> bool:
        """
        Send a message to a WhatsApp Channel (newsletter).
        Requires the channel_id from the Channels dashboard.

        Args:
            channel_id: WhatsApp Channel/newsletter ID.
            content:    Text content of the post.
            media_url:  Optional media URL to attach.
            media_type: Media type ("image", "video", "document").
        """
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "channel",
            "to": channel_id,
            "type": "text",
            "text": {"body": content},
        }
        if media_url:
            payload["type"] = media_type
            payload[media_type] = {"link": media_url}
        return self._post_message(payload)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _send_media(
        self,
        to: str,
        media_type: str,
        *,
        url: str,
        caption: str = "",
    ) -> bool:
        media: dict[str, str] = {"link": url}
        if caption and media_type in ("image", "video"):
            media["caption"] = caption
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: media,
        })

    def _post_message(self, payload: dict[str, Any]) -> bool:
        """POST to the WhatsApp Cloud API messages endpoint."""
        if not self._token:
            logger.warning("[VECTOR][wa-business] no access token configured")
            return False
        try:
            import httpx
            url = f"{_BASE}/{_API_VERSION}/{self._phone_number_id}/messages"
            resp = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            if resp.status_code < 300:
                return True
            logger.warning("[VECTOR][wa-business] API returned {}: {}",
                           resp.status_code, resp.text[:120])
            return False
        except Exception as e:
            logger.debug("[VECTOR][wa-business] request failed: {}", e)
            return False


if __name__ == "__main__":
    ch = WhatsAppBusinessChannel()
    assert ch.channel_id == "whatsapp_business"
    assert hasattr(ch, "send_template")
    assert hasattr(ch, "send_image")
    assert hasattr(ch, "send_reaction")
    assert hasattr(ch, "send_interactive_buttons")
    assert hasattr(ch, "send_interactive_list")
    assert hasattr(ch, "send_channel_message")
    # No token → send returns False gracefully
    assert ch.send_template("919876543210", "hello_world") is False
    print("OK whatsapp_business.py — all methods present, graceful no-token degradation verified")
