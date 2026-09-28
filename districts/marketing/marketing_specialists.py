"""Evidence-checked Marketing / paid-media specialists (SELF_DEV_P5_MARKETING).

Each class is a real ``AgentBase`` citizen (HP, ghost memory, A2A-reachable) for one
selected Claude Code marketing persona.  Two task types per agent:

* ``<x>_brief``  -- reports which persona-specific evidence the caller supplied and what is
  still missing.  A brief is ``ready`` only when every evidence field is present.
* ``<x>_check`` -- the verification action.  It never asks a model whether the work is good.
  It recomputes something from the supplied data: platform character limits, keyword
  presence, CPA/ROAS against targets, wasted search spend, viewability, tracking-event
  coverage, landed-cost margin, outline structure.  Personas with no honest deterministic
  check return ``verified: False`` rather than faking one.

An optional free-text ``query`` gets suggestions through the approved LLM path
(``session_hydration_prompt()`` first).  Those suggestions are always labelled
``suggestion_is_evidence: False``.  Nothing here posts, spends, or edits anything external.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

# Heuristic defaults, used only when the caller supplies no threshold.  Every check reports
# ``limit_source`` ("evidence" or "default") so a default is never mistaken for a client target.
_DEFAULT_WASTE_COST = 10.0
_DEFAULT_MAX_WASTE_SHARE = 0.2
_DEFAULT_MAX_FREQUENCY = 3.5
_DEFAULT_MAX_CTR_DROP_PCT = 30.0
_DEFAULT_MIN_VIEWABILITY_PCT = 50.0  # MRC display standard: 50% of pixels for 1 continuous second
_DEFAULT_MAX_IVT_PCT = 5.0
_DEFAULT_MIN_MARGIN_PCT = 20.0
_MIN_CAROUSEL_SLIDES = 2
_MAX_CAROUSEL_SLIDES = 20
_MAX_CANDIDATES = 20


@dataclass(frozen=True)
class SpecialistProfile:
    """The bounded, independently checkable contract for one marketing persona."""

    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str
    text_limits: tuple[tuple[str, int], ...] = ()  # (draft field, max characters)
    keyword_fields: tuple[str, ...] = ()           # draft fields that must contain draft["target_keyword"]
    analyzer: str = ""                             # key into ANALYZERS


# ── deterministic analyzers ────────────────────────────────────────────────────────────


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows(evidence: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = evidence.get(key)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _threshold(evidence: dict[str, Any], key: str, default: float) -> tuple[float, str]:
    supplied = _num(evidence.get(key))
    return (supplied, "evidence") if supplied is not None else (default, "default")


def _check_search_query_waste(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(evidence, "search_terms")
    if not rows:
        return []
    min_cost, _ = _threshold(evidence, "waste_threshold_cost", _DEFAULT_WASTE_COST)
    max_share, source = _threshold(evidence, "max_waste_share", _DEFAULT_MAX_WASTE_SHARE)
    total = wasted = 0.0
    candidates: list[dict[str, Any]] = []
    for row in rows:
        cost = _num(row.get("cost")) or 0.0
        total += cost
        if (_num(row.get("conversions")) or 0.0) <= 0 and cost >= min_cost:
            wasted += cost
            candidates.append({"query": str(row.get("query", "")), "cost": cost, "clicks": _num(row.get("clicks")) or 0.0})
    candidates.sort(key=lambda c: c["cost"], reverse=True)
    share = wasted / total if total > 0 else 0.0
    return [{
        "check": "wasted_spend_share", "passed": share <= max_share, "actual": round(share, 4),
        "limit": max_share, "limit_source": source, "wasted_cost": round(wasted, 2),
        "total_cost": round(total, 2), "negative_keyword_candidates": candidates[:_MAX_CANDIDATES],
    }]


def _check_ppc_budget(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    target_cpa, target_roas = _num(evidence.get("target_cpa")), _num(evidence.get("target_roas"))
    out: list[dict[str, Any]] = []
    for row in _rows(evidence, "campaigns"):
        name, spend = str(row.get("name", "")), _num(row.get("spend")) or 0.0
        if spend <= 0:
            continue
        conversions, value = _num(row.get("conversions")) or 0.0, _num(row.get("conversion_value"))
        if target_cpa is not None:
            cpa = spend / conversions if conversions > 0 else None
            out.append({"check": "cpa_within_target", "campaign": name, "actual": None if cpa is None else round(cpa, 2),
                        "limit": target_cpa, "limit_source": "evidence", "passed": cpa is not None and cpa <= target_cpa})
        if target_roas is not None and value is not None:
            roas = value / spend
            out.append({"check": "roas_meets_target", "campaign": name, "actual": round(roas, 2),
                        "limit": target_roas, "limit_source": "evidence", "passed": roas >= target_roas})
    return out


def _check_account_structure(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [r for r in _rows(evidence, "campaigns") if (_num(r.get("spend")) or 0.0) > 0]
    if not rows:
        return []
    untracked = [str(r.get("name", "")) for r in rows if r.get("conversion_tracking") is not True]
    no_conv = [str(r.get("name", "")) for r in rows if (_num(r.get("conversions")) or 0.0) <= 0]
    return [
        {"check": "spend_has_confirmed_conversion_tracking", "passed": not untracked, "campaigns_flagged": untracked},
        {"check": "no_spend_without_conversions", "passed": not no_conv, "campaigns_flagged": no_conv},
    ]


def _check_paid_social_metrics(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    max_freq, freq_src = _threshold(evidence, "max_frequency", _DEFAULT_MAX_FREQUENCY)
    max_drop, drop_src = _threshold(evidence, "max_ctr_drop_pct", _DEFAULT_MAX_CTR_DROP_PCT)
    out: list[dict[str, Any]] = []
    for row in _rows(evidence, "ad_sets"):
        name = str(row.get("name", ""))
        freq = _num(row.get("frequency"))
        if freq is not None:
            out.append({"check": "frequency_within_limit", "ad_set": name, "actual": freq, "limit": max_freq,
                        "limit_source": freq_src, "passed": freq <= max_freq})
        ctr, prev = _num(row.get("ctr_pct")), _num(row.get("ctr_pct_prev"))
        if ctr is not None and prev is not None and prev > 0:
            drop = (prev - ctr) / prev * 100.0
            out.append({"check": "ctr_decline_within_limit", "ad_set": name, "actual": round(drop, 2), "limit": max_drop,
                        "limit_source": drop_src, "passed": drop <= max_drop})
    return out


def _check_programmatic_inventory(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    min_view, view_src = _threshold(evidence, "min_viewability_pct", _DEFAULT_MIN_VIEWABILITY_PCT)
    max_ivt, ivt_src = _threshold(evidence, "max_ivt_pct", _DEFAULT_MAX_IVT_PCT)
    out: list[dict[str, Any]] = []
    for row in _rows(evidence, "line_items"):
        name = str(row.get("name", ""))
        view, ivt = _num(row.get("viewability_pct")), _num(row.get("ivt_pct"))
        if view is not None:
            out.append({"check": "viewability_meets_minimum", "line_item": name, "actual": view, "limit": min_view,
                        "limit_source": view_src, "passed": view >= min_view})
        if ivt is not None:
            out.append({"check": "invalid_traffic_within_limit", "line_item": name, "actual": ivt, "limit": max_ivt,
                        "limit_source": ivt_src, "passed": ivt <= max_ivt})
    return out


def _check_tracking_events(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    events = _rows(evidence, "tracked_events")
    required = evidence.get("required_events")
    out: list[dict[str, Any]] = []
    if isinstance(required, list) and required:
        present = {str(e.get("name", "")) for e in events}
        missing = [str(r) for r in required if str(r) not in present]
        out.append({"check": "required_events_present", "passed": not missing, "missing": missing})
    by_name: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_name.setdefault(str(event.get("name", "")), []).append(event)
    # An event sent by both browser pixel and server API needs a shared event_id or platforms double count it.
    undeduped = [
        name for name, group in by_name.items()
        if {str(e.get("source", "")) for e in group} >= {"pixel", "server"} and not all(e.get("has_event_id") is True for e in group)
    ]
    if events:
        out.append({"check": "dual_source_events_deduplicated", "passed": not undeduped, "events_flagged": sorted(undeduped)})
    return out


def _check_cross_border_margin(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    min_margin, source = _threshold(evidence, "min_margin_pct", _DEFAULT_MIN_MARGIN_PCT)
    out: list[dict[str, Any]] = []
    for row in _rows(evidence, "products"):
        price = _num(row.get("price"))
        if price is None or price <= 0:
            continue
        costs = sum(_num(row.get(k)) or 0.0 for k in ("cogs", "shipping", "duties"))
        fees = price * (_num(row.get("platform_fee_pct")) or 0.0) / 100.0
        margin_pct = (price - costs - fees) / price * 100.0
        out.append({"check": "landed_margin_meets_minimum", "sku": str(row.get("sku", "")), "actual": round(margin_pct, 2),
                    "limit": min_margin, "limit_source": source, "passed": margin_pct >= min_margin})
    return out


def _check_outline(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    draft = evidence.get("draft")
    chapters = draft.get("chapters") if isinstance(draft, dict) else None
    if not isinstance(chapters, list):
        return []
    titles = [str(c).strip().lower() for c in chapters]
    duplicates = sorted({t for t in titles if t and titles.count(t) > 1})
    return [
        {"check": "outline_has_chapters", "passed": bool(titles), "actual": len(titles)},
        {"check": "outline_titles_non_empty", "passed": all(titles)},
        {"check": "outline_titles_unique", "passed": not duplicates, "duplicates": duplicates},
    ]


def _check_carousel_slides(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    draft = evidence.get("draft")
    slides = draft.get("slides") if isinstance(draft, dict) else None
    if not isinstance(slides, list):
        return []
    return [{"check": "slide_count_within_platform_range", "actual": len(slides), "limit": [_MIN_CAROUSEL_SLIDES, _MAX_CAROUSEL_SLIDES],
             "passed": _MIN_CAROUSEL_SLIDES <= len(slides) <= _MAX_CAROUSEL_SLIDES}]


ANALYZERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "search_query_waste": _check_search_query_waste,
    "ppc_budget": _check_ppc_budget,
    "account_structure": _check_account_structure,
    "paid_social_metrics": _check_paid_social_metrics,
    "programmatic_inventory": _check_programmatic_inventory,
    "tracking_events": _check_tracking_events,
    "cross_border_margin": _check_cross_border_margin,
    "outline": _check_outline,
    "carousel_slides": _check_carousel_slides,
}


# ── base class ─────────────────────────────────────────────────────────────────────────


class MarketingSpecialist(AgentBase):
    """Base class for read-only, evidence-checked Marketing personas."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="marketing",
            generation=generation,
        )
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][marketing_specialists] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return an auditable report based only on submitted evidence fields."""
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [f for f in self.profile.evidence_fields if supplied.get(f)]
        missing = [f for f in self.profile.evidence_fields if not supplied.get(f)]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        """Recompute persona checks from supplied data.  Never consults a model."""
        supplied = evidence if isinstance(evidence, dict) else {}
        draft = supplied.get("draft") if isinstance(supplied.get("draft"), dict) else {}
        checks: list[dict[str, Any]] = []
        for field, limit in self.profile.text_limits:
            if field in draft:
                length = len(str(draft[field]))
                checks.append({"check": f"{field}_length", "actual": length, "limit": limit, "passed": length <= limit})
        keyword = str(draft.get("target_keyword", "")).strip().lower()
        if keyword:
            for field in self.profile.keyword_fields:
                if field in draft:
                    checks.append({"check": f"{field}_contains_target_keyword", "passed": keyword in str(draft[field]).lower()})
        if self.profile.analyzer:
            checks.extend(ANALYZERS[self.profile.analyzer](supplied))
        return {
            "verified": bool(checks),
            "verified_by": "deterministic_recomputation" if checks else "none",
            "passed": all(c["passed"] for c in checks) if checks else None,
            "checks": checks,
            "note": "" if checks else "No checkable evidence supplied, or no deterministic check exists for this persona; brief completeness only.",
        }

    def synthesize_suggestions(self, query: str, report: dict[str, Any]) -> str:
        """Offer clearly non-evidentiary suggestions through the approved LLM path."""
        hydration = ContextEngine().session_hydration_prompt({"query": query})
        prompt = (
            f"{hydration}\n\nYou are {self.name}, a VECTOR Marketing specialist. "
            "Suggest next steps only; do not assert that missing evidence has been verified and "
            "do not invent metrics, platform policies, or results.\n\n"
            f"Brief report: {report}\n\nRequest: {query}"
        )
        return chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
            district="marketing",
        ).strip()

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        try:
            evidence = task.get("evidence") or params.get("evidence")
            report = self.build_evidence_report(evidence)
            response: dict[str, Any] = {"status": "ok", "report": report}
            if task_type == self.profile.audit_action:
                response["verification"] = self.run_checks(evidence)
            query = str(task.get("query") or params.get("query") or params.get("content") or "").strip()
            if query:
                suggestion = await asyncio.to_thread(self.synthesize_suggestions, query, report)
                if suggestion:
                    response["suggestion"] = suggestion
                    response["suggestion_is_evidence"] = False
            earned = report["status"] == "ready" or bool(response.get("verification", {}).get("verified"))
            if earned:
                self.award_points(20, f"{task_type}_completed")
            return response
        except Exception as exc:
            logger.error("[VECTOR][marketing_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "marketing_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


def _p(name: str, slug: str, primary: str, audit: str, evidence: tuple[str, ...], deliverable: str, **kw: Any) -> SpecialistProfile:
    return SpecialistProfile(name, f"{slug}_001", primary, audit, evidence, deliverable, **kw)


class AppStoreOptimizer(MarketingSpecialist):
    profile = _p("AppStoreOptimizer", "app_store_optimizer", "aso_listing_brief", "aso_listing_check",
                 ("app_category", "target_keywords", "competitor_listings"), "app store listing brief",
                 text_limits=(("title", 30), ("subtitle", 30), ("keywords", 100), ("short_description", 80)),
                 keyword_fields=("title",))


class BaiduSEOSpecialist(MarketingSpecialist):
    profile = _p("BaiduSEOSpecialist", "baidu_seo_specialist", "baidu_seo_brief", "baidu_seo_check",
                 ("site_url", "target_keywords", "icp_status"), "Baidu SEO brief",
                 keyword_fields=("title", "description", "h1"))


class BilibiliContentStrategist(MarketingSpecialist):
    profile = _p("BilibiliContentStrategist", "bilibili_content_strategist", "bilibili_content_brief", "bilibili_title_check",
                 ("audience", "channel_niche", "content_goals"), "Bilibili content brief", text_limits=(("title", 80),))


class BookCoAuthor(MarketingSpecialist):
    profile = _p("BookCoAuthor", "book_co_author", "book_coauthor_brief", "book_outline_check",
                 ("book_premise", "target_reader", "author_voice_samples"), "book outline brief", analyzer="outline")


class CarouselGrowthEngine(MarketingSpecialist):
    profile = _p("CarouselGrowthEngine", "carousel_growth_engine", "carousel_growth_brief", "carousel_slide_check",
                 ("platform", "audience", "topic_backlog"), "carousel growth brief",
                 text_limits=(("caption", 2200),), analyzer="carousel_slides")


class ChinaEcommerceOperator(MarketingSpecialist):
    profile = _p("ChinaEcommerceOperator", "china_ecommerce_operator", "china_ecom_brief", "china_ecom_check",
                 ("platform", "product_catalog", "local_operator"), "China e-commerce operations brief")


class ChinaMarketLocalizationStrategist(MarketingSpecialist):
    profile = _p("ChinaMarketLocalizationStrategist", "china_market_localization_strategist", "china_localization_brief",
                 "china_localization_check", ("source_content", "target_platforms", "native_reviewer"), "China localization brief")


class CrossBorderEcommerce(MarketingSpecialist):
    profile = _p("CrossBorderEcommerce", "cross_border_ecommerce", "cross_border_brief", "cross_border_margin_check",
                 ("origin_market", "destination_market", "products"), "cross-border e-commerce brief",
                 analyzer="cross_border_margin")


class DouyinStrategist(MarketingSpecialist):
    profile = _p("DouyinStrategist", "douyin_strategist", "douyin_strategy_brief", "douyin_content_check",
                 ("audience", "content_pillars", "local_reviewer"), "Douyin strategy brief")


class InstagramCurator(MarketingSpecialist):
    profile = _p("InstagramCurator", "instagram_curator", "instagram_curation_brief", "instagram_caption_check",
                 ("brand_voice", "audience", "content_pillars"), "Instagram curation brief", text_limits=(("caption", 2200),))


class KuaishouStrategist(MarketingSpecialist):
    profile = _p("KuaishouStrategist", "kuaishou_strategist", "kuaishou_strategy_brief", "kuaishou_content_check",
                 ("audience", "content_pillars", "local_reviewer"), "Kuaishou strategy brief")


class LinkedInContentCreator(MarketingSpecialist):
    profile = _p("LinkedInContentCreator", "linkedin_content_creator", "linkedin_content_brief", "linkedin_post_check",
                 ("author_profile", "audience", "content_pillars"), "LinkedIn content brief", text_limits=(("post", 3000),))


class LivestreamCommerceCoach(MarketingSpecialist):
    profile = _p("LivestreamCommerceCoach", "livestream_commerce_coach", "livestream_commerce_brief", "livestream_run_check",
                 ("platform", "product_lineup", "host_profile"), "livestream commerce brief")


class PodcastStrategist(MarketingSpecialist):
    profile = _p("PodcastStrategist", "podcast_strategist", "podcast_strategy_brief", "podcast_episode_check",
                 ("show_concept", "target_listener", "release_cadence"), "podcast strategy brief")


class PrivateDomainOperator(MarketingSpecialist):
    profile = _p("PrivateDomainOperator", "private_domain_operator", "private_domain_brief", "private_domain_funnel_check",
                 ("channels", "audience_segments", "consent_basis"), "private-domain operations brief")


class RedditCommunityBuilder(MarketingSpecialist):
    profile = _p("RedditCommunityBuilder", "reddit_community_builder", "reddit_community_brief", "reddit_post_check",
                 ("subreddits", "community_rules_read", "brand_voice"), "Reddit community brief", text_limits=(("title", 300),))


class ShortVideoEditingCoach(MarketingSpecialist):
    profile = _p("ShortVideoEditingCoach", "short_video_editing_coach", "short_video_edit_brief", "short_video_edit_check",
                 ("platform", "raw_footage_summary", "target_length"), "short-video editing brief")


class TikTokStrategist(MarketingSpecialist):
    profile = _p("TikTokStrategist", "tiktok_strategist", "tiktok_strategy_brief", "tiktok_caption_check",
                 ("audience", "content_pillars", "brand_voice"), "TikTok strategy brief", text_limits=(("caption", 2200),))


class TwitterEngager(MarketingSpecialist):
    profile = _p("TwitterEngager", "twitter_engager", "twitter_engagement_brief", "twitter_post_check",
                 ("brand_voice", "audience", "topics"), "Twitter/X engagement brief", text_limits=(("post", 280),))


class VideoOptimizationSpecialist(MarketingSpecialist):
    profile = _p("VideoOptimizationSpecialist", "video_optimization_specialist", "video_optimization_brief", "video_metadata_check",
                 ("channel", "target_keywords", "video_summary"), "video optimization brief",
                 text_limits=(("title", 100), ("description", 5000)), keyword_fields=("title", "description"))


class XiaohongshuSpecialist(MarketingSpecialist):
    profile = _p("XiaohongshuSpecialist", "xiaohongshu_specialist", "xiaohongshu_note_brief", "xiaohongshu_note_check",
                 ("audience", "product_or_topic", "native_reviewer"), "Xiaohongshu note brief",
                 text_limits=(("title", 20), ("body", 1000)), keyword_fields=("title", "body"))


class ZhihuStrategist(MarketingSpecialist):
    profile = _p("ZhihuStrategist", "zhihu_strategist", "zhihu_strategy_brief", "zhihu_answer_check",
                 ("expertise_area", "target_questions", "native_reviewer"), "Zhihu strategy brief")


class PaidMediaAuditor(MarketingSpecialist):
    profile = _p("PaidMediaAuditor", "paid_media_auditor", "paid_media_audit_brief", "paid_media_account_check",
                 ("platforms", "account_export", "business_goals"), "paid media audit brief", analyzer="account_structure")


class PaidMediaCreativeStrategist(MarketingSpecialist):
    profile = _p("PaidMediaCreativeStrategist", "paid_media_creative_strategist", "paid_creative_brief", "paid_creative_check",
                 ("offer", "audience", "platform_specs"), "paid creative brief")


class PaidMediaPaidSocialStrategist(MarketingSpecialist):
    profile = _p("PaidMediaPaidSocialStrategist", "paid_media_paid_social_strategist", "paid_social_brief", "paid_social_metrics_check",
                 ("platforms", "audience", "budget"), "paid social brief", analyzer="paid_social_metrics")


class PaidMediaPPCStrategist(MarketingSpecialist):
    profile = _p("PaidMediaPPCStrategist", "paid_media_ppc_strategist", "ppc_strategy_brief", "ppc_budget_check",
                 ("account_export", "target_cpa_or_roas", "budget"), "PPC strategy brief", analyzer="ppc_budget")


class PaidMediaProgrammaticBuyer(MarketingSpecialist):
    profile = _p("PaidMediaProgrammaticBuyer", "paid_media_programmatic_buyer", "programmatic_buy_brief", "programmatic_inventory_check",
                 ("dsp", "audience", "budget"), "programmatic buying brief", analyzer="programmatic_inventory")


class PaidMediaSearchQueryAnalyst(MarketingSpecialist):
    profile = _p("PaidMediaSearchQueryAnalyst", "paid_media_search_query_analyst", "search_query_brief", "search_query_waste_check",
                 ("search_terms_report", "conversion_definition", "current_negatives"), "search query analysis brief",
                 analyzer="search_query_waste")


class PaidMediaTrackingSpecialist(MarketingSpecialist):
    profile = _p("PaidMediaTrackingSpecialist", "paid_media_tracking_specialist", "tracking_setup_brief", "tracking_event_check",
                 ("platforms", "tracked_events", "required_events"), "tracking setup brief", analyzer="tracking_events")


SPECIALIST_CLASSES: tuple[type[MarketingSpecialist], ...] = (
    AppStoreOptimizer, BaiduSEOSpecialist, BilibiliContentStrategist, BookCoAuthor, CarouselGrowthEngine,
    ChinaEcommerceOperator, ChinaMarketLocalizationStrategist, CrossBorderEcommerce, DouyinStrategist,
    InstagramCurator, KuaishouStrategist, LinkedInContentCreator, LivestreamCommerceCoach, PodcastStrategist,
    PrivateDomainOperator, RedditCommunityBuilder, ShortVideoEditingCoach, TikTokStrategist, TwitterEngager,
    VideoOptimizationSpecialist, XiaohongshuSpecialist, ZhihuStrategist, PaidMediaAuditor,
    PaidMediaCreativeStrategist, PaidMediaPaidSocialStrategist, PaidMediaPPCStrategist,
    PaidMediaProgrammaticBuyer, PaidMediaSearchQueryAnalyst, PaidMediaTrackingSpecialist,
)


if __name__ == "__main__":
    async def _smoke() -> None:
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            brief = await specialist.run({"type": specialist.profile.primary_action, "evidence": {}})
            assert brief["status"] == "ok" and brief["report"]["missing_evidence"]
            check = await specialist.run({"type": specialist.profile.audit_action, "evidence": {}})
            assert check["verification"]["verified"] is False
        tweet = await TwitterEngager().run({"type": "twitter_post_check", "evidence": {"draft": {"post": "x" * 281}}})
        assert tweet["verification"]["passed"] is False
        logger.info("[VECTOR][marketing_specialists] smoke check passed")

    asyncio.run(_smoke())
