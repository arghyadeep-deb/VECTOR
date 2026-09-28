import sys
import uuid
import json
import re
from pathlib import Path
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory


class ClientManager(AgentBase):
    """
    Manages client relationships, tracks engagement,
    and stores client information for agency operations.
    """

    ENGAGEMENT_TYPES = [
        "initial_contact", "meeting", "call", "email", "proposal_sent",
        "contract_signed", "payment_received", "project_update",
        "deliverable_sent", "feedback_received", "renewal_discussed",
        "churn_risk", "win_back"
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "ClientManager", "agency")
        self.capabilities = ["add_client", "agency", "client", "client_summary", "delete_client", "get_at_risk_clients", "get_client", "get_top_clients", "list_clients", "sales", "track_engagement", "update_client"]
        if ghost:
            self.inherit_ghost(ghost)

        self._clients: dict[str, dict] = {}
        self._engagement_history: list[dict] = []
        self._episodic = EpisodicMemory()
        from core.runtime_paths import data_path

        self._client_file = data_path("clients.json")
        self._load_clients()
        logger.info(f"[VECTOR][client_manager] ClientManager initialized - {len(self._clients)} clients")

    def _load_clients(self) -> None:
        """Load clients from persistent storage."""
        if self._client_file.exists():
            try:
                with open(self._client_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._clients = data.get("clients", {})
                    self._engagement_history = data.get("history", [])
                logger.info(f"[VECTOR][client_manager] Loaded {len(self._clients)} clients")
            except Exception as e:
                logger.error(f"[VECTOR][client_manager] Failed to load clients: {e}")

    def _save_clients(self) -> bool:
        """Save clients to persistent storage."""
        try:
            self._client_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._client_file, "w", encoding="utf-8") as f:
                json.dump({
                    "clients": self._clients,
                    "history": self._engagement_history[-1000:]
                }, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"[VECTOR][client_manager] Failed to save clients: {e}")
            return False

    def add_client(self, name: str, contact: str, notes: str = "", tags: list[str] = None) -> dict:
        """
        Add a new client to the database.
        Returns client record with ID.
        """
        name = name.strip()
        if not name:
            return {"status": "error", "message": "Client name required"}

        if name in self._clients:
            return {"status": "error", "message": "Client already exists", "client": name}

        client_id = str(uuid.uuid4())
        client = {
            "id": client_id,
            "name": name,
            "contact": contact,
            "notes": notes,
            "tags": tags or [],
            "status": "active",
            "created_at": self._get_timestamp(),
            "last_contact": None,
            "engagement_score": 0,
            "total_engagements": 0,
            "lifetime_value": 0.0,
            "projects": []
        }

        self._clients[name] = client
        self._save_clients()

        self._episodic.store(
            event_type="client_added",
            content=f"New client added: {name}",
            tags=["client", "agency", name.lower().replace(" ", "_")],
            source="client_manager"
        )

        self.award_points(10, f"client_added_{name}")
        logger.info(f"[VECTOR][client_manager] Added client: {name}")

        return {"status": "success", "client": client}

    def get_client(self, name: str) -> Optional[dict]:
        """
        Retrieve client information by name.
        Returns None if not found.
        """
        name = name.strip()
        return self._clients.get(name)

    def get_client_by_id(self, client_id: str) -> Optional[dict]:
        """Retrieve client by ID."""
        for client in self._clients.values():
            if client.get("id") == client_id:
                return client
        return None

    def list_clients(self, status: Optional[str] = None) -> list[dict]:
        """
        List all clients, optionally filtered by status.
        Status options: active, inactive, churned, prospect
        """
        if status:
            return [
                c for c in self._clients.values()
                if c.get("status") == status
            ]
        return list(self._clients.values())

    def update_client(self, name: str, updates: dict) -> dict:
        """Update client information."""
        if name not in self._clients:
            return {"status": "error", "message": "Client not found"}

        client = self._clients[name]
        allowed_fields = ["contact", "notes", "tags", "status", "lifetime_value"]

        for key, value in updates.items():
            if key in allowed_fields:
                client[key] = value

        client["updated_at"] = self._get_timestamp()
        self._save_clients()

        self.award_points(3, f"client_updated_{name}")
        return {"status": "success", "client": client}

    def delete_client(self, name: str) -> bool:
        """Delete a client from the database."""
        if name in self._clients:
            del self._clients[name]
            self._save_clients()
            logger.info(f"[VECTOR][client_manager] Deleted client: {name}")
            return True
        return False

    def track_engagement(self, client: str, event_type: str, details: dict | None = None) -> dict:
        """
        Track engagement event with a client.
        Updates engagement score and last contact timestamp.
        """
        if client not in self._clients:
            return {"status": "error", "message": "Client not found"}

        if event_type not in self.ENGAGEMENT_TYPES:
            return {"status": "error", "message": f"Unknown engagement type: {event_type}"}

        engagement = {
            "id": str(uuid.uuid4()),
            "client": client,
            "event_type": event_type,
            "details": details or {},
            "timestamp": self._get_timestamp()
        }

        self._engagement_history.append(engagement)

        client_data = self._clients[client]
        client_data["last_contact"] = engagement["timestamp"]
        client_data["total_engagements"] += 1

        score_map = {
            "initial_contact": 5,
            "meeting": 15,
            "call": 10,
            "email": 3,
            "proposal_sent": 20,
            "contract_signed": 50,
            "payment_received": 40,
            "project_update": 10,
            "deliverable_sent": 15,
            "feedback_received": 8,
            "renewal_discussed": 25,
            "churn_risk": -20,
            "win_back": 30
        }

        score_change = score_map.get(event_type, 5)
        client_data["engagement_score"] += score_change

        if event_type == "payment_received":
            amount = details.get("amount", 0) if details else 0
            client_data["lifetime_value"] += amount

        self._save_clients()

        self._episodic.store(
            event_type=f"client_engagement_{event_type}",
            content=f"Engagement with {client}: {event_type}",
            tags=["client", "engagement", client.lower().replace(" ", "_")],
            source="client_manager"
        )

        self.award_points(score_change // 5, f"engagement_tracked_{event_type}")
        logger.info(f"[VECTOR][client_manager] Tracked {event_type} for {client}")

        return {
            "status": "success",
            "engagement": engagement,
            "new_score": client_data["engagement_score"]
        }

    def get_engagement_history(self, client: str, limit: int = 50) -> list[dict]:
        """Get engagement history for a client."""
        history = [
            e for e in self._engagement_history
            if e.get("client") == client
        ]
        return sorted(history, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_top_clients(self, by: str = "engagement_score", limit: int = 10) -> list[dict]:
        """
        Get top clients by metric.
        Options: engagement_score, lifetime_value, total_engagements
        """
        clients = list(self._clients.values())
        if by == "engagement_score":
            return sorted(clients, key=lambda x: x.get("engagement_score", 0), reverse=True)[:limit]
        elif by == "lifetime_value":
            return sorted(clients, key=lambda x: x.get("lifetime_value", 0), reverse=True)[:limit]
        elif by == "total_engagements":
            return sorted(clients, key=lambda x: x.get("total_engagements", 0), reverse=True)[:limit]
        return clients[:limit]

    def get_client_summary(self) -> dict:
        """Get summary statistics for all clients."""
        total = len(self._clients)
        if total == 0:
            return {
                "total_clients": 0,
                "active_clients": 0,
                "total_engagements": 0,
                "avg_engagement_score": 0,
                "total_lifetime_value": 0
            }

        active = len([c for c in self._clients.values() if c.get("status") == "active"])
        total_engagements = sum(c.get("total_engagements", 0) for c in self._clients.values())
        avg_score = sum(c.get("engagement_score", 0) for c in self._clients.values()) / total
        total_ltv = sum(c.get("lifetime_value", 0) for c in self._clients.values())

        return {
            "total_clients": total,
            "active_clients": active,
            "inactive_clients": total - active,
            "total_engagements": total_engagements,
            "avg_engagement_score": round(avg_score, 1),
            "total_lifetime_value": round(total_ltv, 2),
            "total_lifetime_value_formatted": f"${total_ltv:,.2f}"
        }

    def add_project_to_client(self, client: str, project: dict) -> bool:
        """Add a project to a client's project list."""
        if client not in self._clients:
            return False

        project_id = str(uuid.uuid4())
        project_entry = {
            "id": project_id,
            "name": project.get("name", "Untitled Project"),
            "description": project.get("description", ""),
            "status": project.get("status", "active"),
            "value": project.get("value", 0),
            "created_at": self._get_timestamp(),
            "completed_at": None
        }

        self._clients[client]["projects"].append(project_entry)
        self._save_clients()
        return True

    def get_at_risk_clients(self, threshold: int = 20) -> list[dict]:
        """Get clients with low engagement scores indicating churn risk."""
        at_risk = [
            c for c in self._clients.values()
            if c.get("engagement_score", 0) < threshold and c.get("status") == "active"
        ]
        return sorted(at_risk, key=lambda x: x.get("engagement_score", 0))

    def answer_client_question(self, query: str) -> Optional[dict]:
        """Resolve supported free-text questions through existing read methods.

        Governor chat classification can provide an agent a novel task type and
        retain the actionable request in ``params.query``.  This intentionally
        handles only questions that unambiguously map to real client data; it
        does not use an LLM or pretend to answer an unsupported request.
        """
        normalized = " ".join(query.casefold().split())
        if re.search(r"\b(?:add|create|delete|remove|update|edit|change|set|track|log|record|assign|modify)\b", normalized):
            return None

        has_question_shape = normalized.endswith("?") or bool(re.match(
            r"(?:how many|which|what|who|are there|do we have|can you|could you|would you|show me|list|give me|tell me|any)\b",
            normalized,
        ))
        has_client_context = bool(re.search(r"\bclients?\b", normalized))
        asks_summary = bool(re.search(
            r"\b(?:how many|number of|count of|total)\s+clients?\b|\bclient\s+(?:summary|overview)\b",
            normalized,
        ))
        asks_risk = has_client_context and bool(re.search(
            r"\b(?:at[- ]risk|churn(?:ing)?|need attention)\b", normalized,
        ))

        if not (has_question_shape and has_client_context and (asks_summary or asks_risk)):
            return None

        result = {"status": "ok", "query": query}
        if asks_summary:
            result["summary"] = self.get_client_summary()
        if asks_risk:
            result["at_risk_clients"] = [
                {
                    "name": client.get("name"),
                    "status": client.get("status"),
                    "engagement_score": client.get("engagement_score", 0),
                }
                for client in self.get_at_risk_clients()
            ]
        return result

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "add_client", "get_client", "list_clients", "update_client",
            "delete_client", "track_engagement", "get_top_clients",
            "client_summary", "get_at_risk_clients",
        ]

        # NOTE: add_client/update_client/track_engagement already return their
        # own native "success"/"error" status (their own established public
        # API contract, used directly by callers elsewhere) — passed through
        # unchanged rather than translated, so run() doesn't mask a real
        # "error" result (e.g. duplicate client name) as a fake "ok".
        if task_type == "add_client":
            return self.add_client(p.get("name", ""), p.get("contact", ""), p.get("notes", ""), p.get("tags"))
        if task_type == "get_client":
            client = self.get_client(p.get("name", ""))
            return {"status": "ok", "client": client}
        if task_type == "list_clients":
            return {"status": "ok", "clients": self.list_clients(p.get("status"))}
        if task_type == "update_client":
            return self.update_client(p.get("name", ""), p.get("updates", {}))
        if task_type == "delete_client":
            return {"status": "ok", "deleted": self.delete_client(p.get("name", ""))}
        if task_type == "track_engagement":
            return self.track_engagement(p.get("client", ""), p.get("event_type", ""), p.get("details"))
        if task_type == "get_top_clients":
            return {"status": "ok", "clients": self.get_top_clients(p.get("by", "engagement_score"), p.get("limit", 10))}
        if task_type == "client_summary":
            return {"status": "ok", **self.get_client_summary()}
        if task_type == "get_at_risk_clients":
            return {"status": "ok", "clients": self.get_at_risk_clients(p.get("threshold", 20))}

        query = p.get("query") or p.get("content") or ""
        if isinstance(query, str):
            answer = self.answer_client_question(query)
            if answer is not None:
                return answer

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    manager = ClientManager()

    result = manager.add_client(
        "Acme Corp",
        "contact@acme.com",
        notes="Enterprise client, interested in AI solutions",
        tags=["enterprise", "ai"]
    )
    print(f"Added client: {result['client']['name']}")

    result = manager.track_engagement("Acme Corp", "initial_contact")
    print(f"Engagement tracked, new score: {result['new_score']}")

    result = manager.track_engagement("Acme Corp", "meeting", {"duration_minutes": 30})
    print(f"Meeting logged, new score: {result['new_score']}")

    summary = manager.get_client_summary()
    print(f"Total clients: {summary['total_clients']}")

    print("✅ client_manager.py OK")
