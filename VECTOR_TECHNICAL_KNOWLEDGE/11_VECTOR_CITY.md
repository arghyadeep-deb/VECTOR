# VECTOR City — Districts and Governance

**Purpose:** 33+ districts, governance structure, council  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR City consists of 33+ specialized districts, each containing agents that handle specific domains. Districts are governed by an LLM Council for high-stakes decisions.

**Key Properties:**
- **33+ districts** — specialized domains
- **133+ agents** — distributed across districts
- **LLM Council** — HP > 700 agents vote on high-stakes decisions
- **180 routing rules** — governor routes queries to districts
- **Autonomous operation** — districts operate independently

**File:** `districts/*/`  
**Status:** ✅ ALL 33+ DISTRICTS BUILT

---

## District List

### Phase 1 Districts (Core)

| # | District | Purpose | Agents | Status |
|---|----------|---------|--------|--------|
| 01 | governance/ | LLM Council, governance | llm_council.py | ✅ |
| 02 | security/ | Threat detection | threat_scout.py, node_guard.py, malware_hunter.py | ✅ |
| 03 | coding/ | Code generation | git_bot.py, code_reviewer.py, architect_bot.py, bug_hunter.py, test_writer.py | ✅ |
| 04 | time_calendar/ | Scheduling | kiit_scraper.py, deadline_manager.py, time_blocker.py | ✅ |
| 05 | communications/ | Messaging | communications_adapter.py, person_model.py, style_model.py | ✅ |
| 06 | memory_curator/ | Memory management | consolidation_bot.py, pattern_finder.py | ✅ |
| 07 | research/ | Research | web_scout.py, paper_reader.py, news_aggregator.py, reddit_miner.py, opencli_adapter.py, research_hub.py | ✅ |
| 08 | intelligence/ | Intelligence | (via news_trends + pattern_detective) | ✅ |

### Phase 2 Districts (Life Management)

| # | District | Purpose | Agents | Status |
|---|----------|---------|--------|--------|
| 09 | skills/ | Skill tracking | skill_mapper.py, gap_analyst.py, mastery_tracker.py | ✅ |
| 10 | languages/ | Language learning | hindi_coach.py, bengali_coach.py, assamese_coach.py, english_coach.py, japanese_coach.py | ✅ |
| 11 | interview_prep/ | Interview prep | mock_interviewer.py, report_generator.py, company_researcher.py, feedback_analyst.py | ✅ |
| 12 | learning/ | Video learning | video_ingestor.py, concept_extractor.py, course_tracker.py, note_organizer.py | ✅ |
| 13 | finance/ | Finance | upi_parser.py, expense_tracker.py, budget_analyst.py, tax_calendar.py | ✅ |
| 14 | health/ | Health tracking | sleep_tracker.py, fatigue_monitor.py, exercise_logger.py, biometrics_aggregator.py | ✅ |
| 15 | reflection/ | Reflection | daily_reviewer.py, journal_writer.py, growth_analyst.py | ✅ |

### Phase 3 Districts (Advanced)

| # | District | Purpose | Agents | Status |
|---|----------|---------|--------|--------|
| 16 | startups/ | Startup validation | market_scanner.py, idea_validator.py, competitor_spy.py, revenue_modeler.py | ✅ |
| 17 | investment/ | Investment analysis | stock_analyst.py, fundamentals_bot.py, technical_bot.py, sentiment_bot.py | ✅ |
| 18 | content/ | Content creation | script_generator.py, video_generator.py, voice_generator.py, uploader.py, comfyui_adapter.py, video_merger.py, caption_generator.py | ✅ |
| 19 | agency/ | Agency management | content_strategist.py, client_manager.py, performance_tracker.py | ✅ |
| 20 | karpathy_lab/ | Karpathy study | progress_tracker.py, code_typer.py, data_prep.py, architecture_builder.py, autoresearch_runner.py | ✅ |
| 21 | projects/ | Project management | project_planner.py, deadline_watcher.py, progress_tracker.py, doc_writer.py | ✅ |
| 22 | relationships/ | Relationship management | contact_manager.py, communication_analyst.py | ✅ |
| 23 | privacy/ | Privacy enforcement | data_flow_auditor.py, privacy_enforcer.py | ✅ |
| 24 | pattern_detective/ | Pattern detection | behavior_analyst.py, habit_finder.py | ✅ |
| 25 | news_trends/ | News aggregation | ai_news_bot.py, market_trends_bot.py, opportunity_spotter.py | ✅ |

### Bonus Districts

| District | Purpose | Agents | Status |
|----------|---------|--------|--------|
| calls/ | Call handling | call_screener.py, transcription_bot.py, voice_responder.py | ✅ |
| ops/ | Operations | sre_monitor.py, devops_automator.py, incident_commander.py | ✅ |
| data_analytics/ | Analytics | analytics_reporter.py, performance_benchmarker.py, data_engineer.py | ✅ |
| personal_growth/ | Personal growth | behavioral_nudge_engine.py, zk_steward.py, feedback_synthesizer.py | ✅ |
| documentation/ | Documentation | technical_writer.py, doc_generator.py | ✅ |
| qa/ | Quality assurance | reality_checker.py, evidence_collector.py, workflow_architect.py, api_tester.py, test_results_analyzer.py, accessibility_auditor.py, tool_evaluator.py, workflow_optimizer.py, model_qa_specialist.py | ✅ |
| chief_of_staff/ | Executive assistant | chief_of_staff.py | ✅ |
| marketing/ | Marketing | seo_specialist.py, growth_hacker.py, social_media_strategist.py, content_creator.py, ai_citation_strategist.py | ✅ |
| design/ | Design | ui_designer.py, ux_researcher.py, image_prompt_engineer.py | ✅ |

---

## LLM Council

### Council Structure

**File:** `districts/governance/llm_council.py`  
**Status:** ✅ IMPLEMENTED

```python
class LLMCouncil:
    """LLM Council for high-stakes decisions."""
    
    def __init__(self):
        self.members = []
        self.chairman = None
    
    def get_eligible_voters(self) -> List[AgentBase]:
        """Get agents eligible to vote (HP > 700)."""
        from core.city.agent_registry import AgentRegistry
        registry = AgentRegistry()
        
        voters = [a for a in registry.list() if a.hp > 700]
        
        # Sort by HP
        voters.sort(key=lambda a: a.hp, reverse=True)
        
        # Chairman is highest HP
        if voters:
            self.chairman = voters[0]
        
        return voters
    
    async def deliberate(self, action: Candidate) -> dict:
        """Council deliberation on action."""
        
        # Get eligible voters
        voters = self.get_eligible_voters()
        
        if not voters:
            logger.warning("[VECTOR][council] No eligible voters")
            return {"approved": False, "reason": "No eligible voters"}
        
        # Each voter evaluates
        votes = []
        for voter in voters:
            vote = await self._get_vote(voter, action)
            votes.append(vote)
        
        # Majority wins
        approved_count = sum(1 for v in votes if v["approved"])
        total_count = len(votes)
        
        approved = approved_count / total_count > 0.5
        
        logger.info(f"[VECTOR][council] Vote: {approved_count}/{total_count} approved")
        
        return {
            "approved": approved,
            "votes": votes,
            "chairman": self.chairman.name if self.chairman else None
        }
    
    async def _get_vote(self, voter: AgentBase, action: Candidate) -> dict:
        """Get vote from single voter."""
        
        # Use voter's model access
        from core.inference.provider_client import chat
        
        # Inject context (RULE 1)
        from core.loop.context_engine import context_engine
        hydration = await context_engine.session_hydration_prompt()
        
        prompt = f"""You are {voter.name}, a council member with HP {voter.hp}.

Action proposed:
Type: {action.action_type}
District: {action.district}
Description: {action.description}

Should VECTOR execute this action? Consider:
- Risk level
- Alignment with goals
- Resource cost
- Timing

Vote YES or NO with reasoning.
Return JSON: {{"approved": true/false, "reason": "..."}}
"""
        
        messages = [
            {"role": "system", "content": hydration},
            {"role": "user", "content": prompt}
        ]
        
        response = await chat(
            messages,
            model=voter.model_access["primary"]
        )
        
        try:
            vote = json.loads(response.content)
            return {
                "voter": voter.name,
                "hp": voter.hp,
                "approved": vote["approved"],
                "reason": vote["reason"]
            }
        except Exception as e:
            logger.error(f"[VECTOR][council] Vote parse failed: {e}")
            return {
                "voter": voter.name,
                "hp": voter.hp,
                "approved": False,
                "reason": f"Parse error: {e}"
            }
```

---

## District Routing

### Governor Routes

**File:** `core/city/governor.py`  
**Status:** ✅ IMPLEMENTED

**180 Routing Rules:**

```python
ROUTING_RULES = {
    # Coding district
    "fix.*bug": "coding",
    "write.*code": "coding",
    "review.*pr": "coding",
    "debug.*error": "coding",
    
    # Research district
    "search.*for": "research",
    "find.*paper": "research",
    "research.*topic": "research",
    
    # Finance district
    "upi.*transaction": "finance",
    "track.*expense": "finance",
    "budget.*analysis": "finance",
    
    # Investment district
    "analyze.*stock": "investment",
    "nse.*bse": "investment",
    "portfolio.*review": "investment",
    
    # ... (180 rules total)
}
```

---

## District Communication

### Inter-District Messaging

**File:** `core/city/district_bus.py`  
**Status:** ✅ IMPLEMENTED

```python
class DistrictBus:
    """Event bus for inter-district communication."""
    
    async def publish(self, district: str, event: dict):
        """Publish event to district."""
        await self.event_bus.publish(f"district.{district}", event)
    
    async def subscribe(self, district: str, handler: Callable):
        """Subscribe to district events."""
        await self.event_bus.subscribe(f"district.{district}", handler)
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| District routing | 1-10s | Intent classification |
| Council deliberation | 10-30s | Multiple LLM calls |
| Inter-district messaging | <10ms | Event bus |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `10_AGENT_ARCHITECTURE.md` — Agent system
- `09_GOVERNOR_AND_PERMISSIONS.md` — Governor routing
- `32_ALL_DISTRICTS.md` — District details

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
