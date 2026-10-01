"""
Email Agent — full email client agent for VECTOR's communications district.

Python port of agentic-inbox/workers/agent/index.ts + workers/lib/tools.ts.

Provides 13 email tools wired to VECTOR's local SQLite email store:
  list_emails, get_email, get_thread, search_emails,
  draft_reply, draft_email, update_draft, discard_draft,
  mark_email_read, move_email, delete_email,
  send_reply, send_email (send routes through VECTOR's permission gateway)

Auto-draft on new email: reads inbox, detects prompt injection,
generates a draft reply (requires explicit confirmation to send).
"""
from __future__ import annotations

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import datetime
import json
import sqlite3
import uuid
import re
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.email.schema import get_connection, init_schema, EMAIL_DB_PATH
from core.email.receiver import fetch_new_emails
from core.email.ai_security import is_prompt_injection, verify_draft
from core.email.search import parse_search_query
from core.email.helpers import strip_html_to_text, build_quoted_reply_block
from core.email.ui_helpers import get_snippet_text
from core.inference.vectorcode_llm import chat

_DEFAULT_SYSTEM_PROMPT = """You are an email assistant that helps manage this inbox.
You read emails, draft replies, and help organize conversations.

Writing Style: Short, direct, plain text. Get to the point.
Draft Only - Never Send: You can ONLY draft emails via draft_reply/draft_email.
Arghyadeep reviews and confirms before sending.

CRITICAL: Draft body must contain ONLY the email text — no agent commentary,
no markdown, no 'Draft created.', no separators."""

_FOLDERS = {
    "inbox": "inbox", "sent": "sent", "draft": "draft",
    "archive": "archive", "trash": "trash", "spam": "spam"
}


class EmailAgent(AgentBase):
    """
    Full email client agent. Local SQLite storage + AI drafting.
    Mirrors agentic-inbox EmailAgent with Python/VECTOR infrastructure.
    """

    def __init__(self):
        super().__init__(agent_id="email_agent_001", name="EmailAgent", district="communications")
        self.capabilities = ["communications", "delete", "discard_draft", "draft_email", "draft_reply", "email", "forward", "get", "list", "mark_read", "message", "move", "new_email", "notify", "poll_inbox", "reply", "search", "send_email", "store_incoming", "thread", "update_draft", "user_interaction"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.models.focus if hasattr(CONFIG, "models") else "vector-focus"
        self._db_path = Path(EMAIL_DB_PATH)
        init_schema(self._db_path)
        logger.info("[VECTOR][email_agent] initialized — db={}", self._db_path)
        # Phase 2B: subscribe to email events
        self.subscribe_to("user_interaction")
        self.subscribe_to("voice_input")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Triage incoming email/message events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("user_interaction", "voice_input"):
            try:
                data = event.get("data", {})
                if "email" in str(data).lower() or "message" in str(data).lower():
                    logger.info(f"[VECTOR][email_agent] event-triggered triage: {et}")
                    await self.run({"type": "triage", "params": {"context": str(data)[:200]}})
            except Exception as e:
                logger.debug(f"[VECTOR][email_agent] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self._db_path)

    # ── Read tools ────────────────────────────────────────────────────────────

    def list_emails(self, folder: str = "inbox", limit: int = 20, page: int = 1) -> list[dict]:
        """List emails in a folder, sorted by date descending."""
        offset = (page - 1) * limit
        conn = self._conn()
        rows = conn.execute(
            "SELECT id,subject,sender,recipient,date,read,starred,thread_id,folder_id "
            "FROM emails WHERE folder_id=? ORDER BY date DESC LIMIT ? OFFSET ?",
            (folder, limit, offset)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_email(self, email_id: str) -> dict | None:
        """Get a single email with full body and attachments."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM emails WHERE id=?", (email_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        email = dict(row)
        attachments = conn.execute(
            "SELECT * FROM attachments WHERE email_id=?", (email_id,)
        ).fetchall()
        email["attachments"] = [dict(a) for a in attachments]
        conn.close()
        return email

    def get_thread(self, thread_id: str) -> list[dict]:
        """Get all emails in a thread, sorted chronologically."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM emails WHERE thread_id=? ORDER BY date ASC", (thread_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_emails(self, query: str, folder: str | None = None) -> list[dict]:
        """Search emails using Gmail-style query syntax (from:, to:, subject:, is:, has:, etc.)."""
        parsed = parse_search_query(query)
        folder = folder or parsed.folder
        conditions: list[str] = []
        params: list = []

        if folder:
            conditions.append("folder_id = ?")
            params.append(folder)
        if parsed.from_addr:
            conditions.append("sender LIKE ?")
            params.append(f"%{parsed.from_addr}%")
        if parsed.to_addr:
            conditions.append("recipient LIKE ?")
            params.append(f"%{parsed.to_addr}%")
        if parsed.subject:
            conditions.append("subject LIKE ?")
            params.append(f"%{parsed.subject}%")
        if parsed.is_read is not None:
            conditions.append("read = ?")
            params.append(1 if parsed.is_read else 0)
        if parsed.is_starred is not None:
            conditions.append("starred = ?")
            params.append(1 if parsed.is_starred else 0)
        if parsed.has_attachment:
            conditions.append("id IN (SELECT DISTINCT email_id FROM attachments)")
        if parsed.date_start:
            conditions.append("date >= ?")
            params.append(parsed.date_start)
        if parsed.date_end:
            conditions.append("date <= ?")
            params.append(parsed.date_end)
        if parsed.query:
            conditions.append("(subject LIKE ? OR body LIKE ?)")
            params.extend([f"%{parsed.query}%", f"%{parsed.query}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        conn = self._conn()
        rows = conn.execute(
            f"SELECT id,subject,sender,recipient,date,read,starred,thread_id,folder_id "
            f"FROM emails {where} ORDER BY date DESC LIMIT 50",
            params,
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Draft tools ───────────────────────────────────────────────────────────

    def draft_reply(self, original_email_id: str, to: str, subject: str, body: str) -> dict:
        """Draft a reply — saves to draft folder, does NOT send."""
        # Verify draft removes agent artifacts
        verified = verify_draft(body)
        if verified is None or verified == "":
            return {"error": "Draft verification failed — please try again"}

        original = self.get_email(original_email_id)
        thread_id = original.get("thread_id", original_email_id) if original else original_email_id

        draft_id = str(uuid.uuid4())
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT INTO emails(id,folder_id,subject,sender,recipient,date,body,in_reply_to,thread_id) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (draft_id, "draft", subject, CONFIG.get("owner_email", "arghyadeepdeb020703@gmail.com"), to,
                 datetime.datetime.now().isoformat(), verified, original_email_id, thread_id)
            )
        conn.close()
        logger.info("[VECTOR][email_agent] draft_reply saved: {} → {}", draft_id, to)
        return {"status": "draft_saved", "draftId": draft_id, "to": to, "subject": subject}

    def draft_email(self, to: str, subject: str, body: str) -> dict:
        """Draft a new email (not a reply) — saves to draft folder."""
        verified = verify_draft(body)
        if verified is None or verified == "":
            return {"error": "Draft verification failed — please try again"}

        draft_id = str(uuid.uuid4())
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (draft_id, "draft", subject, CONFIG.get("owner_email", "arghyadeepdeb020703@gmail.com"), to,
                 datetime.datetime.now().isoformat(), verified, draft_id)
            )
        conn.close()
        return {"status": "draft_saved", "draftId": draft_id, "to": to, "subject": subject}

    def update_draft(self, draft_id: str, title: str = None, body: str = None,
                     to: str = None) -> dict | None:
        """Update an existing email draft. Returns updated draft or None if not found."""
        conn = self._conn()
        draft = conn.execute(
            "SELECT * FROM emails WHERE id=? AND folder_id='draft'", (draft_id,)
        ).fetchone()
        if not draft:
            conn.close()
            return None
        updates, params = [], []
        if title is not None:
            updates.append("subject=?"); params.append(title)
        if body is not None:
            updates.append("body=?"); params.append(body)
        if to is not None:
            updates.append("recipient=?"); params.append(to)
        if updates:
            params.append(draft_id)
            conn.execute(f"UPDATE emails SET {','.join(updates)} WHERE id=?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM emails WHERE id=?", (draft_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def discard_draft(self, draft_id: str) -> dict:
        """Delete a draft email."""
        conn = self._conn()
        row = conn.execute("SELECT folder_id FROM emails WHERE id=?", (draft_id,)).fetchone()
        if not row:
            conn.close()
            return {"error": "Draft not found"}
        if row["folder_id"] != "draft":
            conn.close()
            return {"error": "Cannot discard: email is not a draft"}
        with conn:
            conn.execute("DELETE FROM emails WHERE id=?", (draft_id,))
        conn.close()
        return {"status": "discarded", "draftId": draft_id}

    # ── Sending (permission-gated) ────────────────────────────────────────────

    async def send_reply(self, draft_id: str, transport=None) -> dict:
        """Send a saved draft — GATED.

        Outbound email is an outward, hard-to-reverse action, so it goes through
        the permission gateway under the existing RED ``send_email`` tier: the
        owner is notified (to / subject / preview) and it sends ONLY on approval.
        Fail-closed: if the gateway raises or is unreachable, nothing is sent.

        ``transport`` is an injectable ``callable(draft_dict) -> bool`` for the
        actual send channel (the ``vector-email`` Worker's ``/api/v1/agent/send``
        endpoint in Phase 3, or an SMTP sender). With no transport wired yet, an
        approved send returns ``approved_no_transport`` rather than silently
        pretending to have sent. See ``plans/cloud-inbox-brain-bridge.md`` (Phase 2).
        """
        draft = self.get_email(draft_id)
        if not draft:
            return {"status": "error", "message": "draft not found"}
        to = draft.get("recipient", "")
        subject = draft.get("subject", "")
        preview = (draft.get("body") or "")[:200]

        try:
            from core.loop.permission_gateway import PermissionGateway, Action
            gw = PermissionGateway()
            result = await gw.execute(Action(
                action_type="send_email",
                params={"to": to, "subject": subject, "preview": preview, "draft_id": draft_id},
                proposed_by="email_agent",
            ))
        except Exception as e:
            logger.error("[VECTOR][email_agent] gateway unreachable — send blocked (fail-closed): {}", e)
            return {"status": "blocked", "reason": "gateway_unreachable"}

        if not getattr(result, "approved", False):
            logger.info("[VECTOR][email_agent] send not approved for draft {}", draft_id)
            return {"status": "blocked", "reason": "not_approved", "draftId": draft_id}

        if transport is None:
            return {"status": "approved_no_transport", "draftId": draft_id}

        try:
            sent_ok = bool(transport(draft))
        except Exception as e:
            logger.error("[VECTOR][email_agent] transport failed: {}", e)
            return {"status": "error", "message": str(e)}

        if not sent_ok:
            return {"status": "error", "message": "transport reported failure"}

        conn = self._conn()
        with conn:
            conn.execute("UPDATE emails SET folder_id='sent' WHERE id=?", (draft_id,))
        conn.close()
        logger.info("[VECTOR][email_agent] sent draft {} → {}", draft_id, to)
        return {"status": "sent", "draftId": draft_id, "to": to}

    # ── Management tools ──────────────────────────────────────────────────────

    def mark_email_read(self, email_id: str, read: bool) -> dict:
        conn = self._conn()
        with conn:
            conn.execute("UPDATE emails SET read=? WHERE id=?", (1 if read else 0, email_id))
        conn.close()
        return {"status": "updated", "emailId": email_id, "read": read}

    def move_email(self, email_id: str, folder_id: str) -> dict:
        if folder_id not in _FOLDERS:
            return {"error": f"Unknown folder: {folder_id}"}
        conn = self._conn()
        with conn:
            conn.execute("UPDATE emails SET folder_id=? WHERE id=?", (folder_id, email_id))
        conn.close()
        return {"status": "moved", "emailId": email_id, "folder": folder_id}

    def delete_email(self, email_id: str) -> dict:
        conn = self._conn()
        row = conn.execute("SELECT id FROM emails WHERE id=?", (email_id,)).fetchone()
        if not row:
            conn.close()
            return {"error": "Email not found"}
        with conn:
            conn.execute("DELETE FROM emails WHERE id=?", (email_id,))
        conn.close()
        return {"status": "deleted", "emailId": email_id}

    def store_incoming_email(self, sender: str, subject: str, body: str,
                              message_id: str | None = None, thread_id: str | None = None,
                              raw_headers: str | None = None) -> str:
        """Store a received email in the inbox. Returns email_id."""
        email_id = message_id or str(uuid.uuid4())
        resolved_thread_id = thread_id or email_id
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO emails(id,folder_id,subject,sender,recipient,date,"
                "body,thread_id,message_id,raw_headers,read) VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                (email_id, "inbox", subject, sender,
                 CONFIG.get("owner_email", "arghyadeepdeb020703@gmail.com"),
                 datetime.datetime.now().isoformat(),
                 body, resolved_thread_id, message_id, raw_headers)
            )
        conn.close()
        return email_id

    def poll_inbox(self) -> dict:
        """Pull unseen messages from the configured IMAP mailbox into the
        local inbox. Degrades to a no-op (empty result) when IMAP_HOST/
        IMAP_USER/IMAP_PASS aren't configured — see core/email/receiver.py.
        """
        fetched = fetch_new_emails()
        stored = []
        for msg in fetched:
            email_id = self.store_incoming_email(
                sender=msg.sender, subject=msg.subject, body=msg.body,
                message_id=msg.message_id, thread_id=msg.thread_id,
                raw_headers=msg.raw_headers,
            )
            stored.append(email_id)
        if stored:
            self.award_points(5, "inbox_polled")
            logger.info(f"[VECTOR][email_agent] poll_inbox stored {len(stored)} new email(s)")
        return {"fetched": len(fetched), "stored": stored}

    # ── Auto-draft on new email ───────────────────────────────────────────────

    async def handle_new_email(self, email_id: str, sender: str, subject: str,
                                thread_id: str) -> dict:
        """
        Auto-draft: reads incoming email, checks for prompt injection,
        generates a draft reply. Mirrors EmailAgent.handleNewEmail().
        """
        email = self.get_email(email_id)
        if not email:
            return {"status": "error", "error": "Email not found"}

        body = email.get("body", "")

        # Security: check for prompt injection
        if is_prompt_injection(body):
            logger.warning("[VECTOR][email_agent] prompt injection detected — skipping auto-draft: {}", email_id)
            self._get_memory().store(
                event_type="email_injection_blocked",
                content=f"Blocked auto-draft from {sender}: {subject}",
                tags=["communications", "security", "email"],
                source="email_agent",
            )
            return {"status": "blocked", "reason": "prompt_injection_detected"}

        # Build thread context
        thread_emails = self.get_thread(thread_id)
        thread_context = ""
        if len(thread_emails) > 1:
            parts = []
            for e in thread_emails:
                plain = re.sub(r"<[^>]+>", " ", e.get("body", ""))
                parts.append(f"[{e['date']}] {e['sender']} -> {e['recipient']}: {plain[:500]}")
            thread_context = "\n\n".join(parts)

            # Check thread for injection too
            if is_prompt_injection(thread_context):
                logger.warning("[VECTOR][email_agent] injection in thread context — skipping")
                return {"status": "blocked", "reason": "thread_injection_detected"}

        # Build auto-draft prompt
        plain_body = re.sub(r"<[^>]+>", " ", body)
        prompt = (
            f"A new email just arrived. Draft an appropriate reply.\n\n"
            f"From: {sender}\nSubject: {subject}\n\n"
            f"Email body:\n{plain_body[:1500]}"
        )
        if thread_context:
            prompt += f"\n\nThread history:\n{thread_context[:2000]}"

        prompt += "\n\nWrite a reply as plain text. Keep it short and direct. Sign as Arghyadeep."

        try:
            draft_body = chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                timeout=45.0,
            )
            if draft_body:
                re_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
                result = self.draft_reply(email_id, sender, re_subject, draft_body)
                if result.get("error"):
                    logger.warning("[VECTOR][email_agent] auto-draft not saved: {}", result["error"])
                    return {"status": "error", "error": result["error"]}
                self._get_memory().store(
                    event_type="email_auto_draft",
                    content=f"Auto-drafted reply to {sender}: {subject}",
                    tags=["communications", "email", "draft"],
                    source="email_agent",
                )
                self.award_points(20, "auto_draft_created")
                return {"status": "draft_created", "draft": result}
        except Exception as e:
            logger.error("[VECTOR][email_agent] auto-draft failed: {}", e)

        return {"status": "error", "error": "Auto-draft generation failed"}

    # ── Main run dispatcher ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below reads its arguments (email_id/folder/subject/body/...)
        # straight off `task`, never `task["params"]`, so a real dispatch
        # always fell back to the hardcoded defaults, silently ignoring the
        # caller's real request. Verified live before fixing: dispatching
        # "list" with params={"folder": "sent", "limit": 5, "page": 2}
        # called list_emails("inbox", 20, 1) -- the defaults, not what was
        # asked. Given the large number of task types/keys here, flattening
        # params into task once (params values win on overlap, matching
        # every other real-argument-bearing key this method reads) is safer
        # and more maintainable than editing every individual .get() call
        # below -- and keeps every existing flat-shape caller/test working
        # unchanged, since task.get("params") is {} for those.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. Verified live before fixing:
        # {"type": "draft_reply", "params": {"type": "html", ...}} routed
        # as "html" instead of "draft_reply".
        task_type = task.get("type", "list")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "list":
                emails = self.list_emails(task.get("folder", "inbox"),
                                          task.get("limit", 20), task.get("page", 1))
                self.award_points(5, "emails_listed")
                return {"status": "ok", "emails": emails, "count": len(emails)}

            elif task_type == "get":
                email = self.get_email(task.get("email_id", ""))
                if not email:
                    return {"status": "error", "error": "Email not found"}
                self.award_points(5, "email_read")
                return {"status": "ok", "email": email}

            elif task_type == "thread":
                thread = self.get_thread(task.get("thread_id", ""))
                self.award_points(5, "thread_read")
                return {"status": "ok", "thread": thread, "count": len(thread)}

            elif task_type == "search":
                results = self.search_emails(task.get("query", ""), task.get("folder"))
                self.award_points(10, "emails_searched")
                return {"status": "ok", "results": results, "count": len(results)}

            elif task_type == "draft_reply":
                result = self.draft_reply(task.get("original_email_id", ""),
                                          task.get("to", ""), task.get("subject", ""),
                                          task.get("body", ""))
                self.award_points(15, "draft_reply_created")
                return {"status": "ok", "draft": result}

            elif task_type == "draft_email":
                result = self.draft_email(task.get("to", ""), task.get("subject", ""),
                                          task.get("body", ""))
                self.award_points(15, "draft_email_created")
                return {"status": "ok", "draft": result}

            elif task_type == "update_draft":
                result = self.update_draft(
                    task.get("draft_id", ""),
                    title=task.get("title"),
                    body=task.get("body"),
                    to=task.get("to"),
                )
                if result is None:
                    return {"status": "error", "error": "Draft not found"}
                self.award_points(10, "draft_updated")
                return {"status": "ok", "draft": result}

            elif task_type == "discard_draft":
                result = self.discard_draft(task.get("draft_id", ""))
                self.award_points(5, "draft_discarded")
                return {"status": "ok", **result}

            elif task_type == "mark_read":
                result = self.mark_email_read(task.get("email_id", ""), task.get("read", True))
                return {"status": "ok", **result}

            elif task_type == "move":
                result = self.move_email(task.get("email_id", ""), task.get("folder", "archive"))
                return {"status": "ok", **result}

            elif task_type == "delete":
                result = self.delete_email(task.get("email_id", ""))
                return {"status": "ok", **result}

            elif task_type == "new_email":
                result = await self.handle_new_email(
                    task.get("email_id", ""), task.get("sender", ""),
                    task.get("subject", ""), task.get("thread_id", ""),
                )
                return {"status": "ok", **result}

            elif task_type == "poll_inbox":
                result = self.poll_inbox()
                return {"status": "ok", **result}

            elif task_type == "store_incoming":
                email_id = self.store_incoming_email(
                    task.get("sender", ""), task.get("subject", ""),
                    task.get("body", ""), task.get("message_id"),
                    task.get("thread_id"), task.get("raw_headers"),
                )
                self.award_points(10, "email_stored")
                return {"status": "ok", "email_id": email_id}

            elif task_type in ("reply", "send_reply"):
                # 53_PERMISSION_BOUNDARY_INTEGRITY.md Finding 1: this branch
                # called handle_reply_email() -> core/email/sender.py's real
                # smtplib.SMTP send directly, with NO PermissionGateway check
                # — a live, RED-tier "send_email" bypass reachable from any
                # governor.dispatch({"type": "reply", ...}) call (both the
                # autonomous fallthrough in _act_on() and the classify_chat_
                # intent() fast path in commands.py/websocket.py), even
                # though this same class's send_reply() method already
                # implements this exact gate correctly. Reuse that gate here
                # — same Action shape, same fail-closed behavior — rather
                # than inventing a new one.
                _preview_to = task.get("to", "")
                _preview_subject = task.get("subject", "")
                try:
                    from core.loop.permission_gateway import PermissionGateway, Action
                    _gate_result = await PermissionGateway().execute(Action(
                        action_type="send_email",
                        params={
                            "to": _preview_to, "subject": _preview_subject,
                            "preview": (task.get("text") or task.get("html") or "")[:200],
                        },
                        proposed_by="email_agent",
                    ))
                except Exception as _gw_err:
                    logger.error("[VECTOR][email_agent] gateway unreachable — reply blocked (fail-closed): {}", _gw_err)
                    return {"status": "blocked", "reason": "gateway_unreachable"}
                if not getattr(_gate_result, "approved", False):
                    logger.info("[VECTOR][email_agent] reply send not approved")
                    return {"status": "blocked", "reason": "not_approved"}

                from districts.communications.reply_forward import handle_reply_email
                result = handle_reply_email(
                    mailbox_id=task.get("mailbox_id", CONFIG.get("EMAIL_ADDRESS", "")),
                    original_id=task.get("original_email_id", ""),
                    to=task.get("to", ""),
                    from_addr=task.get("from", CONFIG.get("EMAIL_ADDRESS", "")),
                    subject=task.get("subject", ""),
                    html=task.get("html"),
                    text=task.get("text"),
                    cc=task.get("cc"),
                    bcc=task.get("bcc"),
                    attachments=task.get("attachments"),
                )
                if result.get("error"):
                    self.deduct_points(20, "email_task_failed")
                    return {**result, "status": "error"}
                self.award_points(20, "email_replied")
                return {"status": "ok", **result}

            elif task_type == "forward":
                # Same Finding 1 gate as "reply"/"send_reply" above — forward
                # is an equally real outbound send via the same sender path.
                try:
                    from core.loop.permission_gateway import PermissionGateway, Action
                    _gate_result = await PermissionGateway().execute(Action(
                        action_type="send_email",
                        params={
                            "to": task.get("to", ""), "subject": task.get("subject", ""),
                            "preview": (task.get("text") or task.get("html") or "")[:200],
                        },
                        proposed_by="email_agent",
                    ))
                except Exception as _gw_err:
                    logger.error("[VECTOR][email_agent] gateway unreachable — forward blocked (fail-closed): {}", _gw_err)
                    return {"status": "blocked", "reason": "gateway_unreachable"}
                if not getattr(_gate_result, "approved", False):
                    logger.info("[VECTOR][email_agent] forward send not approved")
                    return {"status": "blocked", "reason": "not_approved"}

                from districts.communications.reply_forward import handle_forward_email
                result = handle_forward_email(
                    mailbox_id=task.get("mailbox_id", CONFIG.get("EMAIL_ADDRESS", "")),
                    original_id=task.get("original_email_id", ""),
                    to=task.get("to", ""),
                    from_addr=task.get("from", CONFIG.get("EMAIL_ADDRESS", "")),
                    subject=task.get("subject", ""),
                    html=task.get("html"),
                    text=task.get("text"),
                    cc=task.get("cc"),
                    bcc=task.get("bcc"),
                    attachments=task.get("attachments"),
                )
                if result.get("error"):
                    self.deduct_points(20, "email_task_failed")
                    return {**result, "status": "error"}
                self.award_points(20, "email_forwarded")
                return {"status": "ok", **result}

            else:
                # Status
                conn = self._conn()
                inbox_count = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE folder_id='inbox' AND read=0"
                ).fetchone()[0]
                total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                conn.close()
                self.award_points(5, "email_status_checked")
                return {"status": "ok", "unread_inbox": inbox_count, "total_emails": total}

        except Exception as e:
            logger.error("[VECTOR][email_agent] {}", e)
            self.deduct_points(20, "email_task_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = EmailAgent()

        # Store a test email
        eid = agent.store_incoming_email(
            "test@example.com", "Hello from VECTOR test",
            "<p>This is a test email. How are you?</p>",
        )
        print(f"[OK] store_incoming: email_id={eid}")

        # List inbox
        emails = agent.list_emails("inbox")
        print(f"[OK] list_emails: {len(emails)} in inbox")

        # Get email
        email = agent.get_email(eid)
        print(f"[OK] get_email: subject='{email['subject']}' sender={email['sender']}")

        # Draft a reply
        result = agent.draft_reply(eid, "test@example.com", "Re: Hello from VECTOR test",
                                    "Hi! Doing great, thanks for reaching out. - Arghyadeep")
        print(f"[OK] draft_reply: status={result.get('status')} draftId={result.get('draftId','?')[:8]}")

        # Search
        results = agent.search_emails("VECTOR test")
        print(f"[OK] search_emails: {len(results)} results")

        # Run task
        run_result = await agent.run({"type": "status"})
        print(f"[OK] run status: unread={run_result.get('unread_inbox')} total={run_result.get('total_emails')}")
        print("email_agent.py OK")

    asyncio.run(_smoke())
