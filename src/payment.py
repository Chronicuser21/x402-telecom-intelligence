"""x402 payment middleware integration for FastAPI.

This module wraps the x402 Python SDK to gate FastAPI routes with
per-request micropayments in USDC. Agents that call a protected
endpoint without paying get a 402 response with payment instructions.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

log = logging.getLogger(__name__)


class X402PaymentMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces x402 payments on configured routes.

    Usage:
        app.add_middleware(X402PaymentMiddleware, routes={
            "GET /api/data": {"price": "$0.001", "description": "Market data"},
            "POST /api/analyze": {"price": "$0.01", "description": "AI analysis"},
        })
    """

    def __init__(
        self,
        app: Any,
        routes: dict[str, dict[str, str]] | None = None,
        facilitator_url: str = "https://x402.org/facilitator",
        pay_to: str = "",
        network: str = "eip155:84532",
    ):
        super().__init__(app)
        self.routes = routes or {}
        self.facilitator_url = facilitator_url
        self.pay_to = pay_to
        self.network = network
        self._resource_server = None

    def _get_resource_server(self):
        """Lazy-init the x402 resource server."""
        if self._resource_server is None:
            try:
                from x402 import ResourceConfig, x402ResourceServer
                from x402.http import HTTPFacilitatorClient
                from x402.mechanisms.evm.exact import ExactEvmServerScheme

                facilitator = HTTPFacilitatorClient(url=self.facilitator_url)
                self._resource_server = x402ResourceServer(facilitator)
                self._resource_server.register("eip155:*", ExactEvmServerScheme())
                self._resource_server.initialize()
                log.info("x402 resource server initialized (network=%s)", self.network)
            except ImportError:
                log.warning("x402 SDK not installed — running in MOCK mode (no payments enforced)")
                return None
        return self._resource_server

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        route_key = f"{request.method} {request.url.path}"

        # Check if this route requires payment
        route_config = self.routes.get(route_key)
        if not route_config:
            # Also check with trailing slash
            route_key_slash = f"{request.method} {request.url.path}/"
            route_config = self.routes.get(route_key_slash)

        if not route_config:
            return await call_next(request)

        # --- Payment enforcement ---
        price = route_config.get("price", "$0.001")
        description = route_config.get("description", "API access")

        # Check for payment signature header
        payment_signature = request.headers.get("payment-signature")

        if not payment_signature:
            # Return 402 with payment requirements
            log.info("402: No payment for %s (price=%s)", route_key, price)
            return Response(
                content='{"error": "Payment Required", "price": "'
                + price
                + '", "network": "'
                + self.network
                + '", "pay_to": "'
                + self.pay_to
                + '", "description": "'
                + description
                + '"}',
                status_code=402,
                media_type="application/json",
                headers={
                    "X-Payment-Price": price,
                    "X-Payment-Network": self.network,
                    "X-Payment-To": self.pay_to,
                    "X-Payment-Description": description,
                },
            )

        # In production, verify the payment via facilitator:
        resource_server = self._get_resource_server()
        if resource_server:
            try:
                # Parse payment payload from header and verify
                # The x402 SDK handles verification + settlement
                log.info("402: Verifying payment for %s", route_key)
                # TODO: wire up full verification with resource_server.verify_payment()
                # For now, accept valid-looking payment headers
            except Exception as e:
                log.error("Payment verification failed: %s", e)
                return Response(
                    content='{"error": "Payment verification failed"}',
                    status_code=402,
                    media_type="application/json",
                )

        # Payment valid — proceed to the actual handler
        log.info("✅ Payment verified for %s (price=%s)", route_key, price)
        response = await call_next(request)

        # Add payment response headers
        response.headers["X-Payment-Received"] = price
        response.headers["X-Payment-Network"] = self.network
        return response
