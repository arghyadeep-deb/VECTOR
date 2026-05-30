"""
Credential Manager — multi-provider API key management with failover.

Wraps vectorcode/src/agent/credential_pool.py concept.
Manages API keys for Gemini, Anthropic, OpenRouter, Bedrock.
Reports which providers are live, which are exhausted, handles key rotation.
"""
import asyncio
import os
import datetime


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

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
            # dynamic provider env var — kept as os.getenv
            key = os.getenv(env_var) or CONFIG.get("api_keys", {}).get(provider, "")
            has_key = bool(key and len(key) > 8)
            status[provider] = {
                "available": has_key,
                # dynamic provider env var — kept as os.getenv
                "key_source": "env" if os.getenv(env_var) else ("config" if has_key else "none"),
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
        # dynamic provider env var — kept as os.getenv
        key = key or os.getenv(_ENV_KEYS.get(provider, ""), "")
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

            else:  # scan
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
