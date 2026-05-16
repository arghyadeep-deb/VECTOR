"""
Feedback Synthesizer — collects and synthesizes feedback about VECTOR itself.

Takes feedback from Arghyadeep (voice notes, Obsidian entries, episodic memory)
and converts it into prioritized improvement recommendations for VECTOR.
"""
import sys
import asyncio
import datetime
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

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
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._vault_path = Path(CONFIG.get("paths", {}).get("obsidian_vault",
                                str(Path.home() / "V.E.C.T.O.R Brain")))
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
                except Exception:
                    pass

                content = e.get("content", "")
                event_type = e.get("event_type", "")

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
            return []

    def collect_from_obsidian(self) -> list[str]:
        """Scan Obsidian vault for feedback notes about VECTOR."""
        feedback = []
        if not self._vault_path.exists():
            return feedback

        # Look for notes with feedback keywords
        feedback_keywords = ["VECTOR feedback", "VECTOR issue", "VECTOR bug", "VECTOR improvement",
                             "doesn't work", "fix VECTOR", "VECTOR should", "annoying", "wrong output"]
        for f in sorted(self._vault_path.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                for kw in feedback_keywords:
                    if kw.lower() in content.lower():
                        # Extract the relevant paragraph
                        for para in content.split("\n\n"):
                            if kw.lower() in para.lower():
                                feedback.append(f"[OBSIDIAN:{f.stem}] {para[:150]}")
                        break
            except Exception:
                pass
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
            response = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=25.0)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return _json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][feedback_synth] synthesis failed: {}", e)

        return {
            "themes": ["system errors", "response quality"],
            "top_improvements": ["Improve error handling", "Add more context to responses"],
            "severity": "low",
            "sentiment": "neutral",
            "quick_wins": ["Add better logging", "Improve error messages"],
        }

    def write_feedback_report(self, synthesis: dict, signal_count: int) -> str:
        """Write feedback synthesis to Obsidian."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d")
        content = (
            f"# VECTOR Feedback Report — {ts}\n\n"
            f"**Severity: {synthesis.get('severity', 'none').upper()}** | "
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

    async def run(self, task: dict) -> dict:
        try:
            days = task.get("days", 7)
            # Collect from all sources
            memory_signals = self.collect_from_memory(days=days)
            obsidian_notes = self.collect_from_obsidian()
            all_signals = memory_signals + obsidian_notes

            # Synthesize
            synthesis = await self.synthesize_feedback(memory_signals, obsidian_notes)
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
