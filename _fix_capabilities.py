"""
Auto-audit and add self.capabilities to all VECTOR agents that have run() but no capabilities.
Does NOT touch:
- districts/coding/ (already fixed)
- test files
- core/city/governor.py
"""
import re
from pathlib import Path
import json

BASE = Path(__file__).parent
GOV = BASE / "core" / "city" / "governor.py"
DISTRICTS = BASE / "districts"

# ---- Step 1: Parse DISTRICT_TASK_MAP from governor.py ----
gov_text = GOV.read_text(encoding="utf-8", errors="replace")
start = gov_text.find("DISTRICT_TASK_MAP: dict")
brace_start = gov_text.find("{", start)
depth = 0
end = brace_start
for i in range(brace_start, len(gov_text)):
    if gov_text[i] == "{":
        depth += 1
    elif gov_text[i] == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break

dict_text = gov_text[brace_start:end]
# Build reverse: district -> set of task_types
district_to_tasks: dict[str, set[str]] = {}
for m in re.finditer(r'"([^"]+)"\s*:\s*"([^"]+)"', dict_text):
    task_type = m.group(1)
    district = m.group(2)
    district_to_tasks.setdefault(district, set()).add(task_type)

print("=== District -> task_types (from DISTRICT_TASK_MAP) ===")
for d in sorted(district_to_tasks):
    print(f"  {d}: {len(district_to_tasks[d])} task_types")

# ---- Step 2: Find all agent files with run() but no capabilities ----
SKIP_DISTRICTS = {"coding", "__pycache__"}

def has_run_method(text: str) -> bool:
    return bool(re.search(r"^\s*async\s+def\s+run\s*\(\s*self\s*,\s*(task|action)", text, re.M))

def has_capabilities(text: str) -> bool:
    return "self.capabilities" in text

def extract_task_types_from_run(text: str) -> set[str]:
    """Extract task_type strings from the run() method body."""
    tasks = set()
    # Find run() method body
    run_match = re.search(r"async\s+def\s+run\s*\(\s*self\s*,\s*(task|action)", text)
    if not run_match:
        return tasks
    # Look for patterns like: task == "xxx", task.get("task_type") == "xxx",
    # action == "xxx", t == "xxx", task_type == "xxx"
    patterns = [
        r'(?:task|action|t|task_type)\s*==\s*"([^"]+)"',
        r'(?:task|action|t|task_type)\s*==\s*\'([^\']+)\'',
        r'"task_type"\s*:\s*"([^"]+)"',
        r'get\(\s*"task_type"\s*\)\s*==\s*"([^"]+)"',
        r'get\(\s*"action"\s*\)\s*==\s*"([^"]+)"',
        r'in\s*\(\s*"([^"]+)"',  # rough: "xxx" in (...)
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            tasks.add(m.group(1))
    return tasks

def find_init_end(text: str) -> int | None:
    """Find the position right after super().__init__(...) call in __init__,
    or end of __init__ method, where we can insert self.capabilities."""
    # Find def __init__
    init_match = re.search(r"def\s+__init__\s*\(", text)
    if not init_match:
        return None

    # Find super().__init__(...) call - it may span multiple lines
    super_start = text.find("super().__init__(", init_match.start())
    if super_start == -1:
        super_start = text.find("super().__init__ (", init_match.start())
    if super_start == -1:
        return None

    # Find the closing paren of super().__init__(...)
    paren_start = text.find("(", super_start)
    depth = 0
    end = paren_start
    for i in range(paren_start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    # Find the end of the line
    newline = text.find("\n", end)
    if newline == -1:
        return None
    return newline + 1

def find_insert_position(text: str) -> tuple[int, str] | None:
    """Find where to insert self.capabilities = [...] line.
    Returns (position, indent) or None."""
    init_match = re.search(r"def\s+__init__\s*\(", text)
    if not init_match:
        return None

    # Find super().__init__(...)
    super_start = text.find("super().__init__(", init_match.start())
    if super_start == -1:
        return None

    # Find closing paren
    paren_start = text.find("(", super_start)
    depth = 0
    end = paren_start
    for i in range(paren_start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    # Find end of line containing the closing paren
    newline = text.find("\n", end)
    if newline == -1:
        return None

    # Determine indentation from the super().__init__ line
    line_start = text.rfind("\n", 0, super_start) + 1
    indent_match = re.match(r"(\s+)", text[line_start:super_start])
    indent = indent_match.group(1) if indent_match else "        "

    return (newline + 1, indent)

# Per-district capability hints based on agent name patterns
NAME_TO_CAPS = {
    "threat_scout": ["threat", "malware", "security", "scan", "security_scan", "scan_prompt", "ssrf_check", "taint_check"],
    "malware_hunter": ["malware", "security", "scan", "security_scan"],
    "node_guard": ["security", "node_guard", "malware", "scan"],
    "alert_manager": ["security", "alert", "security_scan"],
    "data_redactor": ["security", "privacy", "data_redact"],
    "detection_rules": ["security", "threat", "detection"],
    "incident_playbook_runner": ["security", "incident"],
    "log_aggregator": ["security", "log", "audit_log", "audit_search", "audit_tail"],
    "network_monitor": ["security", "network", "threat"],
    "siem_pipeline": ["security", "siem", "threat"],
    "skill_spector": ["security", "scan", "security_scan"],
    "threat_detection_engineer": ["threat", "security", "security_scan", "scan_prompt", "ssrf_check"],
    "llm_council": ["vote", "council", "decision", "high_stakes"],
    "product_manager": ["product", "decision", "council"],
    "autopilot": ["autopilot", "governance", "ambient", "directive"],
    "compliance_auditor": ["audit", "compliance", "audit_log", "audit_verify"],
    "credential_manager": ["credential", "security", "governance"],
    "federation_agent": ["federation", "governance"],
    "email_agent": ["email", "message", "notify", "communications", "draft_reply", "send_email"],
    "email_intelligence": ["email", "message", "communications", "draft_reply", "send_email"],
    "script_generator": ["content", "script", "generate", "video"],
    "video_generator": ["content", "video", "generate"],
    "voice_generator": ["content", "voice", "tts", "generate"],
    "uploader": ["content", "upload", "youtube", "instagram"],
    "video_merger": ["content", "video", "merge"],
    "caption_generator": ["content", "caption", "video", "generate"],
    "comfyui_adapter": ["content", "image", "generate", "comfyui"],
    "content_scheduler": ["content", "schedule", "publish"],
    "video_pipeline": ["content", "video", "pipeline"],
    "website_to_video": ["content", "video", "website"],
    "youtube_trends": ["content", "youtube", "trends"],
    "media_studio_agent": ["content", "media", "generate"],
    "asset_video_pipeline": ["content", "video", "asset", "pipeline"],
    "budget_analyst": ["finance", "budget", "money", "budget_check", "budget_status"],
    "expense_tracker": ["finance", "expense", "money", "budget"],
    "upi_parser": ["finance", "upi", "payment", "money"],
    "tax_calendar": ["finance", "tax", "deadline"],
    "financial_analyst": ["finance", "financial", "analysis", "money"],
    "fpa_analyst": ["finance", "fpa", "budget", "analysis"],
    "llm_cost_tracker": ["finance", "cost", "budget", "budget_check", "budget_record"],
    "sleep_tracker": ["health", "sleep", "fatigue"],
    "fatigue_monitor": ["health", "fatigue", "check_fatigue"],
    "exercise_logger": ["health", "exercise"],
    "biometrics_aggregator": ["health", "biometrics"],
    "health_advisor": ["health", "advice"],
    "analytics_reporter": ["data_analytics", "analytics", "report"],
    "data_engineer": ["data_analytics", "etl", "pipeline"],
    "performance_benchmarker": ["data_analytics", "benchmark", "performance"],
    "performance_optimizer": ["data_analytics", "performance", "optimize"],
    "ui_designer": ["design", "ui", "interface"],
    "ux_researcher": ["design", "ux", "research"],
    "image_prompt_engineer": ["design", "image", "prompt"],
    "ai_news_bot": ["news", "ai_news", "venture_pipeline", "mine_social"],
    "market_trends_bot": ["news_trends", "trends", "market", "venture_pipeline"],
    "opportunity_spotter": ["news_trends", "opportunity", "venture_pipeline", "mine_social", "cluster_problems"],
    "venture_pipeline": ["venture_pipeline", "mine_social", "cluster_problems"],
    "social_miner": ["news_trends", "social", "mine_social", "venture_pipeline"],
    "problem_clusterer": ["news_trends", "cluster_problems", "venture_pipeline"],
    "consolidation_bot": ["memory", "consolidate", "remember", "recall"],
    "pattern_finder": ["memory", "pattern", "recall", "consolidate"],
    "context_compressor": ["memory", "compress", "context", "remember"],
    "mock_interviewer": ["interview", "mock_interview"],
    "report_generator": ["interview", "report", "generate"],
    "company_researcher": ["interview", "company", "research"],
    "feedback_analyst": ["interview", "feedback", "analysis"],
    "recruitment_bot": ["interview", "recruitment", "hiring"],
    "stock_analyst": ["investment", "stock", "investment_analysis", "equity_research"],
    "fundamentals_bot": ["investment", "fundamental_analysis", "corporate_finance"],
    "technical_bot": ["investment", "technical_analysis", "trading_analysis"],
    "sentiment_bot": ["investment", "sentiment", "alpha_discovery"],
    "backtest_agent": ["investment", "backtest", "quant_backtest", "backtest_strategy", "vt_backtest"],
    "finagent_agent": ["investment", "finagent", "trading"],
    "hedgebot_agent": ["investment", "hedge", "hedge_run", "hedge_trade"],
    "trading_conductor_agent": ["investment", "trading", "execute_trade", "place_order", "paper_trade"],
    "market_scanner": ["startups", "market", "venture_pipeline", "mine_social"],
    "idea_validator": ["startups", "idea", "validate", "venture_pipeline"],
    "competitor_spy": ["startups", "competitor", "venture_pipeline"],
    "revenue_modeler": ["startups", "revenue", "venture_pipeline"],
    "kiit_scraper": ["kiit", "attendance", "check_attendance", "class", "calendar", "schedule"],
    "deadline_manager": ["deadline", "deadline_check", "calendar", "schedule"],
    "time_blocker": ["time_block", "calendar", "schedule", "time"],
    "content_strategist": ["agency", "content", "strategy"],
    "client_manager": ["agency", "client", "sales"],
    "performance_tracker": ["agency", "performance", "tracking"],
    "sales_strategist": ["agency", "sales", "outbound"],
    "proposal_strategist": ["agency", "proposal", "sales"],
    "call_screener": ["calls", "call", "screen"],
    "transcription_bot": ["calls", "transcription", "transcribe"],
    "voice_responder": ["calls", "voice", "respond"],
    "chief_of_staff": ["chief_of_staff", "brief", "governance"],
    "daily_reviewer": ["daily_review", "reflect", "journal", "reflection"],
    "journal_writer": ["journal", "reflect", "daily_review"],
    "growth_analyst": ["growth", "analysis", "reflect", "progress"],
    "contact_manager": ["relationships", "contact", "communication"],
    "communication_analyst": ["relationships", "communication", "analysis"],
    "skill_mapper": ["skills", "skill_map", "learn"],
    "gap_analyst": ["skills", "gap", "analysis"],
    "mastery_tracker": ["skills", "mastery", "learn"],
    "hindi_coach": ["language", "hindi", "learn"],
    "bengali_coach": ["language", "bengali", "learn"],
    "assamese_coach": ["language", "assamese", "learn"],
    "english_coach": ["language", "english", "learn"],
    "japanese_coach": ["language", "japanese", "learn"],
    "video_ingestor": ["video", "learn", "course", "ingest"],
    "concept_extractor": ["learning", "concept", "extract", "learn"],
    "course_tracker": ["course", "learn", "progress"],
    "note_organizer": ["learning", "notes", "organize"],
    "behavior_analyst": ["pattern_detective", "behavior", "pattern"],
    "habit_finder": ["pattern_detective", "habit", "pattern"],
    "data_flow_auditor": ["privacy", "data_flow", "audit"],
    "privacy_enforcer": ["privacy", "enforce", "data_flow"],
    "behavioral_nudge_engine": ["personal_growth", "nudge", "behavior"],
    "feedback_synthesizer": ["personal_growth", "feedback", "synthesis"],
    "zk_steward": ["personal_growth", "zettelkasten", "notes"],
    "project_planner": ["project", "plan", "deadline_check", "progress"],
    "deadline_watcher": ["deadline", "deadline_check", "project"],
    "progress_tracker": ["progress", "project", "tracking"],
    "doc_writer": ["project", "documentation", "write"],
    "experiment_tracker": ["experiment", "tracking", "project"],
    "progress_tracker": ["progress", "project", "tracking"],
    "sre_monitor": ["ops", "sre", "monitor", "health"],
    "devops_automator": ["ops", "devops", "deploy"],
    "incident_commander": ["ops", "incident", "incident_command"],
    "agent": ["general"],  # fallback for generic agent.py files
    "web_scout": ["search", "research", "search_web"],
    "paper_reader": ["research", "paper", "search_arxiv"],
    "news_aggregator": ["research", "news", "daily_digest"],
    "reddit_miner": ["research", "reddit", "search"],
    "research_hub": ["research", "search", "find"],
    "deep_researcher": ["research", "deep_research", "search"],
    "stealth_scout_agent": ["research", "scrape", "scrape_url", "scrape_stealth"],
    "accessibility_auditor": ["qa", "accessibility", "a11y"],
    "api_tester": ["qa", "api_test", "test"],
    "evidence_collector": ["qa", "evidence", "screenshot"],
    "reality_checker": ["qa", "reality_check", "verify"],
    "test_results_analyzer": ["qa", "test_results", "analysis"],
    "tool_evaluator": ["qa", "tool_eval", "evaluate"],
    "workflow_optimizer": ["qa", "workflow", "optimize"],
    "workflow_architect": ["qa", "workflow", "design"],
    "silent_failure_hunter": ["qa", "silent_failure", "test"],
    "test_engineer": ["qa", "test", "test_engineer"],
    "model_qa_specialist": ["qa", "model_qa", "evaluate"],
    "technical_writer": ["documentation", "docs", "write", "generate_docs"],
    "doc_generator": ["documentation", "docs", "generate", "generate_docs"],
    "seo_specialist": ["marketing", "seo"],
    "growth_hacker": ["marketing", "growth"],
    "social_media_strategist": ["marketing", "social", "social_media"],
    "content_creator": ["marketing", "content", "create"],
    "ai_citation_strategist": ["marketing", "ai_citation", "citation"],
    "seo_agent": ["marketing", "seo"],
    "seo_portfolio": ["marketing", "seo", "portfolio"],
    "google_ads_agent": ["marketing", "google_ads", "ads"],
    "meta_ads_agent": ["marketing", "meta_ads", "ads"],
    "amazon_ads_agent": ["marketing", "amazon_ads", "ads"],
    "ads_orchestrator_agent": ["marketing", "ads", "orchestrate"],
    "competitor_intel_agent": ["marketing", "competitor", "intel"],
    "attribution_agent": ["marketing", "attribution"],
    "cro_agent": ["marketing", "cro", "conversion"],
    "sgtm_agent": ["marketing", "sgtm", "server_side"],
    "social_sim_agent": ["intelligence", "social_sim", "simulation"],
    "vectorintel_agent": ["intelligence", "intel", "surveillance", "flights", "vessels"],
    "science_agent": ["science", "research"],
    "strategy_recommender": ["predictive_analytics", "strategy", "predict"],
    "home_assistant_agent": ["home_assistant", "smart_home"],
}


def determine_capabilities(agent_path: Path, text: str, district: str) -> list[str]:
    """Determine appropriate capabilities for an agent."""
    caps = set()
    fname = agent_path.stem.lower()

    # 1. Name-based caps
    if fname in NAME_TO_CAPS:
        caps.update(NAME_TO_CAPS[fname])

    # 2. Task types from run() method
    run_tasks = extract_task_types_from_run(text)
    caps.update(run_tasks)

    # 3. District task_types from DISTRICT_TASK_MAP (top ones)
    if district in district_to_tasks:
        district_tasks = district_to_tasks[district]
        # Add the most common/relevant ones
        for t in district_tasks:
            # Only add if seems relevant to this agent's domain
            if any(word in t.lower() for word in fname.replace("_", "").split()):
                caps.add(t)

    # 4. If still empty, use district name as default
    if not caps:
        caps.add(district)

    # Remove duplicates and sort
    result = sorted(caps)
    return result


# ---- Step 3: Process each missing agent ----
fixed_count = 0
skipped_count = 0
errors = []

for district_dir in sorted(DISTRICTS.iterdir()):
    if not district_dir.is_dir():
        continue
    district_name = district_dir.name
    if district_name in SKIP_DISTRICTS:
        continue

    for py_file in district_dir.rglob("*.py"):
        # Skip test files
        if "test" in py_file.name.lower() or "test" in str(py_file.relative_to(DISTRICTS)).lower():
            continue

        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            errors.append(f"  ERROR reading {py_file}: {e}")
            continue

        if not has_run_method(text):
            continue
        if has_capabilities(text):
            continue

        # Need to add capabilities
        caps = determine_capabilities(py_file, text, district_name)
        if not caps:
            errors.append(f"  NO CAPS for {py_file}")
            continue

        # Find insert position
        pos_info = find_insert_position(text)
        if pos_info is None:
            errors.append(f"  NO INSERT POS for {py_file}")
            continue

        insert_pos, indent = pos_info

        # Build the capabilities line
        caps_str = ", ".join(f'"{c}"' for c in caps)
        cap_line = f'{indent}self.capabilities = [{caps_str}]\n'

        # Insert
        new_text = text[:insert_pos] + cap_line + text[insert_pos:]

        # Write
        try:
            py_file.write_text(new_text, encoding="utf-8")
            fixed_count += 1
            rel = py_file.relative_to(BASE)
            print(f"FIXED: {rel} -> {caps[:5]}{'...' if len(caps) > 5 else ''}")
        except Exception as e:
            errors.append(f"  ERROR writing {py_file}: {e}")
            skipped_count += 1

print(f"\n=== SUMMARY ===")
print(f"Fixed: {fixed_count}")
print(f"Skipped/Errors: {skipped_count}")
if errors:
    print(f"Errors:")
    for e in errors:
        print(e)
