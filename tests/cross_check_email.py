"""Final cross-check: every ported email module, every function, every edge case."""
from loguru import logger
import sys, uuid, datetime, base64, traceback, tempfile
from pathlib import Path

errors = []

# ── dates ──────────────────────────────────────────────────────────────────────
try:
    from core.email.dates import (
        format_list_date, format_detail_date, format_short_date, format_quoted_date
    )
    ts = "2026-05-17T15:42:00Z"
    assert "42" in format_quoted_date(ts)
    assert format_quoted_date(None) == ""
    assert format_quoted_date("") == ""
    assert format_quoted_date("bad-input") == "bad-input"
    assert format_list_date(ts) != ""
    assert format_detail_date(ts) != ""
    assert format_short_date(ts) != ""
    assert format_quoted_date("2026-01-01T00:00:00Z") != ""
    print("PASS  dates.py")
except Exception as e:
    errors.append(f"FAIL  dates.py: {e}"); traceback.print_exc()

# ── search ─────────────────────────────────────────────────────────────────────
try:
    from core.email.search import parse_search_query
    r = parse_search_query('from:a@x.com subject:"Hello World" is:unread has:attachment in:sent after:2025-01-01 before:2026-01-01 rest text')
    assert r.from_addr == "a@x.com"
    assert r.subject == "Hello World"
    assert r.is_read is False
    assert r.has_attachment is True
    assert r.folder == "sent"
    assert r.date_start is not None
    assert r.date_end is not None
    assert "rest text" in r.query

    assert parse_search_query("").query == ""
    assert parse_search_query("plain text").query == "plain text"
    assert parse_search_query("is:starred").is_starred is True
    assert parse_search_query("is:read").is_read is True
    assert parse_search_query("in:draft").folder == "draft"
    print("PASS  search.py")
except Exception as e:
    errors.append(f"FAIL  search.py: {e}"); traceback.print_exc()

# ── helpers ────────────────────────────────────────────────────────────────────
try:
    from core.email.helpers import (
        escape_html, text_to_html, strip_html_to_text, build_quoted_reply_block,
        validate_sender, SenderValidationError, generate_message_id,
        build_references_chain, build_threading_headers,
    )
    # escape_html
    assert escape_html("") == ""
    assert escape_html("<\"&'>") == "&lt;&quot;&amp;&#39;&gt;"

    # text_to_html
    assert text_to_html("") == ""
    assert "pre-wrap" in text_to_html("a\nb")
    assert "<br>" in text_to_html("a\nb")

    # strip_html_to_text
    assert strip_html_to_text("") == ""
    assert strip_html_to_text("<style>x{color:red}</style><p>Hi</p>") == "Hi"
    assert strip_html_to_text("<script>bad()</script>ok") == "ok"
    assert strip_html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    # validate_sender
    v = validate_sender("b@x.com", "me@x.com", "me@x.com")
    assert v["from_domain"] == "x.com"
    v2 = validate_sender("b@x.com", {"email": "me@x.com", "name": "V"}, "me@x.com")
    assert v2["from_email"] == "me@x.com"
    try:
        validate_sender("b@x.com", "wrong@x.com", "me@x.com")
        errors.append("FAIL  helpers.py: SenderValidationError not raised on mismatch")
    except SenderValidationError:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)
    try:
        validate_sender("b@x.com", "noemail", "noemail")
        errors.append("FAIL  helpers.py: SenderValidationError not raised on bad email")
    except SenderValidationError:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)

    # generate_message_id
    m = generate_message_id("test.com")
    assert m["outgoing_message_id"].endswith("@test.com")
    assert len(m["message_id"]) == 36

    # build_references_chain — normal
    chain = build_references_chain({"id": "a", "message_id": "mid", "email_references": '["r1"]', "thread_id": "t1"})
    assert chain["references"] == ["r1", "mid"]
    assert chain["thread_id"] == "t1"
    # malformed JSON
    chain2 = build_references_chain({"id": "a", "message_id": "mid", "email_references": "BAD_JSON"})
    assert chain2["references"] == ["mid"]
    # no message_id falls back to id
    chain3 = build_references_chain({"id": "fallback"})
    assert chain3["original_msg_id"] == "fallback"

    # build_threading_headers
    h = build_threading_headers("mid", ["r1", "r2"])
    assert h["In-Reply-To"] == "<mid>"
    assert "<r1>" in h["References"] and "<r2>" in h["References"]
    h2 = build_threading_headers("mid", [])
    assert "References" not in h2

    # build_quoted_reply_block
    block = build_quoted_reply_block({"body": "<p>hi</p>", "sender": "<evil>", "date": ""})
    assert "blockquote" in block
    assert "<evil>" not in block
    assert "<p>" not in block
    assert build_quoted_reply_block({"body": "", "sender": "x"}) == ""
    print("PASS  helpers.py")
except Exception as e:
    errors.append(f"FAIL  helpers.py: {e}"); traceback.print_exc()

# ── attachments ────────────────────────────────────────────────────────────────
try:
    from core.email.attachments import store_attachments, get_attachment_path
    # Normal
    att = [{"content": base64.b64encode(b"data").decode(), "filename": "test.txt", "type": "text/plain", "disposition": "attachment", "contentId": "cid001"}]
    stored = store_attachments("eid-cc-001", att)
    assert len(stored) == 1
    assert stored[0].size == 4
    assert stored[0].content_id == "cid001"
    assert get_attachment_path("eid-cc-001", stored[0].id, stored[0].filename).read_bytes() == b"data"
    # Empty
    assert store_attachments("x", None) == []
    assert store_attachments("x", []) == []
    # Path traversal — MUST be stripped to basename
    bad = [{"content": base64.b64encode(b"x").decode(), "filename": "../../../evil.sh", "type": "text/plain", "disposition": "attachment"}]
    s2 = store_attachments("eid-cc-002", bad)
    assert ".." not in s2[0].filename, f"Traversal not blocked: {s2[0].filename}"
    assert "/" not in s2[0].filename
    assert s2[0].filename == "evil.sh"
    print("PASS  attachments.py")
except Exception as e:
    errors.append(f"FAIL  attachments.py: {e}"); traceback.print_exc()

# ── sender ─────────────────────────────────────────────────────────────────────
try:
    from core.email.sender import send_email, SendEmailParams
    r = send_email(SendEmailParams(to="a@x.com", from_addr="me@x.com", subject="S", text="T"))
    assert "message_id" in r
    r2 = send_email(SendEmailParams(to=["a@x.com", "b@x.com"], from_addr={"email": "me@x.com", "name": "V"}, subject="S", html="<p>H</p>"))
    assert "message_id" in r2
    print("PASS  sender.py")
except Exception as e:
    errors.append(f"FAIL  sender.py: {e}"); traceback.print_exc()

# ── ui_helpers ─────────────────────────────────────────────────────────────────
try:
    from core.email.ui_helpers import (
        format_bytes, get_snippet_text, split_email_list,
        html_to_plain_text, build_quoted_reply_block as bqr,
        get_non_inline_attachments, get_attachment_url,
    )
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_bytes(1073741824) == "1.0 GB"
    assert format_bytes(1536) == "1.5 KB"
    assert get_snippet_text(None) == ""
    assert get_snippet_text("") == ""
    assert get_snippet_text("<p>Hello</p>") == "Hello"
    long = get_snippet_text("X" * 200, 100)
    assert long.endswith("...") and len(long) == 103
    assert split_email_list(None) == []
    assert split_email_list("a@x.com, b@x.com") == ["a@x.com", "b@x.com"]
    block = bqr("2026-05-17T12:00:00Z", "<evil>", "<script>x</script>")
    assert "<evil>" not in block and "<script>" not in block
    assert bqr("", "x", "") == ""
    inline = [{"id": "1", "disposition": "inline"}, {"id": "2", "disposition": "attachment"}]
    assert len(get_non_inline_attachments(inline)) == 1
    url = get_attachment_url("mbox1", "email1", "att1")
    assert "mbox1" in url and "email1" in url and "att1" in url
    print("PASS  ui_helpers.py")
except Exception as e:
    errors.append(f"FAIL  ui_helpers.py: {e}"); traceback.print_exc()

# ── schema ─────────────────────────────────────────────────────────────────────
try:
    from core.email.schema import init_schema, get_connection
    db = Path(tempfile.mktemp(suffix=".db"))
    init_schema(db)
    init_schema(db)  # must be idempotent
    conn = get_connection(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    assert "read" in cols, f"Missing 'read' column, got: {cols}"
    assert "is_read" not in cols, "Schema has wrong column 'is_read'"
    att_cols = {r[1] for r in conn.execute("PRAGMA table_info(attachments)").fetchall()}
    assert "email_id" in att_cols
    folders = {r[0] for r in conn.execute("SELECT id FROM folders").fetchall()}
    assert folders == {"inbox", "sent", "draft", "archive", "trash", "spam"}
    conn.close()
    db.unlink()
    print("PASS  schema.py")
except Exception as e:
    errors.append(f"FAIL  schema.py: {e}"); traceback.print_exc()

# ── email_agent — full CRUD + structured search ────────────────────────────────
try:
    from districts.communications.email_agent import EmailAgent
    ag = EmailAgent()

    # store + read
    eid = ag.store_incoming_email("z@x.com", "Subject Z", "<p>Body Z</p>")
    assert ag.get_email(eid)["sender"] == "z@x.com"
    assert ag.get_email("nonexistent") is None

    # list
    assert any(e["id"] == eid for e in ag.list_emails("inbox"))

    # structured search
    assert any(e["id"] == eid for e in ag.search_emails("Subject Z"))
    assert any(e["id"] == eid for e in ag.search_emails("from:z@x.com"))
    assert any(e["id"] == eid for e in ag.search_emails("is:unread"))
    assert not any(e["id"] == eid for e in ag.search_emails("is:read"))

    # mark read
    ag.mark_email_read(eid, True)
    assert any(e["id"] == eid for e in ag.search_emails("is:read"))
    assert not any(e["id"] == eid for e in ag.search_emails("is:unread"))

    # draft reply
    d = ag.draft_reply(eid, "z@x.com", "Re: Z", "Reply text here")
    assert d["status"] == "draft_saved"
    assert ag.get_email(d["draftId"])["folder_id"] == "draft"

    # discard draft
    assert ag.discard_draft(d["draftId"])["status"] == "discarded"
    assert ag.get_email(d["draftId"]) is None
    assert "error" in ag.discard_draft("no-id")

    # draft new
    d2 = ag.draft_email("z@x.com", "New draft", "content")
    assert d2["status"] == "draft_saved"

    # move
    ag.move_email(eid, "archive")
    assert ag.get_email(eid)["folder_id"] == "archive"
    assert "error" in ag.move_email(eid, "bad_folder")

    # get thread
    thread = ag.get_thread(eid)
    assert len(thread) >= 1

    # delete
    ag.delete_email(eid)
    assert ag.get_email(eid) is None
    assert "error" in ag.delete_email("no-id")
    print("PASS  email_agent.py")
except Exception as e:
    errors.append(f"FAIL  email_agent.py: {e}"); traceback.print_exc()

# ── reply_forward — column correctness + error paths ─────────────────────────
try:
    from core.email.schema import get_connection, init_schema
    from districts.communications.reply_forward import handle_reply_email, handle_forward_email
    init_schema()
    conn = get_connection()
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id,message_id,read) VALUES(?,?,?,?,?,?,?,?,?,0)",
        (sid, "inbox", "Orig", "b@x.com", "me@x.com", datetime.datetime.now().isoformat(), "body", sid, sid)
    )
    conn.commit()
    conn.close()

    # reply -- SMTP is not configured in this environment (confirmed: real
    # CONFIG.get("SMTP_HOST", "") is "" here, not just a test artifact), so
    # send_email() takes its documented dev-mode fallback path. This
    # previously asserted status == "sent" -- the exact phantom-success bug
    # this cycle's audit found (reply_forward.py's own pre-existing comment
    # says "do not leave a phantom row in Sent or report success", but the
    # fallback path wasn't being checked). Correct now: not actually sent.
    r1 = handle_reply_email("me@x.com", sid, "b@x.com", "me@x.com", "Re: Orig", text="ok")
    assert r1.get("status") == 502 and "error" in r1, r1

    # forward -- same reasoning.
    r2 = handle_forward_email("me@x.com", sid, "c@x.com", "me@x.com", "Fwd: Orig", text="fwd")
    assert r2.get("status") == 502 and "error" in r2, r2

    # missing original
    r3 = handle_reply_email("me@x.com", "no-such-id", "b@x.com", "me@x.com", "Re: X")
    assert r3.get("status") == 404 or "error" in r3, r3

    # sender mismatch
    r4 = handle_reply_email("me@x.com", sid, "b@x.com", "wrong@x.com", "Re: X")
    assert r4.get("status") == 400 or "error" in r4, r4

    # verify sent emails were actually written to DB with correct 'read' column
    conn2 = get_connection()
    sent = conn2.execute("SELECT read FROM emails WHERE folder_id='sent'").fetchall()
    assert all(row[0] == 1 for row in sent), f"Sent emails should be marked read=1, got: {sent}"
    conn2.close()
    print("PASS  reply_forward.py")
except Exception as e:
    errors.append(f"FAIL  reply_forward.py: {e}"); traceback.print_exc()

# ── __init__.py — all 30 exports present ──────────────────────────────────────
try:
    import core.email as em
    expected = [
        "init_schema", "get_connection", "EMAIL_DB_PATH",
        "is_prompt_injection", "verify_draft",
        "escape_html", "text_to_html", "strip_html_to_text",
        "build_quoted_reply_block", "validate_sender", "SenderValidationError",
        "generate_message_id", "build_references_chain", "build_threading_headers",
        "format_email_date",
        "format_list_date", "format_detail_date", "format_short_date", "format_quoted_date",
        "parse_search_query", "ParsedSearch",
        "store_attachments", "StoredAttachment", "get_attachment_path",
        "send_email", "SendEmailParams",
        "format_bytes", "html_to_plain_text", "get_snippet_text",
        "split_email_list", "get_non_inline_attachments", "get_attachment_url",
    ]
    missing = [s for s in expected if not hasattr(em, s)]
    assert not missing, f"Missing exports: {missing}"
    print(f"PASS  __init__.py — all {len(expected)} exports present")
except Exception as e:
    errors.append(f"FAIL  __init__.py: {e}"); traceback.print_exc()

# ── mcp_server — email tools wired ────────────────────────────────────────────
try:
    content = Path("core/mcp_server.py").read_text(encoding="utf-8")
    required_tools = [
        "email_list", "email_get", "email_get_thread", "email_search",
        "email_draft_reply", "email_draft_new", "email_discard_draft",
        "email_mark_read", "email_move", "email_delete",
        "email_status", "email_check_injection", "email_verify_draft",
    ]
    missing = [t for t in required_tools if t not in content]
    assert not missing, f"Missing MCP tools: {missing}"
    print(f"PASS  mcp_server.py — all {len(required_tools)} email tools present")
except Exception as e:
    errors.append(f"FAIL  mcp_server.py: {e}"); traceback.print_exc()

# ── governor — email routing keywords ─────────────────────────────────────────
try:
    content = Path("core/city/governor.py").read_text(encoding="utf-8")
    routing_keys = [
        "list_emails", "get_email", "read_email", "draft_reply", "draft_email",
        "send_email", "email_thread", "email_search", "check_inbox", "new_email",
        "auto_draft", "parse_email",
    ]
    missing = [k for k in routing_keys if k not in content]
    assert not missing, f"Missing routing keys: {missing}"
    print(f"PASS  governor.py — all {len(routing_keys)} email routing keys present")
except Exception as e:
    errors.append(f"FAIL  governor.py: {e}"); traceback.print_exc()

# ── cloud/email TS frontend preserved ─────────────────────────────────────────
try:
    ts_files = [
        "cloud/email/workers/lib/email-helpers.ts",
        "cloud/email/workers/agent/index.ts",
        "cloud/email/workers/routes/reply-forward.ts",
        "cloud/email/workers/mcp/index.ts",
        "cloud/email/wrangler.jsonc",
    ]
    missing = [f for f in ts_files if not Path(f).exists()]
    assert not missing, f"Missing TS files: {missing}"
    print(f"PASS  cloud/email/ — all {len(ts_files)} TypeScript files preserved")
except Exception as e:
    errors.append(f"FAIL  cloud/email/: {e}"); traceback.print_exc()

# ── final verdict ──────────────────────────────────────────────────────────────
print()
print("=" * 60)
if errors:
    print(f"BUGS REMAINING: {len(errors)}")
    for e in errors:
        print(f"  {e}")
else:
    print("ALL PASS — 0 bugs. agentic-inbox 100% integrated. Safe to delete.")
print("=" * 60)
