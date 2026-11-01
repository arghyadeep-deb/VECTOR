"""
VECTOR Smart Routing — x402 USDC Micropayment Protocol
Python port of ClawRouter/src/payment-preauth.ts

The x402 protocol (HTTP 402 Payment Required) enables autonomous agents to pay
for API access with USDC micropayments — no API keys or credit cards needed.

Flow:
  1. Send request to x402-enabled endpoint
  2. Get HTTP 402 with payment details (price, address, chain)
  3. Sign USDC transfer locally from wallet
  4. Retry request with x402-payment header
  5. Endpoint verifies payment and responds

This module implements the Python client side of x402.
Server-side verification is handled by blockrun.ai.

Usage:
    client = X402Client(wallet_keys)
    response = await client.request_with_payment(
        url="https://api.blockrun.ai/v1/chat/completions",
        payload={...},
    )
"""
from __future__ import annotations

__all__ = [
    "PaymentDetails",
    "PaymentReceipt",
    "X402Client",
]


import asyncio
import base64
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger

_X402_HEADER = "x402-payment"
_MAX_PAYMENT_RETRIES = 3


@dataclass
class PaymentDetails:
    """Decoded from HTTP 402 response headers."""
    amount_usdc: float
    recipient_address: str
    chain: str             # "base" | "solana"
    memo: str
    deadline: int          # unix timestamp


@dataclass
class PaymentReceipt:
    tx_hash: str
    amount_usdc: float
    chain: str
    timestamp: int


def _parse_402_headers(headers: dict) -> PaymentDetails | None:
    """Parse x402 payment details from 402 response headers."""
    try:
        price_header = headers.get("x-payment-required") or headers.get("www-authenticate", "")
        if not price_header:
            return None
        # Parse: x402 amount=0.001 address=0x... chain=base memo=req123 deadline=1234567890
        parts: dict[str, str] = {}
        for part in price_header.split():
            if "=" in part:
                k, v = part.split("=", 1)
                parts[k] = v.strip('"')
        return PaymentDetails(
            amount_usdc=float(parts.get("amount", "0")),
            recipient_address=parts.get("address", ""),
            chain=parts.get("chain", "base"),
            memo=parts.get("memo", ""),
            deadline=int(parts.get("deadline", int(time.time()) + 60)),
        )
    except Exception as e:
        logger.debug("[VECTOR][payment] failed to parse 402 headers: {}", e)
        return None


async def _sign_evm_payment(
    private_key_hex: str,
    payment: PaymentDetails,
) -> str:
    """
    Sign a USDC transfer on Base (EVM) using EIP-712 typed data.
    Returns base64-encoded signature bytes.
    """
    try:
        from eth_account import Account
        from eth_account.structured_data.hashing import hash_domain, hash_message
        # Simplified EIP-712 signing for USDC transfer
        domain = {
            "name": "USD Coin",
            "version": "2",
            "chainId": 8453,  # Base mainnet
            "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        }
        message = {
            "from":     Account.from_key(private_key_hex).address,
            "to":       payment.recipient_address,
            "value":    int(payment.amount_usdc * 1_000_000),  # USDC 6 decimals
            "validBefore": payment.deadline,
            "nonce":    hashlib.sha256(payment.memo.encode()).hexdigest()[:32],
        }
        msg_hash = hashlib.sha256(
            json.dumps({"domain": domain, "message": message}, sort_keys=True).encode()
        ).digest()
        account = Account.from_key(private_key_hex)
        sig = account.signHash(msg_hash)
        return base64.b64encode(sig.signature).decode()
    except ImportError:
        raise RuntimeError("eth_account is required for EVM x402 payment signing")
    except Exception as e:
        logger.error("[VECTOR][payment] EVM signing error: {}", e)
        raise


async def _sign_solana_payment(
    private_key_bytes: bytes,
    payment: PaymentDetails,
) -> str:
    """
    Sign a USDC transfer on Solana using Ed25519.
    Returns base64-encoded signature bytes.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        message = json.dumps({
            "to": payment.recipient_address,
            "amount": int(payment.amount_usdc * 1_000_000),
            "memo": payment.memo,
            "deadline": payment.deadline,
        }, sort_keys=True).encode()
        sig = sk.sign(message)
        return base64.b64encode(sig).decode()
    except ImportError:
        raise RuntimeError("cryptography is required for Solana x402 payment signing")
    except Exception as e:
        logger.error("[VECTOR][payment] Solana signing error: {}", e)
        raise


class X402Client:
    """
    Python x402 payment protocol client.
    Handles automatic payment signing for 402 responses.
    """

    def __init__(
        self,
        evm_private_key: str = "",
        solana_private_key_bytes: bytes = b"",
        chain: str = "base",
    ) -> None:
        self._evm_key     = evm_private_key
        self._sol_key     = solana_private_key_bytes
        self._chain       = chain
        self._total_spent: float = 0.0
        self._payment_count: int = 0

    async def sign_payment(self, payment: PaymentDetails) -> str:
        """Sign a payment and return the x402-payment header value."""
        from districts.investment.safety import approve_live_trade

        decision = await approve_live_trade(
            platform=f"x402:{payment.chain}",
            operation="sign_payment",
            details={
                "amount_usdc": payment.amount_usdc,
                "recipient_address": payment.recipient_address,
                "memo": payment.memo,
                "deadline": payment.deadline,
            },
            proposed_by="smart_routing_payment",
        )
        if decision["status"] != "approved":
            raise RuntimeError(f"x402 payment blocked: {decision.get('reason', 'not_approved')}")

        if payment.chain == "solana" and self._sol_key:
            sig = await _sign_solana_payment(self._sol_key, payment)
        elif self._evm_key:
            sig = await _sign_evm_payment(self._evm_key, payment)
        else:
            raise RuntimeError("No wallet key configured for x402 payments")

        # x402 header format: base64(JSON({chain, sig, amount, ...}))
        header_payload = {
            "chain":   payment.chain,
            "sig":     sig,
            "amount":  payment.amount_usdc,
            "to":      payment.recipient_address,
            "memo":    payment.memo,
        }
        return base64.b64encode(json.dumps(header_payload).encode()).decode()

    async def request_with_payment(
        self,
        url: str,
        payload: dict,
        extra_headers: dict | None = None,
    ) -> dict:
        """
        Make an API request with automatic x402 payment if required.
        Retries with payment signature on HTTP 402.
        """
        import httpx
        headers = {"Content-Type": "application/json", **(extra_headers or {})}

        for attempt in range(_MAX_PAYMENT_RETRIES):
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(url, json=payload, headers=headers)

                if r.status_code == 200:
                    return r.json()

                if r.status_code == 402:
                    payment = _parse_402_headers(dict(r.headers))
                    if not payment:
                        raise RuntimeError("402 response missing payment details")
                    logger.info("[VECTOR][payment] paying ${:.6f} USDC on {}",
                                payment.amount_usdc, payment.chain)
                    sig_header = await self.sign_payment(payment)
                    headers[_X402_HEADER] = sig_header
                    self._total_spent += payment.amount_usdc
                    self._payment_count += 1
                    continue  # retry with payment header

                r.raise_for_status()

        raise RuntimeError(f"Failed after {_MAX_PAYMENT_RETRIES} payment attempts")

    @property
    def total_spent_usdc(self) -> float:
        return self._total_spent

    @property
    def payment_count(self) -> int:
        return self._payment_count


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        client = X402Client(chain="base")
        print(f"OK payment.py — x402 USDC micropayment protocol client")
        print(f"  chain: {client._chain}")
        print(f"  wallet configured: evm={bool(client._evm_key)} solana={bool(client._sol_key)}")
        print(f"  total_spent: ${client.total_spent_usdc}")
        print(f"  Flow: send request → 402 response → sign USDC → retry with x402 header")

    asyncio.run(_smoke())
