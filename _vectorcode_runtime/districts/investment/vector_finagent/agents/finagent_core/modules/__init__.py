"""
Modules - High-level Agno feature modules

Provides unified access to:
- Memory (conversation history, user preferences, agentic memory)
- Teams (multi-agent collaboration)
- Workflows (complex task orchestration with Parallel, Condition, Loop, Router)
- Knowledge (RAG knowledge bases)
- Reasoning (step-by-step reasoning)
- Session (conversation state persistence, AI summaries, history search)
- Guardrails (PII protection, prompt injection, compliance)
- Evaluation (accuracy, performance, reliability)
- Tracing (debugging, monitoring, audit)
- Compression (token optimization for large datasets)
- Hooks (pre/post processing, rate limiting, cost tracking)
- Output Models (structured Pydantic outputs for financial data)
"""

from .memory_module import MemoryModule, AgenticMemoryModule
from .team_module import TeamModule, TeamBuilder
from .workflow_module import (
    WorkflowModule,
    WorkflowBuilder,
    FinancialWorkflowTemplates
)
from .knowledge_module import KnowledgeModule, KnowledgeBuilder
from .reasoning_module import ReasoningModule, ReasoningBuilder
from .session_module import SessionModule, SessionManager
from .guardrails_module import (
    GuardrailsModule,
    FinancialPIIGuardrail,
    PromptInjectionGuardrail,
    TradingComplianceGuardrail,
    OutputValidationGuardrail
)
from .evaluation_module import (
    EvaluationModule,
    AccuracyEvaluator,
    PerformanceEvaluator,
    ReliabilityEvaluator,
    AgentJudgeEvaluator,
    EvaluationResult
)
from .tracing_module import (
    TracingModule,
    Trace,
    Span,
    AuditLogger
)
from .compression_module import (
    CompressionModule,
    FinancialDataCompressor,
    SummarizeStrategy
)
from .hooks_module import (
    HooksModule,
    Hook,
    InputValidationHook,
    OutputFormattingHook,
    AuditLoggingHook,
    RateLimitHook,
    CostTrackingHook
)
from .output_models import (
    OutputModelRegistry,
    OutputValidator,
    TradeSignal,
    StockAnalysis,
    PortfolioAnalysis,
    RiskAssessment,
    MarketAnalysis,
    ResearchReport,
    TradeAction,
    RiskLevel,
    TimeHorizon,
    Sentiment
)

__all__ = [
    # Memory
    "MemoryModule",
    "AgenticMemoryModule",
    # Teams
    "TeamModule",
    "TeamBuilder",
    # Workflows
    "WorkflowModule",
    "WorkflowBuilder",
    "FinancialWorkflowTemplates",
    # Knowledge
    "KnowledgeModule",
    "KnowledgeBuilder",
    # Reasoning
    "ReasoningModule",
    "ReasoningBuilder",
    # Session
    "SessionModule",
    "SessionManager",
    # Guardrails
    "GuardrailsModule",
    "FinancialPIIGuardrail",
    "PromptInjectionGuardrail",
    "TradingComplianceGuardrail",
    "OutputValidationGuardrail",
    # Evaluation
    "EvaluationModule",
    "AccuracyEvaluator",
    "PerformanceEvaluator",
    "ReliabilityEvaluator",
    "AgentJudgeEvaluator",
    "EvaluationResult",
    # Tracing
    "TracingModule",
    "Trace",
    "Span",
    "AuditLogger",
    # Compression
    "CompressionModule",
    "FinancialDataCompressor",
    "SummarizeStrategy",
    # Hooks
    "HooksModule",
    "Hook",
    "InputValidationHook",
    "OutputFormattingHook",
    "AuditLoggingHook",
    "RateLimitHook",
    "CostTrackingHook",
    # Output Models
    "OutputModelRegistry",
    "OutputValidator",
    "TradeSignal",
    "StockAnalysis",
    "PortfolioAnalysis",
    "RiskAssessment",
    "MarketAnalysis",
    "ResearchReport",
    "TradeAction",
    "RiskLevel",
    "TimeHorizon",
    "Sentiment",
]
