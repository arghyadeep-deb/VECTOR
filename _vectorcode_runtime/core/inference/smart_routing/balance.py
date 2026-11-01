"""
VECTOR Smart Routing — EVM + Solana Balance Monitor
Python port of ClawRouter/src/balance.ts + src/solana-balance.ts

Monitors USDC balance on Base (EVM) and Solana for x402 micropayments.
Balance used to gate whether payment-based API calls can proceed.

Usage:
    monitor = BalanceMonitor(evm_address="0x...", chain="base")
    balance = await monitor.get_balance()
    ok = await monitor.check_sufficient(estimated_usd=0.001)
"""
from __future__ import annotations

__all__ = [
    "BalanceMonitor",
    "BalanceSufficiency",
]


import asyncio
import sys
from dataclasses import dataclass
from typing import Optional

from loguru import logger

# USDC contract addresses
_USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"   # USDC on Base
_USDC_SOLANA  = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC on Solana mainnet

# Blockrun API endpoints
_BASE_API    = "https://blockrun.ai/api"
_SOLANA_API  = "https://sol.blockrun.ai/api"


@dataclass
class BalanceSufficiency:
    sufficient: bool
    balance_usdc: float
    required_usdc: float
    chain: str


class BalanceMonitor:
    """
    Monitors USDC balance for x402 payment gating.
    Supports Base (EVM) and Solana chains.
    """

    def __init__(
        self,
        evm_address: str = "",
        solana_address: str = "",
        chain: str = "base",    # "base" | "solana"
    ) -> None:
        self._evm_address     = evm_address
        self._solana_address  = solana_address
        self._chain           = chain
        self._cached_balance: float | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 30.0  # refresh balance every 30s

    async def get_balance(self, force_refresh: bool = False) -> float:
        """Get USDC balance in USD. Cached for 30s."""
        import time
        if not force_refresh and self._cached_balance is not None:
            if time.time() - self._cache_time < self._cache_ttl:
                return self._cached_balance

        if self._chain == "solana":
            balance = await self._get_solana_balance()
        else:
            balance = await self._get_evm_balance()

        self._cached_balance = balance
        self._cache_time = time.time()
        return balance

    async def _get_evm_balance(self) -> float:
        """Get USDC balance on Base (EVM) via RPC."""
        if not self._evm_address:
            return 0.0
        try:
            import httpx
            # ERC-20 balanceOf call: 0x70a08231 + padded address
            addr_padded = self._evm_address.lower().replace("0x", "").zfill(64)
            data = "0x70a08231" + addr_padded
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_call",
                "params": [{"to": _USDC_BASE, "data": data}, "latest"],
            }
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post("https://mainnet.base.org", json=payload)
                result = r.json().get("result", "0x0")
                raw = int(result, 16)
                return raw / 1_000_000  # USDC has 6 decimals
        except Exception as e:
            logger.debug("[VECTOR][balance] EVM balance check failed: {}", e)
            return 0.0

    async def _get_solana_balance(self) -> float:
        """Get USDC balance on Solana via RPC."""
        if not self._solana_address:
            return 0.0
        try:
            import httpx
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    self._solana_address,
                    {"mint": _USDC_SOLANA},
                    {"encoding": "jsonParsed"},
                ],
            }
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post("https://api.mainnet-beta.solana.com", json=payload)
                data = r.json()
                accounts = data.get("result", {}).get("value", [])
                if not accounts:
                    return 0.0
                amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
                return float(amount or 0.0)
        except Exception as e:
            logger.debug("[VECTOR][balance] Solana balance check failed: {}", e)
            return 0.0

    async def check_sufficient(self, estimated_usd: float) -> BalanceSufficiency:
        """Check if balance is sufficient for a given cost estimate."""
        balance = await self.get_balance()
        sufficient = balance >= estimated_usd
        if not sufficient:
            logger.warning("[VECTOR][balance] insufficient: need ${:.6f} have ${:.6f}",
                           estimated_usd, balance)
        return BalanceSufficiency(
            sufficient=sufficient,
            balance_usdc=balance,
            required_usdc=estimated_usd,
            chain=self._chain,
        )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        monitor = BalanceMonitor(chain="base")
        balance = await monitor.get_balance()
        suf = await monitor.check_sufficient(0.001)
        print(f"OK balance.py — EVM+Solana USDC balance monitor")
        print(f"  balance (no address set): ${balance}")
        print(f"  sufficient for $0.001: {suf.sufficient}")
        print(f"  chain: {suf.chain}")

    asyncio.run(_smoke())
