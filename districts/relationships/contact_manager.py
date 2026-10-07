"""
Module: agents/relationships/contact_manager.py
District: relationships | Focus: Contact management, interaction tracking
"""

import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, threading
from typing import Optional


class ContactManager(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ContactManager",
            district="relationships",
            generation=1
        )
        self.capabilities = ["communication", "contact", "relationships"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self._lock = threading.RLock()
        from core.runtime_paths import data_path

        self.db_path = data_path("contacts.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info("[VECTOR][relationships] ContactManager ready")

    def _get_conn(self):
        from core.relationships.schema import get_connection
        return get_connection(self.db_path)

    def _init_db(self):
        with self._lock:
            from core.relationships.schema import init_schema
            init_schema(self.db_path)

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
            district=self.district,
            sensitive=True,
            allow_cloud=False,  # contact data is personal: local Ollama only
        )

    def add_contact(self, name: str, phone: str = "", email: str = "", notes: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            return {"status": "error", "error": "contact name is required"}
        # Contact names stay out of INFO logs and agent lessons (lessons are
        # persisted in ghost memory and re-injected into LLM prompts).
        logger.info("[VECTOR][relationships] Adding contact")
        self.add_lesson({"action": "add_contact"})

        added_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                # Upsert: INSERT OR REPLACE would wipe last_contacted and
                # contact_count (interaction history) when a contact is edited.
                conn.execute(
                    "INSERT INTO contacts (name, phone, email, notes, added_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET phone = excluded.phone, "
                    "email = excluded.email, notes = excluded.notes",
                    (name, phone, email, notes, added_at)
                )
                row = conn.execute("SELECT added_at FROM contacts WHERE name = ?", (name,)).fetchone()
                if row and row[0]:
                    added_at = row[0]
                conn.commit()
            finally:
                conn.close()

        result = {"name": name, "phone": phone, "email": email, "notes": notes, "added_at": added_at}

        self.memory.store(
            event_type="contact_added",
            content=f"Added contact: {name}",
            tags=["relationships", "contact", name],
            context=result,
            source="ContactManager"
        )

        logger.info("[VECTOR][relationships] Contact saved")
        return result

    def get_contact(self, name: str) -> dict:
        logger.info("[VECTOR][relationships] Getting contact")
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT name, phone, email, notes, added_at, last_contacted, contact_count FROM contacts WHERE name = ?",
                    (name,)
                )
                row = cursor.fetchone()
                if not row:
                    return {"error": f"Contact '{name}' not found"}

                cursor2 = conn.execute(
                    "SELECT interaction_type, content, timestamp FROM interactions WHERE contact_name = ? ORDER BY timestamp DESC LIMIT 10",
                    (name,)
                )
                interactions = [{"type": r[0], "content": r[1], "timestamp": r[2]} for r in cursor2.fetchall()]
            finally:
                conn.close()

        return {
            "name": row[0],
            "phone": row[1],
            "email": row[2],
            "notes": row[3],
            "added_at": row[4],
            "last_contacted": row[5],
            "contact_count": row[6],
            "recent_interactions": interactions,
        }

    def list_contacts(self) -> dict:
        logger.info("[VECTOR][relationships] Listing all contacts")
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT name, phone, email, last_contacted, contact_count FROM contacts ORDER BY last_contacted DESC"
                )
                contacts = [
                    {"name": row[0], "phone": row[1], "email": row[2],
                     "last_contacted": row[3], "contact_count": row[4]}
                    for row in cursor
                ]
            finally:
                conn.close()

        return {"total_contacts": len(contacts), "contacts": contacts}

    def track_interaction(self, name: str, interaction: str, interaction_type: str = "general") -> dict:
        logger.info("[VECTOR][relationships] Tracking interaction")
        self.add_lesson({"action": "track_interaction", "type": interaction_type})

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "UPDATE contacts SET last_contacted = ?, contact_count = COALESCE(contact_count, 0) + 1 WHERE name = ?",
                    (timestamp, name)
                )
                if cur.rowcount == 0:
                    # Unknown contact: do not log an orphan interaction and
                    # report it as tracked.
                    conn.rollback()
                    return {"status": "error", "error": f"Contact '{name}' not found"}
                conn.execute(
                    "INSERT INTO interactions (contact_name, interaction_type, content, timestamp) VALUES (?, ?, ?, ?)",
                    (name, interaction_type, interaction, timestamp)
                )
                conn.commit()
            finally:
                conn.close()

        result = {"contact_name": name, "interaction": interaction, "type": interaction_type, "timestamp": timestamp}

        self.memory.store(
            event_type="interaction_tracked",
            content=f"Tracked interaction with {name}: {interaction_type}",
            tags=["relationships", "interaction", name],
            context=result,
            source="ContactManager"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = (task or {}).get("params") or {}
        if p.get("name") and p.get("interaction"):
            result = self.track_interaction(p["name"], p["interaction"])
            return {"status": "ok", **result}
        contact = self.get_contact(p.get("name", "")) if p.get("name") else {}
        if "error" in contact:
            return {"status": "error", "contact": contact}
        return {"status": "ok", "contact": contact}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = ContactManager()
    assert agent.district == "relationships"

    agent.add_contact("Alice", "+919876543210", "alice@email.com", "Work colleague")
    agent.add_contact("Bob", "+919876543211", "bob@email.com", "Friend")

    contact = agent.get_contact("Alice")
    assert "name" in contact
    assert contact["name"] == "Alice"

    agent.track_interaction("Alice", "Met at conference, discussed project", "meeting")
    agent.track_interaction("Bob", "Coffee chat about startup ideas", "casual")

    contacts = agent.list_contacts()
    assert contacts["total_contacts"] >= 2

    print("✅ contact_manager.py OK")
