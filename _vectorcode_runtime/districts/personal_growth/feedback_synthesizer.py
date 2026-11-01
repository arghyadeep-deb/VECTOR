"""
Feedback Synthesizer — collects and synthesizes feedback about VECTOR itself.

Takes feedback from Arghyadeep (voice notes, Obsidian entries, episodic memory)
and converts it into prioritized improvement recommendations for VECTOR.
"""

import asyncio
import datetime
import re
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

class FeedbackSynthesizer(AgentBase):
    """
    Synthesizes feedback about VECTOR from multiple sources into
    prioritized, actionable improvement recommendations.
    """

    def __init__(self):
        super().__init__(agent_id="feedback_synth_001", name="FeedbackSynthesizer", district="personal_growth")
        self.capabilities = ["feedback", "none", "personal_growth", "synthesis"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._vault_path = Path(CONFIG.get("paths", {}).get("obsidian_vault",
                                str(Path.home() / "V.E.C.T.O.R Brain")))
        self._source_errors: list[str] = []
        logger.info("[VECTOR][feedback_synth] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    def collect_from_memory(self, days: int = 7) -> list[str]:
        """Collect feedback signals from episodic memory (errors, HP deductions, ignored outputs)."""
        try:
            mem = self._get_memory()
            events = mem.recall("", limit=200)
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            feedback_signals = []

            for e in events:
                ts_str = e.get("timestamp", "") or e.get("created_at", "")
                try:
                    ts = datetime.datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=datetime.timezone.utc)
                    if ts < cutoff:
                        continue
                except Exception as exc:
                    # Unparseable timestamp: cannot prove it is inside the window.
                    logger.debug("[VECTOR][feedback_synth] skip event, bad timestamp {!r}: {}", ts_str, exc)
                    continue

                content = e.get("content", "") or ""
                event_type = e.get("event_type", "") or ""

                # Collect failure signals
                if "error" in event_type.lower() or "failed" in content.lower():
                    feedback_signals.append(f"[FAILURE] {content[:120]}")
                elif "output_ignored" in event_type.lower():
                    feedback_signals.append(f"[IGNORED] {content[:120]}")
                elif "deduct_points" in content.lower():
                    feedback_signals.append(f"[HP_LOSS] {content[:120]}")

            return feedback_signals[:30]
        except Exception as e:
            logger.warning("[VECTOR][feedback_synth] memory collection failed: {}", e)
            self._source_errors.append(f"memory: {e}")
            return []

    def collect_from_obsidian(self) -> list[str]:
        """Scan Obsidian vault for feedback notes about VECTOR."""
        feedback = []
        if not self._vault_path.exists():
            logger.warning("[VECTOR][feedback_synth] vault not found: {}", self._vault_path)
            self._source_errors.append(f"obsidian: vault not found: {self._vault_path}")
            return feedback

        # Look for notes with feedback keywords
        feedback_keywords = ["VECTOR feedback", "VECTOR issue", "VECTOR bug", "VECTOR improvement",
                             "doesn't work", "fix VECTOR", "VECTOR should", "annoying", "wrong output"]
        # Exclude our own reports ("VECTOR Feedback <date>.md" contains the
        # keyword "VECTOR feedback") so output is never re-ingested as input.
        candidates = [
            f for f in self._vault_path.rglob("*.md")
            if not f.name.startswith("VECTOR Feedback ")
        ]
        for f in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                for kw in feedback_keywords:
                    if kw.lower() in content.lower():
                        # Extract the relevant paragraph
                        for para in content.split("\n\n"):
                            if kw.lower() in para.lower():
                                feedback.append(f"[OBSIDIAN:{f.stem}] {para[:150]}")
                        break
            except Exception as exc:
                logger.warning("[VECTOR][feedback_synth] unreadable note {}: {}", f.name, exc)
        return feedback[:20]

    async def synthesize_feedback(self, signals: list[str], obsidian_notes: list[str]) -> dict:
        """LLM synthesizes all signals into prioritized improvements."""
        all_feedback = signals + obsidian_notes
        if not all_feedback:
            return {
                "themes": [],
                "top_improvements": ["Continue current development trajectory"],
                "severity": "none",
                "sentiment": "positive",
            }

        prompt = (
            f"Synthesize feedback signals about VECTOR AI personal assistant:\n\n"
            f"Signals ({len(all_feedback)}):\n"
            + "\n".join(f"- {s}" for s in all_feedback[:20])
            + "\n\nProvide JSON:\n"
            f'{{"themes": ["list of recurring themes"], '
            f'"top_improvements": ["top 3 specific actionable improvements ranked by impact"], '
            f'"severity": "none|low|medium|high|critical", '
            f'"sentiment": "positive|neutral|negative", '
            f'"quick_wins": ["2 things fixable in <1 day"]}}'
        )
        try:
            import json as _json
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("feedback_synthesizer") or ""
            _msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
            response = chat(model=self._model, messages=_msgs, timeout=25.0)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                parsed = _json.loads(match.group())
                if isinstance(parsed, dict):
                    for key in ("themes", "top_improvements", "quick_wins"):
                        val = parsed.get(key, [])
                        if isinstance(val, str):
                            val = [val]
                        parsed[key] = [str(v) for v in val] if isinstance(val, list) else []
                    parsed["severity"] = str(parsed.get("severity") or "none").lower()
                    parsed["sentiment"] = str(parsed.get("sentiment") or "neutral").lower()
                    return parsed
        except Exception as e:
            logger.warning("[VECTOR][feedback_synth] synthesis failed: {}", e)

        # Never fabricate canned "findings" for real signals: report failure.
        return {
            "themes": [],
            "top_improvements": [],
            "quick_wins": [],
            "severity": "unknown",
            "sentiment": "unknown",
            "synthesis_failed": True,
        }

    def write_feedback_report(self, synthesis: dict, signal_count: int) -> str:
        """Write feedback synthesis to Obsidian."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d")
        content = (
            f"# VECTOR Feedback Report — {ts}\n\n"
            f"**Severity: {str(synthesis.get('severity') or 'none').upper()}** | "
            f"Sentiment: {synthesis.get('sentiment', 'neutral')}\n"
            f"*Signals collected: {signal_count}*\n\n"
            f"## Recurring Themes\n"
            + "\n".join(f"- {t}" for t in synthesis.get("themes", []))
            + "\n\n## Top Improvements (Priority Order)\n"
            + "\n".join(f"{i+1}. {imp}" for i, imp in enumerate(synthesis.get("top_improvements", [])))
            + "\n\n## Quick Wins\n"
            + "\n".join(f"- {w}" for w in synthesis.get("quick_wins", []))
        )
        try:
            report_path = self._vault_path / f"VECTOR Feedback {ts}.md"
            report_path.write_text(content, encoding="utf-8")
            logger.info("[VECTOR][feedback_synth] report written: {}", report_path)
            return str(report_path)
        except Exception as e:
            logger.warning("[VECTOR][feedback_synth] report write failed: {}", e)
            return ""

    async def answer_personal_growth_question(self, query: str) -> str:
        """Answer a free-text question instead of blindly re-running the
        full feedback synthesis pipeline (which writes a new report file
        to the vault and new memory entries on every call, regardless of
        what was actually asked — KNOWN_ISSUES bug pattern: a real,
        unrelated file-write side effect from a stray conversational
        message). Grounded in a lightweight real signal count, not a full
        re-synthesis."""
        try:
            signals = self.collect_from_memory(days=7)
            context = f"{len(signals)} feedback signal(s) collected from memory in the last 7 days."
        except Exception:
            context = "Feedback signal count unavailable right now."
        prompt = (
            "You are VECTOR's FeedbackSynthesizer in the personal_growth "
            "district — you collect and synthesize feedback signals about "
            "the owner's own behavior/work. Answer the owner's question "
            f"using this real context; do not invent data you don't have:"
            f"\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][feedback_synth] answer_personal_growth_question failed: {}", e)
            return context

    async def run(self, task: dict) -> dict:
        query = (
            (task.get("params") or {}).get("query")
            or task.get("query")
            or task.get("text")
            or ""
        ).strip()
        if query:
            answer = await self.answer_personal_growth_question(query)
            if answer:
                self.award_points(10, "personal_growth_question_answered")
                return {"status": "ok", "response": answer}

        try:
            params = task.get("params") if isinstance(task.get("params"), dict) else {}
            days = task.get("days") or params.get("days") or 7
            self._source_errors = []
            # Collect from all sources
            memory_signals = self.collect_from_memory(days=days)
            obsidian_notes = self.collect_from_obsidian()
            all_signals = memory_signals + obsidian_notes
            source_errors = list(self._source_errors)

            if not all_signals and source_errors:
                # Nothing readable: this is NOT "no issues".
                logger.error("[VECTOR][feedback_synth] no feedback source readable: {}", source_errors)
                return {"status": "error", "error": "no feedback source readable", "source_errors": source_errors}

            # Synthesize
            synthesis = await self.synthesize_feedback(memory_signals, obsidian_notes)
            if synthesis.get("synthesis_failed"):
                self.deduct_points(10, "feedback_synthesis_llm_failed")
                return {
                    "status": "error",
                    "error": "synthesis failed",
                    "signals_collected": len(all_signals),
                    "source_errors": source_errors,
                }
            report_path = self.write_feedback_report(synthesis, len(all_signals))

            # Store synthesis in memory
            self._get_memory().store(
                event_type="feedback_synthesized",
                content=f"Feedback: {len(all_signals)} signals, severity={synthesis.get('severity')}, {len(synthesis.get('top_improvements',[]))} improvements",
                tags=["personal_growth", "feedback", "improvement"],
                context={**synthesis, "signal_count": len(all_signals)},
                source="feedback_synthesizer",
            )

            severity = synthesis.get("severity", "none")
            if severity in ("none", "low"):
                self.award_points(40, "feedback_positive")
            elif severity == "medium":
                self.award_points(25, "feedback_medium_issues")
            else:
                self.award_points(15, "feedback_critical_issues_found")
                logger.warning("[VECTOR][feedback_synth] CRITICAL feedback: {}", synthesis.get("top_improvements"))

            return {
                "status": "ok",
                "signals_collected": len(all_signals),
                "synthesis": synthesis,
                "report_path": report_path,
                "source_errors": source_errors,
            }

        except Exception as e:
            logger.error("[VECTOR][feedback_synth] {}", e)
            self.deduct_points(30, "feedback_synthesis_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FeedbackSynthesizer()
        signals = agent.collect_from_memory(days=30)
        print(f"[OK] collect_from_memory: {len(signals)} signals")
        notes = agent.collect_from_obsidian()
        print(f"[OK] collect_from_obsidian: {len(notes)} notes")
        synthesis = await agent.synthesize_feedback(
            ["[FAILURE] decision engine error", "[HP_LOSS] task failed"],
            ["[OBSIDIAN:Daily] VECTOR should remember context better"]
        )
        print(f"[OK] synthesize: severity={synthesis.get('severity')} themes={synthesis.get('themes')[:2]}")
        result = await agent.run({"days": 7})
        print(f"[OK] run: status={result['status']} signals={result.get('signals_collected',0)}")
        print("feedback_synthesizer.py OK")

    asyncio.run(_smoke())
