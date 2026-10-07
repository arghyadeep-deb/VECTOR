"""
Credential Manager — multi-provider API key management with failover.

Wraps vectorcode/src/agent/credential_pool.py concept.
Manages API keys for Gemini, Anthropic, OpenRouter, Bedrock.
Reports which providers are live, which are exhausted, handles key rotation.
"""

import asyncio
import os
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.security.secrets_manager import get_secret

_PROVIDERS = ["gemini", "anthropic", "openrouter", "bedrock"]

_ENV_KEYS = {
    "gemini":      "GEMINI_API_KEY",
    "anthropic":   "ANTHROPIC_API_KEY",
    "openrouter":  "OPENROUTER_API_KEY",
    "bedrock":     "AWS_ACCESS_KEY_ID",
}

class CredentialManager(AgentBase):
    """
    Manages API credentials for multiple LLM providers.
    Checks availability, reports status, validates keys, handles rotation.
    Wraps vectorcode's credential_pool and credential_sources patterns.
    """

    def __init__(self):
        super().__init__(agent_id="credential_manager_001",
                         name="CredentialManager", district="governance")
        self.capabilities = ["credential", "governance", "security", "template", "validate"]
        self._memory: EpisodicMemory | None = None
        logger.info("[VECTOR][cred_mgr] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def scan_available_providers(self) -> dict:
        """Check which LLM providers have credentials configured."""
        status = {}
        for provider, env_var in _ENV_KEYS.items():
            # keyring-first lookup: a key stored only in the OS keyring (not
            # env/config) was previously reported "not_set" by this scan,
            # even though every other call site in VECTOR would have found
            # it fine via get_secret().
            env_val = os.getenv(env_var, "")
            key = env_val or get_secret(env_var) or CONFIG.get("api_keys", {}).get(provider, "")
            has_key = bool(key and len(key) > 8)
            if env_val:
                source = "env"
            elif key and key == get_secret(env_var, allow_keyring=True):
                source = "keyring"
            elif has_key:
                source = "config"
            else:
                source = "none"
            status[provider] = {
                "available": has_key,
                "key_source": source,
                "key_prefix": key[:8] + "..." if has_key else "not_set",
                "cost_tier": "free" if provider == "gemini" else "paid",
            }
        # Ollama is always available (local)
        status["ollama"] = {
            "available": True,
            "key_source": "local",
            "key_prefix": "local",
            "cost_tier": "free",
        }
        available_count = sum(1 for v in status.values() if v["available"])
        return {
            "providers": status,
            "available_count": available_count,
            "cloud_providers_ready": sum(
                1 for k, v in status.items() if v["available"] and k != "ollama"
            ),
            "recommendation": (
                "Add GEMINI_API_KEY to .env for free cloud fallback"
                if not status["gemini"]["available"]
                else f"{available_count} providers ready"
            ),
        }

    def validate_key(self, provider: str, key: str = "") -> dict:
        """Quick validation that a key format looks correct (no network call)."""
        key = key or get_secret(_ENV_KEYS.get(provider, ""))
        patterns = {
            "anthropic": ("sk-ant-", 40),
            "openrouter": ("sk-or-", 30),
            "gemini": ("AI", 20),
            "bedrock": ("AKIA", 16),
        }
        if not key:
            return {"valid": False, "provider": provider, "reason": "No key found"}
        prefix, min_len = patterns.get(provider, ("", 10))
        if prefix and not key.startswith(prefix):
            return {"valid": False, "provider": provider,
                    "reason": f"Expected prefix '{prefix}', got '{key[:8]}'"}
        if len(key) < min_len:
            return {"valid": False, "provider": provider,
                    "reason": f"Key too short ({len(key)} chars, need {min_len}+)"}
        return {"valid": True, "provider": provider, "key_length": len(key)}

    def generate_env_template(self) -> str:
        """Generate .env template for all LLM providers."""
        lines = [
            "# VECTOR LLM Provider Keys — add to .env",
            "# Free tier (1M tokens/day):",
            "GEMINI_API_KEY=your_gemini_key_here",
            "",
            "# Paid (set when ready to use cloud models):",
            "ANTHROPIC_API_KEY=sk-ant-your_key_here",
            "OPENROUTER_API_KEY=sk-or-your_key_here",
            "",
            "# AWS Bedrock (Claude via AWS):",
            "AWS_ACCESS_KEY_ID=your_key_here",
            "AWS_SECRET_ACCESS_KEY=your_secret_here",
            "AWS_DEFAULT_REGION=us-east-1",
        ]
        return "\n".join(lines)

    async def answer_credential_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question grounded in the
        real provider-availability scan, instead of always dumping the raw
        scan_available_providers() dict regardless of what was actually
        asked (KNOWN_ISSUES bug pattern — same shape as the design-district
        #33 fix: 'static config/token data unrelated to the question')."""
        scan = self.scan_available_providers()
        context = (
            f"{scan['available_count']} LLM providers available "
            f"({scan['cloud_providers_ready']} cloud): "
            f"{ {k: v['available'] for k, v in scan['providers'].items()} }. "
            f"Recommendation: {scan['recommendation']}"
        )
        prompt = (
            "You are VECTOR's CredentialManager in the governance district. "
            "Answer the owner's question using this real provider-status "
            f"context — do not invent data you don't have:\n\n{context}\n\n"
            f"Question: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][cred_mgr] answer_credential_question failed: {}", e)
            return context

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "scan")
        try:
            if task_type == "validate":
                result = self.validate_key(task.get("provider", "anthropic"), task.get("key", ""))
                self.award_points(10, "key_validated")
                return {"status": "ok", "validation": result}

            elif task_type == "template":
                template = self.generate_env_template()
                self.award_points(5, "template_generated")
                return {"status": "ok", "template": template}

            elif task_type == "scan":  # this file's own deliberate, self-tested
                                        # action_type (see __main__ smoke test
                                        # below, `agent.run({"type": "scan"})`)
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_credential_question(query)
                    if answer:
                        self._get_memory().store(
                            event_type="credential_question_answered",
                            content=f"CredentialManager answered: {query[:80]}",
                            tags=["governance", "credentials"],
                            source="credential_manager",
                        )
                        self.award_points(10, "credential_question_answered")
                        return {"status": "ok", "response": answer}

                result = self.scan_available_providers()
                self._get_memory().store(
                    event_type="credential_scan",
                    content=f"Providers: {result['available_count']} available, "
                            f"{result['cloud_providers_ready']} cloud",
                    tags=["governance", "credentials", "llm"],
                    source="credential_manager",
                )
                self.award_points(15, "credentials_scanned")
                return {"status": "ok", "credentials": result}

            else:
                # RR-3.7B.1 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                # RR3_7B1_AMBIGUITY_AUTOPILOT_CLOSURE_REPORT.md): this used
                # to be the same `else` branch "scan" fell into, so ANY
                # unrecognized/misrouted task_type (e.g. Governor's HP-
                # lottery fallback selecting CredentialManager for a
                # completely unrelated governance-district action such as
                # privacy.py's "gdpr_check", which has no exact capability
                # match anywhere and no PermissionGateway boundary) silently
                # ran the real scan_available_providers() call -- which
                # returns each configured provider's key_prefix (first 8
                # chars of a real API key) in the HTTP response body. A
                # free-text question is still answered here (safe,
                # LLM-grounded, no key material) exactly as before; anything
                # else now gets an honest "unhandled type" error, matching
                # the dominant pattern every other district agent in this
                # codebase already uses for an unrecognized type, instead of
                # defaulting into a real, key-material-bearing action.
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_credential_question(query)
                    if answer:
                        self._get_memory().store(
                            event_type="credential_question_answered",
                            content=f"CredentialManager answered: {query[:80]}",
                            tags=["governance", "credentials"],
                            source="credential_manager",
                        )
                        self.award_points(10, "credential_question_answered")
                        return {"status": "ok", "response": answer}
                return {"status": "error", "error": f"unhandled type '{task_type}'"}

        except Exception as e:
            logger.error("[VECTOR][cred_mgr] {}", e)
            self.deduct_points(20, "credential_scan_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = CredentialManager()
        scan = agent.scan_available_providers()
        print(f"[OK] scan: {scan['available_count']} providers, cloud={scan['cloud_providers_ready']}")
        print(f"[OK] recommendation: {scan['recommendation']}")
        val = agent.validate_key("anthropic", "sk-ant-api03-test123456789012345678901234567890")
        print(f"[OK] validate: valid={val['valid']}")
        result = await agent.run({"type": "scan"})
        print(f"[OK] run: status={result['status']}")
        print("credential_manager.py OK")

    asyncio.run(_smoke())
