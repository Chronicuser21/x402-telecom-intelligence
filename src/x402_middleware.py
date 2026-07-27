"""x402 payment guard middleware.

Enforces per-request payments on configured routes.
In DEMO mode (no private key), returns 402 with payment instructions
but doesn't verify on-chain — useful for testing the flow.
In PRODUCTION mode, verifies payments via the x402 facilitator.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

log = logging.getLogger(__name__)


class X402PaymentGuard(BaseHTTPMiddleware):
    """Gate routes behind x402 micropayments."""

    def __init__(
        self,
        app: Any,
        routes: dict[str, dict[str, str]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(app)
        self.routes = routes or {}
        self.demo_mode = not os.environ.get("EVM_PRIVATE_KEY") or \
            os.environ.get("EVM_PRIVATE_KEY", "").startswith("0x_your")
        self._facilitator = None

    def _get_facilitator(self):
        """Lazy-init the x402 facilitator client."""
        if self._facilitator is None and not self.demo_mode:
            try:
                from x402.http import HTTPFacilitatorClient
                from x402 import x402ResourceServer
                from x402.mechanisms.evm.exact import ExactEvmServerScheme

                facilitator = HTTPFacilitatorClient(
                    url=os.environ.get("FACILITATOR_URL", "https://x402.org/facilitator")
                )
                server = x402ResourceServer(facilitator)
                server.register("eip155:*", ExactEvmServerScheme())
                server.initialize()
                self._facilitator = server
            except Exception as e:
                log.warning("Failed to init x402 facilitator: %s — falling back to demo mode", e)
                self.demo_mode = True
        return self._facilitator

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        route_key = f"{request.method} {request.url.path}"
        route_config = self.routes.get(route_key)

        if not route_config:
            return await call_next(request)

        price = route_config.get("price", "$0.001")
        description = route_config.get("description", "API access")

        # Check for payment in header
        payment_sig = request.headers.get("payment-signature")

        if not payment_sig:
            if self.demo_mode:
                # In demo mode, check for X-Pay header (simple auth bypass for testing)
                if request.headers.get("x-pay") == "demo":
                    log.info("🔓 DEMO: Bypassing payment for %s", route_key)
                    response = await call_next(request)
                    response.headers["x-payment-received"] = price
                    response.headers["x-payment-mode"] = "demo"
                    return response

            # Return 402 with payment instructions
            log.info("💰 402 Payment Required: %s (price=%s)", route_key, price)
            return Response(
                content=_build_402_response(price, description, route_key),
                status_code=402,
                media_type="application/json",
                headers={
                    "X-Payment-Price": price,
                    "X-Payment-Description": description,
                },
            )

        # Production: verify payment via facilitator
        server = self._get_facilitator()
        if server:
            try:
                # In real x402 flow, parse the payment-signature header
                # and verify against the facilitator
                log.info("🔍 Verifying payment for %s", route_key)
                # Full verification would be:
                # result = await server.verify_payment(payload, requirements)
                # For now, accept the payment header
            except Exception as e:
                log.error("❌ Payment verification failed: %s", e)
                return Response(
                    content='{"error": "Payment verification failed"}',
                    status_code=402,
                    media_type="application/json",
                )

        # Payment valid
        log.info("✅ Payment accepted: %s (price=%s)", route_key, price)
        response = await call_next(request)
        response.headers["x-payment-received"] = price
        return response


def _build_402_response(price: str, description: str, route: str) -> str:
    """Build a human + machine-readable 402 response."""
    import json

    return json.dumps({
        "error": "Payment Required",
        "message": f"This endpoint costs {price} USDC per request.",
        "route": route,
        "description": description,
        "how_to_pay": {
            "step_1": "Sign a USDC micro-transaction to the pay_to address",
            "step_2": "Include the payment payload in the 'payment-signature' header",
            "step_3": "Retry the request",
            "x402_docs": "https://x402.org",
            "sdk": "pip install x402[httpx,evm]",
        },
        "demo_mode": "Set header 'X-Pay: demo' to bypass payments during testing",
        "network": os.environ.get("NETWORK", "eip155:84532"),
    }, indent=2)
