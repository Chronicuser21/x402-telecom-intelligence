"""FastAPI middleware for automatic request tracking / observability."""
from __future__ import annotations

import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .tracker import RequestRecord, tracker

# USDC has 6 decimal places — 1_000_000 atomic units = $1.00
_USDC_DECIMALS = 1_000_000


def _parse_payment_response(header_value: str) -> float:
    """Decode the x402 PAYMENT-RESPONSE header and return the amount in USDC dollars."""
    if not header_value:
        return 0.0
    try:
        from x402.http.utils import decode_payment_response_header
        decoded = decode_payment_response_header(header_value)
        if decoded and decoded.success and decoded.amount:
            return int(decoded.amount) / _USDC_DECIMALS
    except Exception:
        pass
    return 0.0


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Records every request to the tracker with timing, agent identity, and cost."""

    def __init__(self, app: Any):
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()
        status_code = 500
        error = ""
        response: Response | None = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            elapsed = (time.monotonic() - start) * 1000

            agent_id = request.headers.get("x-agent-id", "")
            agent_wallet = request.headers.get("x-agent-wallet", "")

            # Read cost from the x402 settlement header (base64-encoded JSON)
            cost = 0.0
            price = "free"
            if response is not None:
                payment_resp = response.headers.get("PAYMENT-RESPONSE", "")
                if payment_resp:
                    cost = _parse_payment_response(payment_resp)
                    price = f"${cost:.6f}" if cost > 0 else "paid"
                elif status_code == 402:
                    price = "unpaid"

            record = RequestRecord(
                method=request.method,
                path=str(request.url.path),
                agent_id=agent_id,
                agent_wallet=agent_wallet,
                status_code=status_code,
                price=price,
                cost_usdc=cost,
                latency_ms=round(elapsed, 2),
                error=error,
                metadata={
                    "query": str(request.query_params),
                    "user_agent": request.headers.get("user-agent", ""),
                },
            )
            tracker.record(record)

        return response
