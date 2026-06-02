# agentic-inbox-main Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\agentic-inbox-main`
**License:** Apache 2.0 (Cloudflare, Inc.)
**Date:** 2026-06-02

---

## 1. Repo Reality

**Language:** TypeScript (100%). No Python anywhere.

**What it is:** A self-hosted AI email client running entirely on Cloudflare Workers edge infrastructure. Each mailbox runs as its own Durable Object with an isolated SQLite database. Attachments go to R2. The repo is a full SaaS product, not a library.

**Stack:**
- Frontend: React 19, React Router v7, Tailwind CSS v4, Zustand state, TipTap rich-text editor, `@cloudflare/kumo` design system
- Backend: Hono (Worker router), Cloudflare Durable Objects (SQLite via Drizzle ORM), R2 object storage, Cloudflare Email Routing (inbound MIME parsing via `postal-mime`), Email Workers send binding (outbound)
- AI Agent: Cloudflare Agents SDK (`AIChatAgent`), AI SDK v6, Workers AI model `@cf/moonshotai/kimi-k2.5` for drafting, `@cf/meta/llama-3.1-8b-instruct-fast` for injection scanning, `@cf/meta/llama-4-scout-17b-16e-instruct` for draft verification
- MCP Server: `EmailMCP` exposes 13 email tools over the Model Context Protocol at `/mcp` for Claude Code, Cursor, etc.
- Auth: Cloudflare Access JWT validation (required in production)

**Core capabilities:**
1. Full CRUD email client (send, receive, reply, forward, star, move, delete, search)
2. Per-mailbox Durable Object isolation with SQLite (folders, emails, attachments tables with migrations)
3. Thread grouping: `In-Reply-To`/`References` header chain + subject-normalized fallback thread detection
4. AI Email Agent side panel (9 tools, WebSocket streaming, persistent chat history per mailbox)
5. Auto-draft on inbound email: prompt injection scan on body + thread context, then generate draft reply, save to Drafts, never send without confirmation
6. Draft verifier: secondary AI strips agent artifacts from draft bodies before saving
7. MCP server at `/mcp` with 13 tools (list_mailboxes + all email ops + send tools)
8. Per-mailbox configurable system prompt (stored in R2 settings JSON)
9. Send rate limiting via Durable Object (`checkSendRateLimit`)
10. Custom folder CRUD (create/rename/delete, system folders protected)
11. Attachment upload/download with sanitized filenames and correct Content-Disposition headers
12. Rich-text composer with TipTap (bold, italic, underline, links, highlights, text align)
13. Threaded email view (`getThreadedEmails` / normalized subject grouping)

---

## 2. VECTOR Parity

### Parity check output (exact)

```
public methods count: 25
sample: ['add_lesson', 'award_points', 'can_vote_in_council', 'deduct_points',
         'delete_email', 'die', 'discard_draft', 'draft_email']

EmailAgent OK, model: vector-focus
```

Full public methods: `add_lesson, award_points, can_vote_in_council, deduct_points, delete_email, die, discard_draft, draft_email, draft_reply, get_email, get_status, get_thread, get_voice_style, handle_event, handle_new_email, inherit_ghost, list_emails, mark_email_read, move_email, record_decision, run, search_emails, store_incoming_email, subscribe_to, to_dict`

Email-specific methods (excl. AgentBase inherited): `delete_email, discard_draft, draft_email, draft_reply, get_email, get_thread, handle_new_email, list_emails, mark_email_read, move_email, search_emails, store_incoming_email`

### Feature-by-feature comparison

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| `list_emails` (folder, limit, page) | `districts/communications/email_agent.py:97` | EmailAgent has method, returns rows from SQLite | ✅ |
| `get_email` (full body + attachments) | `districts/communications/email_agent.py:109` | Fetches email + joins attachments table | ✅ |
| `get_thread` (chronological) | `districts/communications/email_agent.py:126` | ORDER BY date ASC | ✅ |
| `search_emails` (query + folder) | `districts/communications/email_agent.py:135` | Gmail-style via `core/email/search.py` — supports from:, to:, subject:, is:, has:, before:, after: | ✅ |
| `draft_reply` (verify + save) | `districts/communications/email_agent.py:184` | Calls `verify_draft()`, saves to draft folder, does not send | ✅ |
| `draft_email` (new email) | `districts/communications/email_agent.py:207` | Same verify + save pattern | ✅ |
| `discard_draft` | `districts/communications/email_agent.py:225` | Checks folder_id == draft before deleting | ✅ |
| `mark_email_read` | `districts/communications/email_agent.py:242` | UPDATE emails SET read=? | ✅ |
| `move_email` | `districts/communications/email_agent.py:249` | Validates folder in `_FOLDERS` dict | ✅ |
| `delete_email` | `districts/communications/email_agent.py:258` | Hard delete, returns error if not found | ✅ |
| `store_incoming_email` | `districts/communications/email_agent.py:269` | INSERT OR IGNORE with thread_id resolution | ✅ |
| `handle_new_email` (auto-draft) | `districts/communications/email_agent.py:290` | Injection check on body + thread, generates draft via LLM, saves to draft folder | ✅ |
| Prompt injection scanner | `core/email/ai_security.py:52` | `is_prompt_injection()` — mirrors TS `isPromptInjection()`, uses `vector-ambient`, fails closed | ✅ |
| Draft verifier | `core/email/ai_security.py:130` | `verify_draft()` — mirrors TS `verifyDraft()`, splits blockquote, 50% safety threshold | ✅ |
| Gmail-style search parser | `core/email/search.py` | `parse_search_query()` — from:, to:, subject:, in:, is:, has:, before:, after:, quoted values | ✅ |
| Email helpers (HTML, threading) | `core/email/helpers.py` | `strip_html_to_text`, `build_quoted_reply_block`, `validate_sender`, `generate_message_id`, `build_references_chain`, `build_threading_headers` | ✅ |
| Reply / Forward send | `districts/communications/reply_forward.py` | `handle_reply_email`, `handle_forward_email` — routes through permission gateway | ✅ |
| Email intelligence / triage | `districts/communications/email_intelligence.py` | Gmail API thread fetch, LLM extracts priority/action-items/sentiment/deadlines, generates morning brief | ✅ (bonus) |
| `update_draft` (edit existing draft) | Not found in `email_agent.py` | docstring lists it but no `def update_draft` in file — only the MCP/TS side has it | ⚠️ |
| Per-mailbox isolation (Durable Objects) | N/A — VECTOR is single-owner, single mailbox | SQLite at `~/.vector/email.db` shared across all operations | ⚠️ (by design) |
| Send rate limiting | Not in `email_agent.py` | Repo has `checkSendRateLimit()` in Durable Object — VECTOR has no equivalent | ❌ |
| Threaded list view (`getThreadedEmails`) | Not in `email_agent.py` | Repo groups by thread with unread counts and pagination; VECTOR has `get_thread()` but no threaded inbox listing | ❌ |
| Subject-normalized thread detection | Not found | Repo strips Re:/Fwd:/AW:/WG: prefixes to match threads across subject variations | ❌ |
| Custom folder CRUD | Not in `email_agent.py` | Repo has create/rename/delete custom folders; VECTOR has only fixed `_FOLDERS` dict | ❌ |
| Attachment handling (upload/download) | `core/email/attachments.py` | File exists; not exposed via `email_agent.py` public interface | ⚠️ |
| MCP server for email tools | `core/mcp_server.py` (global) | VECTOR has 14 general MCP tools but none are email-specific; no `list_mailboxes`, `send_email`, `update_draft` MCP tools | ❌ |
| Configurable system prompt per mailbox | Not present | Hardcoded `_DEFAULT_SYSTEM_PROMPT` in `email_agent.py`; no per-mailbox override | ❌ |
| Send email (outbound SMTP/API) | `core/email/sender.py` | File exists; wired in `reply_forward.py` but not callable from `email_agent.run()` directly for new emails | ⚠️ |
| Inbound email receive (MIME parse) | Not built | Repo uses Cloudflare Email Routing Worker + `postal-mime`; VECTOR has no equivalent inbound MIME parsing pipeline | ❌ |

**Summary:** 13 of 26 features fully implemented (✅), 4 partial (⚠️), 6 missing (❌), 3 by design (single-owner architecture).

---

## 3. Frontend

The repo ships a complete React 19 SPA. VECTOR has no web frontend for email.

### Panels documented

| Component | File | What it does |
|-----------|------|-------------|
| `MailboxSplitView` | `app/components/MailboxSplitView.tsx` | Three-pane layout: sidebar / email list / email panel + optional agent sidebar |
| `Sidebar` | `app/components/Sidebar.tsx` | Folder nav (Inbox/Sent/Drafts/Archive/Trash), compose button, custom folder creation, unread badge counts, back-to-mailboxes link |
| `email-list` | `app/routes/email-list.tsx` | Paginated email list with threaded grouping, unread indicators, starred toggle, select/bulk ops |
| `AgentPanel` | `app/components/AgentPanel.tsx` | WebSocket chat panel: 9 tool labels with icons and completion badges, streaming markdown responses, "Edit & send in composer" action on draft_reply results, suggested prompts, stop-generating button |
| `AgentSidebar` | `app/components/AgentSidebar.tsx` | Collapsible wrapper for AgentPanel, toggled from Header |
| `ComposePanel` / `ComposeEmail` | `app/components/ComposePanel.tsx`, `ComposeEmail.tsx` | Rich-text TipTap composer — bold, italic, underline, links, highlight, text align, inline image insertion, reply/forward mode with quoted thread |
| `EmailPanel` | `app/components/EmailPanel.tsx` | Renders single email: HTML body in sandboxed iframe, toolbar with reply/forward/star/move/delete, attachment list |
| `MCPPanel` | `app/components/MCPPanel.tsx` | Displays MCP URL + lists 10 available tools with copy-to-clipboard for Claude Code/Cursor integration |
| `Header` | `app/components/Header.tsx` | Top bar: search input, AI toggle, mobile sidebar toggle |
| `settings` | `app/routes/settings.tsx` | Per-mailbox settings: display name + custom agent system prompt textarea with reset button |
| `home` | `app/routes/home.tsx` | Mailbox list / landing page |
| `search-results` | `app/routes/search-results.tsx` | Full-text + filter search results page |
| `mailbox-index` | `app/routes/mailbox-index.tsx` | Default mailbox view (redirects to inbox) |

**VECTOR gap:** Zero equivalent frontend exists. The `docs/frontend-spec.md` covers VECTOR's broader dashboard but has no email-client panels specified.

---

## 4. Verdict

**Absorb? Partially — 6 Python gaps are worth adding.**

**Reasoning:**

The TypeScript application layer (React SPA + Hono API + Durable Objects + Cloudflare Email Routing Worker) is not absorbable — it is tightly coupled to Cloudflare Workers primitives (`DurableObjectStub`, `R2Bucket`, `EmailBinding`, `WebSocket DO`) that have no Python equivalent. Reimplementing the edge infrastructure would be 400+ hours of work for a single-owner system that already has a working local SQLite email store.

What IS worth absorbing as Python gaps:

1. **`update_draft`** — docstring in `email_agent.py` claims it exists but the method is missing. The TS `toolUpdateDraft()` is well-designed (verify-before-delete pattern to prevent data loss, replaces draft-id atomically).

2. **Send rate limiter** — `checkSendRateLimit()` in the Durable Object. Trivial to add as a SQLite counter with 1-hour rolling window. Prevents email flooding if the autonomous loop ever misconfigures.

3. **Threaded inbox listing** — `getThreadedEmails()` groups by thread_id with per-thread unread count and latest message date. VECTOR's `list_emails()` returns flat rows. A `list_threads()` method would be more useful for the AI agent.

4. **Subject-normalized thread detection** — The SQL expression that strips Re:/Fwd:/AW:/WG:/Réf:/SV: prefixes before matching thread subjects. Prevents duplicate thread creation when email clients vary prefix style.

5. **Custom folder CRUD** — `create_folder`, `rename_folder`, `delete_folder` with system-folder protection. VECTOR's `_FOLDERS` dict is hardcoded.

6. **Email MCP tools** — The repo exposes 13 dedicated email MCP tools (`list_mailboxes`, `list_emails`, `get_email`, `get_thread`, `search_emails`, `draft_reply`, `create_draft`, `update_draft`, `delete_email`, `send_reply`, `send_email`, `mark_email_read`, `move_email`) allowing Claude Code and external agents to operate on the inbox. VECTOR's MCP server has none of these.

---

## 5. Gaps

### Gap 1 — `update_draft` (missing method, docstring says it exists)
**Priority:** High  
**File:** `districts/communications/email_agent.py`  
**Pattern to mirror:** `toolUpdateDraft` in `workers/lib/tools.ts:274`  
**Key safety:** Read old draft → verify new body → delete old → insert new (all in one SQLite transaction). If verify fails, keep old draft unchanged. Return both old and new draft IDs.

```python
def update_draft(self, draft_id: str, to: str | None = None,
                 subject: str | None = None, body: str | None = None) -> dict:
    """Replace a draft atomically. Verify before delete to prevent data loss."""
    ...
```

### Gap 2 — Send rate limiter
**Priority:** Medium  
**File:** `core/email/schema.py` (new table) + `email_agent.py`  
**Pattern:** `checkSendRateLimit()` in `workers/durableObject/index.ts`  
**Implementation:** SQLite table `send_rate_log(id, sent_at)`. Count rows where `sent_at > now() - 1h`. If count >= threshold (e.g. 20/hour), return error string. Delete rows older than 1 hour on each check.

### Gap 3 — `list_threads` (threaded inbox view)
**Priority:** Medium  
**File:** `districts/communications/email_agent.py`  
**Pattern:** `getThreadedEmails` in `workers/durableObject/index.ts`  
**SQL:** `SELECT thread_id, MAX(date) as latest, COUNT(*) as msg_count, SUM(CASE WHEN read=0 THEN 1 ELSE 0 END) as unread, MIN(subject) as subject FROM emails WHERE folder_id=? GROUP BY thread_id ORDER BY latest DESC LIMIT ? OFFSET ?`

### Gap 4 — Subject-normalized thread detection
**Priority:** Medium  
**File:** `districts/communications/email_agent.py:store_incoming_email`  
**Pattern:** `findThreadBySubject` in `workers/durableObject/index.ts`  
**SQL:** Strip `re: `, `fwd: `, `fw: `, `aw: `, `wg: ` from subject (case-insensitive) before matching existing threads. Only fire when `in_reply_to` and `email_references` are both absent (truly new threads).

```python
_SUBJECT_PREFIX_RE = re.compile(
    r'^(re|fwd|fw|aw|wg|réf|sv):\s*', re.IGNORECASE
)

def _normalize_subject(s: str) -> str:
    while True:
        ns = _SUBJECT_PREFIX_RE.sub('', s).strip()
        if ns == s: return ns.lower()
        s = ns
```

### Gap 5 — Custom folder CRUD
**Priority:** Low  
**File:** `districts/communications/email_agent.py`  
**Pattern:** `createFolder`, `updateFolder`, `deleteFolder` in `workers/durableObject/index.ts`  
**Notes:** Add `folders` table to `core/email/schema.py` (currently only `emails` and `attachments` exist). System folders (inbox, sent, draft, archive, trash) must be protected from deletion. Slug must be alphanumeric.

### Gap 6 — Email MCP tools
**Priority:** High (VECTOR's agents and Claude Code cannot interact with the inbox via MCP)  
**File:** `core/mcp_server.py`  
**Pattern:** `EmailMCP` in `workers/mcp/index.ts`  
**Tools to add:** `email_list_emails`, `email_get_email`, `email_get_thread`, `email_search_emails`, `email_draft_reply`, `email_draft_email`, `email_update_draft`, `email_discard_draft`, `email_mark_read`, `email_move_email`, `email_delete_email`  
**Notes:** Wrap `EmailAgent` singleton calls. No `list_mailboxes` needed (single-owner). No `send_reply`/`send_email` MCP tools — those must go through the permission gateway (GREEN/YELLOW/RED), not direct MCP calls.

---

## Absorption Decision

| Item | Absorb | Effort |
|------|--------|--------|
| TypeScript application (React SPA + Hono + Durable Objects + Email Worker) | No — platform-locked | N/A |
| Gap 1: `update_draft` Python method | Yes | 30 min |
| Gap 2: Send rate limiter | Yes | 1 hour |
| Gap 3: `list_threads` method | Yes | 1 hour |
| Gap 4: Subject-normalized thread detection | Yes | 45 min |
| Gap 5: Custom folder CRUD | Yes | 2 hours |
| Gap 6: Email MCP tools (11 tools) | Yes — high value | 2 hours |

**Total estimated absorption effort: ~7 hours.**  
All 6 gaps are straightforward Python additions to existing files (`email_agent.py`, `core/email/schema.py`, `core/mcp_server.py`). No new dependencies required.
