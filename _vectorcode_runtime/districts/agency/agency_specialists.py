"""Deterministic, evidence-gated Agency sales specialists.

These specialists make bounded sales personas real only where caller-supplied
evidence can be checked without asking an LLM to verify its own work.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase


@dataclass(frozen=True)
class AgencySpecialistProfile:
    name: str
    agent_id: str
    brief_action: str
    check_action: str
    required_fields: tuple[str, ...]
    deliverable: str


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def _normalized_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _parse_date(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class AgencySalesSpecialist(AgentBase):
    """Base class for read-only, deterministic Agency sales checks."""

    profile: AgencySpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="agency",
            generation=generation,
        )
        self.capabilities = [self.profile.brief_action, self.profile.check_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][agency_specialists] initialized {}", self.name)

    def _evidence_state(self, evidence: Any) -> tuple[dict[str, Any], list[str], list[str]]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.required_fields if _has_value(supplied.get(field))]
        missing = [field for field in self.profile.required_fields if field not in present]
        return supplied, present, missing

    def build_brief(self, evidence: Any) -> dict[str, Any]:
        _, present, missing = self._evidence_state(evidence)
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.required_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "deterministic": True,
            "read_only": True,
        }

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.brief_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}}. This method read
        # task.get("evidence") directly, never task["params"]["evidence"],
        # so a real dispatch always saw no evidence at all -- confirmed live
        # (task.get("evidence") is None for the nested-params shape) and
        # already fixed once, later, in districts/marketing/
        # marketing_specialists.py's run() (`task.get("evidence") or
        # params.get("evidence")`) but never backported here. Same fix.
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        raw_evidence = task.get("evidence") or params.get("evidence")
        try:
            evidence, _, missing = self._evidence_state(raw_evidence)
            if task_type == self.profile.brief_action or missing:
                report = self.build_brief(evidence)
            else:
                report = self.evaluate(evidence)
                report.setdefault("persona", self.name)
                report.setdefault("deliverable", self.profile.deliverable)
                report.setdefault("missing_evidence", [])
                report.setdefault("deterministic", True)
                report.setdefault("read_only", True)
            if report.get("status") in {"ready", "passed"}:
                self.award_points(10, f"{task_type}_completed")
            return {"status": "ok", "report": report}
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("[VECTOR][agency_specialists] {} rejected evidence: {}", self.name, exc)
            return {
                "status": "ok",
                "report": {
                    **self.build_brief(raw_evidence),
                    "status": "needs_human",
                    "validation_error": str(exc),
                },
            }
        except Exception as exc:
            logger.error("[VECTOR][agency_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "agency_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


class AccountStrategist(AgencySalesSpecialist):
    """Score account health and expansion risk from supplied account evidence."""

    profile = AgencySpecialistProfile(
        "AccountStrategist",
        "account_strategist_001",
        "acct_health_brief",
        "acct_health_check",
        ("engagement_history", "contract_value", "renewal_date", "expansion_signals", "stakeholder_map"),
        "deterministic account health and expansion-risk score",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        history = evidence["engagement_history"]
        stakeholders = evidence["stakeholder_map"]
        signals = evidence["expansion_signals"]
        if not isinstance(history, list) or not isinstance(stakeholders, list) or not isinstance(signals, list):
            raise ValueError("engagement_history, stakeholder_map, and expansion_signals must be lists")
        contract_value = float(evidence["contract_value"])
        renewal = _parse_date(evidence["renewal_date"])
        now = _parse_date(evidence.get("as_of", datetime.now(UTC).isoformat()))
        days_to_renewal = (renewal - now).days
        recent_engagements = sum(
            1 for item in history
            if isinstance(item, dict)
            and _has_value(item.get("date"))
            and 0 <= (now - _parse_date(item["date"])).days <= 60
        )
        decision_roles = {
            str(person.get("role", "")).casefold()
            for person in stakeholders
            if isinstance(person, dict) and _has_value(person.get("role"))
        }
        has_decision_maker = bool(decision_roles & {"economic_buyer", "decision_maker", "champion"})
        positive_signals = sum(
            1 for signal in signals
            if isinstance(signal, dict) and str(signal.get("direction", "")).casefold() == "positive"
        )
        negative_signals = sum(
            1 for signal in signals
            if isinstance(signal, dict) and str(signal.get("direction", "")).casefold() == "negative"
        )
        health_score = max(
            0,
            min(
                100,
                40
                + min(recent_engagements, 4) * 10
                + (15 if has_decision_maker else -10)
                + positive_signals * 8
                - negative_signals * 12
                + (8 if contract_value > 0 else -15)
                - (15 if days_to_renewal < 30 else 0),
            ),
        )
        checks = [
            _check("recent_engagement_present", recent_engagements > 0, recent_engagements),
            _check("decision_stakeholder_mapped", has_decision_maker, sorted(decision_roles)),
            _check("contract_value_positive", contract_value > 0, contract_value),
            _check("renewal_not_already_past", days_to_renewal >= 0, days_to_renewal),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "health_score": int(health_score),
            "risk_band": "low" if health_score >= 75 else "medium" if health_score >= 50 else "high",
            "days_to_renewal": days_to_renewal,
            "recent_engagements_60d": recent_engagements,
            "positive_expansion_signals": positive_signals,
            "negative_expansion_signals": negative_signals,
        }


class DealStrategist(AgencySalesSpecialist):
    """Check one deal's MEDDPICC completeness without pipeline-level summaries."""

    profile = AgencySpecialistProfile(
        "DealStrategist",
        "deal_strategist_001",
        "deal_meddpicc_brief",
        "deal_meddpicc_check",
        ("metrics", "economic_buyer", "decision_criteria", "decision_process", "identified_pain", "champion", "competition"),
        "MEDDPICC completeness and risk report for one deal",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        field_quality = {
            "metrics": isinstance(evidence["metrics"], dict) and len(evidence["metrics"]) >= 2,
            "economic_buyer": isinstance(evidence["economic_buyer"], dict)
            and _has_value(evidence["economic_buyer"].get("name"))
            and _has_value(evidence["economic_buyer"].get("role")),
            "decision_criteria": len(_normalized_set(evidence["decision_criteria"])) >= 2,
            "decision_process": isinstance(evidence["decision_process"], list) and len(evidence["decision_process"]) >= 2,
            "identified_pain": len(str(evidence["identified_pain"]).strip()) >= 20,
            "champion": isinstance(evidence["champion"], dict)
            and _has_value(evidence["champion"].get("name"))
            and evidence["champion"].get("validated") is True,
            "competition": len(_normalized_set(evidence["competition"])) >= 1,
        }
        weak_fields = sorted(field for field, passed in field_quality.items() if not passed)
        checks = [_check(f"{field}_is_strong", passed, evidence[field]) for field, passed in field_quality.items()]
        return {
            "status": "passed" if not weak_fields else "needs_human",
            "checks": checks,
            "weak_fields": weak_fields,
            "completeness_score": round((len(field_quality) - len(weak_fields)) / len(field_quality), 4),
        }


class SalesEngineer(AgencySalesSpecialist):
    """Verify technical requirements are covered by a supplied solution design."""

    profile = AgencySpecialistProfile(
        "SalesEngineer",
        "sales_engineer_001",
        "tech_fit_brief",
        "tech_fit_check",
        ("technical_requirements", "solution_design"),
        "technical fit and requirements-coverage report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        required = _normalized_set(evidence["technical_requirements"])
        design = evidence["solution_design"]
        if not required or not isinstance(design, dict):
            raise ValueError("technical_requirements must be a list and solution_design must be a mapping")
        addressed = _normalized_set(design.get("addressed_capabilities"))
        integrations = _normalized_set(design.get("integrations"))
        all_covered = addressed | integrations
        missing = sorted(required - all_covered)
        extra = sorted(all_covered - required)
        checks = [
            _check("requirements_are_non_empty", bool(required), sorted(required)),
            _check("solution_addresses_every_required_capability", not missing, missing),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "coverage": round((len(required) - len(missing)) / len(required), 4),
            "missing_capabilities": missing,
            "extra_capabilities": extra,
        }


class OutboundSequenceStrategist(AgencySalesSpecialist):
    """Validate outreach sequence cadence and channel constraints."""

    profile = AgencySpecialistProfile(
        "OutboundSequenceStrategist",
        "outbound_sequence_strategist_001",
        "out_seq_brief",
        "out_seq_check",
        ("touches",),
        "outbound/outreach sequence cadence and channel-diversity validation",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        touches = evidence["touches"]
        if not isinstance(touches, list) or not touches:
            raise ValueError("touches must be a non-empty list")
        days: dict[int, int] = {}
        week_counts: dict[int, int] = {}
        channels: set[str] = set()
        valid_shape = True
        for touch in touches:
            if not isinstance(touch, dict) or not _has_value(touch.get("day")) or not _has_value(touch.get("channel")):
                valid_shape = False
                continue
            day = int(touch["day"])
            channel = str(touch["channel"]).casefold()
            days[day] = days.get(day, 0) + 1
            week_counts[day // 7] = week_counts.get(day // 7, 0) + 1
            channels.add(channel)
        duplicate_days = sorted(day for day, count in days.items() if count > 1)
        overloaded_weeks = sorted(week for week, count in week_counts.items() if count > 3)
        checks = [
            _check("touches_have_day_and_channel", valid_shape, len(touches)),
            _check("no_duplicate_touch_day", not duplicate_days, duplicate_days),
            _check("max_three_touches_per_week", not overloaded_weeks, overloaded_weeks),
            _check("at_least_two_channels", len(channels) >= 2, sorted(channels)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "touch_count": len(touches),
            "channels": sorted(channels),
            "duplicate_days": duplicate_days,
            "overloaded_weeks": overloaded_weeks,
        }


class PipelineVelocityAnalyst(AgencySalesSpecialist):
    """Compute stage conversion and velocity from supplied stage transitions."""

    profile = AgencySpecialistProfile(
        "PipelineVelocityAnalyst",
        "pipeline_velocity_analyst_001",
        "pipe_velocity_brief",
        "pipe_velocity_check",
        ("stage_transitions",),
        "pipeline conversion and velocity math report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        transitions = evidence["stage_transitions"]
        if not isinstance(transitions, list) or not transitions:
            raise ValueError("stage_transitions must be a non-empty list")
        entered: dict[str, set[str]] = {}
        exited: dict[str, set[str]] = {}
        durations: dict[str, list[float]] = {}
        valid_shape = True
        for transition in transitions:
            if not isinstance(transition, dict):
                valid_shape = False
                continue
            deal_id = str(transition.get("deal_id", "")).strip()
            from_stage = str(transition.get("from_stage", "")).casefold().strip()
            to_stage = str(transition.get("to_stage", "")).casefold().strip()
            days = float(transition.get("days_in_stage", -1))
            if not deal_id or not from_stage or not to_stage or days < 0:
                valid_shape = False
                continue
            entered.setdefault(from_stage, set()).add(deal_id)
            exited.setdefault(from_stage, set()).add(deal_id)
            entered.setdefault(to_stage, set()).add(deal_id)
            durations.setdefault(from_stage, []).append(days)
        conversion_rates = {
            stage: round(len(exited.get(stage, set())) / len(deals), 4)
            for stage, deals in entered.items()
            if deals
        }
        avg_days = {
            stage: round(sum(values) / len(values), 2)
            for stage, values in durations.items()
            if values
        }
        checks = [
            _check("transitions_have_required_shape", valid_shape, len(transitions)),
            _check("at_least_two_deals_observed", len({str(t.get("deal_id", "")) for t in transitions if isinstance(t, dict)}) >= 2, len(transitions)),
            _check("conversion_rates_computed", bool(conversion_rates), conversion_rates),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "conversion_rates": conversion_rates,
            "average_days_in_stage": avg_days,
            "stage_count": len(conversion_rates),
        }


class ProposalCoverageStrategist(AgencySalesSpecialist):
    """Verify proposal coverage against explicit client requirements."""

    profile = AgencySpecialistProfile(
        "ProposalCoverageStrategist",
        "proposal_coverage_strategist_001",
        "prop_coverage_brief",
        "prop_coverage_check",
        ("required_capabilities", "addressed_capabilities"),
        "proposal requirements-coverage verification report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        required = _normalized_set(evidence["required_capabilities"])
        addressed = _normalized_set(evidence["addressed_capabilities"])
        if not required:
            raise ValueError("required_capabilities must be a non-empty list")
        missing = sorted(required - addressed)
        checks = [
            _check("proposal_addresses_every_required_capability", not missing, missing),
            _check("proposal_has_no_empty_addressed_list", bool(addressed), sorted(addressed)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "coverage": round((len(required) - len(missing)) / len(required), 4),
            "missing_capabilities": missing,
            "addressed_capabilities": sorted(addressed),
        }


class SalesCoach(AgencySalesSpecialist):
    """Check a supplied sales call's rubric coverage.

    Collapses the sales-coach and sales-discovery-coach personas: both need
    the identical deterministic capability -- does the call address each
    required rubric item? -- differing only in which rubric the caller
    supplies (a general coaching rubric vs. a discovery-call rubric such as
    budget/authority/need/timeline). Building two agents for the same check
    would be count-padding, the same reasoning already applied to
    OutboundSequenceStrategist.
    """

    profile = AgencySpecialistProfile(
        "SalesCoach",
        "sales_coach_001",
        "sales_coaching_brief",
        "sales_coaching_check",
        ("call_transcript", "rubric_items"),
        "sales call rubric-coverage report (general coaching or discovery-call rubric)",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        transcript = evidence["call_transcript"]
        rubric = evidence["rubric_items"]
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("call_transcript must be non-empty text")
        if not isinstance(rubric, list) or not rubric:
            raise ValueError("rubric_items must be a non-empty list")
        lowered_transcript = transcript.casefold()
        rubric_items = sorted({str(item).strip() for item in rubric if str(item).strip()})
        covered = sorted(item for item in rubric_items if item.casefold() in lowered_transcript)
        missing = sorted(set(rubric_items) - set(covered))
        checks = [
            _check("rubric_is_non_empty", bool(rubric_items), rubric_items),
            _check("every_rubric_item_addressed", not missing, missing),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "coverage": round(len(covered) / len(rubric_items), 4) if rubric_items else 0.0,
            "covered_items": covered,
            "missing_items": missing,
        }


class SalesDataExtractionAgent(AgencySalesSpecialist):
    """Extract and validate MTD/YTD sales totals from supplied raw records.

    Deterministic date-window arithmetic on caller-supplied rows; never
    forecasts or projects future values -- that would need a real prediction
    capability this agent does not have and must not fake.
    """

    profile = AgencySpecialistProfile(
        "SalesDataExtractionAgent",
        "sales_data_extraction_agent_001",
        "sales_data_extraction_brief",
        "sales_data_extraction_check",
        ("records", "as_of_date"),
        "MTD/YTD sales totals extracted from supplied raw records, with malformed rows flagged",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        records = evidence["records"]
        if not isinstance(records, list) or not records:
            raise ValueError("records must be a non-empty list")
        as_of = _parse_date(evidence["as_of_date"])

        valid: list[dict[str, Any]] = []
        malformed: list[Any] = []
        for row in records:
            if not isinstance(row, dict):
                malformed.append(row)
                continue
            try:
                row_date = _parse_date(row["date"])
                amount = float(row["amount"])
            except (KeyError, TypeError, ValueError):
                malformed.append(row)
                continue
            valid.append({
                "date": row_date,
                "amount": amount,
                "rep": str(row.get("rep", "")).strip() or "unassigned",
            })

        mtd = [r for r in valid if r["date"].year == as_of.year and r["date"].month == as_of.month]
        ytd = [r for r in valid if r["date"].year == as_of.year]

        mtd_total = round(sum(r["amount"] for r in mtd), 2)
        ytd_total = round(sum(r["amount"] for r in ytd), 2)

        by_rep_ytd: dict[str, float] = {}
        for r in ytd:
            by_rep_ytd[r["rep"]] = round(by_rep_ytd.get(r["rep"], 0.0) + r["amount"], 2)

        checks = [
            _check("all_rows_well_formed", not malformed, len(malformed)),
            _check("at_least_one_valid_row", bool(valid), len(valid)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "mtd_total": mtd_total,
            "ytd_total": ytd_total,
            "by_rep_ytd": by_rep_ytd,
            "valid_row_count": len(valid),
            "malformed_row_count": len(malformed),
            "malformed_rows": malformed,
        }


class LoanOfficerAssistant(AgencySalesSpecialist):
    """Check supplied applicant financials against supplied eligibility criteria.

    Deterministic ratio arithmetic only (DTI, LTV, down-payment %) -- never
    approves, denies, or gives lending/regulatory advice. Named as a Wave 3
    vertical candidate in the owner's own Blueprint ("(C) Industries — Four
    Waves.md"), which permits VECTOR to "research and build ahead" of a wave;
    the original P6 disclosure's "needs legal_compliance advisory input" gap
    stays true for the ADVISORY/approval side, which this agent deliberately
    does not attempt -- it only tells a human which caller-defined criteria
    the supplied numbers do or don't meet.
    """

    profile = AgencySpecialistProfile(
        "LoanOfficerAssistant",
        "loan_officer_assistant_001",
        "loan_eligibility_brief",
        "loan_eligibility_check",
        ("applicant_financials", "eligibility_rules"),
        "loan eligibility-criteria check against supplied applicant financials (not a lending decision or advice)",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        financials = evidence["applicant_financials"]
        rules = evidence["eligibility_rules"]
        if not isinstance(financials, dict) or not isinstance(rules, dict):
            raise ValueError("applicant_financials and eligibility_rules must both be mappings")

        monthly_income = float(financials["monthly_income"])
        monthly_debts = float(financials["monthly_debts"])
        credit_score = float(financials["credit_score"])
        requested_amount = float(financials["requested_amount"])
        property_value = float(financials["property_value"])
        down_payment = float(financials["down_payment"])
        if monthly_income <= 0 or property_value <= 0:
            raise ValueError("monthly_income and property_value must be positive")

        dti = round(monthly_debts / monthly_income, 4)
        ltv = round(requested_amount / property_value, 4)
        down_payment_pct = round(down_payment / property_value, 4)

        max_dti = float(rules["max_dti"])
        min_credit_score = float(rules["min_credit_score"])
        max_ltv = float(rules["max_ltv"])
        min_down_payment_pct = float(rules["min_down_payment_pct"])

        checks = [
            _check("dti_within_limit", dti <= max_dti, {"dti": dti, "max_dti": max_dti}),
            _check(
                "credit_score_meets_minimum",
                credit_score >= min_credit_score,
                {"credit_score": credit_score, "min_credit_score": min_credit_score},
            ),
            _check("ltv_within_limit", ltv <= max_ltv, {"ltv": ltv, "max_ltv": max_ltv}),
            _check(
                "down_payment_meets_minimum",
                down_payment_pct >= min_down_payment_pct,
                {"down_payment_pct": down_payment_pct, "min_down_payment_pct": min_down_payment_pct},
            ),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "dti": dti,
            "ltv": ltv,
            "down_payment_pct": down_payment_pct,
            "meets_all_supplied_criteria": all(item["passed"] for item in checks),
            "disclaimer": (
                "Eligibility-criteria check only, not a lending decision, approval, or "
                "regulated advice. A licensed human must make the actual decision."
            ),
        }


class PropertyMatchAnalyst(AgencySalesSpecialist):
    """Match supplied buyer requirements against supplied property listings.

    Deterministic filter/match over caller-supplied listings -- no live MLS,
    listing-service, or valuation API. Resolves the real-estate-buyer-seller
    persona, named alongside loan-ops as a Wave 3 vertical candidate in the
    owner's Blueprint: the real, buildable capability was always a match
    check over caller-supplied data, not a missing external listings feed.
    """

    profile = AgencySpecialistProfile(
        "PropertyMatchAnalyst",
        "property_match_analyst_001",
        "property_match_brief",
        "property_match_check",
        ("buyer_requirements", "listings"),
        "buyer-requirement vs. supplied-listings match report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        requirements = evidence["buyer_requirements"]
        listings = evidence["listings"]
        if not isinstance(requirements, dict):
            raise ValueError("buyer_requirements must be a mapping")
        if not isinstance(listings, list) or not listings:
            raise ValueError("listings must be a non-empty list")

        max_budget = float(requirements["max_budget"])
        min_bedrooms = float(requirements.get("min_bedrooms", 0))
        required_features = _normalized_set(requirements.get("required_features", []))
        preferred_locations = _normalized_set(requirements.get("preferred_locations", []))

        matches: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        valid_shape = True
        for listing in listings:
            if not isinstance(listing, dict) or not _has_value(listing.get("address")) or not _has_value(
                listing.get("price")
            ):
                valid_shape = False
                continue
            price = float(listing["price"])
            bedrooms = float(listing.get("bedrooms", 0))
            features = _normalized_set(listing.get("features", []))
            location = str(listing.get("location", "")).strip().casefold()

            reasons = []
            if price > max_budget:
                reasons.append("over_budget")
            if bedrooms < min_bedrooms:
                reasons.append("too_few_bedrooms")
            missing_features = sorted(required_features - features)
            if missing_features:
                reasons.append("missing_features:" + ",".join(missing_features))
            if preferred_locations and location not in preferred_locations:
                reasons.append("location_not_preferred")

            record = {"address": listing["address"], "price": price, "reasons": reasons}
            (rejected if reasons else matches).append(record)

        checks = [
            _check("listings_have_required_shape", valid_shape, len(listings)),
            _check("at_least_one_match_found", bool(matches), len(matches)),
        ]
        return {
            "status": "passed" if valid_shape and matches else "needs_human",
            "checks": checks,
            "matched_listings": matches,
            "rejected_listings": rejected,
            "match_count": len(matches),
            "total_listings": len(listings),
        }


class RecruitmentSpecialist(AgencySalesSpecialist):
    """Check a supplied candidate against a supplied job requisition's stated criteria.

    Deterministic skills/experience/certification coverage check -- no ATS
    connector, no candidate sourcing, no hiring decision. Resolves the
    recruitment-specialist persona for the agentic-back-office services the
    owner's Blueprint's Wave 2 plan anticipates selling to SMBs (screening
    and requisition-checking is exactly that shape of back-office task).
    """

    profile = AgencySpecialistProfile(
        "RecruitmentSpecialist",
        "recruitment_specialist_001",
        "recruitment_fit_brief",
        "recruitment_fit_check",
        ("requisition", "candidate"),
        "candidate-vs-requisition fit report (skills, experience, certifications)",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        requisition = evidence["requisition"]
        candidate = evidence["candidate"]
        if not isinstance(requisition, dict) or not isinstance(candidate, dict):
            raise ValueError("requisition and candidate must both be mappings")

        required_skills = _normalized_set(requisition.get("required_skills", []))
        if not required_skills:
            raise ValueError("requisition.required_skills must be a non-empty list")
        min_experience = float(requisition.get("min_experience_years", 0))
        required_certs = _normalized_set(requisition.get("required_certifications", []))

        candidate_skills = _normalized_set(candidate.get("skills", []))
        candidate_experience = float(candidate.get("experience_years", 0))
        candidate_certs = _normalized_set(candidate.get("certifications", []))

        missing_skills = sorted(required_skills - candidate_skills)
        missing_certs = sorted(required_certs - candidate_certs)

        checks = [
            _check("all_required_skills_present", not missing_skills, missing_skills),
            _check(
                "meets_minimum_experience",
                candidate_experience >= min_experience,
                {"candidate": candidate_experience, "required": min_experience},
            ),
            _check("all_required_certifications_present", not missing_certs, missing_certs),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "missing_skills": missing_skills,
            "missing_certifications": missing_certs,
            "skills_coverage": round((len(required_skills) - len(missing_skills)) / len(required_skills), 4),
        }


SPECIALIST_CLASSES: tuple[type[AgencySalesSpecialist], ...] = (
    AccountStrategist,
    DealStrategist,
    SalesEngineer,
    OutboundSequenceStrategist,
    PipelineVelocityAnalyst,
    ProposalCoverageStrategist,
    SalesCoach,
    SalesDataExtractionAgent,
    LoanOfficerAssistant,
    PropertyMatchAnalyst,
    RecruitmentSpecialist,
)


if __name__ == "__main__":
    async def _smoke() -> None:
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            missing = await specialist.run({"type": specialist.profile.check_action, "evidence": {}})
            assert missing["status"] == "ok"
            assert missing["report"]["status"] == "needs_human"
        logger.info("[VECTOR][agency_specialists] smoke check passed")

    asyncio.run(_smoke())
