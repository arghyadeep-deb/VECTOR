"""E2 tests — Cloudflare Workers API gateway structure.

All tests verify the TypeScript worker source without requiring wrangler or a live deployment.
Actual deploy runs separately: ! cd api && npx wrangler deploy
"""
from __future__ import annotations

import unittest
from pathlib import Path


_API_DIR = Path(__file__).parent.parent.parent / "api"
_SRC = _API_DIR / "src"


# ── wrangler.toml ─────────────────────────────────────────────────────────────


class TestWranglerToml(unittest.TestCase):
    """api/wrangler.toml is correctly configured for Cloudflare deployment."""

    def _content(self) -> str:
        return (_API_DIR / "wrangler.toml").read_text(encoding="utf-8")

    def test_wrangler_toml_exists(self):
        self.assertTrue((_API_DIR / "wrangler.toml").exists())

    def test_wrangler_app_name_vector_api(self):
        self.assertIn('name = "vector-api"', self._content())

    def test_wrangler_main_is_index_ts(self):
        self.assertIn('main = "src/index.ts"', self._content())

    def test_wrangler_has_kv_namespace(self):
        self.assertIn("RATE_LIMIT_KV", self._content())

    def test_wrangler_documents_api_key_secret(self):
        self.assertIn("VECTOR_API_KEY", self._content())


# ── api/src/index.ts ──────────────────────────────────────────────────────────


class TestIndexTs(unittest.TestCase):
    """api/src/index.ts — main Worker entry point."""

    def _src(self) -> str:
        return (_SRC / "index.ts").read_text(encoding="utf-8")

    def test_index_ts_exists(self):
        self.assertTrue((_SRC / "index.ts").exists())

    def test_has_env_interface(self):
        self.assertIn("export interface Env", self._src())

    def test_env_has_vector_api_key(self):
        self.assertIn("VECTOR_API_KEY", self._src())

    def test_env_has_rate_limit_kv(self):
        self.assertIn("RATE_LIMIT_KV", self._src())

    def test_status_is_public_path(self):
        src = self._src()
        self.assertIn("/status", src)

    def test_health_is_public_path(self):
        src = self._src()
        self.assertIn("/health", src)

    def test_handles_cors_options(self):
        self.assertIn("OPTIONS", self._src())

    def test_has_auth_check(self):
        self.assertIn("verifyAuth", self._src())

    def test_has_rate_limit_check(self):
        self.assertIn("checkRateLimit", self._src())

    def test_exports_default_fetch_handler(self):
        self.assertIn("export default", self._src())
        self.assertIn("fetch(", self._src())


# ── api/src/router.ts ─────────────────────────────────────────────────────────


class TestRouterTs(unittest.TestCase):
    """api/src/router.ts — request proxy logic."""

    def _src(self) -> str:
        return (_SRC / "router.ts").read_text(encoding="utf-8")

    def test_router_ts_exists(self):
        self.assertTrue((_SRC / "router.ts").exists())

    def test_has_allowed_paths_set(self):
        self.assertIn("ALLOWED_PATHS", self._src())

    def test_allowed_paths_includes_status(self):
        self.assertIn('"/status"', self._src())

    def test_allowed_paths_includes_agents(self):
        self.assertIn('"/agents"', self._src())

    def test_allowed_paths_includes_heartbeat(self):
        self.assertIn('"/heartbeat"', self._src())

    def test_has_node_poll_route(self):
        src = self._src()
        self.assertIn("/nodes/", src)
        self.assertIn("/poll", src)
        self.assertIn("nodePoll", src)

    def test_has_command_result_route(self):
        src = self._src()
        self.assertIn("/commands/", src)
        self.assertIn("/result", src)
        self.assertIn("commandResult", src)

    def test_commands_are_targeted_to_nodes(self):
        src = self._src()
        self.assertIn("target_node", src)
        self.assertIn("termux-room-node", src)
        self.assertIn("legion-heavy-node", src)

    def test_returns_503_on_upstream_failure(self):
        self.assertIn("503", self._src())

    def test_returns_cors_header(self):
        self.assertIn("Access-Control-Allow-Origin", self._src())

    def test_returns_404_for_unknown_paths(self):
        self.assertIn("404", self._src())


# ── api/src/auth.ts ───────────────────────────────────────────────────────────


class TestAuthTs(unittest.TestCase):
    """api/src/auth.ts — Bearer token verification."""

    def _src(self) -> str:
        return (_SRC / "auth.ts").read_text(encoding="utf-8")

    def test_auth_ts_exists(self):
        self.assertTrue((_SRC / "auth.ts").exists())

    def test_exports_verify_auth(self):
        self.assertIn("export function verifyAuth", self._src())

    def test_checks_bearer_prefix(self):
        self.assertIn("Bearer", self._src())

    def test_returns_401_on_missing_auth(self):
        self.assertIn("401", self._src())

    def test_returns_403_on_wrong_token(self):
        self.assertIn("403", self._src())

    def test_compares_against_env_api_key(self):
        self.assertIn("env.VECTOR_API_KEY", self._src())


# ── api/src/rate_limiter.ts ───────────────────────────────────────────────────


class TestRateLimiterTs(unittest.TestCase):
    """api/src/rate_limiter.ts — sliding window KV rate limiter."""

    def _src(self) -> str:
        return (_SRC / "rate_limiter.ts").read_text(encoding="utf-8")

    def test_rate_limiter_ts_exists(self):
        self.assertTrue((_SRC / "rate_limiter.ts").exists())

    def test_exports_check_rate_limit(self):
        self.assertIn("export async function checkRateLimit", self._src())

    def test_uses_kv_namespace(self):
        self.assertIn("KVNamespace", self._src())

    def test_has_sliding_window_logic(self):
        # Filters timestamps outside the window
        self.assertIn("filter", self._src())

    def test_returns_429_indicator(self):
        # Returns boolean true → caller sends 429
        src = self._src()
        self.assertTrue("return true" in src or "429" in src)

    def test_has_expiration_ttl(self):
        self.assertIn("expirationTtl", self._src())


class TestD1Schema(unittest.TestCase):
    """api/schema.sql â€” D1 command queue schema."""

    def _schema(self) -> str:
        return (_API_DIR / "schema.sql").read_text(encoding="utf-8")

    def test_schema_has_target_node(self):
        self.assertIn("target_node", self._schema())

    def test_schema_has_result_columns(self):
        schema = self._schema()
        self.assertIn("result", schema)
        self.assertIn("error", schema)
        self.assertIn("completed_at", schema)

    def test_schema_has_target_status_index(self):
        self.assertIn("idx_command_queue_target_status", self._schema())

    def test_additive_migration_exists_for_existing_d1(self):
        migration = _API_DIR / "migrations" / "0002_command_node_results.sql"
        self.assertTrue(migration.exists())
        text = migration.read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE command_queue ADD COLUMN target_node", text)
        self.assertIn("idx_command_queue_target_status", text)


if __name__ == "__main__":
    unittest.main()
