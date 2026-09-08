# All Agents

**Purpose:** Complete list of all 133+ agents
**Level:** System Level (Level 1)

---

## Overview

VECTOR has 133+ agents distributed across 33 districts. Each agent inherits from AgentBase and has HP (0-1000).

**Key Properties:**
- **133+ agents** — specialized roles
- **HP system** — 0-1000, death at 0
- **Council gate** — >700 HP for voting
- **Ghost memory** — preserved after death

---

## Governance District (01)

### llm_council.py

**Purpose:** Deliberative council for high-stakes decisions
**HP:** Chairman >800, Members >700
**Model:** vector-reasoning + vector-r1 + qwen3:30b-a3b + vector-chairman
**Status:** ✅ IMPLEMENTED

```python
class LLMCouncil(AgentBase):
    async def deliberate(self, decision: dict) -> dict:
        """3-stage deliberation."""
        # Stage 1: Individual votes
        votes = await self._collect_votes(decision)
        
        # Stage 2: Discussion
        discussion = await self._discuss(votes)
        
        # Stage 3: Final vote
        final = await self._final_vote(discussion)
        
        return final
```

---

## Security District (02)

### threat_scout.py
**Purpose:** Process/registry/network scanning
**Status:** ✅ IMPLEMENTED

### node_guard.py
**Purpose:** Node protection
**Status:** ✅ IMPLEMENTED

### malware_hunter.py
**Purpose:** Malware detection (VirusTotal + MIME + LightGBM)
**Status:** ✅ IMPLEMENTED

### privacy_enforcer.py
**Purpose:** Cloud vs local enforcement
**Status:** ✅ IMPLEMENTED

---

## Coding District (03)

### git_bot.py
**Purpose:** Git operations (commit, push, pull)
**Permission:** RED tier for push
**Status:** ✅ IMPLEMENTED

### code_reviewer.py
**Purpose:** AST-based code review
**Status:** ✅ IMPLEMENTED

### architect_bot.py
**Purpose:** Architecture suggestions
**Status:** ✅ IMPLEMENTED

### bug_hunter.py
**Purpose:** Bug detection
**Status:** ✅ IMPLEMENTED

### test_writer.py
**Purpose:** Test generation
**Status:** ✅ IMPLEMENTED

### minimal_change_engineer.py
**Purpose:** Minimum-viable diffs
**Status:** ✅ IMPLEMENTED

### codebase_onboarding_engineer.py
**Purpose:** Codebase exploration
**Status:** ✅ IMPLEMENTED

### rapid_prototyper.py
**Purpose:** Fast prototyping
**Status:** ✅ IMPLEMENTED

---

## Time/Calendar District (04)

### kiit_scraper.py
**Purpose:** KIIT schedule scraping (Playwright)
**Status:** ✅ IMPLEMENTED

### deadline_manager.py
**Purpose:** Deadline tracking
**Status:** ✅ IMPLEMENTED

### time_blocker.py
**Purpose:** Time blocking
**Status:** ✅ IMPLEMENTED

---

## Communications District (05)

### communications_adapter.py
**Purpose:** VectorCode gateway adapter
**Status:** ✅ IMPLEMENTED

### person_model.py
**Purpose:** Person context
**Status:** ✅ IMPLEMENTED

### style_model.py
**Purpose:** Communication style
**Status:** ✅ IMPLEMENTED

---

## Memory Curator District (06)

### consolidation_bot.py
**Purpose:** Episodic → semantic consolidation
**Status:** ✅ IMPLEMENTED

### pattern_finder.py
**Purpose:** Pattern extraction
**Status:** ✅ IMPLEMENTED

---

## Research District (07)

### web_scout.py
**Purpose:** Web research
**Status:** ✅ IMPLEMENTED

### paper_reader.py
**Purpose:** ArXiv paper reading
**Status:** ✅ IMPLEMENTED

### news_aggregator.py
**Purpose:** RSS/news aggregation
**Status:** ✅ IMPLEMENTED

### reddit_miner.py
**Purpose:** Reddit scraping
**Status:** ✅ IMPLEMENTED

### opencli_adapter.py
**Purpose:** OpenCLI integration
**Status:** ✅ IMPLEMENTED

### research_hub.py
**Purpose:** Research coordination
**Status:** ✅ IMPLEMENTED

---

## Skills District (09)

### skill_mapper.py
**Purpose:** Skill graph mapping
**Status:** ✅ IMPLEMENTED

### gap_analyst.py
**Purpose:** Gap analysis
**Status:** ✅ IMPLEMENTED

### mastery_tracker.py
**Purpose:** Skill mastery tracking
**Status:** ✅ IMPLEMENTED

---

## Languages District (10)

### hindi_coach.py
**Purpose:** Hindi language coaching
**Status:** ✅ IMPLEMENTED

### bengali_coach.py
**Purpose:** Bengali language coaching
**Status:** ✅ IMPLEMENTED

### assamese_coach.py
**Purpose:** Assamese language coaching
**Status:** ✅ IMPLEMENTED

### english_coach.py
**Purpose:** English language coaching
**Status:** ✅ IMPLEMENTED

### japanese_coach.py
**Purpose:** Japanese language coaching
**Status:** ✅ IMPLEMENTED

---

## Interview Prep District (11)

### mock_interviewer.py
**Purpose:** Mock interviews
**Status:** ✅ IMPLEMENTED

### report_generator.py
**Purpose:** 50-100 page reports
**Status:** ✅ IMPLEMENTED

### company_researcher.py
**Purpose:** Company research
**Status:** ✅ IMPLEMENTED

### feedback_analyst.py
**Purpose:** Interview feedback
**Status:** ✅ IMPLEMENTED

---

## Learning District (12)

### video_ingestor.py
**Purpose:** Video URL ingestion (yt-dlp)
**Status:** ✅ IMPLEMENTED

### concept_extractor.py
**Purpose:** Concept extraction
**Status:** ✅ IMPLEMENTED

### course_tracker.py
**Purpose:** Course progress
**Status:** ✅ IMPLEMENTED

### note_organizer.py
**Purpose:** Note organization
**Status:** ✅ IMPLEMENTED

---

## Finance District (13)

### upi_parser.py
**Purpose:** UPI SMS parsing (ADB)
**Status:** ✅ IMPLEMENTED

### expense_tracker.py
**Purpose:** Expense tracking
**Status:** ✅ IMPLEMENTED

### budget_analyst.py
**Purpose:** Budget analysis
**Status:** ✅ IMPLEMENTED

### tax_calendar.py
**Purpose:** Indian FY deadlines
**Status:** ✅ IMPLEMENTED

### financial_analyst.py
**Purpose:** Financial analysis
**Status:** ✅ IMPLEMENTED

### fpa_analyst.py
**Purpose:** FP&A analysis
**Status:** ✅ IMPLEMENTED

---

## Health District (14)

### sleep_tracker.py
**Purpose:** Sleep tracking
**Status:** ✅ IMPLEMENTED

### fatigue_monitor.py
**Purpose:** EAR-based fatigue scoring
**Status:** ✅ IMPLEMENTED

### exercise_logger.py
**Purpose:** Exercise logging
**Status:** ✅ IMPLEMENTED

### biometrics_aggregator.py
**Purpose:** Biometric aggregation
**Status:** ✅ IMPLEMENTED

---

## Reflection District (15)

### daily_reviewer.py
**Purpose:** 2AM daily review
**Status:** ✅ IMPLEMENTED

### journal_writer.py
**Purpose:** Obsidian journal writing
**Status:** ✅ IMPLEMENTED

### growth_analyst.py
**Purpose:** Growth analysis
**Status:** ✅ IMPLEMENTED

---

## Startups District (16)

### market_scanner.py
**Purpose:** Nightly Reddit/HN/G2 scan
**Status:** ✅ IMPLEMENTED

### idea_validator.py
**Purpose:** 11-dimension scoring + revenue-velocity gate
**Status:** ✅ IMPLEMENTED

### competitor_spy.py
**Purpose:** Competitor analysis
**Status:** ✅ IMPLEMENTED

### revenue_modeler.py
**Purpose:** Revenue modeling
**Status:** ✅ IMPLEMENTED

---

## Investment District (17)

### stock_analyst.py
**Purpose:** NSE/BSE analysis (NEVER trades)
**Status:** ✅ IMPLEMENTED

### fundamentals_bot.py
**Purpose:** Fundamental analysis
**Status:** ✅ IMPLEMENTED

### technical_bot.py
**Purpose:** Technical analysis
**Status:** ✅ IMPLEMENTED

### sentiment_bot.py
**Purpose:** Sentiment analysis
**Status:** ✅ IMPLEMENTED

---

## Content District (18)

### script_generator.py
**Purpose:** Script generation
**Status:** ✅ IMPLEMENTED

### video_generator.py
**Purpose:** SadTalker + FFmpeg CUDA
**Status:** ✅ IMPLEMENTED

### voice_generator.py
**Purpose:** Voice synthesis
**Status:** ✅ IMPLEMENTED

### uploader.py
**Purpose:** YouTube/Instagram upload
**Status:** ✅ IMPLEMENTED

### comfyui_adapter.py
**Purpose:** ComfyUI integration
**Status:** ✅ IMPLEMENTED

### video_merger.py
**Purpose:** Video merging
**Status:** ✅ IMPLEMENTED

### caption_generator.py
**Purpose:** Caption generation
**Status:** ✅ IMPLEMENTED

### analytics_retriever.py
**Purpose:** Post metrics (YouTube/Instagram)
**Status:** ✅ IMPLEMENTED

### blog_publisher.py
**Purpose:** Dev.to/Hashnode/Medium publishing
**Status:** ✅ IMPLEMENTED

### post_job.py
**Purpose:** Post job tracking
**Status:** ✅ IMPLEMENTED

---

## Agency District (19)

### content_strategist.py
**Purpose:** Content strategy
**Status:** ✅ IMPLEMENTED

### client_manager.py
**Purpose:** Client management
**Status:** ✅ IMPLEMENTED

### performance_tracker.py
**Purpose:** Performance tracking
**Status:** ✅ IMPLEMENTED

### sales_strategist.py
**Purpose:** Sales strategy
**Status:** ✅ IMPLEMENTED

### proposal_strategist.py
**Purpose:** Proposal writing
**Status:** ✅ IMPLEMENTED

---

## Karpathy Lab District (20)

### progress_tracker.py
**Purpose:** 30min/day tracker
**Status:** ✅ IMPLEMENTED

### code_typer.py
**Purpose:** Code typing practice
**Status:** ✅ IMPLEMENTED

### data_prep.py
**Purpose:** Data preparation
**Status:** ✅ IMPLEMENTED

### architecture_builder.py
**Purpose:** Architecture building
**Status:** ✅ IMPLEMENTED

### autoresearch_runner.py
**Purpose:** Auto-research
**Status:** ✅ IMPLEMENTED

---

## Projects District (21)

### project_planner.py
**Purpose:** Project planning
**Status:** ✅ IMPLEMENTED

### deadline_watcher.py
**Purpose:** Deadline alerts (T-7/3/1/0)
**Status:** ✅ IMPLEMENTED

### progress_tracker.py
**Purpose:** Progress tracking
**Status:** ✅ IMPLEMENTED

### doc_writer.py
**Purpose:** Documentation (5 types)
**Status:** ✅ IMPLEMENTED

---

## Remaining Districts (22-25, Bonus)

All agents in remaining districts follow the same pattern:
- Inherit from AgentBase
- Implement `_execute_task(query, task_type)`
- HP-gated for council
- Ghost memory on death

See `32_ALL_DISTRICTS.md` for complete district list.

---

## Agent Summary

| Category | Count |
|----------|-------|
| Governance | 1 |
| Security | 4 |
| Coding | 8 |
| Time/Calendar | 3 |
| Communications | 3 |
| Memory | 2 |
| Research | 6 |
| Skills | 3 |
| Languages | 5 |
| Interview Prep | 4 |
| Learning | 4 |
| Finance | 6 |
| Health | 4 |
| Reflection | 3 |
| Startups | 4 |
| Investment | 4 |
| Content | 10 |
| Agency | 5 |
| Karpathy Lab | 5 |
| Projects | 4 |
| Relationships | 2 |
| Privacy | 2 |
| Pattern Detective | 2 |
| News/Trends | 3 |
| Bonus Districts | ~28 |
| **Total** | **133+** |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `10_AGENT_ARCHITECTURE.md` — Agent base class
- `11_VECTOR_CITY.md` — City structure
- `32_ALL_DISTRICTS.md` — District list

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
