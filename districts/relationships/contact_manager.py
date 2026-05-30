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
import uuid, asyncio, json, datetime, sqlite3
from typing import Optional


class ContactManager(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ContactManager",
            district="relationships",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.db_path = Path("./data/contacts.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info("[VECTOR][relationships] ContactManager ready")

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS contacts (
            name TEXT PRIMARY KEY,
            phone TEXT,
            email TEXT,
            notes TEXT,
            added_at TEXT,
            last_contacted TEXT,
            contact_count INTEGER DEFAULT 0
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name TEXT,
            interaction_type TEXT,
            content TEXT,
            timestamp TEXT
        )""")
        conn.commit()
        conn.close()

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
        )

    def add_contact(self, name: str, phone: str = "", email: str = "", notes: str = "") -> dict:
        logger.info(f"[VECTOR][relationships] Adding contact: {name}")
        self.add_lesson({"action": "add_contact", "name": name})

        conn = sqlite3.connect(self.db_path)
        added_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO contacts (name, phone, email, notes, added_at) VALUES (?, ?, ?, ?, ?)",
            (name, phone, email, notes, added_at)
        )
        conn.commit()
        conn.close()

        result = {"name": name, "phone": phone, "email": email, "notes": notes, "added_at": added_at}

        self.memory.store(
            event_type="contact_added",
            content=f"Added contact: {name}",
            tags=["relationships", "contact", name],
            context=result,
            source="ContactManager"
        )

        logger.info(f"[VECTOR][relationships] Contact '{name}' added")
        return result

    def get_contact(self, name: str) -> dict:
        logger.info(f"[VECTOR][relationships] Getting contact: {name}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT name, phone, email, notes, added_at, last_contacted, contact_count FROM contacts WHERE name = ?",
            (name,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"error": f"Contact '{name}' not found"}

        cursor2 = conn.execute(
            "SELECT interaction_type, content, timestamp FROM interactions WHERE contact_name = ? ORDER BY timestamp DESC LIMIT 10"
        ) if row else None

        interactions = []
        if cursor2:
            for r in cursor2:
                interactions.append({"type": r[0], "content": r[1], "timestamp": r[2]})

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT name, phone, email, last_contacted, contact_count FROM contacts ORDER BY last_contacted DESC"
        )
        contacts = []
        for row in cursor:
            contacts.append({
                "name": row[0],
                "phone": row[1],
                "email": row[2],
                "last_contacted": row[3],
                "contact_count": row[4],
            })
        conn.close()

        return {"total_contacts": len(contacts), "contacts": contacts}

    def track_interaction(self, name: str, interaction: str, interaction_type: str = "general") -> dict:
        logger.info(f"[VECTOR][relationships] Tracking interaction with: {name}")
        self.add_lesson({"action": "track_interaction", "contact": name, "type": interaction_type})

        conn = sqlite3.connect(self.db_path)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        conn.execute(
            "INSERT INTO interactions (contact_name, interaction_type, content, timestamp) VALUES (?, ?, ?, ?)",
            (name, interaction_type, interaction, timestamp)
        )

        conn.execute(
            "UPDATE contacts SET last_contacted = ?, contact_count = contact_count + 1 WHERE name = ?",
            (timestamp, name)
        )
        conn.commit()
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
        p = task.get("params", {})
        if p.get("name") and p.get("interaction"):
            result = self.track_interaction(p["name"], p["interaction"])
            return {"status": "ok", **result}
        contact = self.get_contact(p.get("name", "")) if p.get("name") else {}
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