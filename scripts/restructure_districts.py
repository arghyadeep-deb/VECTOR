"""
Restructure districts/ to match agency-agents repo structure.
- Renames files (strips vector-ag- / vector- prefix, matches repo naming)
- Creates new districts: academic/, engineering/, paid_media/, product/,
  project_management/, sales/, strategy/, support/, testing/
- Moves agents to correct districts
- Adds subfolders to game_development/ (blender/, godot/, roblox_studio/, unity/, unreal_engine/)
- Deletes duplicates and non-agent files
- Python .py files are NOT touched
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent / "agents" / "districts"

created = []
moved = []
deleted = []
errors = []


def mkdirs(*paths):
    for p in paths:
        d = ROOT / p
        d.mkdir(parents=True, exist_ok=True)
        if str(d) not in created:
            created.append(str(d))


def mv(src_rel: str, dst_rel: str):
    src = ROOT / src_rel
    dst = ROOT / dst_rel
    if not src.exists():
        errors.append(f"MISSING src: {src_rel}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst != src:
        dst.unlink()  # overwrite if exists
    shutil.move(str(src), str(dst))
    moved.append(f"{src_rel} → {dst_rel}")


def rm(rel: str):
    p = ROOT / rel
    if p.exists():
        p.unlink()
        deleted.append(rel)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Create all new districts + subfolders
# ══════════════════════════════════════════════════════════════════════════════
mkdirs(
    "academic",
    "engineering",
    "paid_media",
    "product",
    "project_management",
    "sales",
    "strategy",
    "strategy/coordination",
    "strategy/playbooks",
    "strategy/runbooks",
    "strategy/examples",
    "support",
    "testing",
    # game_development subfolders
    "game_development/blender",
    "game_development/godot",
    "game_development/roblox_studio",
    "game_development/unity",
    "game_development/unreal_engine",
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. academic/ — from research/
# ══════════════════════════════════════════════════════════════════════════════
for slug in ["anthropologist", "geographer", "historian", "narratologist", "psychologist"]:
    mv(f"research/vector-ag-academic-{slug}.md", f"academic/academic-{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 3. design/ — strip vector-ag-design- prefix
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "brand-guardian", "image-prompt-engineer", "inclusive-visuals-specialist",
    "ui-designer", "ux-architect", "ux-researcher", "visual-storyteller", "whimsy-injector",
]:
    mv(f"design/vector-ag-design-{slug}.md", f"design/design-{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 4. engineering/ — consolidate from coding/, docs/, comms/, data_analytics/, ops/, security/
# ══════════════════════════════════════════════════════════════════════════════
# From coding/
for slug in [
    "ai-engineer", "autonomous-optimization-architect", "backend-architect",
    "cms-developer", "code-reviewer", "codebase-onboarding-engineer",
    "database-optimizer", "embedded-firmware-engineer", "feishu-integration-developer",
    "filament-optimization-specialist", "frontend-developer", "git-workflow-master",
    "minimal-change-engineer", "mobile-app-builder", "rapid-prototyper",
    "senior-developer", "software-architect", "solidity-smart-contract-engineer",
    "wechat-mini-program-developer",
]:
    mv(f"coding/vector-ag-engineering-{slug}.md", f"engineering/engineering-{slug}.md")

# backend-architect-with-memory (integrations)
mv("coding/vector-ag-backend-architect-with-memory.md", "engineering/engineering-backend-architect-with-memory.md")

# From documentation/
mv("documentation/vector-ag-engineering-technical-writer.md", "engineering/engineering-technical-writer.md")

# From data_analytics/
mv("data_analytics/vector-ag-engineering-ai-data-remediation-engineer.md", "engineering/engineering-ai-data-remediation-engineer.md")
mv("data_analytics/vector-ag-engineering-data-engineer.md", "engineering/engineering-data-engineer.md")

# From ops/
mv("ops/vector-ag-engineering-devops-automator.md", "engineering/engineering-devops-automator.md")
mv("ops/vector-ag-engineering-incident-response-commander.md", "engineering/engineering-incident-response-commander.md")
mv("ops/vector-ag-engineering-sre.md", "engineering/engineering-sre.md")

# From security/
mv("security/vector-ag-engineering-security-engineer.md", "engineering/engineering-security-engineer.md")
mv("security/vector-ag-engineering-threat-detection-engineer.md", "engineering/engineering-threat-detection-engineer.md")

# From communications/
mv("communications/vector-ag-engineering-email-intelligence-engineer.md", "engineering/engineering-email-intelligence-engineer.md")
mv("communications/vector-ag-engineering-voice-ai-integration-engineer.md", "engineering/engineering-voice-ai-integration-engineer.md")

# ══════════════════════════════════════════════════════════════════════════════
# 5. finance/ — strip prefix, remove duplicates
# ══════════════════════════════════════════════════════════════════════════════
for slug in ["bookkeeper-controller", "financial-analyst", "fpa-analyst", "investment-researcher", "tax-strategist"]:
    mv(f"finance/vector-ag-finance-{slug}.md", f"finance/finance-{slug}.md")

# finance-tracker goes to support/
mv("finance/vector-ag-support-finance-tracker.md", "support/support-finance-tracker.md")

# ══════════════════════════════════════════════════════════════════════════════
# 6. game_development/ — strip prefix + add subfolders
# ══════════════════════════════════════════════════════════════════════════════
mv("game_development/vector-ag-blender-addon-engineer.md", "game_development/blender/blender-addon-engineer.md")
mv("game_development/vector-ag-game-audio-engineer.md", "game_development/game-audio-engineer.md")
mv("game_development/vector-ag-game-designer.md", "game_development/game-designer.md")
mv("game_development/vector-ag-godot-gameplay-scripter.md", "game_development/godot/godot-gameplay-scripter.md")
mv("game_development/vector-ag-godot-multiplayer-engineer.md", "game_development/godot/godot-multiplayer-engineer.md")
mv("game_development/vector-ag-godot-shader-developer.md", "game_development/godot/godot-shader-developer.md")
mv("game_development/vector-ag-level-designer.md", "game_development/level-designer.md")
mv("game_development/vector-ag-narrative-designer.md", "game_development/narrative-designer.md")
mv("game_development/vector-ag-roblox-avatar-creator.md", "game_development/roblox_studio/roblox-avatar-creator.md")
mv("game_development/vector-ag-roblox-experience-designer.md", "game_development/roblox_studio/roblox-experience-designer.md")
mv("game_development/vector-ag-roblox-systems-scripter.md", "game_development/roblox_studio/roblox-systems-scripter.md")
mv("game_development/vector-ag-technical-artist.md", "game_development/technical-artist.md")
mv("game_development/vector-ag-unity-architect.md", "game_development/unity/unity-architect.md")
mv("game_development/vector-ag-unity-editor-tool-developer.md", "game_development/unity/unity-editor-tool-developer.md")
mv("game_development/vector-ag-unity-multiplayer-engineer.md", "game_development/unity/unity-multiplayer-engineer.md")
mv("game_development/vector-ag-unity-shader-graph-artist.md", "game_development/unity/unity-shader-graph-artist.md")
mv("game_development/vector-ag-unreal-multiplayer-architect.md", "game_development/unreal_engine/unreal-multiplayer-architect.md")
mv("game_development/vector-ag-unreal-systems-engineer.md", "game_development/unreal_engine/unreal-systems-engineer.md")
mv("game_development/vector-ag-unreal-technical-artist.md", "game_development/unreal_engine/unreal-technical-artist.md")
mv("game_development/vector-ag-unreal-world-builder.md", "game_development/unreal_engine/unreal-world-builder.md")

# ══════════════════════════════════════════════════════════════════════════════
# 7. marketing/ — strip prefix, extract paid_media/
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "agentic-search-optimizer", "ai-citation-strategist", "app-store-optimizer",
    "baidu-seo-specialist", "bilibili-content-strategist", "book-co-author",
    "carousel-growth-engine", "china-ecommerce-operator", "china-market-localization-strategist",
    "content-creator", "cross-border-ecommerce", "douyin-strategist", "growth-hacker",
    "instagram-curator", "kuaishou-strategist", "linkedin-content-creator",
    "livestream-commerce-coach", "podcast-strategist", "private-domain-operator",
    "reddit-community-builder", "seo-specialist", "short-video-editing-coach",
    "social-media-strategist", "tiktok-strategist", "twitter-engager",
    "video-optimization-specialist", "wechat-official-account", "weibo-strategist",
    "xiaohongshu-specialist", "zhihu-strategist",
]:
    mv(f"marketing/vector-ag-marketing-{slug}.md", f"marketing/marketing-{slug}.md")

# paid_media/ — from marketing/
for slug in [
    "auditor", "creative-strategist", "paid-social-strategist",
    "ppc-strategist", "programmatic-buyer", "search-query-analyst", "tracking-specialist",
]:
    mv(f"marketing/vector-ag-paid-media-{slug}.md", f"paid_media/paid-media-{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 8. product/ — from personal_growth/
# ══════════════════════════════════════════════════════════════════════════════
for slug in ["behavioral-nudge-engine", "feedback-synthesizer", "manager", "sprint-prioritizer", "trend-researcher"]:
    mv(f"personal_growth/vector-ag-product-{slug}.md", f"product/product-{slug}.md")

# zk-steward goes to specialized/
mv("personal_growth/vector-ag-zk-steward.md", "specialized/zk-steward.md")

# ══════════════════════════════════════════════════════════════════════════════
# 9. project_management/ — from projects/ + specialized/
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "experiment-tracker", "jira-workflow-steward", "project-shepherd",
    "studio-operations", "studio-producer",
]:
    mv(f"projects/vector-ag-project-management-{slug}.md", f"project_management/project-management-{slug}.md")

mv("specialized/vector-ag-project-manager-senior.md", "project_management/project-manager-senior.md")

# ══════════════════════════════════════════════════════════════════════════════
# 10. sales/ — from agency/ (rename folder contents)
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "account-strategist", "coach", "deal-strategist", "discovery-coach",
    "engineer", "outbound-strategist", "pipeline-analyst", "proposal-strategist",
]:
    mv(f"agency/vector-ag-sales-{slug}.md", f"sales/sales-{slug}.md")

# These two live in specialized/ in the repo
mv("agency/vector-ag-sales-outreach.md", "specialized/sales-outreach.md")
mv("agency/vector-ag-sales-data-extraction-agent.md", "specialized/sales-data-extraction-agent.md")

# ══════════════════════════════════════════════════════════════════════════════
# 11. spatial_computing/ — strip prefix
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "macos-spatial-metal-engineer", "terminal-integration-specialist",
    "visionos-spatial-engineer", "xr-cockpit-interaction-specialist",
    "xr-immersive-developer", "xr-interface-architect",
]:
    mv(f"spatial_computing/vector-ag-{slug}.md", f"spatial_computing/{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 12. specialized/ — consolidate from governance/ + coding/ + communications/
# ══════════════════════════════════════════════════════════════════════════════
# From governance/
gov_specialized = {
    "accounts-payable-agent": "accounts-payable-agent",
    "agentic-identity-trust": "agentic-identity-trust",
    "agents-orchestrator": "agents-orchestrator",
    "automation-governance-architect": "automation-governance-architect",
    "compliance-auditor": "compliance-auditor",
    "data-consolidation-agent": "data-consolidation-agent",
    "identity-graph-operator": "identity-graph-operator",
    "report-distribution-agent": "report-distribution-agent",
    "specialized-chief-of-staff": "specialized-chief-of-staff",
    "specialized-document-generator": "specialized-document-generator",
    "specialized-mcp-builder": "specialized-mcp-builder",
    "specialized-salesforce-architect": "specialized-salesforce-architect",
    "specialized-workflow-architect": "specialized-workflow-architect",
}
for src_slug, dst_slug in gov_specialized.items():
    mv(f"governance/vector-ag-{src_slug}.md", f"specialized/{dst_slug}.md")

# support-legal-compliance-checker → support/
mv("governance/vector-ag-support-legal-compliance-checker.md", "support/support-legal-compliance-checker.md")

# From coding/
mv("coding/vector-ag-lsp-index-engineer.md", "specialized/lsp-index-engineer.md")
mv("coding/vector-ag-specialized-developer-advocate.md", "specialized/specialized-developer-advocate.md")

# From communications/
mv("communications/vector-ag-language-translator.md", "specialized/language-translator.md")

# Rename existing specialized/ files (strip vector-ag- prefix)
for slug in [
    "blockchain-security-auditor", "corporate-training-designer", "customer-service",
    "government-digital-presales-consultant", "healthcare-customer-service",
    "healthcare-marketing-compliance", "hospitality-guest-services", "hr-onboarding",
    "legal-billing-time-tracking", "legal-client-intake", "legal-document-review",
    "loan-officer-assistant", "real-estate-buyer-seller", "recruitment-specialist",
    "retail-customer-returns", "specialized-civil-engineer",
    "specialized-cultural-intelligence-strategist", "specialized-french-consulting-market",
    "specialized-korean-business-navigator", "specialized-model-qa",
    "study-abroad-advisor", "supply-chain-strategist",
]:
    mv(f"specialized/vector-ag-{slug}.md", f"specialized/{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 13. strategy/ — consolidate all NEXUS docs
# ══════════════════════════════════════════════════════════════════════════════
mv("governance/nexus_strategy.md", "strategy/nexus-strategy.md")
mv("governance/nexus_executive_brief.md", "strategy/EXECUTIVE-BRIEF.md")
mv("governance/nexus_quickstart.md", "strategy/QUICKSTART.md")
mv("governance/nexus_activation_prompts.md", "strategy/coordination/agent-activation-prompts.md")
mv("chief_of_staff/nexus_handoff_templates.md", "strategy/coordination/handoff-templates.md")

for i, (src, dst) in enumerate([
    ("nexus_phase_0_discovery", "phase-0-discovery"),
    ("nexus_phase_1_strategy", "phase-1-strategy"),
    ("nexus_phase_2_foundation", "phase-2-foundation"),
    ("nexus_phase_3_build", "phase-3-build"),
    ("nexus_phase_4_hardening", "phase-4-hardening"),
    ("nexus_phase_5_launch", "phase-5-launch"),
    ("nexus_phase_6_operate", "phase-6-operate"),
]):
    mv(f"projects/{src}.md", f"strategy/playbooks/{dst}.md")

mv("projects/nexus_runbook_startup_mvp.md", "strategy/runbooks/scenario-startup-mvp.md")
mv("projects/nexus_runbook_enterprise.md", "strategy/runbooks/scenario-enterprise-feature.md")
mv("projects/nexus_runbook_incident_response.md", "strategy/runbooks/scenario-incident-response.md")
mv("projects/nexus_runbook_marketing.md", "strategy/runbooks/scenario-marketing-campaign.md")

mv("projects/workflow_book_chapter.md", "strategy/examples/workflow-book-chapter.md")
mv("projects/workflow_landing_page.md", "strategy/examples/workflow-landing-page.md")
mv("projects/workflow_spatial_discovery.md", "strategy/examples/nexus-spatial-discovery.md")
mv("projects/workflow_startup_mvp.md", "strategy/examples/workflow-startup-mvp.md")
mv("projects/workflow_with_memory.md", "strategy/examples/workflow-with-memory.md")

# ══════════════════════════════════════════════════════════════════════════════
# 14. support/ — from data_analytics/, ops/, communications/
# ══════════════════════════════════════════════════════════════════════════════
mv("data_analytics/vector-ag-support-analytics-reporter.md", "support/support-analytics-reporter.md")
mv("ops/vector-ag-support-infrastructure-maintainer.md", "support/support-infrastructure-maintainer.md")
mv("communications/vector-ag-support-executive-summary-generator.md", "support/support-executive-summary-generator.md")
mv("communications/vector-ag-support-support-responder.md", "support/support-support-responder.md")

# ══════════════════════════════════════════════════════════════════════════════
# 15. testing/ — from qa/
# ══════════════════════════════════════════════════════════════════════════════
for slug in [
    "accessibility-auditor", "api-tester", "evidence-collector",
    "performance-benchmarker", "reality-checker", "test-results-analyzer",
    "tool-evaluator", "workflow-optimizer",
]:
    mv(f"qa/vector-ag-testing-{slug}.md", f"testing/testing-{slug}.md")

# ══════════════════════════════════════════════════════════════════════════════
# 16. DELETE — duplicates and non-agent files
# ══════════════════════════════════════════════════════════════════════════════
to_delete = [
    # Contributing doc — not an agent
    "specialized/vector-ag-contributing-zh-cn.md",
    # coding/ old duplicates (vector- prefix without -ag-)
    "coding/vector-engineering-ai-engineer.md",
    "coding/vector-engineering-backend-architect.md",
    "coding/vector-engineering-code-reviewer.md",
    "coding/vector-engineering-senior-developer.md",
    "coding/vector-specialized-developer-advocate.md",
    "coding/vector-specialized-workflow-architect.md",
    # finance/ old duplicates
    "finance/vector-finance-financial-analyst.md",
    "finance/vector-finance-investment-researcher.md",
    "finance/vector-finance-tax-strategist.md",
    # security/ old duplicates
    "security/vector-compliance-auditor.md",
    "security/vector-engineering-security-engineer.md",
    # governance/ old duplicates
    "governance/vector-agents-orchestrator.md",
    "governance/vector-specialized-chief-of-staff.md",
    # marketing/ old duplicates
    "marketing/vector-marketing-content-creator.md",
    "marketing/vector-marketing-growth-hacker.md",
    "marketing/vector-marketing-seo-specialist.md",
    "marketing/vector-marketing-social-media-strategist.md",
    # core/ duplicates (moved to engineering/)
    "core/vector-engineering-devops-automator.md",
    "core/vector-engineering-incident-response-commander.md",
]
for f in to_delete:
    rm(f)

# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"RESTRUCTURE COMPLETE")
print(f"{'='*60}")
print(f"  Directories created : {len(created)}")
print(f"  Files moved/renamed : {len(moved)}")
print(f"  Files deleted       : {len(deleted)}")
if errors:
    print(f"\nWARNINGS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
else:
    print(f"  Errors              : 0")
print(f"{'='*60}\n")
