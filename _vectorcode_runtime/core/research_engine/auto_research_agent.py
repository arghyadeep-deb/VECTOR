"""Auto research agent — orchestrates the full hypothesis-to-report pipeline."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from .models import Hypothesis, ExperimentDesign, ExperimentResult, AnalysisResult, ResearchReport
from .experiment_designer import ExperimentDesigner
from .sandbox_executor import SandboxExecutor
from .result_analyzer import ResultAnalyzer
from .report_assembler import ReportAssembler


class AutoResearchAgent:
    def __init__(
        self,
        designer: Optional[ExperimentDesigner] = None,
        executor: Optional[SandboxExecutor] = None,
        analyzer: Optional[ResultAnalyzer] = None,
        assembler: Optional[ReportAssembler] = None,
    ):
        self.designer = designer or ExperimentDesigner()
        self.executor = executor or SandboxExecutor()
        self.analyzer = analyzer or ResultAnalyzer()
        self.assembler = assembler or ReportAssembler()
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"HYP-{ts}-{self._id_counter:03d}"

    def generate_hypothesis(self, topic: str) -> Hypothesis:
        logger.info("Generating hypothesis for topic: {}", topic)
        patterns = self._get_memory_patterns(topic)

        variables = {}
        expected = ""
        if patterns:
            variables = {"key_patterns": patterns}
            expected = f"Patterns detected: {', '.join(patterns[:3])}"

        return Hypothesis(
            id=self._next_id(),
            title=f"Hypothesis on {topic}",
            description=f"Investigate the effects and characteristics of {topic} based on available data and memory patterns.",
            variables=variables,
            expected_outcome=expected,
            confidence=0.6,
            status="proposed",
            created_at=datetime.now(timezone.utc).isoformat(),
            source="auto_research_agent",
        )

    def _get_memory_patterns(self, topic: str) -> list[str]:
        patterns: list[str] = []
        try:
            from core.memory.episodic import EpisodicMemory
            memory = EpisodicMemory()
            results = memory.recall(topic, limit=5)
            for r in results:
                content = r.get("content", "") if isinstance(r, dict) else str(r)
                if len(content) > 100:
                    content = content[:100]
                if content:
                    patterns.append(content)
        except ImportError:
            logger.warning("EpisodicMemory not available — skipping memory patterns")
        except Exception as exc:
            logger.warning("Memory pattern retrieval failed: {}", exc)
        return patterns

    def design_experiment(self, hypothesis: Hypothesis) -> ExperimentDesign:
        return self.designer.design(hypothesis)

    def execute_experiment(self, design: ExperimentDesign, code: str = "") -> ExperimentResult:
        if not code:
            code = self._default_experiment_code(design)
        return self.executor.execute(design, code)

    def analyze_results(self, result: ExperimentResult) -> AnalysisResult:
        return self.analyzer.analyze(result)

    def assemble_report(
        self,
        hypothesis: Hypothesis,
        design: ExperimentDesign,
        analysis: AnalysisResult,
    ) -> ResearchReport:
        return self.assembler.assemble(hypothesis, design, analysis)

    def run_full_cycle(self, topic: str, experiment_code: str = "") -> ResearchReport:
        logger.info("Starting full research cycle for topic: {}", topic)
        hypothesis = self.generate_hypothesis(topic)
        logger.info("Step 1/5 — Hypothesis generated: {} ({})", hypothesis.id, hypothesis.title)

        design = self.design_experiment(hypothesis)
        logger.info("Step 2/5 — Experiment designed: {} ({})", design.experiment_type, design.hypothesis_id)

        result = self.execute_experiment(design, experiment_code)
        logger.info("Step 3/5 — Experiment executed: status={}", result.status)

        analysis = self.analyze_results(result)
        logger.info("Step 4/5 — Analysis complete: supports_hypothesis={}", analysis.supports_hypothesis)

        report = self.assemble_report(hypothesis, design, analysis)
        logger.info("Step 5/5 — Report assembled: {} sections", len(report.sections))

        hypothesis.status = "accepted" if analysis.supports_hypothesis else "rejected"
        logger.info("Full research cycle complete for topic '{}'", topic)
        return report

    def run_from_hypothesis(self, hypothesis: Hypothesis, code: str = "") -> ResearchReport:
        logger.info("Running full cycle from existing hypothesis: {} ({})", hypothesis.id, hypothesis.title)
        design = self.design_experiment(hypothesis)
        result = self.execute_experiment(design, code)
        analysis = self.analyze_results(result)
        report = self.assemble_report(hypothesis, design, analysis)
        report = self._validate_results(report)
        hypothesis.status = "accepted" if analysis.supports_hypothesis else "rejected"
        return report

    async def scheduled_research(self, interval_hours: int = 6) -> None:
        logger.info("Scheduled research started — fires every {}h", interval_hours)
        while True:
            try:
                # Sleep FIRST. Firing a full cycle at startup pushed blocking network
                # work onto an executor thread immediately, which made shutdown/cancel
                # hang on the unjoinable thread (found 2026-07-08 via the test suite).
                await asyncio.sleep(interval_hours * 3600)
                topics = self._suggest_research_topics()
                for topic in topics:
                    logger.info("Scheduled research on topic: {}", topic)
                    report = await asyncio.to_thread(self.run_full_cycle, topic)
                    logger.info("Scheduled research completed: {} — supports={}", report.sections.get("title", "?"), report.analysis.supports_hypothesis if report.analysis else "N/A")
                logger.info("Scheduled research cycle complete — sleeping {}h", interval_hours)
            except asyncio.CancelledError:
                logger.info("Scheduled research cancelled")
                break
            except Exception as exc:
                logger.error("Scheduled research error: {}", exc)
                await asyncio.sleep(300)

    def _suggest_research_topics(self) -> list[str]:
        topics: list[str] = []
        try:
            from core.memory.episodic import EpisodicMemory
            memory = EpisodicMemory()
            patterns = memory.recall("research gap open question", limit=3)
            for p in patterns:
                content = p.get("content", "") if isinstance(p, dict) else str(p)
                if content and len(content) > 10:
                    topics.append(content[:80])
        except ImportError:
            logger.warning("EpisodicMemory unavailable for topic suggestions")
        except Exception as exc:
            logger.warning("Topic suggestion failed: {}", exc)
        if not topics:
            topics = ["recent advances in AI agents", "LLM benchmark performance trends", "evaluation methodology for autonomous systems"]
        return topics

    def _validate_results(self, report: ResearchReport) -> ResearchReport:
        warnings: list[str] = []
        if report.analysis is None:
            warnings.append("No analysis data available")
        elif report.analysis.statistical_tests is None or len(report.analysis.statistical_tests) == 0:
            warnings.append("No statistical tests were performed")
        elif report.analysis.significance >= 0.05:
            warnings.append("Results are not statistically significant (p >= 0.05)")
        if report.experiment and report.experiment.sample_size < 10:
            warnings.append(f"Small sample size ({report.experiment.sample_size}) — results may not be reliable")
        if warnings:
            logger.warning("Report validation: {}", "; ".join(warnings))
            if report.sections is None:
                report.sections = {}
            report.sections["validation_warnings"] = warnings
        return report

    def _default_experiment_code(self, design: ExperimentDesign) -> str:
        n = design.sample_size
        return f'''\
import random
import statistics
import math

def run_experiment():
    random.seed(42)
    n = {n}

    control = [random.gauss(100, 15) for _ in range(n)]
    treatment = [random.gauss(105, 15) for _ in range(n)]

    # SandboxExecutor._extract_stats() parses "STAT:" lines from the
    # subprocess's stdout, not from a logger — the sandbox's restricted
    # __builtins__ doesn't define `logger` at all (no imports allowed for
    # it, and it isn't injected), so logger.info() here would raise
    # NameError and fail every experiment with 0 data points.
    print("STAT:control_mean:" + str(statistics.mean(control)))
    print("STAT:treatment_mean:" + str(statistics.mean(treatment)))
    print("STAT:control_std:" + str(statistics.stdev(control)))
    print("STAT:treatment_std:" + str(statistics.stdev(treatment)))

    return {{
        "control": {{"mean": statistics.mean(control), "std": statistics.stdev(control), "n": n}},
        "treatment": {{"mean": statistics.mean(treatment), "std": statistics.stdev(treatment), "n": n}},
        "delta": statistics.mean(treatment) - statistics.mean(control),
    }}
'''
