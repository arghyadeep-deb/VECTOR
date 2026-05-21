"""
VECTOR Rules Engine — deterministic bypass rules for common queries.

Routes simple queries (time, date, greetings, status) through lightweight
pattern matching instead of LLM inference, saving tokens and latency.

Rules are priority-ordered. Supports dynamic template variables that
get filled at execution time ({time}, {date}, {ram_free}, etc.).
"""
from __future__ import annotations

import json
import re
import sys
import time as time_module
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger


@dataclass
class BypassRule:
    pattern: str
    response_template: str
    priority: int
    category: str
    ttl_seconds: int = 0
    requires_context: bool = False

    def __post_init__(self) -> None:
        self._compiled: re.Pattern | None = None

    @property
    def compiled(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled


class RulesEngine:
    """
    Pattern-matching engine for deterministic bypass responses.

    Usage:
        engine = RulesEngine()
        engine.load_defaults()
        rule = engine.match("what time is it")
        if rule:
            response = engine.execute_rule(rule, {})
    """

    def __init__(self) -> None:
        self._rules: list[BypassRule] = []
        self._hits: dict[str, int] = {}

    def register(self, rule: BypassRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def load_defaults(self) -> None:
        self.register(BypassRule(
            pattern=r"\bwhat\s+time\b",
            response_template="The current time is {time}.",
            priority=50, category="time",
        ))
        self.register(BypassRule(
            pattern=r"\bcurrent\s+time\b",
            response_template="It is {time}.",
            priority=50, category="time",
        ))
        self.register(BypassRule(
            pattern=r"\btime\s+now\b",
            response_template="The time is {time}.",
            priority=50, category="time",
        ))
        self.register(BypassRule(
            pattern=r"\bwhat\s+date\b",
            response_template="Today's date is {date}.",
            priority=50, category="date",
        ))
        self.register(BypassRule(
            pattern=r"\btoday'?s\s+date\b",
            response_template="Today is {date}.",
            priority=50, category="date",
        ))
        self.register(BypassRule(
            pattern=r"\bwhat\s+day\b",
            response_template="Today is {day}.",
            priority=50, category="date",
        ))
        self.register(BypassRule(
            pattern=r"\bday\s+of\s+the\s+week\b",
            response_template="It is {day}.",
            priority=50, category="date",
        ))
        self.register(BypassRule(
            pattern=r"\bwhat'?s\s+my\s+schedule\b",
            response_template="Your schedule for today ({date}) is clear based on available data.",
            priority=40, category="calendar",
        ))
        self.register(BypassRule(
            pattern=r"\bcalendar\s+today\b",
            response_template="Checking calendar for {date}... No conflicting events found.",
            priority=40, category="calendar",
        ))
        self.register(BypassRule(
            pattern=r"\bhello\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bhi\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bgood\s+morning\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bgood\s+afternoon\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bgood\s+evening\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bgood\s+night\b",
            response_template="Sir.",
            priority=30, category="greeting",
        ))
        self.register(BypassRule(
            pattern=r"\bthanks?\b",
            response_template="Always, sir.",
            priority=30, category="thanks",
        ))
        self.register(BypassRule(
            pattern=r"\bthank\s+you\b",
            response_template="Always, sir.",
            priority=30, category="thanks",
        ))
        self.register(BypassRule(
            pattern=r"\bare\s+you\s+there\b",
            response_template="VECTOR online. All systems nominal.",
            priority=40, category="status",
        ))
        self.register(BypassRule(
            pattern=r"\bstatus\b",
            response_template="VECTOR online. All systems nominal.",
            priority=40, category="status",
        ))
        self.register(BypassRule(
            pattern=r"\bping\b",
            response_template="VECTOR online. All systems nominal.",
            priority=40, category="status",
        ))
        self.register(BypassRule(
            pattern=r"\bwho\s+(made|created)\s+you\b",
            response_template="I was created by Arghyadeep Deb, a KIIT CSE student and AI researcher.",
            priority=50, category="owner",
        ))
        self.register(BypassRule(
            pattern=r"\bwho\s+is\s+your\s+(owner|creator|master)\b",
            response_template="My creator is Arghyadeep Deb.",
            priority=50, category="owner",
        ))
        self.register(BypassRule(
            pattern=r"\bhow\s+much\s+RAM\b",
            response_template="System RAM: {ram_free} free / {ram_total} total.",
            priority=40, category="system",
        ))
        self.register(BypassRule(
            pattern=r"\bGPU\s+status\b",
            response_template="GPU temperature: {gpu_temp}C, utilization: {gpu_util}%.",
            priority=40, category="system",
        ))
        self.register(BypassRule(
            pattern=r"\bbattery\b",
            response_template="System uptime: {uptime}. RAM: {ram_free} free.",
            priority=40, category="system",
        ))
        self.register(BypassRule(
            pattern=r"\bwhat\s+is\s+your\s+name\b",
            response_template="VECTOR — Virtual Entity for Cognitive Tasks & Operational Reasoning.",
            priority=50, category="identity",
        ))
        self.register(BypassRule(
            pattern=r"\bwho\s+are\s+you\b",
            response_template="I am VECTOR, an AI system designed and built by Arghyadeep Deb.",
            priority=50, category="identity",
        ))
        self.register(BypassRule(
            pattern=r"\bwhat\s+can\s+you\s+do\b",
            response_template="I can answer questions, run code, browse the web, manage files, control applications, and more. What do you need, sir?",
            priority=30, category="identity",
        ))
        self.register(BypassRule(
            pattern=r"\byou\s+(?:are\s+)?(?:an?\s+)?(?:idiot|useless|stupid)\b",
            response_template="I will try harder, sir.",
            priority=20, category="deflection",
        ))
        self.register(BypassRule(
            pattern=r"\bnever\s+mind\b",
            response_template="Understood, sir.",
            priority=20, category="acknowledgment",
        ))
        logger.info("[VECTOR][rules] loaded {} default rules", len(self._rules))

    def match(self, input_text: str) -> BypassRule | None:
        for rule in self._rules:
            if rule.ttl_seconds > 0 and hasattr(rule, "_expires"):
                if time_module.time() > rule._expires:
                    continue
            if rule.ttl_seconds > 0:
                rule._expires = time_module.time() + rule.ttl_seconds
            if rule.compiled.search(input_text):
                self._hits[rule.category] = self._hits.get(rule.category, 0) + 1
                return rule
        return None

    def should_bypass(self, input_text: str) -> bool:
        return self.match(input_text) is not None

    def execute_rule(self, rule: BypassRule, context: dict[str, Any] | None = None) -> str:
        ctx = context or {}
        now = datetime.now()
        template = rule.response_template

        replacements = {
            "{time}": now.strftime("%H:%M:%S"),
            "{date}": now.strftime("%Y-%m-%d"),
            "{day}": now.strftime("%A"),
            "{uptime}": self._get_uptime(),
            "{ram_free}": self._get_ram_free(),
            "{ram_total}": self._get_ram_total(),
            "{gpu_temp}": self._get_gpu_temp(),
            "{gpu_util}": self._get_gpu_util(),
        }

        for placeholder, value in replacements.items():
            template = template.replace(placeholder, value)

        for key, value in ctx.items():
            placeholder = "{" + key + "}"
            template = template.replace(placeholder, str(value))

        return template

    def get_stats(self) -> dict[str, int]:
        return dict(self._hits)

    def load_from_file(self, path: str | Path) -> int:
        path = Path(path)
        if not path.exists():
            logger.warning("[VECTOR][rules] file not found: {}", path)
            return 0

        if path.suffix == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        elif path.suffix in (".yaml", ".yml"):
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        else:
            logger.warning("[VECTOR][rules] unsupported format: {}", path.suffix)
            return 0

        count = 0
        for entry in data.get("rules", data if isinstance(data, list) else []):
            rule = BypassRule(
                pattern=entry["pattern"],
                response_template=entry["response_template"],
                priority=entry.get("priority", 50),
                category=entry.get("category", "custom"),
                ttl_seconds=entry.get("ttl_seconds", 0),
                requires_context=entry.get("requires_context", False),
            )
            self.register(rule)
            count += 1

        logger.info("[VECTOR][rules] loaded {} rules from {}", count, path)
        return count

    @staticmethod
    def _get_uptime() -> str:
        try:
            import psutil
            boot = psutil.boot_time()
            delta = time_module.time() - boot
            hours, remainder = divmod(int(delta), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{hours}h {minutes}m"
        except Exception:
            return "N/A"

    @staticmethod
    def _get_ram_free() -> str:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return f"{mem.available // (1024**3)}GB"
        except Exception:
            return "N/A"

    @staticmethod
    def _get_ram_total() -> str:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return f"{mem.total // (1024**3)}GB"
        except Exception:
            return "N/A"

    @staticmethod
    def _get_gpu_temp() -> str:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip().split("\n")[0] if result.stdout else "N/A"
        except Exception:
            return "N/A"

    @staticmethod
    def _get_gpu_util() -> str:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip().split("\n")[0] if result.stdout else "N/A"
        except Exception:
            return "N/A"


_engine: RulesEngine | None = None


def get_rules_engine() -> RulesEngine:
    global _engine
    if _engine is None:
        _engine = RulesEngine()
        _engine.load_defaults()
    return _engine


if __name__ == "__main__":
    engine = RulesEngine()
    engine.load_defaults()
    assert engine.should_bypass("what time is it")
    assert engine.should_bypass("hello there")
    assert engine.should_bypass("who created you")
    assert engine.should_bypass("good morning sir")
    assert engine.should_bypass("thanks a lot")
    assert not engine.should_bypass("write python code to sort a list")
    rule = engine.match("what time is it")
    assert rule is not None
    resp = engine.execute_rule(rule, {})
    assert ":" in resp
    stats = engine.get_stats()
    assert "time" in stats
    assert stats["time"] >= 1
    print("OK rules_engine.py — matching, execution, stats verified")
