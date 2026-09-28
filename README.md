# VECTOR: Virtual Entity for Cognitive Tasks & Operational Reasoning

An autonomous multi-agent AI system designed as a Darwinian civilization where AI agents evolve through performance-based HP (Hit Points) system, governed by a council of high-performing agents.

## 🎯 Core Concept

VECTOR City is a Darwinian multi-agent civilization where:
- **VECTOR governs** as the central intelligence layer
- **Agents are citizens** with HP (0-1000) that fluctuate based on performance
- **Agents die at 0 HP** but preserve "ghost memory" for next-generation inheritance
- **You are the God layer** - setting initial conditions and overseeing the system

## 🏗️ Detailed Architecture

### Three-Layer System

```
Layer A — Devices:        Legion Pro 5 (primary) | Old Android Termux (ambient) | Daily phone (alerts)
Layer B — Cloud:          Cloudflare Worker + D1 + KV (api/wrangler.toml) | Supabase | Turso
Layer C — APIs:           Claude Sonnet (Pro chat, build sessions) | Gemini 2.5 Pro (free) | Ollama local
```

### Core Intelligence Flow

VECTOR operates on a continuous autonomous loop with layered processing:

#### 1. Observation Layer (0.5s intervals)
- Sensing module collects data from all device layers
- Environmental monitoring through APIs and direct device access
- Preprocessing of incoming data streams

#### 2. Cognitive Processing (Event-driven)
```
Context Engine → Goal System → Decision Engine → Policy Check → Permission Gateway → Execution
```

#### 3. Action Layer (Permission-gated)
- All actions filtered through Permission Gateway (GREEN/YELLOW/RED)
- Zero direct LLM access to external systems
- Action validation before execution

#### 4. Reflection Layer (2AM cycle)
- Thought chain analysis and storage
- Performance evaluation and HP adjustment
- Memory consolidation and pattern extraction
- Ghost memory preservation for deceased agents

### Component Architecture

#### Context Engine (`core/loop/context_engine.py`)
- Unified world state management
- Session hydration prompt generation before every LLM call
- Cross-domain data integration
- Real-time state synchronization

#### Goal System (`core/loop/goal_system.py`)
- Three-tier goal hierarchy: LONG (years), MID (months), SHORT (days/weeks)
- Pre-seeded foundational goals
- Dynamic goal adjustment based on outcomes
- Priority balancing system

#### Decision Engine (`core/loop/decision_engine.py`)
- Multi-candidate scoring system (4 candidates per decision cycle)
- Scoring formula: 
  - Goal Alignment (30%)
  - Confidence (25%) 
  - Policy Compliance (20%)
  - Urgency (15%)
  - Timing Factors (10%)
  - Cost Efficiency (-5%)
- Candidate selection and ranking

#### Policy Engine (`core/loop/policy.py`)
- Pre-action scoring (`get_score()`)
- Post-action learning (`update_from_outcome()`)
- Adaptive policy adjustment
- Risk assessment integration

#### Permission Gateway (`core/loop/permission_gateway.py`)
- Triple-state system: GREEN (proceed), YELLOW (review), RED (block)
- Security sandbox for all LLM interactions
- Zero-trust architecture for external access
- Audit logging for all permission decisions

#### Reasoning Memory (`core/loop/reasoning_memory.py`)
- Complete thought chain preservation
- Training data generation for future fine-tuning
- Pattern recognition storage
- Cross-agent knowledge transfer mechanism

### Agent Lifecycle & Evolution

#### HP (Hit Points) System
```
Performance-Based Adjustments:
+100 HP  user approved output
+50 HP   task completed well  
+30 HP   output used by VECTOR
+40 HP   council voted for them
-30 HP   task failed
-50 HP   output ignored 3x
-100 HP  critical error
```

#### Access Tiers
Agents are born at 500 HP. HP selects the agent's local model (`AgentBase._calculate_model`):
- **≥800 HP**: `vector-dev` (devstral-based)
- **600–799 HP**: `vector-r1` (deepseek-r1-based)
- **400–599 HP**: `vector-focus` (gemma4:e4b)
- **200–399 HP**: `vector-reasoning` (qwen3:14b)
- **1–199 HP**: `vector-ambient` (gemma4:e2b)
- **≥700 HP**: Council eligibility
- **0 HP**: Agent death + ghost memory preservation

Point awards are damped (repeating the same reason decays the award, and awards shrink near 1000); deductions are not.

#### Ghost Memory Protocol
- Deleted agents' reasoning chains preserved
- Next-generation agents inherit fragmented memory
- Prevents complete knowledge loss
- Enables evolutionary learning

### District Architecture (planned as 25 modules; the repo now has 38 district directories, 39 districts and 170 agents in `config/agent_manifest.yaml`)

Each district follows a standardized agent template with:
- AgentBase inheritance (logging, fallback chains, health monitoring)
- Independent decision-making within domain
- HP-based performance tracking
- Inter-district communication protocols

#### Phase 1 Districts (Foundation)
1. **Governance**: LLM Council (700+ HP only), Proposal System, Vote Tracking
2. **Security**: ThreatScout (anomaly detection), MalwareHunter (signature analysis), NodeGuard (intrusion prevention)
3. **Coding**: GitBot (repository management), CodeReviewer (quality analysis), BugHunter (defect detection), ArchitectBot (design suggestions)
4. **Time/Calendar**: KIITScraper (academic schedule automation), DeadlineManager (priority-based scheduling)
5. **Communications**: VectorCode (messaging backbone), Kimi K2.6 adapter (multilingual support)
6. **Memory Curator**: LightRAG (vector storage), ConsolidationBot (memory merging), PatternFinder (trend detection)
7. **Research**: OpenCLI (automated command-line research), PaperReader (academic parsing), NewsAggregator (current events)
8. **Intelligence**: PatternDetective (cross-domain correlations), NewsTrends (media analysis)

### Technical Implementation Details

#### Core Loop (`core/loop/autonomous_loop.py`)
- Main execution controller
- Timing regulation (0.5s observation cycles)
- Error handling and recovery
- Resource monitoring

#### API Layer (`core/api/`)
- FastAPI-based REST endpoints
- WebSocket connections for real-time updates
- Authentication and rate limiting
- Documentation generation

#### Cloud Services
- **Cloudflare**:
  - Worker: Unified brain relay for heartbeat, command queue, and memory reads
  - Workers: Edge computing for lightweight tasks
  - D1: SQL database for structured data
  - R2: Object storage for media/files
  - KV: Key-value store for caching
- **Databases**:
  - Supabase: Relational data and authentication
  - Turso: Edge-optimized SQLite for low-latency access

#### Local Processing
- **Ollama**: Local LLM inference for privacy-sensitive tasks
- **Model Management**: Dynamic model loading/unloading based on HP tiers
- **GPU Utilization**: RTX 5070 Ti optimization for local inference

### Data Flow & Integration

```
Device Sensors → Context Engine → 
[Goal System → Decision Engine → Policy → Permission Gateway] → 
[District Agents] → 
Action Execution → 
Results → Reasoning Memory → 
HP Adjustment → 
[Ghost Memory Archive] → 
Reflection (2AM) → 
Obsidian Vault Sync
```

### Extensibility Patterns

#### Adding New Districts
1. Create district folder in `districts/`
2. Implement AgentBase inheritance
3. Register district in configuration
4. Establish inter-district communication protocols
5. Define HP earning/loss criteria specific to domain

#### Custom Agent Development
1. Extend AgentBase class
2. Implement domain-specific `think()` and `act()` methods
3. Define HP adjustment rules
4. Set up required permissions
5. Integrate with memory and goal systems

## 🏘️ Detailed District Structure (original 25-district plan — see `districts/` and `config/agent_manifest.yaml` for what exists now)

### Phase 1 - Core Foundation (Days 1-25)
01. **governance/** 
   - LLM Council: 700+ HP agents only, proposal/vote system
   - Constitutional Agent: Rule enforcement and amendment
   - Election Manager: Periodic leadership cycles
   - Policy Archivist: Historical decision tracking

02. **security/**
   - ThreatScout: Behavioral anomaly detection, ML-based threat identification
   - MalwareHunter: Signature analysis, heuristic scanning, quarantine systems
   - NodeGuard: Network monitoring, intrusion prevention, firewall management
   - AuditTrail: Security event logging, forensic analysis, compliance reporting

03. **coding/**
   - GitBot: Repository automation, branch management, merge conflict resolution
   - CodeReviewer: Static analysis, style checking, security vulnerability scanning
   - BugHunter: Defect reproduction, root cause analysis, fix suggestion generation
   - ArchitectBot: Design pattern recommendation, technical debt assessment, refactoring planning

04. **time_calendar/**
   - KIITScraper: Academic schedule extraction, exam timetable parsing, assignment tracking
   - DeadlineManager: Priority-based scheduling, reminder system, workload balancing
   - MeetingOptimizer: Calendar analysis, conflict resolution, time-block suggestions
   - HolidayTracker: Cultural observance recognition, planning assistance

05. **communications/**
   - VectorCode: Message routing, protocol translation, delivery confirmation
   - Kimi K2.6 Adapter: Multilingual support, translation quality assessment
   - NotificationManager: Priority-based alerting, channel selection, do-not-disturb
   - LanguageDetector: Automatic language identification, dialect recognition

06. **memory_curator/**
   - LightRAG: Vector storage, similarity search, knowledge graph integration
   - ConsolidationBot: Memory merging, duplicate removal, importance weighting
   - PatternFinder: Trend detection, anomaly identification, predictive modeling
   - ForgettingCurve: Memory decay modeling, spaced repetition optimization

07. **research/**
   - OpenCLI: Automated terminal-based research, command chaining, result synthesis
   - PaperReader: PDF parsing, citation extraction, methodology analysis
   - NewsAggregator: Multi-source collection, bias detection, trend analysis
   - DeepDiver: Topic exploration, expert identification, resource recommendation

08. **intelligence/**
   - PatternDetective: Cross-domain correlation analysis, emergent behavior detection
   - NewsTrends: Media sentiment analysis, topic modeling, predictive trend casting
   - SignalProcessor: Noise filtering, anomaly detection, feature extraction
   - CorrelationEngine: Statistical relationship discovery, causation vs correlation analysis

### Phase 2 - Personal Development (Days 26-40)
09. **skills/**
   - SkillMapper: Competency tracking, gap analysis, learning path recommendation
   - GapAnalyst: Skill deficiency identification, remediation planning, progress tracking
   - ProficiencyTracker: Mastery level assessment, certification preparation
   - SkillDecayMonitor: Skill atrophy prediction, refreshment scheduling

10. **languages/**
    - HindiCoach(P1): Conversational practice, grammar correction, cultural context
    - BengaliCoach(P2): Script instruction, idiom training, regional variation
    - AssameseCoach(P3): Pronunciation guidance, literature appreciation
    - EnglishCoach: Advanced writing, academic communication, public speaking
    - JapaneseCoach: Kanji learning, honorific systems, business etiquette

11. **interview_prep/**
    - MockInterviewer: Realistic simulation, feedback generation, performance analytics
    - QuestionBank: Domain-specific question curation, difficulty adaptation
    - STARHelper: Situation-Task-Action-Response framework guidance
    - ReportGenerator: 50-100 page comprehensive preparation guides

12. **learning/**
    - VideoIngestor: URL-based video extraction, transcription, summarization
    - ConceptExtractor: Key idea identification, relationship mapping, flashcard generation
    - KnowledgeMapper: Learning path optimization, prerequisite identification
    - RetentionOptimizer: Spaced repetition scheduling, active recall promotion

13. **finance/**
    - UPIParser: ADB SMS extraction, transaction categorization, spending analysis
    - BudgetAnalyst: Forecasting, variance analysis, optimization recommendations
    - TaxCalculator: Liability estimation, deduction identification, filing assistance
    - InvestmentAdvisor: Portfolio analysis, risk assessment, strategy suggestions (non-executing)

14. **health/**
    - SleepTracker: Duration monitoring, quality assessment, circadian rhythm analysis
    - FatigueMonitor: Camera-based eye tracking, blink rate analysis, drowsiness detection
    - VitalSignsLogger: Health metric aggregation, trend analysis, anomaly detection
    - WellnessAdvisor: Lifestyle recommendations, habit formation support, goal setting

15. **reflection/**
    - DailyReviewer: End-of-day analysis, accomplishment tracking, lesson extraction
    - JournalWriter: Automated entry generation, prompt-based writing, privacy controls
    - ObsidianSync: Bidirectional vault synchronization, conflict resolution, metadata preservation
    - PatternRecognizer: Behavioral trend identification, habit formation tracking

### Phase 3 - Advanced Applications (Days 41-50)
16. **startups/**
    - MarketScanner: Nightly Reddit/HackerNews/G2 monitoring, opportunity identification
    - IdeaValidator: Feasibility analysis, market sizing, competitor analysis
    - PitchDeckGenerator: Automated presentation creation, investor targeting
    - MentorMatcher: Advisor recommendation, expertise alignment, availability checking

17. **investment/**
    - StockAnalyst NSE/BSE: Fundamental analysis, technical indicators, valuation models
    - FundamentalsBot: Financial statement analysis, ratio calculation, trend identification (ANALYSIS ONLY)
    - RiskAssessor: Volatility measurement, scenario testing, stress analysis
    - PortfolioOptimizer: Asset allocation suggestions, rebalancing recommendations

18. **content/**
    - ScriptGen: Video/script generation, dialogue creation, narrative structuring
    - SadTalker: Local RTX-powered lip-sync animation, expression generation
    - FFmpegCUDA: GPU-accelerated video processing, format conversion, compression
    - SocialMediaManager: YouTube+Instagrapi integration, posting scheduling, engagement analytics

19. **agency/**
    - ContentStrategist: Audience analysis, platform optimization, editorial planning
    - ClientManager: Relationship tracking, communication history, satisfaction metrics
    - ProposalGenerator: Customized offering creation, pricing analysis, timeline estimation
    - DeliveryTracker: Project monitoring, milestone tracking, quality assurance

20. **karpathy_lab/**
    - 30min/Day Tracker: Consistent practice monitoring, streak maintenance, goal alignment
    - OpenMythos Training Pipeline: Mythological dataset processing, model fine-tuning, evaluation
    - ExperimentTracker: Hypothesis testing, result documentation, reproducibility assurance
    - KnowledgeSynthesizer: Cross-disciplinary connection identification, insight generation

21. **projects/**
    - ProjectPlanner: Scope definition, resource allocation, timeline creation
    - DeadlineWatcher: Milestone monitoring, risk identification, contingency planning
    - GanttGenerator: Visual timeline creation, dependency mapping, progress visualization
    - RetrospectiveFacilitator: Lesson learned extraction, process improvement suggestion

22. **relationships/**
    - ContactManager: Interaction history, preference tracking, communication optimization
    - CommunicationAnalyst: Tone analysis, response pattern recognition, effectiveness measurement
    - ConflictResolver: Disagreement mediation, solution finding, prevention strategies
    - BondStrengthMonitor: Relationship health assessment, nurturing recommendations

23. **privacy/**
    - DataFlowAuditor: Cloud vs local enforcement monitoring, policy compliance verification
    - ConsentManager: Permission tracking, expiration alerts, renewal management
    - Anonymizer: PII identification, data masking, re-encryption protocols
    - PrivacyImpactAssessor: Risk evaluation, mitigation planning, regulatory compliance

24. **pattern_detective/**
    - BehaviorAnalyst: Action sequence recognition, habit identification, anomaly detection
    - HabitFinder: Routine detection, trigger identification, modification suggestion
    - SequencePredictor: Next-action forecasting, probability assessment, confidence intervals
    - DeviationSpotter: Outlier identification, root cause analysis, intervention recommendation

25. **news_trends/**
    - AINewsBot: Artificial intelligence development tracking, breakthrough detection
    - OpportunitySpotter: Emerging technology identification, application potential assessment
    - TrendForecaster: Future direction prediction, confidence intervals, scenario planning
    - ImpactAnalyzer: Societal effect evaluation, ethical consideration analysis, policy recommendation

## 🧠 Obsidian Vault Integration Details

VECTOR maintains bidirectional synchronization with an Obsidian vault for persistent knowledge storage:

### Vault Structure
```
C:\Users\Arghyadeep\V.E.C.T.O.R Brain\
├── Daily\
│   ├── Reflections\
│   │   ├── 2026-05-13.md
│   │   └── ...
│   ├── Council\
│   │   ├── meetings\
│   │   └── decisions\
│   ├── Agent HP\
│   │   ├── agents\
│   │   └── history\
│   ├── Research\
│   │   ├── papers\
│   │   └── experiments\
│   └── Interviews\
│       ├── transcripts\
│       └── analyses\
└── Templates\
    ├── agent_report.md
    ├── research_note.md
    └── meeting_log.md
```

### Sync Mechanisms
- **Write Operations**: VECTOR generates markdown files in appropriate directories
- **Read Operations**: File system watcher detects changes within 30 seconds
- **Conflict Resolution**: Timestamp-based merging with manual override capability
- **Metadata Preservation**: Frontmatter retention for tagging and categorization
- **Link Maintenance**: Wikilink preservation and backlink updating

### Knowledge Flow
1. Agents generate insights during operation
2. Reasoning Memory aggregates related thoughts
3. Reflection period (2AM) creates structured summaries
4. DailyReviewer creates journal entries
5. JournalWriter formats content for Obsidian
6. Files written to vault directory
7. Obsidian indexes new/changed content
8. User can review, expand, and link knowledge
9. VECTOR reads updated vault content in next cycle

## 🛠️ Technical Stack Deep Dive

### Core Components

#### Autonomous Loop (`core/loop/autonomous_loop.py`)
```python
class AutonomousLoop:
    def __init__(self):
        self.context_engine = ContextEngine()
        self.goal_system = GoalSystem()
        self.decision_engine = DecisionEngine()
        self.permission_gateway = PermissionGateway()
        
    async def run(self):
        while True:
            # Observe (0.5s)
            await self.context_engine.update()
            
            # Think (Event-driven)
            goals = self.goal_system.get_active_goals()
            context = self.context_engine.get_state()
            candidates = self.decision_engine.generate_candidates(goals, context)
            
            # Act (Permission-gated)
            approved_actions = []
            for candidate in candidates:
                if self.permission_gateway.check(candidate):
                    approved_actions.append(candidate)
                    
            # Execute actions
            results = await self._execute_actions(approved_actions)
            
            # Reflect (2AM cycle)
            if self._is_reflection_time():
                await self._reflection_cycle(results)
                
            await asyncio.sleep(0.5)
```

#### Context Engine (`core/loop/context_engine.py`)
- Singleton pattern for global state access
- Thread-safe updates with asyncio locks
- Serializable state for persistence
- Change notification system for subscribers
- Compression for large state objects

#### Decision Engine (`core/loop/decision_engine.py`)
- Weighted scoring with dynamic adjustment
- Candidate generation templates per domain
- Uncertainty quantification for confidence scoring
- Cost modeling including API usage, time, and resources
- Temporal decay factors for timing considerations

#### Permission Gateway (`core/loop/permission_gateway.py`)
- Three-tier permission system with escalation paths
- Sandbox execution environments for different risk levels
- Audit trail with cryptographic hashing
- Emergency override procedures
- Integration with external security services

### Supported Technologies with Versions

#### Runtime Environment
- **Python**: 3.12 (minimum; PEP 695 generics in use, runtime tested on 3.13)
- **AsyncIO**: Built-in Python 3.12+ features
- **Pydantic**: 2.7.0 (data validation)
- **Loguru**: 0.7.2 (logging)
- **Typer**: 0.9.0 (CLI interface)

#### Data Storage & Databases
- **Supabase**: PostgreSQL with real-time subscriptions
- **Turso**: libSQL (SQLite fork) with sync capabilities
- **Redis**: 7.2+ (caching, session storage)
- **LiteVector**: Custom vector storage for LightRAG

#### Machine Learning & AI
- **Ollama**: 0.3.0+ (local LLM serving)
- **LightRAG**: 0.1.0+ (retrieval-augmented generation)
- **Sentence Transformers**: 3.0.1 (embedding generation)
- **scikit-learn**: 1.5.0 (traditional ML utilities)

#### Web & APIs
- **FastAPI**: 0.110.0 (high-performance API)
- **Uvicorn**: 0.30.0 (ASGI server)
- **WebSockets**: Real-time bidirectional communication
- **HTTPX**: 0.27.0 (async HTTP client)

#### DevOps & Deployment
- **Docker**: 24.0.0+ (containerization)
- **Cloudflare Workers**: Serverless deployment for the cloud brain relay
- **GitHub Actions**: CI/CD pipeline automation
- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization dashboard

#### Frontend & Interface
- **Streamlit**: 1.35.0 (internal tools and dashboards)
- **React**: 18.3.0 (web interfaces where needed)
- **Tailwind CSS**: 3.4.0 (utility-first styling)
- **shadcn/ui**: Component library for consistent UI

### Performance Characteristics

#### Latency Targets
- **Observation Cycle**: ≤500ms (hard constraint)
- **Decision Making**: ≤200ms (95th percentile)
- **Action Execution**: Variable by domain, <5s for 90% of actions
- **Reflection Cycle**: ≤5min (during off-peak hours)

#### Throughput Capacity
- **Concurrent Agents**: 50+ active agents
- **Daily Decisions**: 10,000+ decisions per day
- **Memory Storage**: 1M+ thought chains retainable
- **API Calls**: 1000+ external API calls/hour (rate-limited)

#### Resource Utilization
- **CPU**: <70% average utilization on Legion Pro 5
- **GPU**: <80% utilization during local LLM inference
- **Memory**: <16GB RAM usage under normal load
- **Storage**: <100GB for operational data (excluding media)

### Security Architecture

#### Defense in Depth
1. **Network Layer**: Cloudflare WAF and Worker authentication
2. **Application Layer**: Permission Gateway, input validation, output sanitization
3. **Data Layer**: Encryption at rest and in transit, PII detection
4. **Access Layer**: Role-based access, API key rotation, session management
5. **Monitoring Layer**: Audit logging, anomaly detection, alerting

#### Data Protection
- **Encryption**: AES-256 for data at rest, TLS 1.3 for data in transit
- **PII Handling**: Automatic detection, redaction, and consent tracking
- **Data Minimization**: Only essential data stored, regular purging schedules
- **User Control**: Export/deletion capabilities, consent management

#### Threat Mitigation
- **Prompt Injection**: Multi-layer validation, sandbox execution
- **Model Poisoning**: Input validation, output verification, ensemble checks
- **Data Exfiltration**: Network monitoring, API call validation, anomaly detection
- **Privilege Escalation**: Least privilege principle, privilege separation

## 📊 Current Development Status

> The authoritative, dated status file is `docs/OPEN_ISSUES.md`. Counts below were checked against the code on 2026-09-25; whether each piece behaves correctly in a live run is tracked there, not here.

### What exists in the repo
- Autonomous loop with observe / think / act / reflect (2AM `reflect_loop`) — `core/loop/autonomous_loop.py`
- Context engine with session hydration — `core/loop/context_engine.py`
- Permission Gateway with GREEN/YELLOW/RED tiers — `core/loop/permission_gateway.py`
- Decision engine with the weighted scoring formula — `core/loop/decision_engine.py`
- Goal system (3 horizons) — `core/brain/goal_system.py`
- HP system with award/deduct/death/ghost memory — `core/city/agent_base.py` (+ `core/security/hp_validator.py`)
- 38 district directories, 39 districts and 170 agents in `config/agent_manifest.yaml` (`documentation` is in the manifest without a directory)
- 31 LLM providers — `core/inference/llm_providers.py`; local-vs-cloud routing — `core/inference/route_policy.py`
- FastAPI backend (`core/api/`), `frontend/` HUD served at `/hud/`, Cloudflare Worker (`api/`)
- Obsidian vault integration — `core/memory/obsidian_sync.py` (vault lives beside the repo at `../V.E.C.T.O.R. Brain/`)

### Known open work
See `docs/OPEN_ISSUES.md` section 0 and `KNOWN_ISSUES.md`. Owner-side items (wake-word recordings, Termux phone node, publishing credentials) are in `TASKS.md`.

## 🚀 Getting Started Guide

### System Requirements
- **Hardware**: 
  - Primary: Legion Pro 5 or equivalent (RTX 3060+ recommended)
  - Optional: Android device for Termux ambient layer
  - Optional: Secondary device for alerts/notifications
- **Storage**: 50GB+ SSD recommended
- **Memory**: 16GB RAM minimum, 32GB+ preferred
- **OS**: Windows 11 (primary), Linux/Android (optional layers)

### Software Dependencies
```bash
# Core requirements
python>=3.12
fastapi>=0.110.0
uvicorn>=0.30.0
pydantic>=2.7.0
loguru>=0.7.2
ollama>=0.3.0

# District-specific (install as needed)
playwright>=1.40.0
lightrag>=0.1.0
sentence-transformers>=3.0.1
supabase>=2.0.0
turso>=0.5.0
```

### Setup Instructions

1. **Environment Preparation**
   ```bash
   # Clone repository
   git clone https://github.com/yourusername/VECTOR.git
   cd VECTOR
   
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configuration**
   ```bash
   # Local development can run with defaults.
   # For production, copy the template and fill real secrets outside git:
   cp .env.hardened.example .env.hardened
   
   # Required production values:
   # - VECTOR_API_KEY
   # - VECTOR_JWT_SECRET
   # - VECTOR_COMFYUI_PATH if using sidecars
   ```

3. **Service Initialization**
   ```bash
   # Start required services in order:
   
   # 1. Local LLM (if using)
   ollama serve &
   
   # 2. Database connections (handled by app)
   
   # 3. Start VECTOR core
   python -m core.loop.autonomous_loop
   ```

4. **Verification**
   - Check logs for startup confirmation
   - Verify API endpoints responding at http://localhost:8000
   - Run `python run_vector.py doctor`
   - Run `GET /health/hardened-readiness` before production use
   - Observe initial district agent spawns in logs
   - Confirm Obsidian vault integration (if configured)

### Development Workflow

```bash
# Running tests
pytest tests/

# Code formatting
black .
isort .

# Type checking
mypy .

# Security scanning
bandit -r .

# Documentation generation
mkdocs serve
```

## 📈 Future Roadmap Enhancements

### Phase 1 Completion Goals
- Full 8-district operational foundation
- Stable HP system with observable evolution
- Reliable autonomous loop with reflection cycles
- Basic user interaction dashboard
- Initial knowledge base seeded in Obsidian

### Phase 2 Objectives
- Personal development district completion
- Language learning and skill tracking systems
- Financial and health monitoring integration
- Advanced communication and relationship management

### Phase 3 Vision
- Entrepreneurial and investment assistance
- Content creation and agency support
- Advanced research and innovation capabilities
- Full societal simulation capabilities

### Long-term Aspirations
- Cross-VECTOR collaboration networks
- Emergent behavior study and guidance
- Ethical AI development framework
- Human-AI symbiosis optimization systems

## 🤝 Community & Contribution Guidelines

While VECTOR is primarily a personal research project, structured contributions are welcome:

### Contribution Types
1. **District Implementations**: New specialized agents following templates
2. **Core Improvements**: Performance, security, or reliability enhancements
3. **Documentation**: Clear explanations, usage examples, tutorials
4. **Bug Reports**: Reproducible issues with expected vs actual behavior
5. **Feature Requests**: Well-scoped enhancements aligned with project vision

### Contribution Process
1. Fork the repository
2. Create feature branch from `dev`
3. Implement changes following coding standards
4. Add/update tests as appropriate
5. Submit pull request with clear description
6. Address review feedback promptly
7. Maintainers will merge after approval

### Coding Standards
- Follow existing code style in modified files
- Type hints for all public functions
- Comprehensive docstrings for public APIs
- Unit tests for new functionality
- Security review for access-modifying changes
- Performance considerations for core loop changes

## 🙏 Acknowledgments

VECTOR builds upon and is inspired by:

### Research Foundations
- Autonomous agent systems and multi-agent frameworks
- Cognitive architectures (ACT-R, SOAR, LIDA)
- Swarm intelligence and evolutionary computation
- Knowledge graphs and semantic web technologies

### Technical Inspirations
- LangChain and LlamaIndex for LLM orchestration
- AutoGPT and BabyAGIT for agent concepts
- Obsidian for personal knowledge management
- Various open-source LLM projects and utilities

### Personal Influences
- Academic background in Computer Science and Engineering
- Professional experience in software architecture
- Passion for AI safety and beneficial development
- Commitment to ethical technology advancement

---

*VECTOR: Building the future of autonomous AI civilization through structured evolution, principled governance, and continuous learning.*

**Current Version**: 0.1.0-alpha (Phase 1 Development)  
**Last Updated**: May 2026  
**Developed by**: Arghyadeep Deb | KIIT CSE 2023-27  
**Hardware Platform**: Legion Pro 5 | RTX 5070 Ti 12GB | 32GB RAM  

*"In the simulation of intelligence, we may find the keys to understanding both artificial and natural cognition."*
