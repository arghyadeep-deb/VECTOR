"""Deep bug-hunt for all ported agentic-inbox email modules."""
import base64
import uuid
import datetime
import tempfile
from pathlib import Path


# ── dates.py ──────────────────────────────────────────────────────────────────

def test_dates_none_and_empty():
    from core.email.dates import format_quoted_date
    assert format_quoted_date(None) == ""
    assert format_quoted_date("") == ""


def test_dates_bad_input_returns_original():
    from core.email.dates import format_quoted_date, format_list_date
    assert format_quoted_date("not-a-date") == "not-a-date"
    assert format_list_date("garbage") == "garbage"


def test_dates_valid_iso():
    from core.email.dates import format_list_date, format_detail_date, format_short_date, format_quoted_date
    ts = "2026-05-17T15:42:00Z"
    assert format_list_date(ts) != ""
    assert format_detail_date(ts) != ""
    assert format_short_date(ts) != ""
    q = format_quoted_date(ts)
    assert "2026" in q
    assert "42" in q  # minutes preserved


def test_dates_midnight():
    from core.email.dates import format_quoted_date
    assert format_quoted_date("2026-01-01T00:00:00Z") != ""


# ── search.py ─────────────────────────────────────────────────────────────────

def test_search_from_operator():
    from core.email.search import parse_search_query
    r = parse_search_query("from:alice@x.com invoice")
    assert r.from_addr == "alice@x.com"
    assert r.query == "invoice"


def test_search_quoted_subject():
    from core.email.search import parse_search_query
    r = parse_search_query('subject:"Re: Hello World"')
    assert r.subject == "Re: Hello World"
    assert r.query == ""


def test_search_is_unread():
    from core.email.search import parse_search_query
    r = parse_search_query("is:unread")
    assert r.is_read is False


def test_search_is_read():
    from core.email.search import parse_search_query
    r = parse_search_query("is:read")
    assert r.is_read is True


def test_search_is_starred():
    from core.email.search import parse_search_query
    r = parse_search_query("is:starred")
    assert r.is_starred is True


def test_search_has_attachment():
    from core.email.search import parse_search_query
    r = parse_search_query("has:attachment")
    assert r.has_attachment is True


def test_search_in_folder():
    from core.email.search import parse_search_query
    r = parse_search_query("in:sent payment")
    assert r.folder == "sent"
    assert r.query == "payment"


def test_search_before_after():
    from core.email.search import parse_search_query
    r = parse_search_query("after:2025-01-01 before:2026-01-01")
    assert r.date_start is not None
    assert r.date_end is not None


def test_search_empty():
    from core.email.search import parse_search_query
    r = parse_search_query("")
    assert r.query == ""


def test_search_no_operators():
    from core.email.search import parse_search_query
    r = parse_search_query("hello world")
    assert r.query == "hello world"
    assert r.from_addr is None


# ── helpers.py ────────────────────────────────────────────────────────────────

def test_escape_html_empty():
    from core.email.helpers import escape_html
    assert escape_html("") == ""


def test_escape_html_xss():
    from core.email.helpers import escape_html
    out = escape_html('<script>alert("xss")</script>')
    assert "<" not in out
    assert ">" not in out


def test_escape_html_all_five():
    from core.email.helpers import escape_html
    out = escape_html("& < > \" '")
    assert "&amp;" in out
    assert "&lt;" in out
    assert "&gt;" in out
    assert "&quot;" in out
    assert "&#39;" in out


def test_text_to_html_empty():
    from core.email.helpers import text_to_html
    assert text_to_html("") == ""


def test_text_to_html_newlines():
    from core.email.helpers import text_to_html
    out = text_to_html("line1\nline2")
    assert "<br>" in out
    assert "white-space:pre-wrap" in out


def test_strip_html_empty():
    from core.email.helpers import strip_html_to_text
    assert strip_html_to_text("") == ""


def test_strip_html_removes_tags():
    from core.email.helpers import strip_html_to_text
    assert strip_html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_removes_style_script():
    from core.email.helpers import strip_html_to_text
    assert "color" not in strip_html_to_text("<style>.x{color:red}</style><p>Hi</p>")
    assert "evil" not in strip_html_to_text("<script>evil()</script>text")


def test_validate_sender_ok():
    from core.email.helpers import validate_sender
    v = validate_sender("to@x.com", "me@example.com", "me@example.com")
    assert v["from_email"] == "me@example.com"
    assert v["from_domain"] == "example.com"


def test_validate_sender_mismatch_raises():
    from core.email.helpers import validate_sender, SenderValidationError
    try:
        validate_sender("to@x.com", "other@x.com", "me@x.com")
        assert False, "Should have raised"
    except SenderValidationError:
        pass


def test_validate_sender_bad_email_raises():
    from core.email.helpers import validate_sender, SenderValidationError
    try:
        validate_sender("to@x.com", "noemail", "noemail")
        assert False, "Should have raised"
    except SenderValidationError:
        pass


def test_generate_message_id():
    from core.email.helpers import generate_message_id
    m = generate_message_id("example.com")
    assert "@example.com" in m["outgoing_message_id"]
    assert len(m["message_id"]) == 36


def test_build_references_chain_normal():
    from core.email.helpers import build_references_chain
    orig = {"id": "abc", "message_id": "msg001", "email_references": '["ref1"]', "thread_id": "thr1"}
    chain = build_references_chain(orig)
    assert chain["original_msg_id"] == "msg001"
    assert "ref1" in chain["references"]
    assert "msg001" in chain["references"]
    assert chain["thread_id"] == "thr1"


def test_build_references_chain_malformed_json():
    from core.email.helpers import build_references_chain
    orig = {"id": "abc", "message_id": "msg002", "email_references": "not-json"}
    chain = build_references_chain(orig)
    assert chain["references"] == ["msg002"]


def test_build_references_chain_no_message_id():
    from core.email.helpers import build_references_chain
    orig = {"id": "fallback-id"}
    chain = build_references_chain(orig)
    assert chain["original_msg_id"] == "fallback-id"


def test_build_threading_headers_with_refs():
    from core.email.helpers import build_threading_headers
    h = build_threading_headers("msg001", ["ref1", "ref2"])
    assert h["In-Reply-To"] == "<msg001>"
    assert "<ref1>" in h["References"]
    assert "<ref2>" in h["References"]


def test_build_threading_headers_empty_refs():
    from core.email.helpers import build_threading_headers
    h = build_threading_headers("msg001", [])
    assert "References" not in h


def test_build_quoted_reply_block_normal():
    from core.email.helpers import build_quoted_reply_block
    block = build_quoted_reply_block({"body": "<p>Hi</p>", "sender": "alice@x.com", "date": "2026-05-17T12:00:00Z"})
    assert "blockquote" in block
    assert "alice@x.com" in block


def test_build_quoted_reply_block_empty_body():
    from core.email.helpers import build_quoted_reply_block
    assert build_quoted_reply_block({"body": "", "sender": "x"}) == ""


def test_build_quoted_reply_block_xss_prevention():
    from core.email.helpers import build_quoted_reply_block
    block = build_quoted_reply_block({"body": "<script>evil()</script>", "sender": "<bad>", "date": ""})
    assert "<script>" not in block
    assert "<bad>" not in block


# ── attachments.py ───────────────────────────────────────────────────────────

def test_attachments_store_normal():
    from core.email.attachments import store_attachments, get_attachment_path
    content = base64.b64encode(b"hello world").decode()
    stored = store_attachments("email-att-001", [{"content": content, "filename": "test.txt", "type": "text/plain", "disposition": "attachment"}])
    assert len(stored) == 1
    assert stored[0].size == len(b"hello world")
    assert stored[0].filename == "test.txt"
    path = get_attachment_path("email-att-001", stored[0].id, stored[0].filename)
    assert path.read_bytes() == b"hello world"


def test_attachments_empty():
    from core.email.attachments import store_attachments
    assert store_attachments("x", None) == []
    assert store_attachments("x", []) == []


def test_attachments_path_traversal_sanitized():
    from core.email.attachments import store_attachments
    content = base64.b64encode(b"x").decode()
    stored = store_attachments("email-evil-001", [{"content": content, "filename": "../../../evil.sh", "type": "text/plain", "disposition": "attachment"}])
    assert ".." not in stored[0].filename
    assert "/" not in stored[0].filename
    assert "\\" not in stored[0].filename


def test_attachments_content_id_preserved():
    from core.email.attachments import store_attachments
    content = base64.b64encode(b"img").decode()
    stored = store_attachments("email-img-001", [{"content": content, "filename": "img.png", "type": "image/png", "disposition": "inline", "contentId": "img001@x.com"}])
    assert stored[0].content_id == "img001@x.com"
    assert stored[0].disposition == "inline"


# ── sender.py ─────────────────────────────────────────────────────────────────

def test_sender_no_smtp():
    from core.email.sender import send_email, SendEmailParams
    p = SendEmailParams(to="dest@x.com", from_addr={"email": "me@x.com", "name": "VECTOR"}, subject="Test", text="Hello")
    result = send_email(p)
    assert "message_id" in result
    # Regression: this used to return the same {"message_id": ...} shape as
    # a genuinely delivered email (phantom success) -- status distinguishes
    # "queued locally, not sent" from a real send without breaking the
    # documented dev-mode fallback (no SMTP configured -> log + queue, never crash).
    assert result.get("status") == "queued_locally", result


def test_sender_list_recipients():
    from core.email.sender import send_email, SendEmailParams
    p = SendEmailParams(to=["a@x.com", "b@x.com"], from_addr="me@x.com", subject="S", html="<p>Hi</p>")
    result = send_email(p)
    assert "message_id" in result


# ── ui_helpers.py ─────────────────────────────────────────────────────────────

def test_format_bytes():
    from core.email.ui_helpers import format_bytes
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert format_bytes(1073741824) == "1.0 GB"
    assert format_bytes(1536) == "1.5 KB"


def test_get_snippet_text_none():
    from core.email.ui_helpers import get_snippet_text
    assert get_snippet_text(None) == ""
    assert get_snippet_text("") == ""


def test_get_snippet_text_html():
    from core.email.ui_helpers import get_snippet_text
    assert get_snippet_text("<p>Hello world</p>") == "Hello world"


def test_get_snippet_text_truncates():
    from core.email.ui_helpers import get_snippet_text
    long_text = "A" * 200
    result = get_snippet_text(long_text, max_length=100)
    assert result.endswith("...")
    assert len(result) == 103


def test_split_email_list():
    from core.email.ui_helpers import split_email_list
    assert split_email_list(None) == []
    assert split_email_list("a@x.com, b@x.com") == ["a@x.com", "b@x.com"]
    assert split_email_list("  a@x.com  ") == ["a@x.com"]


def test_ui_build_quoted_reply_block_empty():
    from core.email.ui_helpers import build_quoted_reply_block
    assert build_quoted_reply_block("2026-05-17T12:00:00Z", "alice@x.com", "") == ""


def test_ui_build_quoted_reply_block_xss():
    from core.email.ui_helpers import build_quoted_reply_block
    block = build_quoted_reply_block("2026-05-17T12:00:00Z", "<bad>", "<script>x</script>")
    assert "<bad>" not in block
    assert "<script>" not in block


# ── schema.py ────────────────────────────────────────────────────────────────

def test_schema_creates_tables():
    from core.email.schema import init_schema, get_connection
    db = Path(tempfile.mktemp(suffix=".db"))
    try:
        init_schema(db)
        conn = get_connection(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "emails" in tables
        assert "attachments" in tables
        assert "folders" in tables
        folders = {r[0] for r in conn.execute("SELECT id FROM folders").fetchall()}
        for f in ("inbox", "sent", "draft", "archive", "trash", "spam"):
            assert f in folders, f"Missing folder: {f}"
        conn.close()
    finally:
        db.unlink(missing_ok=True)


def test_schema_idempotent():
    from core.email.schema import init_schema, get_connection
    db = Path(tempfile.mktemp(suffix=".db"))
    try:
        init_schema(db)
        init_schema(db)  # second call must not crash
        conn = get_connection(db)
        count = conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
        assert count == 6
        conn.close()
    finally:
        db.unlink(missing_ok=True)


# ── email_agent.py ────────────────────────────────────────────────────────────

def test_email_agent_store_and_list():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("alice@x.com", "Test Subject", "<p>Body</p>")
    emails = agent.list_emails("inbox")
    assert any(e["id"] == eid for e in emails)


def test_email_agent_get_email():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("bob@x.com", "Get Test", "body")
    email = agent.get_email(eid)
    assert email is not None
    assert email["sender"] == "bob@x.com"


def test_email_agent_get_nonexistent():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    assert agent.get_email("nonexistent-uuid") is None


def test_email_agent_search_plain():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("charlie@x.com", "Invoice March", "pay now")
    results = agent.search_emails("Invoice")
    assert any(e["id"] == eid for e in results)


def test_email_agent_search_from_operator():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("dave@x.com", "From test", "body")
    results = agent.search_emails("from:dave@x.com")
    assert any(e["id"] == eid for e in results)


def test_email_agent_search_is_unread():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("eve@x.com", "Unread Test", "body")
    results = agent.search_emails("is:unread")
    assert any(e["id"] == eid for e in results)


def test_email_agent_search_is_read_after_mark():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("frank@x.com", "Read Test", "body")
    agent.mark_email_read(eid, True)
    results = agent.search_emails("is:read")
    assert any(e["id"] == eid for e in results)


def test_email_agent_draft_reply():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("grace@x.com", "Draft test", "hello")
    result = agent.draft_reply(eid, "grace@x.com", "Re: Draft test", "Thanks!")
    assert result.get("status") == "draft_saved"
    assert "draftId" in result


def test_email_agent_discard_draft():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("hank@x.com", "Discard test", "body")
    draft = agent.draft_reply(eid, "hank@x.com", "Re: Discard test", "Draft text")
    result = agent.discard_draft(draft["draftId"])
    assert result.get("status") == "discarded"


def test_email_agent_discard_nonexistent():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    result = agent.discard_draft("no-such-id")
    assert "error" in result


def test_email_agent_move_email():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("ivan@x.com", "Move test", "body")
    result = agent.move_email(eid, "archive")
    assert result.get("status") == "moved"
    email = agent.get_email(eid)
    assert email["folder_id"] == "archive"


def test_email_agent_move_invalid_folder():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("judy@x.com", "Move invalid", "body")
    result = agent.move_email(eid, "nonexistent_folder")
    assert "error" in result


def test_email_agent_delete_email():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("kelly@x.com", "Delete test", "body")
    result = agent.delete_email(eid)
    assert result.get("status") == "deleted"
    assert agent.get_email(eid) is None


def test_email_agent_delete_nonexistent():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    result = agent.delete_email("no-such-id")
    assert "error" in result


def test_email_agent_get_thread():
    from districts.communications.email_agent import EmailAgent
    agent = EmailAgent()
    eid = agent.store_incoming_email("liam@x.com", "Thread test", "body")
    thread = agent.get_thread(eid)
    assert len(thread) >= 1


# ── reply_forward.py ─────────────────────────────────────────────────────────

def test_reply_forward_reply():
    from core.email.schema import get_connection, EMAIL_DB_PATH, init_schema
    from districts.communications.reply_forward import handle_reply_email
    init_schema()
    conn = get_connection()
    seed_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id,message_id,read) VALUES(?,?,?,?,?,?,?,?,?,0)",
        (seed_id, "inbox", "Original", "bob@x.com", "me@x.com", datetime.datetime.now().isoformat(), "body", seed_id, seed_id)
    )
    conn.commit()
    conn.close()
    # SMTP is not configured in this environment (real CONFIG.get("SMTP_HOST", "")
    # is "" here, not just a test artifact), so send_email() takes its
    # documented dev-mode fallback path -- this correctly reports the reply
    # was NOT actually sent (previously asserted "sent", the exact
    # phantom-success bug this cycle's audit found and fixed).
    result = handle_reply_email(
        mailbox_id="me@x.com", original_id=seed_id,
        to="bob@x.com", from_addr="me@x.com",
        subject="Re: Original", text="Thanks!"
    )
    assert result.get("status") == 502 and "error" in result, result


def test_reply_forward_forward():
    from core.email.schema import get_connection, init_schema
    from districts.communications.reply_forward import handle_forward_email
    init_schema()
    conn = get_connection()
    seed_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id,message_id,read) VALUES(?,?,?,?,?,?,?,?,?,0)",
        (seed_id, "inbox", "FwdOrig", "carol@x.com", "me@x.com", datetime.datetime.now().isoformat(), "fwd body", seed_id, seed_id)
    )
    conn.commit()
    conn.close()
    # Same reasoning as test_reply_forward_reply(): no SMTP configured here.
    result = handle_forward_email(
        mailbox_id="me@x.com", original_id=seed_id,
        to="dan@x.com", from_addr="me@x.com",
        subject="Fwd: FwdOrig", text="See below."
    )
    assert result.get("status") == 502 and "error" in result, result


def test_reply_forward_missing_original():
    from districts.communications.reply_forward import handle_reply_email
    result = handle_reply_email(
        mailbox_id="me@x.com", original_id="nonexistent-id",
        to="x@x.com", from_addr="me@x.com", subject="S"
    )
    assert result.get("status") == 404 or "error" in result


def test_reply_forward_sender_mismatch():
    from core.email.schema import get_connection, init_schema
    from districts.communications.reply_forward import handle_reply_email
    init_schema()
    conn = get_connection()
    seed_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id,message_id,read) VALUES(?,?,?,?,?,?,?,?,?,0)",
        (seed_id, "inbox", "Mismatch", "x@x.com", "me@x.com", datetime.datetime.now().isoformat(), "body", seed_id, seed_id)
    )
    conn.commit()
    conn.close()
    result = handle_reply_email(
        mailbox_id="me@x.com", original_id=seed_id,
        to="x@x.com", from_addr="wrong@x.com",  # mismatch
        subject="Re: Mismatch"
    )
    assert result.get("status") == 400 or "error" in result
