# SELF_DEV_P5_MARKETING — marketing + paid-media personas (district=marketing)

Spec followed: `SELF_DEV_AGENT_SPEC.md`. Branch: `vector-dev/904e5ac20caa4151a0e154aa473aa667`.

## Verification status (updated by Claude 2026-09-29 -- see "Fix applied" section below)

Everything in this doc below was originally written with no shell access; it has now actually been
run: `python districts/marketing/marketing_specialists.py` smoke check passes,
`tests/test_marketing_district_run_wiring.py` is 41/41 passing.

Also not confirmed (no way to search at the time): that the 29 `agent_id`s and 58 action names are unused elsewhere, and that the YAML still parses.
The 31 persona `.md` files were **not found** in this worktree's `.claude/agents/` (two spot-checks returned "does not exist"),
so each agent's scope is inferred from the persona name and the marketing domain, not from the persona text.

## Post-review fixes (independent review, CHANGES_REQUIRED)

Two ERROR findings, both fixed in this pass, smallest safe change each:

1. **`core/city/governor.py` — missing exact routes.** None of the 58 new capability names had an exact `DISTRICT_TASK_MAP`
   entry, so normal Governor dispatch misrouted several via substring/word-overlap fallback (confirmed examples:
   `search_query_waste_check` -> research, `video_metadata_check` -> learning, `ppc_budget_check` -> governance,
   `paid_social_metrics_check` -> data_analytics, `kuaishou_content_check` -> intelligence). Added all 58 as exact
   `"<action>": "marketing"` entries in `DISTRICT_TASK_MAP` (right after the existing marketing block), plus two regression
   tests in `tests/test_marketing_district_run_wiring.py`: one asserting every specialist capability has an exact `"marketing"`
   route, one asserting the five misrouted examples the review cited now route correctly.
2. **`districts/marketing/_skill_loader.py:48` — `SkillMixin._chat()` skipped session hydration (RULE 1).** `AICitationStrategist`
   (the real match for both `ai-citation-strategist` and `agentic-search-optimizer`) calls `_chat()` for `generate_aeo_strategy`
   and the `competitors` task, and neither path called `session_hydration_prompt()` before `vectorcode_llm.chat()`. Fixed by
   having `_chat()` call `ContextEngine().session_hydration_prompt()` and prepend it (with `_with_skill_system()`, so the skill
   prompt is kept too) as the system message before every call. This is the shared mixin used by 5 marketing agents, so the fix
   closes the gap for all of them, not just AICitationStrategist. Added a regression test that mocks only the external LLM call
   (per `.claude/rules/testing.md` — external APIs may be mocked, `session_hydration_prompt()` itself is not) and asserts the
   real hydration block (`"[SESSION CONTEXT"`) is present in the system message sent to the model.

## Fix applied after the second cross-provider review round (Claude, 2026-09-29)

Everything above was written with no shell access -- Claude ran it for the first time. Result:
`python districts/marketing/marketing_specialists.py` smoke check passed; all 39 existing +
2 new tests in `tests/test_marketing_district_run_wiring.py` passed (41 total after this fix).

The reviewer's third finding, verified real: **`task_completion`** -- `AICitationStrategist
.check_agentic_task_completion()`, this report's own claimed real match for the
`agentic-search-optimizer` persona -- is a real, agent-declared capability with NO
`core/config.py` tier entry at all. Same class of gap T9-fix-1 closed for `email_agent.py`:
`Governor._is_known_task_type()` let it dispatch with zero `PermissionGateway` involvement. The
method itself is a pure deterministic keyword check on caller-supplied text (no network call, no
LLM call, no mutation) -- GREEN. New tier entry added, flagged for the pending independent review.
Two new regression tests: `test_task_completion_has_a_real_tier`,
`test_task_completion_dispatches_via_governor`.

## What was built

31 personas in scope = 2 already real + 29 new.

**Already real, not duplicated (spec: check for an existing match first):**
- `marketing-ai-citation-strategist` -> `districts/marketing/ai_citation_strategist.py` (registered).
- `marketing-agentic-search-optimizer` -> same agent. Its docstring covers Agentic Search Optimization / WebMCP readiness
  (`check_agentic_task_completion`, capability `task_completion`). If the owner wants a separate agent, that is a new decision.

**New: `districts/marketing/marketing_specialists.py`** — 29 `AgentBase` subclasses (born 500 HP, ghost inheritance, generation), registered in
`config/agent_manifest.yaml` under `marketing`, A2A-reachable through the normal registry. Same shape as the approved design-district package
(`design_specialists.py`). Two task types each:
- `<x>_brief` — reports which persona-specific evidence was supplied and what is missing (`ready` vs `needs_human`).
- `<x>_check` — the verification action. Recomputes from supplied data; never asks a model whether the work is good.

LLM use is only an optional free-text `query` -> suggestions, after `ContextEngine().session_hydration_prompt()`, via
`core.inference.vectorcode_llm.chat` (free-tier/local routing). Output is marked `suggestion_is_evidence: False`.
HP is awarded only when a brief is `ready` or a check actually verified something; exceptions deduct HP.

### What each `_check` really verifies

| Kind | Agents | Check |
|---|---|---|
| Numeric analyzers | search_query_analyst | wasted-spend share + negative-keyword candidates from a search-terms report |
| | ppc_strategist | per-campaign CPA / ROAS vs caller-supplied targets |
| | paid_social_strategist | per-ad-set frequency and CTR decline |
| | programmatic_buyer | per-line-item viewability and invalid-traffic rate |
| | tracking_specialist | required-event coverage; pixel+server events must share `event_id` |
| | auditor | spend without confirmed conversion tracking; spend with zero conversions |
| | cross_border_ecommerce | landed-cost margin per SKU |
| Structure | book_co_author, carousel_growth_engine | outline chapters non-empty/unique; carousel slide count |
| Length / keyword | app_store_optimizer, baidu_seo, bilibili, instagram, linkedin, reddit, tiktok, twitter, video_optimization, xiaohongshu | platform character limits and/or target-keyword presence in draft fields |
| **None** (`verified: false`) | china_ecommerce_operator, china_market_localization, douyin, kuaishou, livestream_commerce_coach, podcast_strategist, private_domain_operator, short_video_editing_coach, zhihu, paid_media_creative_strategist | No honest deterministic check exists. They give an evidence-completeness brief only, and say so. Not faked with an LLM stub. |

## Tier entries (NEW — flagged for the pending independent review)

58 new GREEN entries added to `PermissionConfig.green` in `core/config.py` (marked with a comment there). **No existing entry changed or loosened.**
Every handler is in-memory / recompute-only (no posting, spending, sending, or external edit):

aso_listing_brief, aso_listing_check, baidu_seo_brief, baidu_seo_check, bilibili_content_brief, bilibili_title_check, book_coauthor_brief,
book_outline_check, carousel_growth_brief, carousel_slide_check, china_ecom_brief, china_ecom_check, china_localization_brief,
china_localization_check, cross_border_brief, cross_border_margin_check, douyin_strategy_brief, douyin_content_check,
instagram_curation_brief, instagram_caption_check, kuaishou_strategy_brief, kuaishou_content_check, linkedin_content_brief,
linkedin_post_check, livestream_commerce_brief, livestream_run_check, podcast_strategy_brief, podcast_episode_check,
private_domain_brief, private_domain_funnel_check, reddit_community_brief, reddit_post_check, short_video_edit_brief,
short_video_edit_check, tiktok_strategy_brief, tiktok_caption_check, twitter_engagement_brief, twitter_post_check,
video_optimization_brief, video_metadata_check, xiaohongshu_note_brief, xiaohongshu_note_check, zhihu_strategy_brief,
zhihu_answer_check, paid_media_audit_brief, paid_media_account_check, paid_creative_brief, paid_creative_check,
paid_social_brief, paid_social_metrics_check, ppc_strategy_brief, ppc_budget_check, programmatic_buy_brief,
programmatic_inventory_check, search_query_brief, search_query_waste_check, tracking_setup_brief, tracking_event_check.

The actions that would publish or spend (posting, campaign edits, budget changes) are **deliberately not built**. When they are, they need
YELLOW/RED tiers and the PermissionGateway.

## Tests

`tests/test_marketing_district_run_wiring.py` — 10 new tests appended (existing 7-class trip-wire tests untouched). No mocks; real agents, real
`PermissionConfig`, real manifest file. They cover: count/unique ids, manifest<->class capability match, GREEN-and-only-GREEN tiering, both actions
per agent on empty evidence, unknown-type rejection, HP earned only on ready evidence, the `{"type","params":{"evidence"}}` production shape, and
hand-computed results for twitter/search-query/ppc/tracking/cross-border. **Not yet run.**

## Caveats and risks

- Platform limits (ASO 30/30/100/80, X 280, LinkedIn 3000, Instagram caption 2200, YouTube 100/5000, Reddit title 300, Xiaohongshu 20/1000, Bilibili title 80,
  TikTok caption 2200 as a conservative figure) are static constants from memory, not fetched. Platforms change them; re-verify before relying on them.
- Threshold defaults (waste, frequency, CTR drop, IVT, margin) are heuristics used only when the caller supplies none; every result carries `limit_source`.
- `core/city/governor.py` `DISTRICT_TASK_MAP` now has an exact `"marketing"` entry for all 58 capability names (post-review fix,
  see above). Dispatch by declared capability / A2A also still works unchanged.
- Existing partial overlaps I did not remove: `google_ads_agent` (PPC), `meta_ads_agent` (paid social), `attribution_agent` + `sgtm_agent`
  (tracking), `ads_orchestrator_agent` (auditor). The new agents differ in that they take supplied evidence and recompute; they do not call platform APIs.
- Only the required test file was touched; no other suite was run.

## If this were split further — what I would deprioritize

Lowest real-world priority now (China-platform, need a native/local reviewer and have no deterministic check): **china_ecommerce_operator,
china_market_localization_strategist, douyin_strategist, kuaishou_strategist, livestream_commerce_coach, private_domain_operator, zhihu_strategist**
(plus baidu_seo, bilibili, xiaohongshu, which do have length/keyword checks). Next: podcast_strategist, book_co_author, short_video_editing_coach.
Highest value, keep first: the seven paid-media agents (numeric checks), then app_store_optimizer, video_optimization, linkedin, twitter, reddit.
