"""VectorCode agent type definitions — 60+ specialized agents."""
import uuid

from core.city.agent_base import AgentBase


def _make_agent(class_name: str, domain: str, preferred_model: str):
    """Factory that builds a VectorCode agent class overriding model after init."""
    def __init__(self):
        super(cls, self).__init__(
            agent_id=str(uuid.uuid4())[:8],
            name=class_name,
            district="coding",
        )
        # Override HP-based model with the task-specific preferred model
        self.model = preferred_model
        self.domain = domain

    cls = type(class_name, (AgentBase,), {"__init__": __init__})
    return cls


# ─── Core domain ──────────────────────────────────────────────────────────────
CoderAgent          = _make_agent("CoderAgent",          "core",     "vector-coder")
ReviewerAgent       = _make_agent("ReviewerAgent",       "core",     "vector-coder")
TesterAgent         = _make_agent("TesterAgent",         "core",     "vector-coder")
DebuggerAgent       = _make_agent("DebuggerAgent",       "core",     "vector-coder")
ArchitectAgent      = _make_agent("ArchitectAgent",      "core",     "vector-reasoning")
DocWriterAgent      = _make_agent("DocWriterAgent",      "core",     "vector-coder")
OptimizerAgent      = _make_agent("OptimizerAgent",      "core",     "vector-coder")
IntegrationAgent    = _make_agent("IntegrationAgent",    "core",     "vector-coder")
RefactorerAgent     = _make_agent("RefactorerAgent",     "core",     "vector-coder")
ProfilerAgent       = _make_agent("ProfilerAgent",       "core",     "vector-coder")
MigratorAgent       = _make_agent("MigratorAgent",       "core",     "vector-reasoning")
ScaffolderAgent     = _make_agent("ScaffolderAgent",     "core",     "vector-coder")
LinterAgent         = _make_agent("LinterAgent",         "core",     "vector-coder")
FormatterAgent      = _make_agent("FormatterAgent",      "core",     "vector-coder")
TypeCheckerAgent    = _make_agent("TypeCheckerAgent",    "core",     "vector-coder")

# ─── Security domain ──────────────────────────────────────────────────────────
SecurityAuditorAgent = _make_agent("SecurityAuditorAgent", "security", "vector-reasoning")
ThreatAnalystAgent   = _make_agent("ThreatAnalystAgent",   "security", "vector-reasoning")
PenTesterAgent       = _make_agent("PenTesterAgent",       "security", "vector-reasoning")
ComplianceAgent      = _make_agent("ComplianceAgent",      "security", "vector-reasoning")
CryptoAgent          = _make_agent("CryptoAgent",          "security", "vector-reasoning")
VulnScannerAgent     = _make_agent("VulnScannerAgent",     "security", "vector-reasoning")
InjectionDetectorAgent = _make_agent("InjectionDetectorAgent", "security", "vector-coder")

# ─── DevOps domain ────────────────────────────────────────────────────────────
GitBotAgent         = _make_agent("GitBotAgent",         "devops",   "vector-coder")
CIAgent             = _make_agent("CIAgent",             "devops",   "vector-coder")
DeployAgent         = _make_agent("DeployAgent",         "devops",   "vector-reasoning")
MonitorAgent        = _make_agent("MonitorAgent",        "devops",   "vector-focus")
InfraAgent          = _make_agent("InfraAgent",          "devops",   "vector-reasoning")
DockerAgent         = _make_agent("DockerAgent",         "devops",   "vector-coder")
K8sAgent            = _make_agent("K8sAgent",            "devops",   "vector-reasoning")
PipelineAgent       = _make_agent("PipelineAgent",       "devops",   "vector-coder")
ReleaseAgent        = _make_agent("ReleaseAgent",        "devops",   "vector-reasoning")

# ─── Research domain ──────────────────────────────────────────────────────────
WebScoutAgent       = _make_agent("WebScoutAgent",       "research", "vector-reasoning")
PaperReaderAgent    = _make_agent("PaperReaderAgent",    "research", "vector-reasoning")
MarketAnalystAgent  = _make_agent("MarketAnalystAgent",  "research", "vector-reasoning")
DataMinerAgent      = _make_agent("DataMinerAgent",      "research", "vector-reasoning")
TrendTrackerAgent   = _make_agent("TrendTrackerAgent",   "research", "vector-reasoning")
NewsAggregatorAgent = _make_agent("NewsAggregatorAgent", "research", "vector-focus")
SummarizerAgent     = _make_agent("SummarizerAgent",     "research", "vector-reasoning")
FactCheckerAgent    = _make_agent("FactCheckerAgent",    "research", "vector-reasoning")
CitationAgent       = _make_agent("CitationAgent",       "research", "vector-reasoning")

# ─── Support domain ───────────────────────────────────────────────────────────
HelpDeskAgent       = _make_agent("HelpDeskAgent",       "support",  "vector-focus")
OnboardingAgent     = _make_agent("OnboardingAgent",     "support",  "vector-focus")
TrainingAgent       = _make_agent("TrainingAgent",       "support",  "vector-reasoning")
FeedbackAgent       = _make_agent("FeedbackAgent",       "support",  "vector-focus")
IncidentAgent       = _make_agent("IncidentAgent",       "support",  "vector-reasoning")
BugTriageAgent      = _make_agent("BugTriageAgent",      "support",  "vector-coder")
EscalationAgent     = _make_agent("EscalationAgent",     "support",  "vector-reasoning")
ReportingAgent      = _make_agent("ReportingAgent",      "support",  "vector-coder")

# ─── Specialist domain ────────────────────────────────────────────────────────
MLEngineerAgent     = _make_agent("MLEngineerAgent",     "core",     "vector-reasoning")
DataEngineerAgent   = _make_agent("DataEngineerAgent",   "core",     "vector-coder")
APIDesignerAgent    = _make_agent("APIDesignerAgent",    "core",     "vector-reasoning")
DBDesignerAgent     = _make_agent("DBDesignerAgent",     "core",     "vector-reasoning")
UIReviewerAgent     = _make_agent("UIReviewerAgent",     "core",     "vector-coder")
AccessibilityAgent  = _make_agent("AccessibilityAgent",  "core",     "vector-coder")
PerformanceAgent    = _make_agent("PerformanceAgent",    "core",     "vector-reasoning")
CacheAgent          = _make_agent("CacheAgent",          "core",     "vector-coder")
NetworkAgent        = _make_agent("NetworkAgent",        "devops",   "vector-reasoning")
StorageAgent        = _make_agent("StorageAgent",        "devops",   "vector-coder")
AuthAgent           = _make_agent("AuthAgent",           "security", "vector-reasoning")
SecretsAgent        = _make_agent("SecretsAgent",        "security", "vector-reasoning")


if __name__ == "__main__":
    import inspect
    import agent_types as at
    agents = [c for _, c in inspect.getmembers(at, inspect.isclass)
              if c.__name__.endswith("Agent") and c.__name__ != "AgentBase"]
    print(f"Agent count: {len(agents)}")
    a = CoderAgent()
    assert a.model == "vector-coder", f"got {a.model}"
    assert a.domain == "core"
    print("agent_types.py OK")


