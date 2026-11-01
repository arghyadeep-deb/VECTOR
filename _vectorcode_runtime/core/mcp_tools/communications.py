"""MCP communications tools."""

from loguru import logger


def add_email_tools(mcp) -> None:
    """Register email tools from agentic-inbox (13 tools).

    Mirrors EmailMCP from cloud/email/workers/mcp/index.ts.
    Clients: Claude Code, Cursor — connect via /mcp endpoint.
    """
    import json as _json

    try:
        from districts.communications.email_agent import EmailAgent
        _email_agent = EmailAgent()

        @mcp.tool
        def email_list(folder: str = "inbox", limit: int = 20, page: int = 1) -> str:
            """List emails in a folder (inbox/sent/draft/archive/trash/spam)."""
            try:
                emails = _email_agent.list_emails(folder, limit, page)
                return _json.dumps({"emails": emails, "count": len(emails)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_get(email_id: str) -> str:
            """Get a single email with full body content and attachments."""
            try:
                email = _email_agent.get_email(email_id)
                if not email:
                    return _json.dumps({"error": "Email not found"})
                return _json.dumps(email)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_get_thread(thread_id: str) -> str:
            """Get all emails in a conversation thread, sorted chronologically."""
            try:
                thread = _email_agent.get_thread(thread_id)
                return _json.dumps({"thread": thread, "count": len(thread)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_search(query: str, folder: str = "") -> str:
            """Search emails by subject and body text. Optional folder filter."""
            try:
                results = _email_agent.search_emails(query, folder or None)
                return _json.dumps({"results": results, "count": len(results)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_draft_reply(original_email_id: str, to: str, subject: str, body: str) -> str:
            """Draft a reply to an existing email. Saves to Drafts folder. Does NOT send.
            Body must be plain text — no HTML, no markdown."""
            try:
                result = _email_agent.draft_reply(original_email_id, to, subject, body)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_draft_new(to: str, subject: str, body: str) -> str:
            """Draft a new outbound email (not a reply). Saves to Drafts. Does NOT send.
            Arghyadeep reviews all drafts before sending."""
            try:
                result = _email_agent.draft_email(to, subject, body)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_discard_draft(draft_id: str) -> str:
            """Delete a draft email that is no longer needed."""
            try:
                result = _email_agent.discard_draft(draft_id)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_mark_read(email_id: str, read: bool = True) -> str:
            """Mark an email as read or unread."""
            try:
                result = _email_agent.mark_email_read(email_id, read)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_move(email_id: str, folder: str) -> str:
            """Move an email to a folder (inbox/sent/draft/archive/trash/spam)."""
            try:
                result = _email_agent.move_email(email_id, folder)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_delete(email_id: str) -> str:
            """Permanently delete an email."""
            try:
                result = _email_agent.delete_email(email_id)
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_status() -> str:
            """Get email inbox status: unread count and total emails."""
            try:
                import asyncio as _asyncio
                # get_event_loop() fails in the MCP worker thread (no current loop).
                result = _asyncio.run(_email_agent.run({"type": "status"}))
                return _json.dumps(result)
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_check_injection(body: str) -> str:
            """Scan an email body for prompt injection attempts. Returns {is_injection: bool}."""
            try:
                from core.email.ai_security import is_prompt_injection
                result = is_prompt_injection(body)
                return _json.dumps({"is_injection": result})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        @mcp.tool
        def email_verify_draft(body: str) -> str:
            """Verify a draft email body — removes agent artifacts. Returns cleaned body."""
            try:
                from core.email.ai_security import verify_draft
                cleaned = verify_draft(body)
                return _json.dumps({"verified_body": cleaned, "ok": bool(cleaned)})
            except Exception as e:
                return _json.dumps({"error": str(e)})

        logger.info("[VECTOR][mcp] email tools registered (13 tools)")
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] email tools unavailable: {e}")
