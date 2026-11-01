"""
VECTOR Research Engine — core/research_engine/

spec-10: Research Lab module for hypothesis-driven experimentation,
statistical analysis, and automated report generation.

Public API:
    from core.research_engine import (
        Hypothesis, ExperimentDesign, ExperimentResult,
        AnalysisResult, ResearchReport,
        ExperimentDesigner, SandboxExecutor,
        ResultAnalyzer, ReportAssembler, AutoResearchAgent,
    )
"""

from loguru import logger

from .__version__ import __version__
from .models import (
    Hypothesis,
    ExperimentDesign,
    ExperimentResult,
    AnalysisResult,
    ResearchReport,
)
from .experiment_designer import ExperimentDesigner
from .sandbox_executor import SandboxExecutor
from .result_analyzer import ResultAnalyzer
from .report_assembler import ReportAssembler
from .auto_research_agent import AutoResearchAgent
from .bootstrap_sandbox import BootstrapSandbox

logger.info("[VECTOR] research_engine.spec-10 loaded (v{})", __version__)

__all__ = [
    "__version__",
    "Hypothesis",
    "ExperimentDesign",
    "ExperimentResult",
    "AnalysisResult",
    "ResearchReport",
    "ExperimentDesigner",
    "SandboxExecutor",
    "ResultAnalyzer",
    "ReportAssembler",
    "AutoResearchAgent",
    "BootstrapSandbox",
]
