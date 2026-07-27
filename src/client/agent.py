"""x402-paying agent client — REAL payments via the x402 SDK.

This is the buyer side — an AI agent that automatically discovers paid
telecom forensics endpoints and pays for them via x402 micropayments on Base Sepolia.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)


class X402AgentClient:
    """An AI agent client that pays for API access via x402.

    In production, this signs real USDC micro-transactions.
    In demo mode, it uses the X-Pay: demo header.

    Usage:
        client = X402AgentClient(base_url="http://localhost:8000")
        data = await client.decode_sip_packet("INVITE sip:bob@biloxi.com SIP/2.0...")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str = "telecom-agent-001",
        private_key: str = "",
        demo_mode: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.private_key = private_key
        self.demo_mode = demo_mode
        self._http = httpx.AsyncClient(timeout=30.0)
        self._total_spent = 0.0
        self._x402_client = None

    def _init_x402(self):
        """Lazy-init the x402 client for real payment signing."""
        if self._x402_client is not None:
            return

        if self.demo_mode or not self.private_key:
            log.info("🔓 Demo mode — payments will use X-Pay header")
            return

        try:
            from x402 import x402Client
            from x402.http import x402HTTPClient
            from x402.mechanisms.evm.exact import ExactEvmClientScheme, register_exact_evm_client
            from eth_account import Account

            account = Account.from_key(self.private_key)
            log.info("🔑 Wallet loaded: %s", account.address)

            # Create x402 client with EVM signer
            client = x402Client()
            # Register the exact EVM scheme for automatic payment signing
            register_exact_evm_client(
                client,
                network="eip155:84532",  # Base Sepolia
                private_key=self.private_key,
            )
            self._x402_client = x402HTTPClient(client)
            log.info("✅ x402 client initialized for wallet %s", account.address[:10] + "...")

        except Exception as e:
            log.warning("Failed to init x402 client: %s — falling back to demo mode", e)
            self.demo_mode = True

    def _headers(self) -> dict[str, str]:
        """Build request headers with agent identity."""
        h = {
            "x-agent-id": self.agent_id,
            "User-Agent": f"x402-telecom-agent-client/0.1 ({self.agent_id})",
        }
        if self.demo_mode:
            h["X-Pay"] = "demo"
        return h

    async def pay_and_fetch(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict[str, Any]:
        """Make a paid request to an x402-gated telecom endpoint.

        In demo mode: uses X-Pay: demo header.
        In production: the x402 SDK intercepts 402 responses and signs payments.
        """
        self._init_x402()
        url = f"{self.base_url}{path}"
        headers = self._headers()

        log.info("🤖 %s %s (agent=%s)", method, path, self.agent_id)

        # If we have the real x402 client, use it for automatic payment
        if self._x402_client and not self.demo_mode:
            try:
                resp = await self._http.request(
                    method, url, params=params, json=json_body, headers=headers
                )

                if resp.status_code == 402:
                    # Parse payment requirements from the 402 block
                    payment_required = self._x402_client.get_payment_required_response(
                        get_header=lambda name: resp.headers.get(name),
                        body=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                    )

                    # Create and sign payment voucher
                    payment_headers = self._x402_client.handle_payment_required(payment_required)

                    if payment_headers:
                        headers.update(payment_headers)
                        resp = await self._http.request(
                            method, url, params=params, json=json_body, headers=headers
                        )

                # Track spending from response header
                price = resp.headers.get("x-payment-response", "")
                if price:
                    try:
                        self._total_spent += float(price)
                    except (ValueError, TypeError):
                        pass

                if resp.status_code >= 400:
                    log.error("❌ %d: %s", resp.status_code, resp.text[:200])
                    return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}

                log.info("✅ %d (total: $%.6f)", resp.status_code, self._total_spent)
                return resp.json()

            except Exception as e:
                log.error("❌ x402 payment failed: %s", e)
                return {"error": str(e)}

        # Demo mode: simple header bypass
        resp = await self._http.request(
            method, url, params=params, json=json_body, headers=headers
        )

        if resp.status_code >= 400:
            log.error("❌ %d: %s", resp.status_code, resp.text[:200])
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}

        log.info("✅ %d (demo)", resp.status_code)
        return resp.json()

    async def close(self):
        await self._http.aclose()

    async def get_tool_catalog(self) -> dict:
        """Free Catalog: Auto-discover available telecom tools and pricing mapping."""
        return await self.pay_and_fetch("GET", "/api/v1/tools/list-products")

    async def check_engine_health(self) -> dict:
        """Free Catalog: Verify compute layer and Ollama status."""
        return await self.pay_and_fetch("GET", "/api/v1/tools/health")

    async def normalize_phone(self, raw_string: str, region: str = "US") -> dict:
        """Paid Tool ($0.005): Normalize phone string using local libphonenumber layer."""
        return await self.pay_and_fetch(
            "POST", "/api/v1/tools/phone-normalize", json_body={"raw_string": raw_string, "region": region}
        )

    async def decode_sip_packet(self, raw_sip_message: str) -> dict:
        """Paid Tool ($0.02): Parse multi-line raw SIP text payload via local Qwen 2.5 compute."""
        return await self.pay_and_fetch(
            "POST", "/api/v1/tools/sip-decode", json_body={"rawSipMessage": raw_sip_message}
        )

    async def diagnose_call_trace(self, sip_trace: str) -> dict:
        """Paid Tool ($0.05): Execute premium diagnostics on call logs using Q.850 heuristics."""
        return await self.pay_and_fetch(
            "POST", "/api/v1/tools/call-diagnose", json_body={"sipTrace": sip_trace}
        )

    @property
    def total_spent(self) -> float:
        return self._total_spent


async def main():
    """Demo: run the updated telecom agent client against the local workspace server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    base_url = os.environ.get("AGENT_BASE_URL", "http://localhost:8000")
    private_key = os.environ.get("AGENT_PRIVATE_KEY", "")
    demo_mode = not bool(private_key)

    client = X402AgentClient(base_url=base_url, private_key=private_key, demo_mode=demo_mode)

    try:
        # 1. Access Free Layer
        catalog = await client.get_tool_catalog()
        log.info("Catalog Discovered: %s", json.dumps(catalog, indent=2))

        # 2. Trigger Paid Computation Routing Engine
        sample_sip = (
            "INVITE sip:bob@biloxi.com SIP/2.0\r\n"
            "v: SIP/2.0/UDP ://atlanta.com;branch=z9hG4bK776asdhds\r\n"
            "f: Alice <sip:alice@atlanta.com>;tag=1928301774\r\n"
            "t: Bob <sip:bob@biloxi.com>\r\n"
            "i: a84b4c76e66710@://atlanta.com\r\n"
            "CSeq: 314159 INVITE\r\n"
            "Content-Length: 0"
        )
        
        result = await client.decode_sip_packet(sample_sip)
        log.info("Forensic Result: %s", json.dumps(result, indent=2))

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
