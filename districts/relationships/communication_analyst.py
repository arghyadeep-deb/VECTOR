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
        )

    def analyze_communication_style(self, contact_name: str) -> dict:
        logger.info(f"[VECTOR][relationships] Analyzing communication style for: {contact_name}")
        self.add_lesson({"action": "analyze_communication_style", "contact": contact_name})

        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        interactions = mem.recall(contact_name, limit=50)
        mem.close()

        if not interactions:
            interactions = [{"content": f"Sample interaction with {contact_name} for baseline analysis", "event_type": "message"}]

        texts = [i.get("content", "") for i in interactions]
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
        logger.info(f"[VECTOR][relationships] Suggesting reconnection for: {contact_name}")
        self.add_lesson({"action": "suggest_reconnect", "contact": contact_name})

        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        interactions = mem.recall(contact_name, limit=30)
        mem.close()

        last_interaction = interactions[0] if interactions else None
        last_time = last_interaction.get("timestamp", "") if last_interaction else "Unknown"

        style = self.communication_profiles.get(contact_name, {})
        style_str = style.get("style", "formal" if style.get("formality_score", 0.5) > 0.6 else "casual")

        prompt = f"""Suggest the best way to reconnect with '{contact_name}'.
Last contact: {last_time}
Communication style: {style_str}
Recent interactions: {json.dumps([i.get('content','')[:100] for i in interactions[:5]])}
Include: 1) Best reconnection method (call/message/email), 2) Opening line suggestion, 3) Timing recommendation, 4) Topic ideas, 5) Expected response style."""
        suggestion = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        result = {
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
        logger.info(f"[VECTOR][relationships] Generating relationship insights for: {contact_name}")
        self.add_lesson({"action": "generate_relationship_insights", "contact": contact_name})

        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        interactions = mem.recall(contact_name, limit=50)
        mem.close()

        interaction_types = collections.Counter(i.get("event_type", "unknown") for i in interactions)
        content_keywords = collections.Counter()
        for i in interactions:
            words = i.get("content", "").split()[:20]
            content_keywords.update(words)

        style = self.communication_profiles.get(contact_name, {})

        prompt = f"""Generate comprehensive relationship insights for '{contact_name}':
Interaction types: {dict(interaction_types.most_common(5))}
Top keywords: {content_keywords.most_common(10)}
Communication style: {style}
Total interactions: {len(interactions)}
Include: 1) Relationship strength (1-10), 2) Trust level, 3) Communication health, 4) Shared interests, 5) Relationship trajectory (improving/stable/declining), 6) Actionable recommendations."""
        insights = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        result = {
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
        p = task.get("params", {})
        result = self.generate_relationship_insights(p.get("contact", ""))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CommunicationAnalyst()
    assert agent.district == "relationships"

    style = agent.analyze_communication_style("Alice")
    assert "style_data" in style
    assert style["contact_name"] == "Alice"

    reconnect = agent.suggest_reconnect("Alice")
    assert "reconnection_suggestion" in reconnect

    insights = agent.generate_relationship_insights("Alice")
    assert "relationship_insights" in insights

    print("✅ communication_analyst.py OK")