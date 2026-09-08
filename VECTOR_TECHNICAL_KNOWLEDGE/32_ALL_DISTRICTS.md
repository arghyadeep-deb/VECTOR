# All Districts

**Purpose:** Complete list of all 33 districts
**Level:** System Level (Level 1)

---

## Overview

VECTOR City contains 33 districts, each with specialized agents. The governor routes queries to districts via 180 routing rules.

**Key Properties:**
- **33 districts** — specialized functional areas
- **133+ agents** — distributed across districts
- **180 routing rules** — governor decision tree
- **HP-gated** — agents >700 HP get council vote

---

## Phase 1 Districts (Core)

### 01. governance/

**Purpose:** LLM Council, decision-making
**Agents:** llm_council.py
**HP Gate:** >700 HP for voting
**Status:** ✅ IMPLEMENTED

### 02. security/

**Purpose:** Threat detection, malware scanning
**Agents:** threat_scout.py, node_guard.py, malware_hunter.py, privacy_enforcer.py
**Status:** ✅ IMPLEMENTED

### 03. coding/

**Purpose:** Code generation, review, git
**Agents:** git_bot.py, code_reviewer.py, architect_bot.py, bug_hunter.py, test_writer.py, minimal_change_engineer.py, codebase_onboarding_engineer.py, rapid_prototyper.py
**Status:** ✅ IMPLEMENTED

### 04. time_calendar/

**Purpose:** Schedule management, deadlines
**Agents:** kiit_scraper.py, deadline_manager.py, time_blocker.py
**Status:** ✅ IMPLEMENTED

### 05. communications/

**Purpose:** 30+ messaging platforms
**Agents:** communications_adapter.py, person_model.py, style_model.py
**Status:** ✅ IMPLEMENTED

### 06. memory_curator/

**Purpose:** Memory consolidation, pattern finding
**Agents:** consolidation_bot.py, pattern_finder.py
**Status:** ✅ IMPLEMENTED

### 07. research/

**Purpose:** Web research, paper reading
**Agents:** web_scout.py, paper_reader.py, news_aggregator.py, reddit_miner.py, opencli_adapter.py, research_hub.py
**Status:** ✅ IMPLEMENTED

### 08. intelligence/

**Purpose:** Pattern detection, news trends
**Agents:** (absorbed into news_trends + pattern_detective)
**Status:** ✅ IMPLEMENTED

---

## Phase 2 Districts (Productivity)

### 09. skills/

**Purpose:** Skill mapping, gap analysis
**Agents:** skill_mapper.py, gap_analyst.py, mastery_tracker.py
**Status:** ✅ IMPLEMENTED

### 10. languages/

**Purpose:** Language coaching
**Agents:** hindi_coach.py, bengali_coach.py, assamese_coach.py, english_coach.py, japanese_coach.py
**Status:** ✅ IMPLEMENTED

### 11. interview_prep/

**Purpose:** Interview preparation
**Agents:** mock_interviewer.py, report_generator.py, company_researcher.py, feedback_analyst.py
**Status:** ✅ IMPLEMENTED

### 12. learning/

**Purpose:** Video ingestion, concept extraction
**Agents:** video_ingestor.py, concept_extractor.py, course_tracker.py, note_organizer.py
**Status:** ✅ IMPLEMENTED

### 13. finance/

**Purpose:** Budget tracking, UPI parsing
**Agents:** upi_parser.py, expense_tracker.py, budget_analyst.py, tax_calendar.py, financial_analyst.py, fpa_analyst.py
**Status:** ✅ IMPLEMENTED

### 14. health/

**Purpose:** Sleep tracking, fatigue monitoring
**Agents:** sleep_tracker.py, fatigue_monitor.py, exercise_logger.py, biometrics_aggregator.py
**Status:** ✅ IMPLEMENTED

### 15. reflection/

**Purpose:** Daily review, journal writing
**Agents:** daily_reviewer.py, journal_writer.py, growth_analyst.py
**Status:** ✅ IMPLEMENTED

### 21. projects/

**Purpose:** Project planning, deadline tracking
**Agents:** project_planner.py, deadline_watcher.py, progress_tracker.py, doc_writer.py
**Status:** ✅ IMPLEMENTED

---

## Phase 3 Districts (Business)

### 16. startups/

**Purpose:** Market scanning, idea validation
**Agents:** market_scanner.py, idea_validator.py, competitor_spy.py, revenue_modeler.py
**Status:** ✅ IMPLEMENTED

### 17. investment/

**Purpose:** Stock analysis (NEVER trades)
**Agents:** stock_analyst.py, fundamentals_bot.py, technical_bot.py, sentiment_bot.py
**Status:** ✅ IMPLEMENTED

### 18. content/

**Purpose:** Script generation, video production
**Agents:** script_generator.py, video_generator.py, voice_generator.py, uploader.py, comfyui_adapter.py, video_merger.py, caption_generator.py, analytics_retriever.py, blog_publisher.py, post_job.py
**Status:** ✅ IMPLEMENTED

### 19. agency/

**Purpose:** Content strategy, client management
**Agents:** content_strategist.py, client_manager.py, performance_tracker.py, sales_strategist.py, proposal_strategist.py
**Status:** ✅ IMPLEMENTED

### 20. karpathy_lab/

**Purpose:** 30min/day learning tracker
**Agents:** progress_tracker.py, code_typer.py, data_prep.py, architecture_builder.py, autoresearch_runner.py
**Status:** ✅ IMPLEMENTED

### 22. relationships/

**Purpose:** Contact management
**Agents:** contact_manager.py, communication_analyst.py
**Status:** ✅ IMPLEMENTED

### 23. privacy/

**Purpose:** Data flow auditing
**Agents:** data_flow_auditor.py, privacy_enforcer.py
**Status:** ✅ IMPLEMENTED

### 24. pattern_detective/

**Purpose:** Behavior analysis
**Agents:** behavior_analyst.py, habit_finder.py
**Status:** ✅ IMPLEMENTED

### 25. news_trends/

**Purpose:** AI news, opportunity spotting
**Agents:** ai_news_bot.py, market_trends_bot.py, opportunity_spotter.py
**Status:** ✅ IMPLEMENTED

---

## Bonus Districts

### calls/

**Purpose:** Call handling
**Agents:** call_screener.py, transcription_bot.py, voice_responder.py
**Status:** ✅ IMPLEMENTED

### ops/

**Purpose:** SRE, DevOps, incidents
**Agents:** sre_monitor.py, devops_automator.py, incident_commander.py
**Status:** ✅ IMPLEMENTED

### data_analytics/

**Purpose:** Data insights, benchmarks
**Agents:** analytics_reporter.py, performance_benchmarker.py, data_engineer.py
**Status:** ✅ IMPLEMENTED

### personal_growth/

**Purpose:** Behavioral nudges, Zettelkasten
**Agents:** behavioral_nudge_engine.py, zk_steward.py, feedback_synthesizer.py
**Status:** ✅ IMPLEMENTED

### documentation/

**Purpose:** Technical writing
**Agents:** technical_writer.py, doc_generator.py
**Status:** ✅ IMPLEMENTED

### qa/

**Purpose:** Quality assurance
**Agents:** reality_checker.py, evidence_collector.py, workflow_architect.py, api_tester.py, test_results_analyzer.py, accessibility_auditor.py, tool_evaluator.py, workflow_optimizer.py, model_qa_specialist.py
**Status:** ✅ IMPLEMENTED

### chief_of_staff/

**Purpose:** Morning/evening briefs
**Agents:** chief_of_staff.py
**Status:** ✅ IMPLEMENTED

### marketing/

**Purpose:** SEO, growth, social media
**Agents:** seo_specialist.py, growth_hacker.py, social_media_strategist.py, content_creator.py, ai_citation_strategist.py
**Status:** ✅ IMPLEMENTED

### design/

**Purpose:** UI/UX design
**Agents:** ui_designer.py, ux_researcher.py, image_prompt_engineer.py
**Status:** ✅ IMPLEMENTED

---

## District Summary

| Phase | Districts | Agents |
|-------|-----------|--------|
| Phase 1 | 8 | ~30 |
| Phase 2 | 8 | ~35 |
| Phase 3 | 10 | ~40 |
| Bonus | 7 | ~28 |
| **Total** | **33** | **133+** |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `11_VECTOR_CITY.md` — City structure
- `33_ALL_AGENTS.md` — Agent list

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
