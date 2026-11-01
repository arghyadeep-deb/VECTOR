"""NudgeEngine — monitors activity patterns and generates proactive nudges."""

import asyncio

__all__ = [
    "nudge_engine",
    "NudgeEngine",
]

import datetime
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger
from core.config import CONFIG


class NudgeEngine:
    def __init__(self):
        self._latest: dict | None = None
        self._session_start = time.time()
        self._last_idle_time = 0.0
        self._check_interval = 30
        self._subscribers: list = []

    @property
    def latest(self) -> dict | None:
        return self._latest

    def dismiss(self):
        self._latest = None

    def subscribe(self, callback):
        """Register callback(nudge_dict), fired on every new nudge.

        Used by the realtime voice layer (design Phase 5: proactive speech).
        Returns an unsubscribe function. Subscriber failures are swallowed so
        one bad subscriber can't break nudge generation.
        """
        self._subscribers.append(callback)

        def _unsubscribe():
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass
        return _unsubscribe

    def _notify(self, nudge: dict) -> None:
        for cb in list(self._subscribers):
            try:
                cb(nudge)
            except Exception as e:
                logger.debug(f"[VECTOR][nudge] subscriber error suppressed: {e}")

    def push(self, text: str, source: str = "proactive", need: str = "", priority: float = 0.8) -> dict:
        """Surface a proactive nudge directly (e.g. from the anticipation engine).

        The frontend polls /nudge/latest, so setting _latest here makes the
        prediction visible to the owner without an LLM round-trip. Subscribers
        (realtime voice) are notified so high-priority nudges can be SPOKEN.
        """
        self._latest = {
            "text": text,
            "rule": source,
            "need": need,
            "priority": priority,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "signals": {},
        }
        logger.info(f"[VECTOR][nudge] (proactive) {source}: {text}")
        self._notify(self._latest)
        return self._latest

    async def tick(self):
        signals = self._collect_signals()
        rule = self._match_rule(signals)
        if rule:
            text = await self._generate_nudge(rule, signals)
            self._latest = {
                "text": text,
                "rule": rule["name"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "signals": signals,
            }
            logger.info(f"[VECTOR][nudge] {rule['name']}: {text}")
            self._notify(self._latest)

    def _collect_signals(self) -> dict:
        signals = {
            "uptime_minutes": (time.time() - self._session_start) / 60,
            "git_commits_1h": self._count_git_commits(60),
            "git_commits_5m": self._count_git_commits(5),
            "idle_seconds": 0,
            "errors_5m": 0,
        }
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu < 5:
                signals["idle_seconds"] = self._last_idle_time + self._check_interval
            else:
                signals["idle_seconds"] = 0
                self._last_idle_time = 0
        except Exception:
            signals["idle_seconds"] = 0
        return signals

    def _count_git_commits(self, minutes: int) -> int:
        try:
            since = f"{minutes} minutes ago"
            r = subprocess.run(
                ["git", "log", f"--since={since}", "--oneline"],
                capture_output=True, text=True, timeout=5,
                cwd=Path(__file__).parent.parent.parent,
            )
            return len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
        except Exception:
            return 0

    def _match_rule(self, signals: dict) -> dict | None:
        rules = [
            {
                "name": "deep_work",
                "condition": (
                    signals["uptime_minutes"] >= 45
                    and signals["idle_seconds"] < 30
                    and signals["git_commits_5m"] >= 1
                ),
                "template": "deep_work",
            },
            {
                "name": "long_session",
                "condition": signals["uptime_minutes"] >= 120 and signals["idle_seconds"] < 30,
                "template": "long_session",
            },
            {
                "name": "idle",
                "condition": signals["idle_seconds"] >= 600,
                "template": "idle",
            },
        ]
        for rule in rules:
            if rule["condition"]:
                return rule
        return None

    async def _generate_nudge(self, rule: dict, signals: dict) -> str:
        import httpx
        prompts = {
            "deep_work": (
                "Generate a one-sentence encouraging nudge for a developer "
                "who has been coding for 45+ minutes with recent git commits. "
                "Acknowledge their focus briefly. No emoji."
            ),
            "long_session": (
                "Generate a one-sentence gentle nudge suggesting a short break "
                "for a developer who has been working for 2+ hours. No emoji."
            ),
            "idle": (
                "Generate a one-sentence helpful nudge for a developer who has "
                "been idle for 10+ minutes. Ask if they need help researching "
                "something. No emoji."
            ),
        }
        prompt = prompts.get(rule["template"], "")
        if not prompt:
            return "You seem to be in a good rhythm. Keep going."

        try:
            from core.inference.provider_client import ProviderClient
            _client = ProviderClient()
            result = await _client.chat(
                messages=[{"role": "user", "content": prompt}],
                tier="conversation",
                max_tokens=80,
                temperature=0.7,
                caller_id="nudge_engine",
            )
            if result and result.content:
                return result.content.strip()
        except Exception as e:
            logger.warning("[VECTOR][nudge] LLM failed: {}", e)

        return self._fallback_nudge(rule["template"])

    def _fallback_nudge(self, template: str) -> str:
        fallbacks = {
            "deep_work": "You've been in deep focus for 45 minutes. The work is solid.",
            "long_session": "You've been at this for 2 hours. A quick break will help.",
            "idle": "You seem idle. Want me to run some diagnostics?",
        }
        return fallbacks.get(template, "Stay sharp, sir.")


nudge_engine = NudgeEngine()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
