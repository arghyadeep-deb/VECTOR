import sys
from pathlib import Path

import asyncio
import datetime
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import yaml
from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase


@dataclass
class DetectionRule:
    id: str
    name: str
    description: str = ""
    condition_type: str = "threshold"
    params: dict = field(default_factory=dict)
    severity: int = 5
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    source: str = ""
    response: list[str] = field(default_factory=list)


@dataclass
class RuleMatch:
    rule_name: str
    severity: int
    triggered_at: str = ""
    evidence: dict = field(default_factory=dict)
    suggested_action: str = ""

    def __post_init__(self):
        if not self.triggered_at:
            self.triggered_at = datetime.datetime.now(datetime.timezone.utc).isoformat()


class DetectionRules(AgentBase):
    def __init__(self, rules_dir: str | None = None):
        super().__init__(str(uuid.uuid4()), "DetectionRules", "security")
        self.capabilities = ["detection", "hot_reload", "list_rules", "match_event", "security", "threat"]
        from core.runtime_paths import data_path

        self._rules_dir = Path(rules_dir) if rules_dir else data_path("security", "rules")
        self._packaged_rules_dir = Path(__file__).parent / "data" / "rules"
        self._rules: list[DetectionRule] = []
        self._event_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=10000)
        self._running = False
        self._rate_counters: dict[str, list[float]] = defaultdict(list)
        self._load_rules()

    def _load_rules(self) -> None:
        self._rules = []
        rules_dir = self._rules_dir if self._rules_dir.exists() else self._packaged_rules_dir
        if not rules_dir.exists():
            logger.warning("[VECTOR][detection_rules] rules dir not found: {}", self._rules_dir)
            return
        for yaml_file in sorted(rules_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data or "rules" not in data:
                    continue
                for r in data["rules"]:
                    if not r.get("enabled", True):
                        continue
                    condition = r.get("condition", {})
                    self._rules.append(DetectionRule(
                        id=r.get("id", ""),
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        condition_type=condition.get("type", "threshold"),
                        params=condition,
                        severity=r.get("severity", 5),
                        enabled=r.get("enabled", True),
                        tags=r.get("tags", []),
                        source=r.get("source", ""),
                        response=r.get("response", []),
                    ))
                logger.info("[VECTOR][detection_rules] loaded {} rules from {}", len(data.get("rules", [])), yaml_file.name)
            except Exception as e:
                logger.error("[VECTOR][detection_rules] failed to load {}: {}", yaml_file, e)
        logger.info("[VECTOR][detection_rules] {} rules loaded (enabled)", len(self._rules))

    def hot_reload(self) -> int:
        before = len(self._rules)
        self._load_rules()
        after = len(self._rules)
        logger.info("[VECTOR][detection_rules] hot reload: {} → {} rules", before, after)
        return after

    async def process_loop(self) -> None:
        self._running = True
        logger.info("[VECTOR][detection_rules] process loop started — {} rules", len(self._rules))
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                matches = self.evaluate(event)
                if matches:
                    for m in matches:
                        logger.warning("[VECTOR][detection_rules] MATCH: {} (sev={})", m.rule_name, m.severity)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[VECTOR][detection_rules] process error: {}", e)

    async def feed_event(self, event: Any) -> None:
        try:
            await asyncio.wait_for(self._event_queue.put(event), timeout=1.0)
        except (asyncio.TimeoutError, asyncio.QueueFull):
            logger.warning("[VECTOR][detection_rules] event queue full")

    def evaluate(self, event: Any) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        event_dict = event if isinstance(event, dict) else (event.model_dump() if hasattr(event, "model_dump") else {})
        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                triggered = False
                evidence: dict[str, Any] = {"rule_id": rule.id, "event": str(event_dict)[:200]}
                if rule.condition_type == "threshold":
                    triggered = self.evaluate_threshold(rule, event_dict, evidence)
                elif rule.condition_type == "pattern":
                    triggered = self.evaluate_pattern(rule, event_dict, evidence)
                elif rule.condition_type == "rate":
                    triggered = self.evaluate_rate(rule, event_dict, evidence)
                elif rule.condition_type == "composite":
                    triggered = self.evaluate_composite(rule, event_dict, evidence)
                if triggered:
                    matches.append(RuleMatch(
                        rule_name=rule.name,
                        severity=rule.severity,
                        evidence=evidence,
                        suggested_action=", ".join(rule.response) if rule.response else "alert",
                    ))
            except Exception as e:
                logger.error("[VECTOR][detection_rules] rule '{}' eval error: {}", rule.name, e)
        return matches

    def evaluate_threshold(self, rule: DetectionRule, event: dict, evidence: dict) -> bool:
        field = rule.params.get("field", "")
        operator = rule.params.get("operator", ">")
        threshold = rule.params.get("value", 0)
        actual = event.get(field)
        if actual is None:
            return False
        try:
            actual_f = float(actual)
            threshold_f = float(threshold)
            if operator == ">":
                result = actual_f > threshold_f
            elif operator == "<":
                result = actual_f < threshold_f
            elif operator == ">=":
                result = actual_f >= threshold_f
            elif operator == "<=":
                result = actual_f <= threshold_f
            elif operator == "==":
                result = actual_f == threshold_f
            else:
                result = False
            if result:
                evidence["actual"] = actual_f
                evidence["threshold"] = threshold_f
                evidence["operator"] = operator
            return result
        except (TypeError, ValueError):
            return False

    def evaluate_pattern(self, rule: DetectionRule, event: dict, evidence: dict) -> bool:
        field = rule.params.get("field", "")
        pattern_str = rule.params.get("pattern", "")
        if not pattern_str:
            return False
        text = str(event.get(field, ""))
        try:
            match = re.search(pattern_str, text, re.IGNORECASE)
            if match:
                evidence["pattern"] = pattern_str
                evidence["matched_on"] = match.group()
            return match is not None
        except re.error:
            return False

    def evaluate_rate(self, rule: DetectionRule, event: dict, evidence: dict) -> bool:
        field = rule.params.get("field", "")
        threshold = rule.params.get("threshold", 10)
        window = rule.params.get("window", 60)
        pattern = rule.params.get("pattern", "")
        now = time.time()
        key = rule.id
        if pattern:
            text = str(event.get(field, ""))
            try:
                if not re.search(pattern, text, re.IGNORECASE):
                    return False
            except re.error:
                return False
        else:
            pass
        self._rate_counters[key].append(now)
        self._rate_counters[key] = [t for t in self._rate_counters[key] if t > now - window]
        count = len(self._rate_counters[key])
        if count >= threshold:
            evidence["count"] = count
            evidence["threshold"] = threshold
            evidence["window_sec"] = window
            return True
        return False

    def evaluate_composite(self, rule: DetectionRule, event: dict, evidence: dict) -> bool:
        conditions = rule.params.get("conditions", [])
        logic = rule.params.get("logic", "AND").upper()
        if not conditions:
            return False
        results: list[bool] = []
        for cond in conditions:
            sub_rule = DetectionRule(
                id=f"{rule.id}_sub",
                name=rule.name,
                condition_type=cond.get("type", "threshold"),
                params=cond,
            )
            if sub_rule.condition_type == "threshold":
                results.append(self.evaluate_threshold(sub_rule, event, {}))
            elif sub_rule.condition_type == "pattern":
                results.append(self.evaluate_pattern(sub_rule, event, {}))
            elif sub_rule.condition_type == "rate":
                results.append(self.evaluate_rate(sub_rule, event, {}))
            else:
                results.append(False)
        if logic == "AND":
            return all(results)
        elif logic == "OR":
            return any(results)
        elif logic == "NOT":
            return not any(results)
        return False

    def stop(self) -> None:
        self._running = False

    async def run(self, task: dict | None = None) -> dict:
        task = task or {}
        task_type = task.get("type") or "list_rules"
        params = task.get("params") or {}
        supported = ["hot_reload", "list_rules", "match_event"]

        if task_type in ("list_rules", "stats"):
            return {"status": "ok", "rules_loaded": len(self._rules), "rules": [r.id for r in self._rules]}
        if task_type in ("match_event", "evaluate"):
            event = params.get("event", params)
            return {"status": "ok", "matches": [m.__dict__ for m in self.evaluate(event)]}
        if task_type == "hot_reload":
            return {"status": "ok", "rules_loaded": self.hot_reload()}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "what detection rules do you currently have loaded?" previously
        # hit the bare "unhandled type" error stub. Route it to the same
        # list_rules() this agent already treats as its safe, argument-free
        # DEFAULT when task_type is entirely absent (see task_type =
        # task.get("type") or "list_rules" above) — read-only, no side
        # effects.
        query = (
            params.get("query") or params.get("content")
            or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return {"status": "ok", "rules_loaded": len(self._rules), "rules": [r.id for r in self._rules]}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": supported,
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    dr = DetectionRules()
    test_event = {"cpu_percent": 96.0, "source": "system_monitor"}
    matches = dr.evaluate(test_event)
    print(f"DetectionRules OK — {len(dr._rules)} rules loaded, {len(matches)} matches on test event")
    for m in matches:
        print(f"  MATCH: {m.rule_name} (sev={m.severity})")
    print("detection_rules.py OK")
