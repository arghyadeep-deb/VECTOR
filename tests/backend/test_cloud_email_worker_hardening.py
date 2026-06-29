from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _after(source: str, needle: str) -> str:
    index = source.index(needle)
    return source[index:]


def test_mailbox_delete_purges_durable_object_and_r2_attachments() -> None:
    source = _after(
        _read("cloud/email/workers/index.ts"),
        'app.delete("/api/v1/mailboxes/:mailboxId"',
    )
    handler = source[: source.index("// -- Emails")]

    list_pos = handler.index("listAttachmentKeys()")
    r2_pos = handler.index("BUCKET.delete(attachmentKeys)")
    purge_pos = handler.index("purgeMailboxData()")
    settings_pos = handler.index("BUCKET.delete(key)")

    assert list_pos < r2_pos < purge_pos < settings_pos


def test_mailbox_durable_object_exposes_full_purge_helpers() -> None:
    source = _read("cloud/email/workers/durableObject/index.ts")

    assert "async listAttachmentKeys(): Promise<string[]>" in source
    assert "`SELECT email_id, id, filename FROM attachments`" in source
    assert "async purgeMailboxData()" in source
    assert "DELETE FROM attachments" in source
    assert "DELETE FROM emails" in source
    assert "DELETE FROM folders" in source
    assert "FOLDER_DISPLAY_NAMES[id]" in source


def test_draft_replacement_creates_new_draft_before_deleting_old_one() -> None:
    source = _after(
        _read("cloud/email/workers/index.ts"),
        'app.post("/api/v1/mailboxes/:mailboxId/drafts"',
    )
    handler = source[: source.index('app.get("/api/v1/mailboxes/:mailboxId/emails/:id"')]

    create_pos = handler.index("stub.createEmail(Folders.DRAFT")
    delete_pos = handler.index("stub.deleteEmail(draft_id)")

    assert create_pos < delete_pos


def test_agent_update_draft_creates_new_draft_before_deleting_old_one() -> None:
    source = _after(
        _read("cloud/email/workers/lib/tools.ts"),
        "export async function toolUpdateDraft",
    )
    handler = source[: source.index("export async function toolMarkEmailRead")]

    create_pos = handler.index("stub.createEmail(")
    delete_pos = handler.index("stub.deleteEmail(params.draftId)")

    assert create_pos < delete_pos
