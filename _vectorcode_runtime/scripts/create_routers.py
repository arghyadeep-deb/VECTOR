"""Script to create all missing VECTOR API routers."""
import sys
from pathlib import Path


routers_dir = Path(__file__).parent.parent / 'core' / 'api' / 'routers'


def ep(path, method, name, doc, fields=None):
    return (path, method, name, doc, fields or [])


specs = {
    'health.py': ('/health', 'health', [
        ep('/check-fatigue', 'get', 'check_fatigue', 'Real-time fatigue detection via EAR scoring.'),
        ep('/sleep', 'post', 'track_sleep', 'Log and analyze sleep quality.',
           [('duration_hours','float','0.0'),('quality','int','0'),('notes','str','""')]),
        ep('/biometrics', 'get', 'aggregate_biometrics', 'Aggregate biometric data.'),
        ep('/exercise', 'post', 'log_exercise', 'Log a workout session.',
           [('exercise_type','str','"cardio"'),('duration_min','int','30'),('intensity','str','"medium"')]),
        ep('/status', 'get', 'health_status', 'Overall health district status.'),
    ]),
    'finance.py': ('/finance', 'finance', [
        ep('/budget-analyze', 'post', 'budget_analyze', 'Monthly budget variance and forecasts.',
           [('month','str','""'),('data','str','""')]),
        ep('/expenses', 'get', 'list_expenses', 'List recent expenses with categories.'),
        ep('/expenses/log', 'post', 'log_expense', 'Log expense with auto-categorization.',
           [('amount','float','0.0'),('description','str','""'),('category','str','""')]),
        ep('/tax-plan', 'post', 'tax_plan', 'Tax planning recommendations and deductions.',
           [('income','float','0.0'),('year','int','2026')]),
        ep('/cost-tracker', 'get', 'llm_cost_summary', 'LLM API cost usage and budget remaining.'),
    ]),
    'design.py': ('/design', 'design', [
        ep('/component-spec', 'post', 'spec_component', 'Component specification with accessibility.',
           [('name','str','""'),('component_type','str','"button"'),('requirements','str','""')]),
        ep('/image-prompt', 'post', 'image_prompt', 'Optimized AI image generation prompt.',
           [('concept','str','""'),('style','str','"photorealistic"'),('aspect','str','"16:9"')]),
        ep('/ux-research', 'post', 'ux_research', 'UX research: journey mapping, persona generation.',
           [('product','str','""'),('target_user','str','""'),('research_type','str','"journey_map"')]),
        ep('/tokens', 'post', 'generate_tokens', 'Design system tokens: colors, spacing, typography.',
           [('brand_name','str','""'),('primary_color','str','"#000000"'),('style','str','"modern"')]),
    ]),
    'analytics.py': ('/analytics', 'analytics', [
        ep('/pipeline-health', 'get', 'pipeline_health', 'Data pipeline health: DB stats, NULL columns.'),
        ep('/etl-run', 'post', 'etl_run', 'ETL pipeline: bronze to silver to gold.',
           [('source','str','""'),('target','str','"silver"'),('filters','str','""')]),
        ep('/report', 'post', 'analytics_report', 'Analytics report: trends, anomalies, forecasts.',
           [('period','str','"30d"'),('metrics','str','"all"')]),
        ep('/benchmark', 'post', 'benchmark_run', 'Performance benchmark across time periods.',
           [('metric','str','""'),('baseline','str','""')]),
    ]),
    'privacy.py': ('/privacy', 'privacy', [
        ep('/scan-sharing', 'post', 'scan_data_sharing', 'Detect PII leaks and unauthorized data sharing.',
           [('scope','str','"full"'),('data_types','str','"all"')]),
        ep('/gdpr-check', 'post', 'gdpr_check', 'GDPR compliance check.',
           [('data_category','str','""'),('processing_purpose','str','""')]),
        ep('/redact', 'post', 'redact_data', 'Redact sensitive PII from text.',
           [('text','str','""'),('types','str','"all"')]),
        ep('/audit-flow', 'post', 'audit_data_flow', 'Audit what data flows where across VECTOR.',
           [('system','str','"all"'),('depth','int','2')]),
    ]),
    'coding_extended.py': ('/coding', 'coding', [
        ep('/review', 'post', 'code_review', 'Full code review with metrics and recommendations.',
           [('file_path','str','""'),('code','str','""'),('context','str','""')]),
        ep('/architect', 'post', 'architect_advice', 'Architecture advice and design patterns.',
           [('description','str','""'),('constraints','str','""')]),
        ep('/rapid-prototype', 'post', 'rapid_prototype', 'Generate rapid prototype for a described feature.',
           [('feature','str','""'),('stack','str','"python"')]),
        ep('/db-optimize', 'post', 'db_optimize', 'Database query optimization and indexing strategy.',
           [('query','str','""'),('schema','str','""')]),
        ep('/test-write', 'post', 'write_tests', 'Generate tests for a function or class.',
           [('code','str','""'),('test_type','str','"unit"')]),
    ]),
    'qa.py': ('/qa', 'qa', [
        ep('/write-tests', 'post', 'qa_write_tests', 'Generate comprehensive test suite.',
           [('code','str','""'),('coverage_target','int','80')]),
        ep('/analyze-results', 'post', 'analyze_test_results', 'Analyze test results: flakiness, regressions.',
           [('results','str','""'),('baseline','str','""')]),
        ep('/accessibility-audit', 'post', 'accessibility_audit', 'WCAG accessibility audit.',
           [('url','str','""'),('html','str','""')]),
        ep('/api-test', 'post', 'api_test', 'Validate API endpoint correctness.',
           [('endpoint','str','""'),('method','str','"GET"'),('expected_status','int','200')]),
        ep('/reality-check', 'post', 'reality_check', 'Fact-check LLM output against evidence.',
           [('claim','str','""'),('context','str','""')]),
    ]),
    'projects.py': ('/projects', 'projects', [
        ep('/create', 'post', 'create_project', 'Create project with roadmap and milestones.',
           [('name','str','""'),('description','str','""'),('deadline','str','""')]),
        ep('/list', 'get', 'list_projects', 'List all active projects with progress.'),
        ep('/experiment', 'post', 'track_experiment', 'Track experiment: hypothesis, run, results.',
           [('name','str','""'),('hypothesis','str','""'),('metric','str','""')]),
        ep('/deadline', 'get', 'upcoming_deadlines', 'Get upcoming project deadlines.'),
    ]),
    'learning.py': ('/learning', 'learning', [
        ep('/ingest-video', 'post', 'ingest_video', 'Extract transcript and concepts from any video URL.',
           [('url','str','""'),('language','str','"en"')]),
        ep('/track-course', 'post', 'track_course', 'Track course enrollment and completion.',
           [('course_name','str','""'),('platform','str','""'),('progress_pct','int','0')]),
        ep('/extract-concepts', 'post', 'extract_concepts', 'Extract concept dependency graph from content.',
           [('content','str','""'),('depth','int','2')]),
        ep('/quiz-generate', 'post', 'generate_quiz', 'Generate quiz from learned material.',
           [('topic','str','""'),('difficulty','str','"medium"'),('count','int','5')]),
    ]),
    'interview.py': ('/interview', 'interview', [
        ep('/start', 'post', 'start_interview', 'Start a mock interview session.',
           [('role','str','""'),('company','str','""'),('interview_type','str','"behavioral"')]),
        ep('/generate-question', 'post', 'generate_question', 'Generate interview question.',
           [('role','str','""'),('difficulty','str','"medium"'),('question_type','str','"behavioral"')]),
        ep('/evaluate', 'post', 'evaluate_answer', 'Score and give feedback on an interview answer.',
           [('question','str','""'),('answer','str','""'),('role','str','""')]),
        ep('/company-research', 'post', 'company_research', 'Research company: culture, hiring patterns.',
           [('company','str','""'),('role','str','""')]),
        ep('/report', 'post', 'interview_report', 'Generate interview performance analysis report.',
           [('session_id','str','""')]),
    ]),
    'languages.py': ('/languages', 'languages', [
        ep('/{lang}/vocabulary', 'post', 'vocabulary_practice', 'Practice vocabulary.',
           [('word_count','int','10'),('level','str','"beginner"')]),
        ep('/{lang}/grammar', 'post', 'grammar_practice', 'Grammar drill.',
           [('topic','str','""'),('level','str','"beginner"')]),
        ep('/{lang}/dialogue', 'post', 'dialogue_practice', 'Conversational dialogue practice.',
           [('scenario','str','"daily life"'),('level','str','"beginner"')]),
        ep('/{lang}/study-guide', 'post', 'study_guide', 'Generate personalized study plan.',
           [('current_level','str','"beginner"'),('goal','str','"conversational"'),('hours_per_week','int','5')]),
    ]),
    'news.py': ('/news', 'news', [
        ep('/fetch', 'post', 'fetch_news', 'Fetch latest AI and tech news.',
           [('topics','str','"AI"'),('limit','int','10')]),
        ep('/spot-opportunities', 'post', 'spot_opportunities', 'Analyze trends for business opportunities.',
           [('domain','str','""'),('timeframe','str','"7d"')]),
        ep('/market-trends', 'post', 'market_trends', 'Sector sentiment and market trend analysis.',
           [('sector','str','"technology"'),('depth','str','"summary"')]),
        ep('/daily-brief', 'get', 'daily_brief', 'Get the daily trending summary brief.'),
    ]),
    'patterns.py': ('/patterns', 'patterns', [
        ep('/detect', 'post', 'detect_patterns', 'Detect behavioral patterns from episodic memory.',
           [('days','int','30'),('category','str','"all"')]),
        ep('/habits', 'get', 'identify_habits', 'Identify recurring habits (positive and negative).'),
        ep('/insights', 'post', 'generate_insights', 'Generate actionable insights from patterns.',
           [('pattern_type','str','"all"')]),
        ep('/habit-plan', 'post', 'habit_plan', 'Create habit change intervention plan.',
           [('habit','str','""'),('goal','str','"break"')]),
    ]),
    'reflection.py': ('/reflection', 'reflection', [
        ep('/daily-review', 'post', 'daily_review', 'Run VECTOR daily reflection.',
           [('force','bool','False')]),
        ep('/journal', 'post', 'journal_entry', 'Write structured journal entry.',
           [('mood','str','"neutral"'),('highlights','str','""'),('lessons','str','""')]),
        ep('/growth-analysis', 'post', 'growth_analysis', 'Analyze progress and growth metrics.',
           [('period','str','"7d"')]),
    ]),
    'relationships.py': ('/relationships', 'relationships', [
        ep('/contacts', 'get', 'list_contacts', 'List managed contacts with relationship metadata.'),
        ep('/contacts/add', 'post', 'add_contact', 'Add or update a contact.',
           [('name','str','""'),('tier','str','"acquaintance"'),('interests','str','""')]),
        ep('/communication-style', 'post', 'communication_style', 'Analyze communication style.',
           [('contact_name','str','""'),('message_history','str','""')]),
        ep('/outreach-plan', 'post', 'outreach_plan', 'Suggest who to reach out to and how.',
           [('goal','str','"maintain"'),('count','int','3')]),
    ]),
    'skills.py': ('/skills', 'skills', [
        ep('/map', 'get', 'skill_map', 'Knowledge graph of current skills and proficiency.'),
        ep('/gap-analysis', 'post', 'gap_analysis', 'Identify skill gaps toward a goal.',
           [('target_role','str','""'),('timeframe','str','"6m"')]),
        ep('/mastery', 'post', 'track_mastery', 'Track mastery level for a skill.',
           [('skill','str','""'),('level','int','1'),('evidence','str','""')]),
        ep('/practice-suggest', 'post', 'suggest_practice', 'Suggest targeted practice exercises.',
           [('skill','str','""'),('current_level','int','1')]),
    ]),
    'startups.py': ('/startups', 'startups', [
        ep('/validate-idea', 'post', 'validate_idea', 'Market viability scoring for a startup idea.',
           [('idea','str','""'),('market','str','""'),('differentiator','str','""')]),
        ep('/market-scan', 'post', 'market_scan', 'TAM/SAM/SOM analysis for a market.',
           [('market','str','""'),('geography','str','"global"')]),
        ep('/competitor-analysis', 'post', 'competitor_analysis', 'Competitive landscape analysis.',
           [('product','str','""'),('competitors','str','""')]),
        ep('/revenue-model', 'post', 'revenue_model', 'Build financial projections.',
           [('business_type','str','""'),('price_point','float','0.0'),('target_customers','int','1000')]),
    ]),
    'karpathy.py': ('/karpathy', 'karpathy', [
        ep('/run-training', 'post', 'run_training', 'Execute training run with fixed time budget.',
           [('script','str','"train.py"'),('config','str','""'),('budget_minutes','int','30')]),
        ep('/propose-improvement', 'post', 'propose_improvement', 'Suggest architectural improvements.',
           [('current_results','str','""'),('model_arch','str','""')]),
        ep('/apply-patch', 'post', 'apply_patch_and_test', 'Apply improvement patch and rerun.',
           [('patch','str','""'),('metric','str','"val_loss"')]),
        ep('/experiment-history', 'get', 'experiment_history', 'Full history of training runs.'),
    ]),
    'ops.py': ('/ops', 'ops', [
        ep('/incident', 'post', 'incident_command', 'Trigger incident response.',
           [('title','str','""'),('severity','str','"medium"'),('description','str','""')]),
        ep('/slo-check', 'get', 'slo_check', 'Check current SLO status and error budgets.'),
        ep('/post-mortem', 'post', 'post_mortem', 'Generate post-mortem analysis.',
           [('incident_id','str','""'),('timeline','str','""'),('root_cause','str','""')]),
        ep('/error-classify', 'post', 'error_classify', 'Classify error by category and severity.',
           [('error_message','str','""'),('stack_trace','str','""')]),
    ]),
    'chief.py': ('/chief', 'chief', [
        ep('/morning-brief', 'get', 'morning_brief', 'Get the 08:00 executive morning brief.'),
        ep('/evening-brief', 'get', 'evening_brief', 'Get the 22:00 accomplishment summary.'),
        ep('/executive-brief', 'post', 'executive_brief', 'Generate executive brief.',
           [('topics','str','"all"'),('format','str','"bullets"')]),
        ep('/route-escalation', 'post', 'route_escalation', 'Intelligently route a task.',
           [('task','str','""'),('urgency','str','"medium"')]),
        ep('/filter-noise', 'post', 'filter_noise', 'Classify events as SIGNAL/ROUTINE/NOISE.',
           [('events','str','""')]),
    ]),
    'calls.py': ('/calls', 'calls', [
        ep('/screen', 'post', 'screen_call', 'Screen incoming call for spam.',
           [('caller_number','str','""'),('caller_name','str','""')]),
        ep('/transcribe', 'post', 'transcribe_call', 'Transcribe a call recording to text.',
           [('audio_path','str','""'),('language','str','"auto"')]),
        ep('/respond', 'post', 'voice_respond', 'Generate AI-driven call response.',
           [('transcript','str','""'),('context','str','""')]),
        ep('/contacts', 'get', 'list_call_contacts', 'List call screening whitelist.'),
        ep('/contacts/add', 'post', 'add_call_contact', 'Add contact to whitelist.',
           [('name','str','""'),('number','str','""'),('tier','str','"known"')]),
    ]),
    'agency.py': ('/agency', 'agency', [
        ep('/trends', 'post', 'analyze_trends', 'Analyze content trends for a niche.',
           [('niche','str','""'),('platform','str','"all"'),('days','int','30')]),
        ep('/topics', 'post', 'suggest_topics', 'Generate content topic ideas.',
           [('niche','str','""'),('count','int','10'),('format','str','"blog"')]),
        ep('/content-plan', 'post', 'create_content_plan', 'Create structured content plan.',
           [('brand','str','""'),('goal','str','""'),('weeks','int','4')]),
        ep('/roi', 'post', 'roi_analysis', 'Performance tracking and ROI analysis.',
           [('campaign','str','""'),('spend','float','0.0'),('revenue','float','0.0')]),
    ]),
    'documentation.py': ('/documentation', 'documentation', [
        ep('/api-reference', 'post', 'api_reference', 'Auto-generate API reference from code.',
           [('file_path','str','""'),('format','str','"markdown"')]),
        ep('/generate', 'post', 'generate_docs', 'Generate technical documentation.',
           [('topic','str','""'),('doc_type','str','"architecture"'),('depth','str','"detailed"')]),
        ep('/changelog', 'post', 'generate_changelog', 'Generate changelog from git history.',
           [('version','str','""'),('since_tag','str','""')]),
        ep('/weekly-summary', 'get', 'weekly_summary', 'Generate weekly progress summary.'),
    ]),
    'governance_extended.py': ('/governance', 'governance', [
        ep('/roadmap', 'post', 'product_roadmap', 'Generate product roadmap with RICE scoring.',
           [('features','str','""'),('timeline','str','"quarter"'),('constraints','str','""')]),
        ep('/federation', 'post', 'delegate_task', 'Delegate task to another agent.',
           [('task','str','""'),('target_agent','str','""'),('priority','str','"medium"')]),
        ep('/autopilot/status', 'get', 'autopilot_status', 'Autonomous task execution status.'),
        ep('/autopilot/trigger', 'post', 'autopilot_trigger', 'Trigger autonomous workflow.',
           [('workflow','str','""'),('params','str','""')]),
    ]),
    # Core infrastructure routers
    'brain.py': ('/brain', 'brain', [
        ep('/goals', 'get', 'get_goals', 'List all VECTOR goals (LONG/MID/SHORT horizon).'),
        ep('/goals/add', 'post', 'add_goal', 'Add or update a goal.',
           [('title','str','""'),('horizon','str','"short"'),('priority','float','0.5')]),
        ep('/goals/immediate', 'get', 'immediate_actions', 'Get immediate action candidates.'),
        ep('/synthesis', 'post', 'synthesize', 'Synthesize multiple district outputs into one narrative.',
           [('outputs','str','""'),('synthesis_type','str','"daily"')]),
        ep('/hypothesis/generate', 'post', 'generate_hypothesis', 'Generate hypothesis from observation.',
           [('observation','str','""')]),
        ep('/hypothesis/active', 'get', 'active_hypotheses', 'List all active untested hypotheses.'),
        ep('/hypothesis/test', 'post', 'test_hypothesis', 'Test hypothesis against new evidence.',
           [('hypothesis_id','str','""'),('evidence','str','""')]),
        ep('/red-team/attack', 'post', 'red_team_attack', 'Adversarial attack on a plan.',
           [('plan','str','""'),('context','str','""')]),
        ep('/red-team/audit', 'post', 'red_team_audit', 'Audit a policy for vulnerabilities.',
           [('policy','str','""')]),
        ep('/epistemic/summary', 'get', 'epistemic_summary', 'VECTOR self-knowledge map.'),
        ep('/epistemic/staleness', 'get', 'epistemic_staleness', 'List stale knowledge areas.'),
    ]),
    'city.py': ('/city', 'city', [
        ep('/districts', 'get', 'list_districts', 'List all 47 districts with agent counts.'),
        ep('/agents/history', 'post', 'agent_history', 'Full generation history for an agent.',
           [('agent_id','str','""')]),
        ep('/evolution/generations', 'get', 'generation_map', 'Map of all agent generations.'),
        ep('/evolution/spawn', 'post', 'spawn_successor', 'Spawn a successor agent for a dead agent.',
           [('dead_agent_id','str','""'),('district','str','""')]),
        ep('/dispatch', 'post', 'direct_dispatch', 'Direct governor dispatch.',
           [('task_type','str','""'),('params','str','""')]),
    ]),
    'control.py': ('/control', 'control', [
        ep('/pc/screenshot', 'get', 'pc_screenshot', 'Capture current screen.'),
        ep('/pc/type', 'post', 'pc_type', 'Type text via keyboard (YELLOW gate).',
           [('text','str','""'),('delay_ms','int','50')]),
        ep('/pc/click', 'post', 'pc_click', 'Click at screen coordinates (YELLOW gate).',
           [('x','int','0'),('y','int','0'),('button','str','"left"')]),
        ep('/pc/launch-app', 'post', 'pc_launch_app', 'Launch application (YELLOW gate).',
           [('app_name','str','""'),('args','str','""')]),
        ep('/phone/status', 'get', 'phone_status', 'ADB bridge connection status.'),
        ep('/phone/notifications', 'get', 'phone_notifications', 'Read phone notifications via ADB.'),
        ep('/phone/screenshot', 'get', 'phone_screenshot', 'Capture phone screen via ADB.'),
    ]),
}


def build_router(filename, prefix, tag, endpoints):
    lines = [
        f'"""VECTOR {tag} router - {prefix}/* endpoints."""',
        'import sys',
        'from pathlib import Path',
        'sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))',
        'from fastapi import APIRouter, HTTPException',
        'from pydantic import BaseModel',
        'from loguru import logger',
        '',
        f'router = APIRouter(prefix="{prefix}", tags=["{tag}"])',
        '',
        '',
    ]

    for path, method, name, doc, fields in endpoints:
        fn_name = name.replace('-', '_')
        if fields:
            model_name = fn_name.title().replace('_', '') + 'Req'
            lines.append(f'class {model_name}(BaseModel):')
            for fname, ftype, fdefault in fields:
                lines.append(f'    {fname}: {ftype} = {fdefault}')
            lines.append('')

        dec = f'@router.{method}("{path}")'
        if method == 'get' or not fields:
            lines += [dec, f'async def {fn_name}():']
        else:
            model_name = fn_name.title().replace('_', '') + 'Req'
            lines += [dec, f'async def {fn_name}(body: {model_name}):']

        lines.append(f'    """{doc}"""')
        lines.append('    from core.city.governor import GovernorCouncil')
        lines.append('    gov = GovernorCouncil()')
        lines.append('    try:')
        if method == 'get' or not fields:
            lines.append(f'        return await gov.dispatch({{"type": "{name}", "params": {{}}}})')
        else:
            lines.append(f'        return await gov.dispatch({{"type": "{name}", "params": body.model_dump()}})')
        lines.append('    except Exception as e:')
        lines.append(f'        logger.error("[VECTOR][{tag}] {name} failed: {{}}", e)')
        lines.append(f'        raise HTTPException(status_code=500, detail="internal server error")')
        lines.append('')

    return '\n'.join(lines)


created = 0
for filename, (prefix, tag, endpoints) in specs.items():
    p = routers_dir / filename
    if p.exists():
        print(f'SKIP (exists): {filename}')
        continue
    content = build_router(filename, prefix, tag, endpoints)
    p.write_text(content, encoding='utf-8')
    created += 1

print(f'Created {created} routers')
