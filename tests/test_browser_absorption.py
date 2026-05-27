"""Tests for the auto-browser absorption: dom_pruner, pii_scrub, auth_profiles.

All tests are deterministic and run without Playwright or any browser binary.
Guarded paths (Pillow screenshot redaction) are tested for graceful fallback.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── DOMPruner ─────────────────────────────────────────────────────────────────

class TestDOMPruner:
    def setup_method(self):
        from core.browser.dom_pruner import DOMPruner
        self.pruner = DOMPruner(max_elements=3)
        self.elements = [
            {"type": "button",   "text": "Submit",   "is_visible": True,  "y": 100},
            {"type": "input",    "name": "email",    "is_visible": True,  "y": 50},
            {"type": "link",     "text": "Home",     "is_visible": True,  "y": 30},
            {"type": "input",    "name": "password", "is_visible": True,  "y": 60},
            {"type": "select",   "name": "country",  "is_visible": True,  "y": 200},
            {"type": "checkbox", "label": "Remember","is_visible": False,  "y": 300},
        ]

    def test_prune_limits_count(self):
        result = self.pruner.prune(self.elements)
        assert len(result) == 3

    def test_prune_respects_max_elements_override(self):
        result = self.pruner.prune(self.elements, max_elements=2)
        assert len(result) == 2

    def test_prune_empty_returns_empty(self):
        assert self.pruner.prune([]) == []

    def test_prune_under_limit_returns_all(self):
        few = self.elements[:2]
        assert self.pruner.prune(few) == few

    def test_task_keyword_boosts_relevant_elements(self):
        result = self.pruner.prune(self.elements, task_goal="login with email and password")
        names = {e.get("name") or e.get("text") for e in result}
        assert "email" in names or "password" in names

    def test_hidden_elements_penalized(self):
        result = self.pruner.prune(self.elements, task_goal="remember me")
        hidden = [e for e in result if not e.get("is_visible", True)]
        assert len(hidden) == 0 or len(result) < 3  # hidden only selected if needed

    def test_prune_observation_modifies_copy(self):
        obs = {"interactable_elements": self.elements, "url": "https://example.com"}
        pruned = self.pruner.prune_observation(obs)
        assert len(pruned["interactable_elements"]) == 3
        assert pruned["elements_total"] == 6
        assert pruned["elements_pruned"] == 3
        assert len(obs["interactable_elements"]) == 6  # original unchanged

    def test_prune_observation_uses_interactable_or_elements(self):
        obs = {"elements": self.elements[:4]}
        pruned = self.pruner.prune_observation(obs)
        assert pruned["elements_total"] == 4

    def test_record_interaction_boosts(self):
        self.pruner.record_interaction("btn-1")
        button = {"type": "div", "element_id": "btn-1", "is_visible": True, "y": 500}
        many = [{"type": "text", "is_visible": True, "y": i} for i in range(10)]
        result = self.pruner.prune([button] + many)
        assert button in result

    def test_recency_set_bounded(self):
        for i in range(100):
            self.pruner.record_interaction(f"el-{i}")
        assert len(self.pruner._recently_interacted) <= 50

    def test_get_dom_pruner_singleton(self):
        from core.browser.dom_pruner import get_dom_pruner
        a = get_dom_pruner()
        b = get_dom_pruner()
        assert a is b


# ── PiiScrubber ───────────────────────────────────────────────────────────────

class TestScrubText:
    def setup_method(self):
        from core.browser.pii_scrub import scrub_text
        self.scrub = scrub_text

    def test_email_detected(self):
        r = self.scrub("Contact us at support@example.com today.")
        assert r.scrubbed
        assert "support@example.com" not in r.text
        assert "[REDACTED]" in r.text

    def test_jwt_detected(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abc123xyz"
        r = self.scrub(f"Token: {jwt}")
        assert r.scrubbed

    def test_bearer_token_detected(self):
        r = self.scrub("Authorization: Bearer ghp_abcdefghijklmnopqrst1234567890AB")
        assert r.scrubbed

    def test_aws_access_key_detected(self):
        # 19-char key (A + [KSIARP] + [IDA] + 16 alphanumeric) followed by space
        r = self.scrub("Key: AKIABCDEFGHIJKLMNOP is the access key id")
        assert r.scrubbed

    def test_pem_header_detected(self):
        r = self.scrub("-----BEGIN PRIVATE KEY----- content here")
        assert r.scrubbed

    def test_ssn_detected(self):
        r = self.scrub("SSN: 123-45-6789")
        assert r.scrubbed

    def test_phone_us_detected(self):
        r = self.scrub("Call (800) 555-1234 for help")
        assert r.scrubbed

    def test_clean_text_no_hits(self):
        r = self.scrub("The weather is nice today. No secrets here.")
        assert not r.scrubbed

    def test_empty_string_no_crash(self):
        r = self.scrub("")
        assert not r.scrubbed
        assert r.text == ""

    def test_enabled_patterns_filter(self):
        r = self.scrub("support@example.com", enabled_patterns={"jwt_token"})
        assert not r.scrubbed  # email pattern not enabled

    def test_custom_replacement(self):
        r = self.scrub("support@example.com", replacement="***")
        assert "***" in r.text

    def test_hit_has_expected_fields(self):
        r = self.scrub("support@example.com")
        assert r.hits
        hit = r.hits[0]
        assert "pattern" in hit
        assert "offset" in hit
        assert "length" in hit

    def test_credit_card_luhn_valid(self):
        r = self.scrub("Card: 4111111111111111")
        assert r.scrubbed

    def test_credit_card_luhn_invalid_not_redacted(self):
        r = self.scrub("Not a card: 4111111111111112")
        # invalid Luhn — should not be redacted
        assert "4111111111111112" in r.text


class TestScrubNetworkBody:
    def setup_method(self):
        from core.browser.pii_scrub import scrub_network_body
        self.scrub = scrub_network_body

    def test_json_body_scrubbed(self):
        body = json.dumps({"email": "user@example.com"})
        result, hits = self.scrub(body, "application/json")
        assert hits

    def test_binary_content_type_skipped(self):
        body = b"\x89PNG\r\n"
        result, hits = self.scrub(body, "image/png")
        assert result is body
        assert hits == []

    def test_none_body_returns_none(self):
        result, hits = self.scrub(None, "application/json")
        assert result is None
        assert hits == []


class TestScrubConsoleMessages:
    def setup_method(self):
        from core.browser.pii_scrub import scrub_console_messages
        self.scrub = scrub_console_messages

    def test_pii_in_console_scrubbed(self):
        msgs = [{"text": "Logged in as user@example.com", "level": "log"}]
        cleaned, hits = self.scrub(msgs)
        assert hits
        assert "user@example.com" not in cleaned[0]["text"]
        assert cleaned[0].get("pii_redacted") is True

    def test_clean_messages_unchanged(self):
        msgs = [{"text": "Page loaded", "level": "log"}]
        cleaned, hits = self.scrub(msgs)
        assert not hits
        assert cleaned[0]["text"] == "Page loaded"


class TestPiiScrubberService:
    def setup_method(self):
        from core.browser.pii_scrub import PiiScrubber
        self.scrubber = PiiScrubber(enabled=True)

    def test_text_method(self):
        r = self.scrubber.text("support@example.com")
        assert r.scrubbed

    def test_disabled_scrubber_passthrough(self):
        from core.browser.pii_scrub import PiiScrubber
        s = PiiScrubber(enabled=False)
        r = s.text("support@example.com")
        assert not r.scrubbed

    def test_screenshot_disabled_passthrough(self):
        from core.browser.pii_scrub import PiiScrubber
        s = PiiScrubber(screenshot_enabled=False)
        result, hits = s.screenshot(b"fakeimage", [{"text": "key@example.com", "x": 0, "y": 0, "width": 100, "height": 20}])
        assert result == b"fakeimage"
        assert hits == []

    def test_network_disabled_passthrough(self):
        from core.browser.pii_scrub import PiiScrubber
        s = PiiScrubber(network_enabled=False)
        result, hits = s.network_body('{"email": "a@b.com"}', "application/json")
        assert hits == []

    def test_summary_has_keys(self):
        summary = self.scrubber.summary()
        assert "enabled" in summary
        assert "patterns" in summary

    def test_get_pii_scrubber_singleton(self):
        from core.browser.pii_scrub import get_pii_scrubber
        a = get_pii_scrubber()
        b = get_pii_scrubber()
        assert a is b


# ── BrowserAuthStore ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_store(tmp_path):
    from core.browser.auth_profiles import BrowserAuthStore
    return BrowserAuthStore(root=tmp_path)


class TestBrowserAuthStore:
    def test_save_and_load(self, tmp_store):
        state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
        tmp_store.save("github", state)
        loaded = tmp_store.load("github")
        assert loaded["cookies"][0]["value"] == "abc"

    def test_save_string_state(self, tmp_store):
        state = {"cookies": [], "origins": []}
        tmp_store.save("gitlab", json.dumps(state))
        loaded = tmp_store.load("gitlab")
        assert loaded["cookies"] == []

    def test_load_missing_raises_keyerror(self, tmp_store):
        with pytest.raises(KeyError):
            tmp_store.load("nonexistent")

    def test_list_empty(self, tmp_store):
        assert tmp_store.list() == []

    def test_list_after_save(self, tmp_store):
        tmp_store.save("a", {"cookies": [], "origins": []})
        tmp_store.save("b", {"cookies": [], "origins": []})
        profiles = tmp_store.list()
        names = {p["profile_name"] for p in profiles}
        assert {"a", "b"} <= names

    def test_list_sorted_by_last_saved(self, tmp_store):
        import time
        tmp_store.save("first", {"cookies": [], "origins": []})
        time.sleep(0.01)
        tmp_store.save("second", {"cookies": [], "origins": []})
        profiles = tmp_store.list()
        assert profiles[0]["profile_name"] == "second"

    def test_get_returns_metadata(self, tmp_store):
        tmp_store.save("myprofile", {"cookies": [], "origins": []}, metadata={"url": "https://example.com"})
        info = tmp_store.get("myprofile")
        assert info["state_exists"] is True
        assert info["metadata"]["url"] == "https://example.com"

    def test_get_missing_raises_keyerror(self, tmp_store):
        with pytest.raises(KeyError):
            tmp_store.get("ghost")

    def test_delete_existing(self, tmp_store):
        tmp_store.save("todel", {"cookies": [], "origins": []})
        result = tmp_store.delete("todel")
        assert result is True
        with pytest.raises(KeyError):
            tmp_store.load("todel")

    def test_delete_missing_returns_false(self, tmp_store):
        assert tmp_store.delete("ghost") is False

    def test_overwrite_save(self, tmp_store):
        tmp_store.save("overwrite", {"cookies": [{"name": "a", "value": "1"}], "origins": []})
        tmp_store.save("overwrite", {"cookies": [], "origins": []})
        loaded = tmp_store.load("overwrite")
        assert loaded["cookies"] == []

    def test_normalize_name_valid(self, tmp_store):
        assert tmp_store.normalize_name("my-profile.v2") == "my-profile.v2"

    def test_normalize_name_empty_raises(self, tmp_store):
        with pytest.raises(ValueError):
            tmp_store.normalize_name("")

    def test_normalize_name_invalid_chars_raises(self, tmp_store):
        with pytest.raises(ValueError):
            tmp_store.normalize_name("../evil")

    def test_path_traversal_blocked(self, tmp_store):
        with pytest.raises(PermissionError):
            tmp_store._resolve_path(tmp_store._root, "../outside")

    def test_export_creates_archive(self, tmp_store):
        tmp_store.save("exportme", {"cookies": [], "origins": []})
        result = tmp_store.export("exportme")
        assert Path(result["archive_path"]).exists()
        assert result["archive_name"].startswith("exportme-")

    def test_export_missing_raises(self, tmp_store):
        with pytest.raises(FileNotFoundError):
            tmp_store.export("ghost")

    def test_import_profile_round_trip(self, tmp_store):
        tmp_store.save("roundtrip", {"cookies": [{"name": "x", "value": "y"}], "origins": []})
        export = tmp_store.export("roundtrip")
        tmp_store.delete("roundtrip")
        result = tmp_store.import_profile(export["archive_name"])
        assert result["imported"] is True
        loaded = tmp_store.load("roundtrip")
        assert loaded["cookies"][0]["value"] == "y"

    def test_import_overwrite_false_raises(self, tmp_store):
        tmp_store.save("exists", {"cookies": [], "origins": []})
        export = tmp_store.export("exists")
        with pytest.raises(FileExistsError):
            tmp_store.import_profile(export["archive_name"], overwrite=False)

    def test_import_overwrite_true_succeeds(self, tmp_store):
        tmp_store.save("overwr", {"cookies": [{"name": "old", "value": "1"}], "origins": []})
        export = tmp_store.export("overwr")
        tmp_store.save("overwr", {"cookies": [{"name": "new", "value": "2"}], "origins": []})
        result = tmp_store.import_profile(export["archive_name"], overwrite=True)
        assert result["imported"] is True

    def test_get_auth_store_singleton(self):
        from core.browser.auth_profiles import get_auth_store
        a = get_auth_store()
        b = get_auth_store()
        assert a is b


# ── MCP browser tools ─────────────────────────────────────────────────────────

def test_mcp_browser_tools_exist():
    import asyncio
    from core.mcp_server import _make_server
    server = _make_server()

    async def _check():
        listed = await server.list_tools()
        names = set(listed.keys()) if isinstance(listed, dict) else {t.name for t in listed}
        assert "browser_prune_dom" in names, f"browser_prune_dom missing from {names}"
        assert "browser_list_auth_profiles" in names, f"browser_list_auth_profiles missing from {names}"
        assert "browser_save_auth_profile" in names, f"browser_save_auth_profile missing from {names}"

    asyncio.run(_check())


# ── App still builds ──────────────────────────────────────────────────────────

def test_create_app_builds():
    from core.api.app import create_app
    assert create_app() is not None
