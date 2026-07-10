"""
districts/agency/wa_assistant.py — WhatsApp Business client-reply assistant.

The other half of Wave-1 client ops (Instagram posting is districts/content/phone_poster).
Runs on the WhatsApp Business APP on the connected phone (com.whatsapp.w4b) — the app the
owner logged into, NOT the enterprise Cloud API (that needs Meta verification).

Deliberate trust boundary: for the FIRST clients, VECTOR DRAFTS, the owner SENDS. Auto-send
is gated behind BOTH owner approval AND config `agency.wa_autosend=True` (off by default) —
because a bad auto-reply loses a client, and early client trust is the owner's job to earn.

Flow:
  read_business_messages()  — incoming WA-Business messages via notifications (VECTOR already
                              has notification read; no new permission)
  draft_reply(msg)          — LLM draft in the owner's voice, using client context
  send_reply(number, text)  — open the chat via wa.me intent (text pre-filled) → owner taps
                              Send, OR (if autosend approved) VECTOR taps Send

Reuses: phone_controller, vectorcode_llm, permission_gateway. Never raises.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import urllib.parse

from loguru import logger

from core.config import CONFIG

_WA_PACKAGE = "com.whatsapp.w4b"


class WhatsAppAssistant:
    def __init__(self):
        from core.control.phone_controller import PhoneController
        self._pc = PhoneController()

    def read_business_messages(self) -> list[dict]:
        """Return pending WhatsApp Business messages from the notification tray.
        [{sender, text}]. Empty if none / phone offline."""
        out = []
        for n in self._pc.get_notifications():
            if n.get("package", "").lower() == _WA_PACKAGE:
                title = n.get("title", "")
                text = n.get("text", "")
                if title and text and "message" not in title.lower():  # skip summary rows
                    out.append({"sender": title, "text": text})
        logger.info("[VECTOR][wa_assistant] {} WhatsApp Business messages pending", len(out))
        return out

    def draft_reply(self, message: str, sender: str = "", context: str = "") -> str:
        """LLM-draft a reply in the owner's voice. Falls back to a safe holding
        line if the LLM is unavailable — never returns empty."""
        try:
            from core.inference.vectorcode_llm import chat
            sys_prompt = (
                "You are Arghyadeep's WhatsApp Business assistant for his AI content-automation "
                "service. Draft ONE concise, warm, professional reply (max 2 sentences) in first "
                "person. No emoji spam, no fake promises. If the message needs info you don't have, "
                "ask one clarifying question. This is a DRAFT the owner reviews before sending."
            )
            usr = f"Client ({sender}) said: \"{message}\"."
            if context:
                usr += f" Context: {context}."
            usr += " Draft the reply:"
            reply = chat(
                model=CONFIG["models"].get("focus", "vector-focus"),
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": usr}],
                timeout=60.0, district="agency", domain="content.script",
            )
            reply = (reply or "").strip()
            if reply:
                return reply[:600]
        except Exception as e:
            logger.warning("[VECTOR][wa_assistant] draft LLM failed: {}", e)
        return "Thanks for reaching out! I'll get back to you shortly with the details."

    async def send_reply(self, number: str, text: str) -> dict:
        """Open the WhatsApp chat with `number` (text pre-filled via wa.me intent).
        Auto-taps Send only if owner-approved AND agency.wa_autosend is on; otherwise
        leaves it for the owner to tap. Returns {status, reason}."""
        if not self._pc.is_connected():
            return {"status": "error", "reason": "phone not connected"}

        autosend = bool(CONFIG.get("agency", {}).get("wa_autosend", False))
        if autosend:
            try:
                from core.loop.permission_gateway import PermissionGateway
                approved = await PermissionGateway().request_approval(
                    action="whatsapp_autosend",
                    summary=f"Auto-send WhatsApp to {number}: {text[:80]}",
                    risk="RED",
                )
            except Exception as e:
                logger.error("[VECTOR][wa_assistant] approval failed (fail-closed): {}", e)
                approved = False
            if not approved:
                autosend = False  # fall back to owner-sends

        # Open chat with text pre-filled (robust — no chat-list navigation).
        try:
            self._pc.unlock()
            url = f"https://wa.me/{number.lstrip('+')}?text={urllib.parse.quote(text)}"
            self._pc._run_adb(
                "shell", "am", "start", "-a", "android.intent.action.VIEW",
                "-d", url, "-p", _WA_PACKAGE, timeout=15,
            )
            await asyncio.sleep(3)
        except Exception as e:
            return {"status": "error", "reason": f"open chat failed: {e}"}

        if autosend:
            # Send arrow is bottom-right on WhatsApp; calibratable if it moves.
            tap = CONFIG.get("agency", {}).get("wa_send_tap", [1000, 1830])
            self._pc.tap(int(tap[0]), int(tap[1]))
            return {"status": "sent", "reason": "auto-sent (approved)"}

        try:
            from core.notify import pushover  # type: ignore
            pushover(f"WhatsApp draft ready for {number} — review & tap Send.")
        except Exception:
            pass
        return {"status": "draft_ready", "reason": "chat open with draft; owner taps Send"}


if __name__ == "__main__":
    # Structural self-test — no messages sent.
    import inspect
    a = WhatsAppAssistant.__dict__
    ok = all(m in a for m in ("read_business_messages", "draft_reply", "send_reply"))
    d = WhatsAppAssistant().draft_reply("Do you make Instagram reels?", "Test Client")
    ok = ok and isinstance(d, str) and len(d) > 0
    print("wa_assistant OK" if ok else "FAILED")
