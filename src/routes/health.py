"""Free endpoints — health check, service info, pricing."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import settings

router = APIRouter()


@router.get("/health")
async def health():
    """Health check — no payment required."""
    return {"status": "ok", "service": "x402-agent-service", "version": "0.1.0"}


@router.get("/")
async def root():
    """Service info and available endpoints."""
    return {
        "service": "x402 Agent Service",
        "version": "0.1.0",
        "protocol": "x402 (HTTP 402 Payment Required)",
        "network": settings.network,
        "pricing": {
            "data": settings.price_data,
            "analysis": settings.price_analysis,
            "search": settings.price_search,
        },
        "endpoints": {
            "GET /health": "Free — health check",
            "GET /api/data/market": f"Paid ({settings.price_data}) — market data snapshot",
            "GET /api/data/news": f"Paid ({settings.price_data}) — news headlines",
            "POST /api/analyze": f"Paid ({settings.price_analysis}) — text analysis",
            "POST /api/search": f"Paid ({settings.price_search}) — semantic search",
            "GET /dashboard": "Auth required — observability dashboard",
        },
        "docs": "/docs",
    }
