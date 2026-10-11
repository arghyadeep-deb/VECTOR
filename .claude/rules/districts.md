# Districts

> This is the ORIGINAL 25-district build plan. The current manifest is the source of truth: 274 agents across 41 configured districts. Treat runtime inventory evidence from `ManifestLoader.inventory()` as canonical rather than stale prose counts.

## Phase 1 — Build These First (Days 1-25)
```
01. governance/      — LLM Council (700+ HP only vote)
02. security/        — ThreatScout, MalwareHunter, NodeGuard
03. coding/          — GitBot, CodeReviewer, BugHunter, ArchitectBot
04. time_calendar/   — KIITScraper (Playwright), DeadlineManager
05. communications/  — vectorcode channel adapters (Telegram, WhatsApp, Discord, Slack, Gmail, 30+ platforms)
06. memory_curator/  — LightRAG, ConsolidationBot, PatternFinder
07. research/        — OpenCLI autoresearch, PaperReader, NewsAggregator
08. intelligence/    — PatternDetective, NewsTrends
```

## Phase 2 — Days 26-40
```
09. skills/          — SkillMapper (pre-seeded), GapAnalyst
10. languages/       — HindiCoach(P1), BengaliCoach(P2), AssameseCoach(P3), EnglishCoach, JapaneseCoach
11. interview_prep/  — MockInterviewer, ReportGenerator (50-100 page output)
12. learning/        — VideoIngestor (any URL), ConceptExtractor
13. finance/         — UPIParser (ADB SMS), BudgetAnalyst, TaxCalendar
14. health/          — SleepTracker, FatigueMonitor (camera-based)
15. reflection/      — DailyReviewer, JournalWriter → Obsidian vault
```

## Phase 3 — Days 41-50
```
16. startups/        — MarketScanner (nightly Reddit/HN/G2), IdeaValidator
17. investment/      — StockAnalyst NSE/BSE, FundamentalsBot (ANALYSIS ONLY, never trades)
18. content/         — ScriptGen, SadTalker (local RTX), FFmpeg CUDA, YouTube+Instagrapi
19. agency/          — ContentStrategist, ClientManager
20. karpathy_lab/    — 30min/day tracker, OpenMythos training pipeline
21. projects/        — ProjectPlanner, DeadlineWatcher
22. relationships/   — ContactManager, CommunicationAnalyst
23. privacy/         — DataFlowAuditor (cloud vs local enforcement)
24. pattern_detective/ — BehaviorAnalyst, HabitFinder
25. news_trends/     — AINewsBot, OpportunitySpotter
```

## Obsidian Vault
```
Path: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\   (VECTOR_VAULT_PATH in .env; the code default in core/config.py is ~\V.E.C.T.O.R Brain, a separate stray folder that only holds Daily\ and Reflections\)
VECTOR writes to: Daily\ Reflections\ Council\ Agent HP\ Research\ Interviews\
VECTOR reads from: all .md files (watchdog ingests within 30s)
```
