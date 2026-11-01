import sys
import uuid
import json
from pathlib import Path
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

_MAX_CALL_HISTORY = 1000
_VALID_PRIORITIES = {"blocked", "normal", "priority", "vip"}
_HIDDEN_IDS = {"unknown", "private", "blocked"}


def _mask_caller(caller_id: str) -> str:
    """Redact a phone number for logs: keep only the last 4 characters."""
    cid = str(caller_id or "")
    return ("***" + cid[-4:]) if len(cid) > 4 else "***"


class CallScreener(AgentBase):
    """
    Screens incoming calls, checks caller against known contacts,
    and analyzes spam likelihood using pattern recognition and LLM.
    """

    SPAM_INDICATORS = [
        "unknown_number", "private_number", "blocked",
        "telemarketing", "scam_likely", "robocall"
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "CallScreener", "calls")
        self.capabilities = ["add_call_contact", "call", "call_history", "calls", "list_call_contacts", "screen"]
        if ghost:
            self.inherit_ghost(ghost)

        self._known_contacts: dict[str, dict] = {}
        self._call_history: list[dict] = []
        self._spam_threshold = 0.7
        self._auto_reject_enabled = True
        from core.runtime_paths import data_path

        self._contacts_file = data_path("call_contacts.json")
        self._load_contacts()
        logger.info("[VECTOR][call_screener] CallScreener initialized - {} contacts", len(self._known_contacts))

    def _load_contacts(self) -> None:
        """Load known contacts from storage."""
        if self._contacts_file.exists():
            try:
                with open(self._contacts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._known_contacts = data.get("contacts", {})
                logger.info("[VECTOR][call_screener] Loaded {} contacts", len(self._known_contacts))
            except Exception as e:
                logger.error("[VECTOR][call_screener] Failed to load contacts: {}", type(e).__name__)

    def _save_contacts(self) -> bool:
        """Save contacts to storage."""
        try:
            self._contacts_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._contacts_file, "w", encoding="utf-8") as f:
                json.dump({"contacts": self._known_contacts}, f, indent=2)
            return True
        except Exception as e:
            logger.error("[VECTOR][call_screener] Failed to save contacts: {}", type(e).__name__)
            return False

    def add_contact(self, caller_id: str, name: str, relation: str = "known",
                   notes: str = "", priority: str = "normal") -> dict:
        """
        Add a contact to the whitelist.
        Priority: blocked, normal, priority, vip
        """
        caller_id = self._normalize_caller_id(caller_id)
        # A whitelist entry for a hidden/empty ID would allow EVERY hidden-ID
        # caller (fail-open for scams); an unknown priority string likewise.
        if caller_id in _HIDDEN_IDS:
            return {"status": "error", "message": "a real caller number is required"}
        if priority not in _VALID_PRIORITIES:
            return {"status": "error", "message": "invalid priority"}

        contact = {
            "id": str(uuid.uuid4()),
            "name": name,
            "caller_id": caller_id,
            "relation": relation,
            "notes": notes,
            "priority": priority,
            "added_at": self._get_timestamp(),
            "call_count": 0,
            "last_call": None
        }

        self._known_contacts[caller_id] = contact
        self._save_contacts()

        self.award_points(5, "contact_added")
        logger.info("[VECTOR][call_screener] Added contact ({})", _mask_caller(caller_id))

        return {"status": "success", "contact": contact}

    def screen_call(self, caller_id: str) -> dict:
        """
        Screen an incoming call and return screening decision.
        """
        caller_id = self._normalize_caller_id(caller_id)

        result = {
            "caller_id": caller_id,
            "timestamp": self._get_timestamp(),
            "is_known": False,
            "contact": None,
            "spam_score": 0.0,
            "decision": "allow",
            "reason": ""
        }

        if caller_id in self._known_contacts:
            contact = self._known_contacts[caller_id]
            result["is_known"] = True
            result["contact"] = {
                "name": contact["name"],
                "priority": contact["priority"],
                "relation": contact["relation"]
            }

            contact["call_count"] += 1
            contact["last_call"] = result["timestamp"]
            self._save_contacts()

            if contact["priority"] == "blocked":
                result["decision"] = "block"
                result["reason"] = f"Contact '{contact['name']}' is blocked"
            elif contact["priority"] == "vip":
                result["decision"] = "allow"
                result["reason"] = f"VIP contact '{contact['name']}' - always allow"
            else:
                result["decision"] = "allow"
                result["reason"] = f"Known contact: {contact['name']}"

            self.award_points(3, "known_caller_screened")

        elif caller_id == "unknown" or caller_id == "private" or caller_id == "blocked":
            _sc = self.get_spam_score(caller_id)
            result["spam_score"] = float(_sc.get("score", 0.5))
            if _sc.get("degraded"):
                result["degraded"] = True
            result["decision"] = "review" if result["spam_score"] < self._spam_threshold else "block"
            result["reason"] = "Unknown caller ID"

            self.deduct_points(5, "unknown_caller")
        else:
            spam_score = self.get_spam_score(caller_id)
            result["spam_score"] = spam_score.get("score", 0.5)
            if spam_score.get("degraded"):
                result["degraded"] = True

            if result["spam_score"] >= self._spam_threshold and self._auto_reject_enabled:
                result["decision"] = "auto_reject"
                result["reason"] = f"High spam score ({result['spam_score']:.2f})"
                self.deduct_points(10, "spam_call_auto_rejected")
            else:
                result["decision"] = "review"
                result["reason"] = f"Possible spam (score: {result['spam_score']:.2f})"

        call_record = {
            "caller_id": caller_id,
            "decision": result["decision"],
            "spam_score": result["spam_score"],
            "timestamp": result["timestamp"]
        }
        self._call_history.append(call_record)
        if len(self._call_history) > _MAX_CALL_HISTORY:
            del self._call_history[:-_MAX_CALL_HISTORY]

        logger.info("[VECTOR][call_screener] Screened {}: {}", _mask_caller(caller_id), result["decision"])
        return result

    def _normalize_caller_id(self, caller_id: str) -> str:
        """Normalize caller ID for consistent matching."""
        if not caller_id:
            return "unknown"

        cleaned = "".join(c for c in caller_id if c.isdigit() or c == "+")

        if cleaned.startswith("91") and len(cleaned) > 10:
            cleaned = cleaned[2:]

        if len(cleaned) == 10:
            cleaned = "+1" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("1"):
            cleaned = "+" + cleaned

        return cleaned if cleaned else caller_id

    def get_spam_score(self, caller_id: str) -> dict:
        """
        Analyze caller ID for spam likelihood.
        Returns score from 0.0 (not spam) to 1.0 (definitely spam).
        """
        caller_id = self._normalize_caller_id(caller_id)

        score = 0.0
        factors = []

        if caller_id in ["unknown", "private", "blocked"]:
            score += 0.4
            factors.append({"factor": "hidden_id", "contribution": 0.4})

        digit_pattern = "".join(c for c in caller_id if c.isdigit())
        if digit_pattern:
            if digit_pattern.count(digit_pattern[0]) == len(digit_pattern):
                score += 0.3
                factors.append({"factor": "repetitive_digits", "contribution": 0.3})

            if digit_pattern in str(self._call_history):
                recent_count = sum(
                    1 for c in self._call_history[-20:]
                    if caller_id in str(c.get("caller_id", ""))
                )
                if recent_count > 3:
                    score += 0.2
                    factors.append({"factor": "frequent_caller", "contribution": 0.2})

        llm_analysis = self._analyze_spam_with_llm(caller_id)
        # LLM failed/unparseable: the score is heuristic-only, not a confident
        # verdict. Callers see degraded=True; decisions never become "allow".
        degraded = not llm_analysis.get("ok", True)
        if llm_analysis.get("is_spam"):
            score += 0.3
            factors.append({"factor": "llm_detection", "contribution": 0.3})

        score = min(score, 1.0)

        return {
            "caller_id": caller_id,
            "score": round(score, 2),
            "factors": factors,
            "verdict": "spam" if score >= 0.7 else "likely_spam" if score >= 0.5 else "unknown",
            "degraded": degraded,
        }

    def _calculate_spam_score(self, caller_id: str) -> float:
        """Compatibility helper used by the unknown/private caller path."""
        return float(self.get_spam_score(caller_id).get("score", 0.5))

    def _analyze_spam_with_llm(self, caller_id: str) -> dict:
        """Use LLM to analyze caller ID patterns for spam."""
        prompt = f"""Analyze this caller ID/number for spam likelihood:
{caller_id}

Consider:
1. Is this a valid phone number format?
2. Does it match common spam/telemarketing patterns?
3. Any suspicious characteristics?

Respond with ONLY: SPAM or NOT_SPAM
"""

        try:
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC

            async def _call():
                r = await _PC().chat(
                    messages=[{"role": "user", "content": prompt}],
                    tier="fast",
                    temperature=0.1,
                    max_tokens=10,
                    caller_id="call_screener",
                    # Caller numbers are call content: local Ollama only.
                    sensitive=True,
                    district="calls",
                )
                return r.content

            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                llm_response = pool.submit(_asyncio.run, _call()).result(timeout=10).strip().upper()

            # "NOT_SPAM" contains "SPAM": test the negative first.
            if "NOT_SPAM" in llm_response or "NOT SPAM" in llm_response:
                return {"is_spam": False, "ok": True}
            if "SPAM" in llm_response:
                return {"is_spam": True, "ok": True}
            logger.warning("[VECTOR][call_screener] LLM spam verdict unparseable")
            return {"is_spam": False, "ok": False}

        except Exception as e:
            logger.warning("[VECTOR][call_screener] LLM spam analysis failed: {}", type(e).__name__)
            return {"is_spam": False, "ok": False}

    def auto_reject(self, caller_id: str) -> dict:
        """
        Automatically reject a call based on spam score.
        Returns rejection status.
        """
        spam_score = self.get_spam_score(caller_id)

        if spam_score["score"] < self._spam_threshold:
            return {
                "rejected": False,
                "reason": f"Spam score ({spam_score['score']:.2f}) below threshold"
            }

        rejection = {
            "caller_id": caller_id,
            "spam_score": spam_score["score"],
            "timestamp": self._get_timestamp(),
            "reason": f"Spam score ({spam_score['score']:.2f}) exceeded threshold ({self._spam_threshold})"
        }

        logger.info("[VECTOR][call_screener] Auto-rejected {}: {}", _mask_caller(caller_id), rejection["reason"])
        self.deduct_points(5, "call_auto_rejected")

        return {
            "rejected": True,
            **rejection
        }

    def set_spam_threshold(self, threshold: float) -> bool:
        """Set the spam score threshold for auto-rejection."""
        if 0.0 <= threshold <= 1.0:
            self._spam_threshold = threshold
            logger.info("[VECTOR][call_screener] Spam threshold set to {}", threshold)
            return True
        return False

    def enable_auto_reject(self, enabled: bool = True) -> None:
        """Enable or disable auto-rejection of spam calls."""
        self._auto_reject_enabled = enabled
        logger.info("[VECTOR][call_screener] Auto-reject {}", "enabled" if enabled else "disabled")

    def get_call_history(self, limit: int = 50) -> list[dict]:
        """Get recent call screening history."""
        return sorted(
            self._call_history[-limit:],
            key=lambda x: x["timestamp"],
            reverse=True
        )

    def get_contact(self, caller_id: str) -> Optional[dict]:
        """Get contact by caller ID."""
        caller_id = self._normalize_caller_id(caller_id)
        return self._known_contacts.get(caller_id)

    def remove_contact(self, caller_id: str) -> bool:
        """Remove a contact."""
        caller_id = self._normalize_caller_id(caller_id)
        if caller_id in self._known_contacts:
            del self._known_contacts[caller_id]
            self._save_contacts()
            return True
        return False

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        action = task.get("type", "")
        p = task.get("params", {}) or {}
        if action == "list_call_contacts":
            return {
                "status": "ok",
                "contacts": list(self._known_contacts.values()),
                "count": len(self._known_contacts),
            }
        if action == "add_call_contact":
            result = self.add_contact(
                caller_id=p.get("number", p.get("caller_id", "")),
                name=p.get("name", ""),
                relation=p.get("tier", p.get("relation", "known")),
                notes=p.get("notes", ""),
                priority=p.get("priority", "normal"),
            )
            if result.get("status") == "success":
                result["status"] = "ok"
            return result
        if action == "call_history":
            return {"status": "ok", "history": self.get_call_history(), "count": len(self._call_history)}
        result = self.screen_call(p.get("caller_id", "unknown"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    screener = CallScreener()

    screener.add_contact("+919876543210", "John Doe", "friend", priority="vip")

    result = screener.screen_call("+919876543210")
    print(f"VIP Call: {result['decision']}")

    spam = screener.get_spam_score("+11234567890")
    print(f"Spam score: {spam['score']}")

    print("✅ call_screener.py OK")
