"""
VECTOR Smart Routing
Intelligent LLM routing — port of ClawRouter's routing + payment + compression stack.

Components:
  classifier      — 15-dim complexity scoring in < 1ms → SIMPLE/MEDIUM/COMPLEX/REASONING
  model_catalog   — 55+ models with pricing, capabilities, fallback chains
  compressor      — 7-layer context compression (15-40% token savings)
  request_cache   — SHA-256 dedup + 30s TTL response cache
  fallback_chain  — structured fallback with per-model timeouts
  wallet          — BIP-39/BIP-44/SLIP-10 HD wallet for EVM + Solana
  balance         — USDC balance monitoring (Base + Solana)
  payment         — x402 USDC micropayment protocol client
  proxy           — OpenAI-compatible local proxy (port 8402)
  stats           — usage analytics + JSONL request journal
  response_store  — persistent response storage
  partners        — partner API registry (Exa, Jina, Serper, Firecrawl)

Quick start:
    from core.inference.smart_routing import classify, compress, RequestCache

    # Classify prompt complexity
    decision = classify("Prove the Riemann hypothesis step by step")
    logger.info(decision.tier)   # REASONING


    # Compress messages before sending to LLM
    result = compress(messages)
    logger.info(f"Saved {result.savings_pct:.0%} tokens")


    # Cache repeated requests
    cache = RequestCache()
    key = cache.cache_key(messages, model="gpt-4o")
"""
__version__ = "1.0.0"

from core.inference.smart_routing.classifier import (
    classify, Tier, Profile, RoutingDecision, DimensionScore,
    DIMENSION_WEIGHTS, TIER_BOUNDARIES,
)
from core.inference.smart_routing.model_catalog import (
    ModelEntry, MODEL_CATALOG, MODEL_ALIASES,
    cheapest_for_tier, fallback_chain_for, estimate_cost, baseline_cost, savings_pct,
    get_model, resolve_alias,
)
from core.inference.smart_routing.compressor import compress, should_compress, CompressionResult
from core.inference.smart_routing.request_cache import RequestCache, get_cache
from core.inference.smart_routing.fallback_chain import execute_with_fallback, FallbackChainExecutor
from core.inference.smart_routing.wallet import (
    generate_mnemonic, validate_mnemonic, derive_evm_key,
    derive_solana_key_bytes, derive_all_keys, ensure_wallet, DerivedKeys,
)
from core.inference.smart_routing.balance import BalanceMonitor, BalanceSufficiency
from core.inference.smart_routing.payment import X402Client, PaymentDetails
from core.inference.smart_routing.stats import RequestJournal, UsageStats, get_journal
from core.inference.smart_routing.response_store import ResponseStore, StoredResponse
from core.inference.smart_routing.partners import PartnerRegistry, get_registry
from core.inference.smart_routing.proxy import SmartRoutingProxy

__all__ = [
    # Classifier
    "classify", "Tier", "Profile", "RoutingDecision", "DimensionScore",
    # Model catalog
    "ModelEntry", "MODEL_CATALOG", "MODEL_ALIASES",
    "cheapest_for_tier", "fallback_chain_for", "estimate_cost", "baseline_cost",
    "get_model", "resolve_alias",
    # Compression
    "compress", "should_compress", "CompressionResult",
    # Cache
    "RequestCache", "get_cache",
    # Fallback
    "execute_with_fallback", "FallbackChainExecutor",
    # Wallet
    "generate_mnemonic", "validate_mnemonic", "derive_evm_key",
    "derive_solana_key_bytes", "derive_all_keys", "ensure_wallet", "DerivedKeys",
    # Balance
    "BalanceMonitor", "BalanceSufficiency",
    # Payment
    "X402Client", "PaymentDetails",
    # Stats
    "RequestJournal", "UsageStats", "get_journal",
    # Response store
    "ResponseStore", "StoredResponse",
    # Partners
    "PartnerRegistry", "get_registry",
    # Proxy
    "SmartRoutingProxy",
]
