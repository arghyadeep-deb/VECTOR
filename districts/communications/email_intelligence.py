"""
Email Intelligence Engineer — extracts structured context from Gmail threads.

Converts raw email threads into reasoning-ready data for VECTOR:
participant graph, action items, deadlines, sentiment, priority.
"""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from pathlib import Path
import asyncio
import datetime
import re


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat


class EmailIntelligence(AgentBase):
    """Converts raw email threads into structured, reasoning-ready VECTOR context."""

    def __init__(self):
        super().__init__(agent_id="email_intel_001", name="EmailIntelligence", district="communications")
        self.capabilities = ["communications", "draft_reply", "email", "message", "send_email"]
        self._memory: EpisodicMemory | None = None
        self._fetch_error: str | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][email_intel] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_gmail_service(self):
        """Get Gmail API service via Google OAuth."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds_path = Path.home() / ".vector" / "google_credentials.json"
            token_path = Path.home() / ".vector" / "gmail_token.json"
            if not token_path.exists():
                logger.warning("[VECTOR][email_intel] Gmail token not found — run: python -m core.integrations.gmail_auth")
                return None
            creds = Credentials.from_authorized_user_file(str(token_path))
            return build("gmail", "v1", credentials=creds)
        except Exception as e:
            logger.warning("[VECTOR][email_intel] Gmail service unavailable: {}", e)
            self._fetch_error = str(e)
            return None

    def fetch_recent_threads(self, max_results: int = 20) -> list[dict]:
        """Fetch recent email threads from Gmail."""
        self._fetch_error = None
        service = self._get_gmail_service()
        if service is None:
            return []
        try:
            threads = service.users().threads().list(
                userId="me", maxResults=max_results, labelIds=["INBOX"]
            ).execute().get("threads", [])
            result = []
            for t in threads[:max_results]:
                thread_data = service.users().threads().get(userId="me", id=t["id"]).execute()
                messages = thread_data.get("messages", [])
                parsed = self._parse_thread(messages)
                if parsed:
                    result.append(parsed)
            return result
        except Exception as e:
            logger.warning("[VECTOR][email_intel] fetch threads failed: {}", e)
            self._fetch_error = str(e)
            return []

    def _parse_thread(self, messages: list[dict]) -> dict | None:
        """Extract structured data from a Gmail thread."""
        if not messages:
            return None
        participants = set()
        subject = ""
        body_parts = []
        latest_date = ""

        for msg in messages:
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            if not subject:
                subject = headers.get("Subject", "(no subject)")
            participants.add(headers.get("From", ""))
            participants.add(headers.get("To", ""))
            latest_date = headers.get("Date", "")
            # Extract body text
            body = msg.get("snippet", "")
            if body:
                body_parts.append(body)

        return {
            "subject": subject,
            "participants": [p for p in participants if "@" in p][:5],
            "message_count": len(messages),
            "date": latest_date,
            "body_preview": " | ".join(body_parts[:3])[:400],
        }

    async def extract_intelligence(self, thread: dict) -> dict:
        """LLM extracts action items, deadlines, priority, sentiment from thread."""
        prompt = (
            f"Email thread analysis for VECTOR AI personal assistant.\n\n"
            f"Subject: {thread['subject']}\n"
            f"Participants: {', '.join(thread['participants'])}\n"
            f"Preview: {thread['body_preview']}\n\n"
            f"Extract as JSON:\n"
            f'{{"priority": "high|medium|low", '
            f'"action_items": ["list of things I need to do"], '
            f'"deadlines": ["any deadlines mentioned"], '
            f'"sentiment": "positive|neutral|negative", '
            f'"category": "academic|personal|professional|spam", '
            f'"requires_reply": true|false, '
            f'"summary": "1 sentence"}}'
        )
        try:
            response = chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout=15.0,
            )
            import json as _json
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return _json.loads(match.group())
        except Exception as e:
            logger.debug("[VECTOR][email_intel] intelligence extract failed: {}", e)
        return {
            "priority": "medium",
            "action_items": [],
            "deadlines": [],
            "sentiment": "neutral",
            "category": "unknown",
            "requires_reply": False,
            "summary": thread.get("subject", "unknown"),
        }

    async def generate_email_brief(self, threads: list[dict], intelligence: list[dict]) -> str:
        """Generate a concise email brief for VECTOR's morning/evening digest."""
        high_priority = [(t, i) for t, i in zip(threads, intelligence) if i.get("priority") == "high"]
        requires_reply = [(t, i) for t, i in zip(threads, intelligence) if i.get("requires_reply")]
        all_actions = []
        for i in intelligence:
            all_actions.extend(i.get("action_items", []))

        brief = f"## Email Brief — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        brief += f"**{len(threads)} threads scanned**\n\n"

        if high_priority:
            brief += "### 🔴 High Priority\n"
            for t, i in high_priority[:3]:
                brief += f"- {t['subject']}: {i.get('summary','')}\n"
            brief += "\n"

        if requires_reply:
            brief += f"### 📩 Needs Reply ({len(requires_reply)})\n"
            for t, i in requires_reply[:3]:
                brief += f"- {t['subject']}\n"
            brief += "\n"

        if all_actions:
            brief += f"### ✅ Action Items ({len(all_actions)})\n"
            for action in all_actions[:5]:
                brief += f"- {action}\n"

        return brief

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 full-repo mechanical sweep finding): the real
        # governor dispatch shape is {"type": ..., "params": {...}} -- limit
        # was read straight off `task`, never `task["params"]`, so a real
        # dispatch always fell back to the hardcoded default (15). Capture
        # task_type from the UNMERGED task first (a nested params dict could
        # carry its own "type" key -- see districts/communications/
        # email_agent.py's identical fix), then flatten params into task.
        task_type = task.get("type", "brief")
        task = {**task, **(task.get("params") or {})}
        try:
            threads = self.fetch_recent_threads(max_results=task.get("limit", 15))

            if not threads and getattr(self, "_fetch_error", None):
                # Gmail is configured but the fetch failed: that is an error, not "no mail".
                self.deduct_points(10, "email_fetch_failed")
                return {"status": "error", "error": f"Gmail fetch failed: {self._fetch_error}", "threads": 0}

            if not threads:
                self.award_points(10, "email_check_no_gmail")
                return {"status": "ok", "message": "Gmail not connected — see KNOWN_ISSUES.md for setup", "threads": 0}

            intelligence = []
            for thread in threads:
                intel = await self.extract_intelligence(thread)
                intelligence.append(intel)

            brief = await self.generate_email_brief(threads, intelligence)
            high_count = sum(1 for i in intelligence if i.get("priority") == "high")
            reply_count = sum(1 for i in intelligence if i.get("requires_reply"))
            all_actions = [a for i in intelligence for a in i.get("action_items", [])]

            # Store in episodic memory
            self._get_memory().store(
                event_type="email_intelligence_run",
                content=f"Email: {len(threads)} threads, {high_count} high priority, {reply_count} need reply",
                tags=["communications", "email", "intelligence"],
                context={"threads": len(threads), "high_priority": high_count, "actions": len(all_actions)},
                source="email_intelligence",
            )

            self.award_points(40 + high_count * 5, "email_intelligence_complete")
            return {
                "status": "ok",
                "threads_analyzed": len(threads),
                "high_priority": high_count,
                "requires_reply": reply_count,
                "action_items": all_actions[:10],
                "brief": brief,
            }

        except Exception as e:
            logger.error("[VECTOR][email_intel] {}", e)
            self.deduct_points(30, "email_intelligence_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = EmailIntelligence()
        # Test with mock thread (Gmail not connected in test)
        mock_thread = {
            "subject": "KIIT ERP Attendance Update",
            "participants": ["kiit@kiit.ac.in", "2305119@kiit.ac.in"],
            "message_count": 2,
            "date": "Mon, 1 Jan 2026",
            "body_preview": "Your attendance has been updated. Current: 75%. Please maintain above 75% to avoid detainment.",
        }
        intel = await agent.extract_intelligence(mock_thread)
        print(f"[OK] extract_intelligence: priority={intel.get('priority')} category={intel.get('category')}")
        brief = await agent.generate_email_brief([mock_thread], [intel])
        print(f"[OK] generate_email_brief: {len(brief)} chars")
        result = await agent.run({"type": "brief", "limit": 5})
        print(f"[OK] run: status={result['status']} threads={result.get('threads_analyzed', result.get('threads', 0))}")
        print("email_intelligence.py OK")

    asyncio.run(_smoke())
