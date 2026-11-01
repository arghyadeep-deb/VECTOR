
import sys
import json
import re
import uuid
import asyncio
import datetime
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from core.memory.policy import PolicyMemory
from loguru import logger

_CHAIRMAN = CONFIG.get("models", {}).get("chairman", "vector-reasoning")

# Event categories returned by filter_noise
_SIGNAL = "SIGNAL"
_ROUTINE = "ROUTINE"
_NOISE = "NOISE"

# HP drop threshold that triggers a SIGNAL escalation
_HP_DROP_SIGNAL_THRESHOLD = 100

# Minimum HP below which a district is flagged as dying
_DISTRICT_DYING_HP = 100

class ChiefOfStaff(AgentBase):
    """
    VECTOR's master coordinator — sits above all districts.

    Responsibilities:
    - filter_noise(): classify events as SIGNAL / ROUTINE / NOISE
    - generate_executive_brief(): LLM-synthesised 5-bullet daily brief
    - route_escalation(): route or escalate issues to the right district
    - enforce_consistency(): flag and evolve dying districts
    - morning_brief(): 08:00 combined brief
    - evening_brief(): 22:00 accomplishment + pending summary

    RULE 11: all LLM calls via Ollama (vector-reasoning). No Claude API at runtime.
    RULE 1:  session_hydration_prompt() before every LLM call.
    RULE 8:  every session stored in reasoning_chains.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ChiefOfStaff",
            district="chief_of_staff",
            generation=generation,
        )
        self.capabilities = ["brief", "chief_of_staff", "consistency_check", "evening_brief", "executive_brief", "governance", "morning_brief", "route", "scan", "subconscious"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        self._policy = PolicyMemory()
        logger.info(
            f"[VECTOR][chief_of_staff] ready gen={generation} hp={self.health_points}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _call_chairman(self, system: str, user: str, timeout: float = 120.0) -> str:
        """Blocking Ollama call — always via ollama_safe, RULE 11."""
        try:
            from core.inference.vectorcode_llm import chat
            from core.prompt_library import get_library as _gl
            _sys_override = _gl().get_for_agent("chief_of_staff")
            effective_system = _sys_override or system

            result = chat(
                model=_CHAIRMAN,
                domain="orchestration",   # gpt-oss-120b → gpt-5 → gpt-oss-120b(groq) → ... → ollama
                messages=[
                    {"role": "system", "content": effective_system},
                    {"role": "user", "content": user},
                ],
                timeout=timeout,
            )
            return result or ""
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] chairman call failed: {e}")
            return ""

    def _fetch_events_since(self, hours: int = 24) -> list[dict]:
        """Pull recent episodic_memory rows ordered ascending by timestamp.

        On failure returns [] but records ``self._events_error`` so callers can tell
        "no events" from "event pull failed" (a failed pull must never read as all-clear).
        """
        self._events_error = None
        cutoff = (
            datetime.datetime.now() - datetime.timedelta(hours=hours)
        ).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT event_type, content, tags, source, timestamp "
                "FROM episodic_memory "
                "WHERE timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] fetch_events failed: {e}")
            self._events_error = str(e) or type(e).__name__
            return []

    def _agent_hp_leaderboard(self) -> list[dict]:
        """Return top-3 agents by HP from the live registry."""
        try:
            from core.city.agent_registry import get_registry

            all_agents = get_registry().list_all()
            alive = [a for a in all_agents if a.get("is_alive", False)]
            alive.sort(key=lambda a: a.get("health_points", 0), reverse=True)
            return alive[:3]
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] hp_leaderboard failed: {e}")
            return []

    def _goal_progress_summary(self) -> str:
        """Pull the latest long-horizon goal facts from semantic memory."""
        try:
            rows = []
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value FROM semantic_memory "
                "WHERE category IN ('goal', 'long_horizon_goal', 'goal_progress') "
                "ORDER BY updated_at DESC LIMIT 5"
            )
            rows = cur.fetchall()
            if not rows:
                return "No long-horizon goal data found."
            return "; ".join(f"{r[0]}: {r[1]}" for r in rows)
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] goal_progress failed: {e}")
            return "Goal progress unavailable."

    def _kiit_today(self) -> str:
        """Best-effort: fetch today's KIIT schedule from semantic memory."""
        try:
            today = datetime.date.today().isoformat()
            result = self._memory.recall_fact(f"kiit_schedule:{today}")
            if result and result.get("value"):
                return result["value"]
            # Fallback: any recent KIIT event
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content FROM episodic_memory "
                "WHERE (tags LIKE '%kiit%' OR source LIKE '%kiit%') "
                "ORDER BY timestamp DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0] if row else "No KIIT schedule data today."
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] kiit_today failed: {e}")
            return "KIIT schedule unavailable."

    def _karpathy_streak(self) -> str:
        """Pull Karpathy streak fact from semantic memory."""
        try:
            result = self._memory.recall_fact("karpathy_streak")
            if result and result.get("value"):
                return f"Karpathy streak: {result['value']}"
            return "Karpathy streak: no data."
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] karpathy_streak failed: {e}")
            return "Karpathy streak: unavailable."

    # ── Core capabilities ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_tags(tags_raw) -> set[str]:
        """Tags arrive as a list, a JSON-encoded list (how episodic.store persists them)
        or a comma-separated string. Naive comma-splitting of '["security", "threat"]'
        yields '["security"' and never matches 'security' (real events were dropped)."""
        if isinstance(tags_raw, str):
            text = tags_raw.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        tags_raw = parsed
                except ValueError:
                    pass
        items = tags_raw if isinstance(tags_raw, (list, tuple, set)) else str(tags_raw or "").split(",")
        return {str(t).strip().strip("[]\"' ").lower() for t in items if str(t).strip()}

    def _classify(self, ev: dict, routine_types: set[str]) -> str:
        ev_type = str(ev.get("event_type") or "").lower()
        content = str(ev.get("content") or "")
        tags = self._parse_tags(ev.get("tags"))

        classification = _NOISE

        # Urgent markers win over the ROUTINE type/substring match, otherwise e.g.
        # 'security_scan' or a 'CRITICAL' heartbeat is classified ROUTINE and dropped.
        if (
            "security" in tags or "threat" in tags or "malware" in tags
            or "security" in ev_type
            or "deadline" in tags or "kiit" in tags or "deadline" in ev_type
            or "CRITICAL" in content
        ):
            classification = _SIGNAL
        elif ev_type in routine_types or any(
            rt in ev_type for rt in ("scan", "sync", "tick", "heartbeat")
        ):
            classification = _ROUTINE
        elif ev_type == "goal_achieved" or "goal_achieved" in tags:
            classification = _SIGNAL
        elif "hp_drop" in ev_type:
            match = re.search(r"(\d+)\s*HP", content)
            if match is None:
                # Unparseable magnitude: cannot prove it is small, so show it.
                classification = _SIGNAL
            elif int(match.group(1)) >= _HP_DROP_SIGNAL_THRESHOLD:
                classification = _SIGNAL
            else:
                classification = _ROUTINE
        elif "council" in tags or "council" in ev_type:
            classification = _SIGNAL
        elif "executive_brief" in tags:
            classification = _SIGNAL
        return classification

    def filter_noise(self, events: list[dict]) -> list[dict]:
        """
        Classify each event as SIGNAL / ROUTINE / NOISE.

        SIGNAL criteria (any match):
          - tags contain 'security' or 'threat'
          - event_type contains 'hp_drop' and magnitude >= _HP_DROP_SIGNAL_THRESHOLD
          - tags contain 'deadline' or 'kiit'
          - event_type is 'goal_achieved'
          - content contains 'CRITICAL' (uppercase)

        ROUTINE: consolidate, research scans, daily review, memory ops.
        NOISE:   everything else.

        Returns only the SIGNAL subset with a 'classification' key injected.
        """
        signals: list[dict] = []
        routine_types = {
            "consolidate", "memory_consolidation", "daily_review",
            "research_scan", "news_scan", "paper_scan", "episodic_store",
            "tick", "heartbeat", "governor_dispatch",
        }

        for ev in events:
            if not isinstance(ev, dict):
                ev = {"event_type": "unparseable_event", "content": str(ev)[:200]}
            try:
                classification = self._classify(ev, routine_types)
            except Exception as e:
                # Fail toward SHOWING the item — never hide an event we could not parse.
                logger.warning(f"[VECTOR][chief_of_staff] classify failed, surfacing event: {e}")
                classification = _SIGNAL
            ev["classification"] = classification
            if classification == _SIGNAL:
                signals.append(ev)

        logger.info(
            f"[VECTOR][chief_of_staff] filter_noise: "
            f"{len(events)} in → {len(signals)} SIGNAL"
        )
        return signals

    async def generate_executive_brief(self) -> dict:
        """
        Produce the 5-bullet executive summary for Arghyadeep.

        Steps:
        1. get_world_state() for live context
        2. Fetch last 24h events
        3. Filter to SIGNAL only
        4. LLM call → structured 5-bullet brief (vector-reasoning)
        5. Write to Obsidian Daily/Executive Brief — {date}.md
        6. Store in episodic_memory

        Returns dict with: brief_text, signal_count, obsidian_ok, date
        """
        date_str = datetime.date.today().isoformat()
        logger.info(f"[VECTOR][chief_of_staff] generate_executive_brief: {date_str}")

        # Step 1 — live world state
        try:
            world_state = self._context.get_world_state()
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] world_state failed: {e}")
            world_state = {}

        # Step 2 — last 24h events
        all_events = self._fetch_events_since(hours=24)

        # Step 3 — filter to SIGNAL
        signals = self.filter_noise(list(all_events))

        # Step 4 — build LLM prompt
        events_error = getattr(self, "_events_error", None)
        events_unavailable = bool(events_error)
        signal_lines = "\n".join(
            f"- [{str(e.get('timestamp') or '')[:16]}] {e.get('event_type', '')}: "
            f"{str(e.get('content') or '')[:120]}"
            for e in signals[:20]
        ) or (
            "EVENT DATA UNAVAILABLE — the episodic event pull failed; "
            "this is NOT an all-clear."
            if events_unavailable
            else "No significant signals today."
        )

        leaderboard = self._agent_hp_leaderboard()
        top3 = "; ".join(
            f"{a.get('name')} ({a.get('health_points')} HP)"
            for a in leaderboard
        ) or "No agents registered."

        goal_summary = self._goal_progress_summary()

        world_snippet = str(world_state)[:400] if world_state else "unavailable"

        prompt = (
            f"Date: {date_str}\n\n"
            f"VECTOR World State (snapshot):\n{world_snippet}\n\n"
            f"Significant events today ({len(signals)} signals):\n{signal_lines}\n\n"
            f"Top 3 agents by HP: {top3}\n\n"
            f"Long-horizon goal progress: {goal_summary}\n\n"
            "Produce a concise 5-bullet executive brief for Arghyadeep Deb. "
            "Use exactly these headers:\n"
            "1. ACCOMPLISHED — What VECTOR did autonomously today\n"
            "2. DECISIONS NEEDED — What requires Arghyadeep's input\n"
            "3. HP LEADERBOARD — Top 3 agents and their status\n"
            "4. GOAL PROGRESS — % toward long-horizon goals\n"
            "5. RECOMMENDED ACTION — One clear action for Arghyadeep today\n\n"
            "Be direct. No filler. Arghyadeep reads this at a glance."
        )

        # RULE 1 — session hydration before LLM call
        hydration = self._context.session_hydration_prompt()

        brief_text = await asyncio.to_thread(self._call_chairman, hydration, prompt)
        llm_ok = bool(brief_text)
        if not brief_text:
            brief_text = (
                f"## Executive Brief — {date_str}\n\n"
                f"1. ACCOMPLISHED — {len(all_events)} events processed.\n"
                f"2. DECISIONS NEEDED — LLM unavailable; check logs. "
                f"Unsummarised signals ({len(signals)}):\n{signal_lines}\n"
                f"3. HP LEADERBOARD — {top3}\n"
                f"4. GOAL PROGRESS — {goal_summary}\n"
                "5. RECOMMENDED ACTION — Check system health."
            )
            logger.warning(
                "[VECTOR][chief_of_staff] chairman unavailable — using fallback brief"
            )
        if events_unavailable:
            brief_text = (
                f"WARNING: event data unavailable ({events_error}) — "
                "signals could not be assessed; do NOT read this brief as all-clear.\n\n"
                + brief_text
            )

        note_content = (
            f"# Executive Brief — {date_str}\n\n"
            f"{brief_text}\n\n"
            f"---\n"
            f"*Generated by ChiefOfStaff · {len(signals)} signals · "
            f"{len(all_events)} total events*"
        )

        # Step 5 — write to Obsidian
        obsidian_ok = False
        try:
            self._obsidian.write_note(
                title=f"Executive Brief — {date_str}",
                content=note_content,
                folder="Daily",
                tags=["executive_brief", "chief_of_staff", "vector", date_str],
            )
            obsidian_ok = True
            logger.info(
                f"[VECTOR][chief_of_staff] executive brief written to Obsidian Daily/"
            )
        except Exception as e:
            logger.error(f"[VECTOR][chief_of_staff] Obsidian write failed: {e}")

        # Step 6 — store in episodic_memory (RULE 8)
        self._memory.store(
            event_type="executive_brief",
            content=f"Executive brief {date_str}: {len(signals)} signals, {len(all_events)} events",
            tags=["executive_brief", "chief_of_staff", "governance"],
            source="chief_of_staff",
        )
        self._memory.store_chain(
            situation="executive_brief_generation",
            goal_ids=["daily_coordination"],
            steps=["get_world_state", "fetch_events", "filter_noise", "llm_brief", "obsidian_write"],
            action="generate_executive_brief",
            outcome=f"{len(signals)} signals; obsidian_ok={obsidian_ok}",
            reward=0.9 if obsidian_ok else 0.5,
        )

        if obsidian_ok:
            self.award_points(40, f"executive_brief {date_str}")
        else:
            self.deduct_points(10, "executive_brief obsidian write failed")

        return {
            "brief_text": brief_text,
            "signal_count": len(signals),
            "event_count": len(all_events),
            "events_unavailable": events_unavailable,
            "llm_ok": llm_ok,
            "obsidian_ok": obsidian_ok,
            "date": date_str,
        }

    async def route_escalation(self, issue: dict) -> dict:
        """
        Route an issue to the appropriate district or escalate to LLM Council.

        Checks DISTRICT_TASK_MAP first (fast keyword match).
        Unknown tasks escalate to governance/llm_council.
        Always logs the routing decision to episodic_memory.

        Returns dict with: routed_to, method, council_result (if escalated)
        """
        from core.city.governor import DISTRICT_TASK_MAP

        if not isinstance(issue, dict):
            issue = {"description": str(issue)} if issue else {}
        issue_type = str(issue.get("type") or issue.get("task_type") or "unknown").lower()
        issue_desc = str(issue.get("description") or issue)

        # Keyword match
        district = None
        for keyword, dist in DISTRICT_TASK_MAP.items():
            if keyword in issue_type:
                district = dist
                break

        method = "keyword_match"
        council_result: dict | None = None
        escalation_error: str | None = None

        if district:
            logger.info(
                f"[VECTOR][chief_of_staff] route_escalation: '{issue_type}' → "
                f"{district} (keyword match)"
            )
        else:
            # Unknown — escalate to LLM Council
            logger.warning(
                f"[VECTOR][chief_of_staff] route_escalation: '{issue_type}' unknown "
                "→ escalating to governance/llm_council"
            )
            method = "council_escalation"
            district = "governance"
            try:
                from districts.governance.llm_council import LLMCouncil

                council = LLMCouncil()
                council_result = await council.convene(
                    question=(
                        f"Which VECTOR district should handle this issue?\n"
                        f"Type: {issue_type}\n"
                        f"Description: {issue_desc[:300]}"
                    ),
                    stakes="medium",
                    requester_hp=self.health_points,
                )
                verdict = str(council_result.get("verdict") or "")
                # Try to extract district name from verdict
                for kw_dist in set(DISTRICT_TASK_MAP.values()):
                    if kw_dist in verdict.lower():
                        district = kw_dist
                        break
                logger.info(
                    f"[VECTOR][chief_of_staff] council verdict → district={district}"
                )
            except Exception as e:
                logger.error(f"[VECTOR][chief_of_staff] council escalation failed: {e}")
                escalation_error = str(e) or type(e).__name__

        # Log the routing decision (RULE 8)
        self._memory.store(
            event_type="escalation_routed",
            content=(
                f"issue='{issue_type}' routed to '{district}' "
                f"method={method}"
                + (f" ESCALATION_FAILED: {escalation_error}" if escalation_error else "")
            ),
            tags=["chief_of_staff", "routing", district],
            source="chief_of_staff",
        )
        if escalation_error:
            self.deduct_points(5, f"route_escalation_failed:{issue_type}")
        else:
            self.award_points(10, f"route_escalation:{issue_type}")

        result = {
            "routed_to": district,
            "method": method,
            "council_result": council_result,
            "issue_type": issue_type,
            "escalation_ok": escalation_error is None,
        }
        if escalation_error:
            result["escalation_error"] = escalation_error
        return result

    async def enforce_consistency(self) -> dict:
        """
        Health-check all districts.

        - Flag any district where ALL living agents have HP <= _DISTRICT_DYING_HP.
        - Trigger EvolutionEngine.check_and_evolve() for dying districts.

        Returns dict with: flagged_districts, evolution_results
        """
        from core.city.agent_registry import get_registry
        from core.city.evolution_engine import EvolutionEngine

        reg = get_registry()
        counts = reg.count_by_district()
        flagged: list[str] = []
        evolution_results: dict[str, dict] = {}

        for district, _ in counts.items():
            agents = reg.get_by_district(district)
            if not agents:
                continue
            alive_agents = [a for a in agents if getattr(a, "health_points", 0) > 0]
            # A district whose agents are ALL dead is the worst case, not a healthy one.
            max_hp = (
                max(getattr(a, "health_points", 0) for a in alive_agents)
                if alive_agents else 0
            )
            if max_hp <= _DISTRICT_DYING_HP:
                flagged.append(district)
                logger.warning(
                    f"[VECTOR][chief_of_staff] enforce_consistency: "
                    f"district '{district}' dying — max HP={max_hp}"
                )
                try:
                    # Use singleton — has constructors registered at boot.
                    # A fresh EvolutionEngine() has zero constructors.
                    # Also pass ALL agents (not just alive) so check_and_evolve()
                    # can find hp==0 agents to respawn — it only evolves dead ones.
                    from core.city.evolution_engine import get_evolution_engine
                    engine = get_evolution_engine()
                    evo_result = await engine.check_and_evolve(agents)
                    evolution_results[district] = evo_result
                    logger.info(
                        f"[VECTOR][chief_of_staff] evolution triggered for "
                        f"'{district}': {evo_result}"
                    )
                except Exception as e:
                    logger.error(
                        f"[VECTOR][chief_of_staff] evolution_engine failed "
                        f"for '{district}': {e}"
                    )
                    evolution_results[district] = {"error": str(e)}

        # Store consistency check result
        self._memory.store(
            event_type="consistency_check",
            content=(
                f"Checked {len(counts)} districts; "
                f"{len(flagged)} dying: {flagged}"
            ),
            tags=["chief_of_staff", "consistency", "governance"],
            source="chief_of_staff",
        )

        if flagged:
            self.deduct_points(5 * len(flagged), f"dying districts: {flagged}")
        else:
            self.award_points(15, "all districts healthy")

        return {
            "flagged_districts": flagged,
            "evolution_results": evolution_results,
            "districts_checked": len(counts),
        }

    async def morning_brief(self) -> dict:
        """
        08:00 morning brief — executive summary + KIIT schedule + Karpathy streak
        + highest-priority goal action for today.
        """
        date_str = datetime.date.today().isoformat()
        logger.info(f"[VECTOR][chief_of_staff] morning_brief: {date_str}")

        brief_result = await self.generate_executive_brief()
        kiit_info = self._kiit_today()
        karpathy = self._karpathy_streak()
        goal_summary = self._goal_progress_summary()

        # RULE 1 — session hydration
        hydration = self._context.session_hydration_prompt()

        morning_prompt = (
            f"Date: {date_str} | Time: 08:00\n\n"
            f"Executive Brief:\n{brief_result.get('brief_text', '')[:800]}\n\n"
            f"KIIT Today: {kiit_info}\n\n"
            f"{karpathy}\n\n"
            f"Goal Progress: {goal_summary}\n\n"
            "Write a crisp morning briefing for Arghyadeep. "
            "Include: priority task for today, any KIIT obligations, "
            "Karpathy reminder if streak is at risk. Under 150 words."
        )

        morning_text = await asyncio.to_thread(
            self._call_chairman, hydration, morning_prompt, 90.0
        )
        if not morning_text:
            morning_text = (
                f"Good morning {date_str}.\n"
                f"KIIT: {kiit_info}\n"
                f"{karpathy}\n"
                "LLM brief unavailable — check logs.\n\n"
                f"{brief_result.get('brief_text', '')}"
            )

        if brief_result.get("events_unavailable"):
            morning_text = (
                "WARNING: event data unavailable — signals could not be assessed; "
                "do NOT read this brief as all-clear.\n\n" + morning_text
            )

        note_content = (
            f"# Morning Brief — {date_str}\n\n"
            f"{morning_text}\n\n"
            f"---\n"
            f"*KIIT: {kiit_info}*\n"
            f"*{karpathy}*"
        )

        obsidian_ok = False
        try:
            self._obsidian.write_note(
                title=f"Morning Brief — {date_str}",
                content=note_content,
                folder="Daily",
                tags=["morning_brief", "chief_of_staff", "vector", date_str],
            )
            obsidian_ok = True
        except Exception as e:
            logger.error(f"[VECTOR][chief_of_staff] morning brief obsidian failed: {e}")

        self._memory.store(
            event_type="morning_brief",
            content=f"Morning brief {date_str}: {len(morning_text)} chars",
            tags=["morning_brief", "chief_of_staff"],
            source="chief_of_staff",
        )

        if obsidian_ok:
            self.award_points(30, f"morning_brief {date_str}")
        else:
            self.deduct_points(5, "morning_brief obsidian failed")

        return {
            "morning_text": morning_text,
            "kiit_info": kiit_info,
            "karpathy": karpathy,
            "obsidian_ok": obsidian_ok,
            "date": date_str,
        }

    async def evening_brief(self) -> dict:
        """
        22:00 evening brief — what was accomplished, what is pending tomorrow,
        HP leaderboard recap.
        """
        date_str = datetime.date.today().isoformat()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        logger.info(f"[VECTOR][chief_of_staff] evening_brief: {date_str}")

        all_events = self._fetch_events_since(hours=16)  # day's work
        signals = self.filter_noise(list(all_events))
        leaderboard = self._agent_hp_leaderboard()
        top3 = "; ".join(
            f"{a.get('name')} ({a.get('health_points')} HP)"
            for a in leaderboard
        ) or "No agents."

        events_error = getattr(self, "_events_error", None)
        accomplished_lines = "\n".join(
            f"- {e.get('event_type', '')}: {str(e.get('content') or '')[:100]}"
            for e in signals[:15]
        ) or (
            "EVENT DATA UNAVAILABLE — the episodic event pull failed; NOT an all-clear."
            if events_error
            else "No significant events."
        )

        # Pending tomorrow from deadline/goals semantic memory
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value FROM semantic_memory "
                "WHERE category IN ('deadline', 'pending_task', 'reminder') "
                "ORDER BY updated_at DESC LIMIT 5"
            )
            pending_rows = cur.fetchall()
            pending_lines = (
                "; ".join(f"{r[0]}: {r[1]}" for r in pending_rows)
                or "No pending tasks recorded."
            )
        except Exception as e:
            logger.warning(f"[VECTOR][chief_of_staff] pending tasks pull failed: {e}")
            pending_lines = "Pending tasks UNAVAILABLE (data pull failed) — not an all-clear."

        hydration = self._context.session_hydration_prompt()

        evening_prompt = (
            f"Date: {date_str} (end of day) | Tomorrow: {tomorrow}\n\n"
            f"Today's accomplishments (signals):\n{accomplished_lines}\n\n"
            f"HP Leaderboard: {top3}\n\n"
            f"Pending tomorrow: {pending_lines}\n\n"
            "Write a concise evening recap for Arghyadeep. "
            "Cover: what VECTOR accomplished, what needs attention tomorrow, "
            "which agents performed best. Under 200 words."
        )

        evening_text = await asyncio.to_thread(
            self._call_chairman, hydration, evening_prompt, 90.0
        )
        if not evening_text:
            evening_text = (
                f"Evening recap {date_str}.\n"
                f"Signals today: {len(signals)}.\n"
                f"{accomplished_lines}\n"
                f"Pending tomorrow: {pending_lines}\n"
                f"HP Leaders: {top3}\n"
                "LLM brief unavailable."
            )
        if events_error:
            evening_text = (
                f"WARNING: event data unavailable ({events_error}) — "
                "do NOT read this recap as all-clear.\n\n" + evening_text
            )

        note_content = (
            f"# Evening Brief — {date_str}\n\n"
            f"{evening_text}\n\n"
            f"---\n"
            f"*{len(all_events)} events · {len(signals)} signals today*\n"
            f"*HP Leaders: {top3}*"
        )

        obsidian_ok = False
        try:
            self._obsidian.write_note(
                title=f"Evening Brief — {date_str}",
                content=note_content,
                folder="Daily",
                tags=["evening_brief", "chief_of_staff", "vector", date_str],
            )
            obsidian_ok = True
        except Exception as e:
            logger.error(f"[VECTOR][chief_of_staff] evening brief obsidian failed: {e}")

        self._memory.store(
            event_type="evening_brief",
            content=f"Evening brief {date_str}: {len(signals)} signals, {len(all_events)} events",
            tags=["evening_brief", "chief_of_staff"],
            source="chief_of_staff",
        )

        if obsidian_ok:
            self.award_points(30, f"evening_brief {date_str}")
        else:
            self.deduct_points(5, "evening_brief obsidian failed")

        return {
            "evening_text": evening_text,
            "signal_count": len(signals),
            "event_count": len(all_events),
            "top_agents": leaderboard,
            "events_unavailable": bool(events_error),
            "obsidian_ok": obsidian_ok,
            "date": date_str,
        }

    # ── Governor dispatch interface ────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        Standard Governor dispatch interface.

        Supported task types:
          "executive_brief"    → generate_executive_brief()
          "morning_brief"      → morning_brief()
          "evening_brief"      → evening_brief()
          "route"              → route_escalation(task["issue"])
          "consistency_check"  → enforce_consistency()
          default              → generate_executive_brief()
        """
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_type = (task.get("type") or "executive_brief").lower()

        try:
            if task_type == "executive_brief":
                result = await self.generate_executive_brief()
            elif task_type == "morning_brief":
                result = await self.morning_brief()
            elif task_type == "evening_brief":
                result = await self.evening_brief()
            elif task_type == "route":
                issue = task.get("issue") or task.get("params") or {}
                result = await self.route_escalation(issue)
            elif task_type == "consistency_check":
                result = await self.enforce_consistency()
            elif task_type == "subconscious":
                result = await self.run_subconscious()
            else:
                logger.info(
                    f"[VECTOR][chief_of_staff] unknown task type '{task_type}' "
                    "→ defaulting to executive_brief"
                )
                result = await self.generate_executive_brief()

            return {"status": "ok", "agent": self.name, "task": task_type, **result}

        except Exception as e:
            logger.error(f"[VECTOR][chief_of_staff] run({task_type}) error: {e}")
            self.deduct_points(30, f"run error: {task_type}")
            return {"status": "error", "agent": self.name, "task": task_type, "error": str(e)}

    async def run_subconscious(self) -> dict:
        """
        Trigger one iteration of SubconsciousLoop.

        The subconscious loop compares the current VECTOR world state against the
        previous situation report and decides: noop | act:<action> | escalate:<reason>.

        Called by the 30-minute APScheduler job and available as a Governor
        task type ("subconscious").

        Returns dict with: decision, elapsed_ms, status
        """
        import time
        t0 = time.monotonic()
        try:
            from districts.chief_of_staff.subconscious_loop import SubconsciousLoop
            loop = SubconsciousLoop()
            result = await loop.run_once()
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if result.get("error"):
                # run_once swallows its own failures into a "noop" decision; that must not
                # be reported as a successful all-quiet tick.
                logger.warning(
                    f"[VECTOR][chief_of_staff] subconscious tick failed: {result['error']}"
                )
                self.deduct_points(5, "subconscious_tick_failed")
                return {"elapsed_ms": elapsed_ms, **result, "status": "error"}
            logger.info(
                f"[VECTOR][chief_of_staff] subconscious tick done "
                f"decision={result.get('decision', '?')} elapsed={elapsed_ms}ms"
            )
            self.award_points(5, "subconscious_tick")
            return {
                "status": "ok",
                "elapsed_ms": elapsed_ms,
                **result,
            }
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(f"[VECTOR][chief_of_staff] run_subconscious failed: {e}")
            self.deduct_points(5, "subconscious_tick_failed")
            return {"status": "error", "error": str(e), "elapsed_ms": elapsed_ms}

    # ── Autonomous scheduled loop ──────────────────────────────────────────────

    async def run_forever(self) -> None:
        """
        RULE 2 — never crashes.
        Schedule:
          08:00 (catch-up until 12:00) → morning_brief(), once/day, retried if undelivered
          22:00 onward → evening_brief(), once/day, retried if undelivered
          Every 30 min → enforce_consistency()
        """
        logger.info("[VECTOR][chief_of_staff] run_forever started")
        _last_consistency_check = datetime.datetime.min
        _done: dict[str, datetime.date] = {}            # brief name -> date delivered
        _attempt: dict[str, datetime.datetime] = {}     # brief name -> last attempt
        _retry_after = datetime.timedelta(minutes=15)

        async def _maybe_brief(name: str, due: bool, now: datetime.datetime) -> None:
            # Once per day, caught up if the 5-minute window was missed (sleep/restart),
            # retried (throttled) if delivery failed instead of being marked sent.
            if not due or _done.get(name) == now.date():
                return
            last = _attempt.get(name)
            if last is not None and now - last < _retry_after:
                return
            _attempt[name] = now
            result = await getattr(self, name)()
            if result.get("obsidian_ok"):
                _done[name] = now.date()
            else:
                logger.warning(
                    f"[VECTOR][chief_of_staff] {name} not delivered — will retry"
                )

        while self.is_alive:
            try:
                now = datetime.datetime.now()

                # Morning brief from 08:00 (catch-up until noon)
                await _maybe_brief("morning_brief", 8 <= now.hour < 12, now)

                # Evening brief from 22:00
                await _maybe_brief("evening_brief", now.hour >= 22, now)

                # Consistency check every 30 minutes
                elapsed = (now - _last_consistency_check).total_seconds()
                if elapsed >= 1800:
                    await self.enforce_consistency()
                    _last_consistency_check = now

            except Exception as e:
                logger.error(f"[VECTOR][chief_of_staff] tick error: {e}")
                self.deduct_points(5, "tick error")

            # Sleep in 1s increments so is_alive is checked regularly (60s per tick).
            for _ in range(60):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)

        logger.warning("[VECTOR][chief_of_staff] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    import tempfile

    async def _smoke():
        cos = ChiefOfStaff()
        assert cos.health_points == 500
        assert cos.name == "ChiefOfStaff"
        assert cos.district == "chief_of_staff"

        # ── filter_noise smoke test (no LLM needed) ──────────────────────────
        fake_events = [
            {"event_type": "daily_review", "content": "10 events reviewed", "tags": "reflection,daily", "source": "daily_reviewer", "timestamp": "2026-05-16T01:00:00"},
            {"event_type": "security_alert", "content": "Threat detected", "tags": "security,threat", "source": "threat_scout", "timestamp": "2026-05-16T09:00:00"},
            {"event_type": "heartbeat", "content": "loop tick ok", "tags": "", "source": "loop", "timestamp": "2026-05-16T10:00:00"},
            {"event_type": "goal_achieved", "content": "KIIT assignment submitted", "tags": "goal_achieved,kiit", "source": "deadline_manager", "timestamp": "2026-05-16T11:00:00"},
            {"event_type": "research_scan", "content": "Scanned 5 papers", "tags": "research,scan", "source": "paper_reader", "timestamp": "2026-05-16T12:00:00"},
        ]
        signals = cos.filter_noise(fake_events)
        assert len(signals) == 2, f"Expected 2 signals, got {len(signals)}: {[s['event_type'] for s in signals]}"
        signal_types = {s["event_type"] for s in signals}
        assert "security_alert" in signal_types
        assert "goal_achieved" in signal_types
        print(f"  filter_noise OK: {len(fake_events)} in → {len(signals)} signals")

        # ── generate_executive_brief with temp Obsidian vault ────────────────
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Daily").mkdir()
            cos._obsidian._vault = vault

            result = await cos.generate_executive_brief()
            assert isinstance(result, dict)
            assert "brief_text" in result
            assert "date" in result
            brief_path = vault / "Daily" / f"Executive Brief — {result['date']}.md"
            assert brief_path.exists(), f"Obsidian note not written: {brief_path}"
            print(f"  generate_executive_brief OK: signal_count={result['signal_count']} obsidian_ok={result['obsidian_ok']}")

        # ── route_escalation smoke test ──────────────────────────────────────
        route = await cos.route_escalation({"type": "git_status", "description": "check recent commits"})
        assert route["routed_to"] == "coding", f"Expected 'coding', got '{route['routed_to']}'"
        assert route["method"] == "keyword_match"
        print(f"  route_escalation OK: {route['issue_type']} → {route['routed_to']}")

        print(f"✅ chief_of_staff.py OK  HP={cos.health_points}")

    asyncio.run(_smoke())
