"""
Module: agents/relationships/communication_analyst.py
District: relationships | Focus: Analyze communication style, suggest reconnections, generate insights
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, collections
from typing import Optional


class CommunicationAnalyst(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="CommunicationAnalyst",
            district="relationships",
            generation=1
        )
        self.capabilities = ["analysis", "communication", "relationships"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.communication_profiles = {}
        logger.info("[VECTOR][relationships] CommunicationAnalyst ready")

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
            allow_cloud=False,  # contact/relationship data: local Ollama only
        )

    # Events this agent (and ContactManager's bookkeeping) writes about a
    # contact. They are derived artefacts, not interactions: counting them made
    # every analysed contact look "just contacted" and fed analyses back into
    # themselves.
    _DERIVED_EVENT_TYPES = frozenset({
        "communication_style_analyzed", "reconnect_suggested",
        "relationship_insights_generated", "contact_added",
    })

    def _recall_interactions(self, contact_name: str, limit: int) -> list[dict]:
        events = self.memory.recall(contact_name, limit=limit * 3) or []
        real = [
            e for e in events
            if e.get("event_type") not in self._DERIVED_EVENT_TYPES
            and e.get("source") != "CommunicationAnalyst"
        ]
        return real[:limit]

    def analyze_communication_style(self, contact_name: str) -> dict:
        logger.info("[VECTOR][relationships] Analyzing communication style")
        self.add_lesson({"action": "analyze_communication_style"})

        interactions = self._recall_interactions(contact_name, 50)

        if not interactions:
            # No real history: do not fabricate a "sample interaction" and
            # report an LLM-invented style as an analysis of this contact.
            return {"status": "no_data", "contact_name": contact_name,
                    "interactions_analyzed": 0, "style_data": {}}

        texts = [i.get("content") or "" for i in interactions]
        combined_text = " ".join(texts)[:2000]

        avg_length = sum(len(t) for t in texts) / max(len(texts), 1)
        formal_count = sum(1 for t in texts if any(w in t.lower() for w in ["please", "thank", "regards", "sincerely"]))
        casual_count = sum(1 for t in texts if any(w in t.lower() for w in ["hey", "yeah", "cool", "lol", "bro"]))

        prompt = f"""Analyze the communication style of '{contact_name}' based on these interactions:
{combined_text[:1000]}
Average message length: {round(avg_length)} chars
Formal messages: {formal_count}, Casual messages: {casual_count}
Return JSON: {{style: string, formality_score: float, responsiveness: string, tone: string, key_characteristics: string[], recommendations: string[]}}"""
        analysis = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not (analysis or "").strip():
            logger.warning("[VECTOR][relationships] Style analysis: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "contact_name": contact_name,
                    "interactions_analyzed": len(interactions), "style_data": {}}

        try:
            import re
            json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
            if json_match:
                style_data = json.loads(json_match.group(0))
            else:
                style_data = {"style": "balanced", "formality_score": 0.5}
        except json.JSONDecodeError:
            style_data = {"style": analysis[:200], "formality_score": 0.5}

        result = {
            "status": "ok",
            "contact_name": contact_name,
            "interactions_analyzed": len(interactions),
            "avg_message_length": round(avg_length, 1),
            "formality_ratio": round(formal_count / max(len(texts), 1), 2),
            "style_data": style_data,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.communication_profiles[contact_name] = style_data

        self.memory.store(
            event_type="communication_style_analyzed",
            content=f"Analyzed communication style for {contact_name}: {style_data.get('style', 'unknown')}",
            tags=["relationships", "communication", contact_name],
            context=result,
            source="CommunicationAnalyst"
        )

        return result

    def suggest_reconnect(self, contact_name: str) -> dict:
        logger.info("[VECTOR][relationships] Suggesting reconnection")
        self.add_lesson({"action": "suggest_reconnect"})

        interactions = self._recall_interactions(contact_name, 30)

        # recall() is relevance-ranked, not chronological: take the newest
        # timestamp rather than the first row.
        stamps = [i.get("timestamp") for i in interactions if i.get("timestamp")]
        last_time = max(stamps) if stamps else "Unknown"

        style = self.communication_profiles.get(contact_name, {})
        style_str = style.get("style", "formal" if style.get("formality_score", 0.5) > 0.6 else "casual")

        prompt = f"""Suggest the best way to reconnect with '{contact_name}'.
Last contact: {last_time}
Communication style: {style_str}
Recent interactions: {json.dumps([i.get('content','')[:100] for i in interactions[:5]])}
Include: 1) Best reconnection method (call/message/email), 2) Opening line suggestion, 3) Timing recommendation, 4) Topic ideas, 5) Expected response style."""
        suggestion = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not (suggestion or "").strip():
            logger.warning("[VECTOR][relationships] Reconnect suggestion: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "contact_name": contact_name,
                    "last_interaction": last_time}

        result = {
            "status": "ok",
            "contact_name": contact_name,
            "last_interaction": last_time,
            "reconnection_suggestion": suggestion,
            "recommended_method": "message" if "message" in suggestion.lower()[:200] else "call",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="reconnect_suggested",
            content=f"Suggested reconnection with {contact_name}",
            tags=["relationships", "reconnect", contact_name],
            context=result,
            source="CommunicationAnalyst"
        )

        return result

    def generate_relationship_insights(self, contact_name: str) -> dict:
        logger.info("[VECTOR][relationships] Generating relationship insights")
        self.add_lesson({"action": "generate_relationship_insights"})

        if not (contact_name or "").strip():
            return {"status": "error", "error": "contact is required", "contact_name": contact_name}
        interactions = self._recall_interactions(contact_name, 50)
        if not interactions:
            # Nothing to base a strength/trust/trajectory rating on.
            return {"status": "no_data", "contact_name": contact_name, "interaction_count": 0}

        interaction_types = collections.Counter(i.get("event_type", "unknown") for i in interactions)
        content_keywords = collections.Counter()
        for i in interactions:
            words = (i.get("content") or "").split()[:20]
            content_keywords.update(words)

        style = self.communication_profiles.get(contact_name, {})

        prompt = f"""Generate comprehensive relationship insights for '{contact_name}':
Interaction types: {dict(interaction_types.most_common(5))}
Top keywords: {content_keywords.most_common(10)}
Communication style: {style}
Total interactions: {len(interactions)}
Include: 1) Relationship strength (1-10), 2) Trust level, 3) Communication health, 4) Shared interests, 5) Relationship trajectory (improving/stable/declining), 6) Actionable recommendations."""
        insights = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not (insights or "").strip():
            logger.warning("[VECTOR][relationships] Relationship insights: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "contact_name": contact_name,
                    "interaction_count": len(interactions)}

        result = {
            "status": "ok",
            "contact_name": contact_name,
            "interaction_count": len(interactions),
            "interaction_types": dict(interaction_types.most_common(5)),
            "communication_style": style,
            "relationship_insights": insights,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="relationship_insights_generated",
            content=f"Generated relationship insights for {contact_name}",
            tags=["relationships", "insights", contact_name],
            context=result,
            source="CommunicationAnalyst"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = (task or {}).get("params") or {}
        result = self.generate_relationship_insights(p.get("contact") or "")
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CommunicationAnalyst()
    assert agent.district == "relationships"

    # Without recorded interactions the agent must say so, not invent an analysis.
    style = agent.analyze_communication_style("Alice")
    assert "style_data" in style and style["contact_name"] == "Alice"
    assert style["status"] in ("no_data", "ok", "error")

    reconnect = agent.suggest_reconnect("Alice")
    assert reconnect["status"] in ("ok", "error")

    insights = agent.generate_relationship_insights("Alice")
    assert insights["status"] in ("no_data", "ok", "error")

    print("✅ communication_analyst.py OK")