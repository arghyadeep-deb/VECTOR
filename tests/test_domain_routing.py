"""Domain alignment layer — best model per work domain with fallbacks (2026-07-02).

Offline: tests chain registration + role→domain resolution + guardrails.
No network (the actual provider_client call path is covered by live verification).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inference.model_catalog import (
    get_domains, chain_for_domain, domain_local_only, is_model_allowed,
    reload_catalog,
)
from core.inference.vectorcode_llm import _resolve_domain, _ROLE_TO_DOMAIN


@pytest.fixture(autouse=True)
def _fresh():
    reload_catalog()
    yield


# ── domain registration in model_pool ────────────────────────────────────────

def test_all_domains_registered_as_pool_models():
    from core.inference.model_pool import MODEL_POOL
    for name in get_domains():
        assert f"domain:{name}" in MODEL_POOL


def test_domain_pool_chain_matches_catalog():
    from core.inference.model_pool import MODEL_POOL
    for name, dom in get_domains().items():
        assert MODEL_POOL[f"domain:{name}"] == list(dom.chain)


# ── role → domain resolution ─────────────────────────────────────────────────

def test_explicit_domain_wins():
    assert _resolve_domain("vector-focus", "coding.review") == "coding.review"


def test_role_defaults():
    assert _resolve_domain("vector-coder", "") == "coding.generation"
    assert _resolve_domain("vector-reasoning", "") == "orchestration"
    assert _resolve_domain("vector-focus", "") == "agentic.loop"
    assert _resolve_domain("vector-multilingual", "") == "multilingual.indic"
    assert _resolve_domain("vector-deep", "") == "research"


def test_unmapped_role_returns_empty():
    assert _resolve_domain("some-random-model", "") == ""


def test_every_role_domain_exists_in_catalog():
    domains = get_domains()
    for role, dom in _ROLE_TO_DOMAIN.items():
        assert dom in domains, f"role '{role}' → unknown domain '{dom}'"


# ── never-crash + guardrail invariants ───────────────────────────────────────

def test_every_domain_ends_on_ollama():
    for name, dom in get_domains().items():
        assert dom.chain[-1][0] == "ollama", f"'{name}' missing ollama terminal"


def test_security_domain_local_only():
    assert domain_local_only("security") is True
    assert all(p == "ollama" for p, _ in chain_for_domain("security"))


def test_no_domain_chain_leaks_paid_model():
    for name, dom in get_domains().items():
        for prov, model in dom.chain:
            if prov == "ollama":
                continue
            assert is_model_allowed(prov, model), (
                f"domain '{name}': {prov}/{model} would be blocked by whitelist")


def test_flagship_domains_present():
    # The domains flagship agents will be tagged with must all exist.
    needed = {"content.script", "coding.generation", "coding.review",
              "coding.architecture", "research", "orchestration", "vision"}
    assert needed.issubset(set(get_domains().keys()))


if __name__ == "__main__":
    # real test, no mocks
    ok = _resolve_domain("vector-coder", "") == "coding.generation"
    print("✅ test_domain_routing OK" if ok else "❌ FAILED")
