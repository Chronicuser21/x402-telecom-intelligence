"""Paid data endpoints — REAL market data from CoinGecko, real news headlines.

These endpoints return live data gated by x402 payments.
CoinGecko free API: no key needed, rate-limited to 10-30 req/min.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, Query

router = APIRouter(prefix="/api/data", tags=["data"])

# CoinGecko free API (no key needed)
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_coingecko = httpx.AsyncClient(timeout=10.0, headers={"accept": "application/json"})

# Symbol → CoinGecko ID mapping
SYMBOL_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "DOGE": "dogecoin", "ADA": "cardano", "XRP": "ripple",
    "DOT": "polkadot", "AVAX": "avalanche-2", "MATIC": "matic-network",
    "LINK": "chainlink", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "NEAR": "near", "ARB": "arbitrum",
    "OP": "optimism", "SUI": "sui", "APT": "aptos",
    "USDC": "usd-coin", "USDT": "tether", "DAI": "dai",
}

# Coin → symbol for display
COIN_SYMBOLS = {v: k for k, v in SYMBOL_MAP.items()}


@router.get("/market")
async def market_data(
    symbols: str = Query("BTC,ETH,SOL", description="Comma-separated symbols"),
    agent_id: str = Header("", alias="x-agent-id"),
):
    """Real-time market data from CoinGecko.

    Returns price, 24h change, volume, and market cap for each symbol.
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    coin_ids = [SYMBOL_MAP.get(s, s.lower()) for s in symbol_list]

    try:
        resp = await _coingecko.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": ",".join(coin_ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        # Fallback to simulated data if CoinGecko is rate-limited
        return {
            "source": "simulated (CoinGecko rate-limited)",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols": symbol_list,
            "data": {
                s: {"price_usd": 0, "change_24h_pct": 0, "volume_24h": 0, "market_cap": 0}
                for s in symbol_list
            },
        }

    data = {}
    for symbol in symbol_list:
        coin_id = SYMBOL_MAP.get(symbol, symbol.lower())
        if coin_id in raw:
            d = raw[coin_id]
            data[symbol] = {
                "price_usd": d.get("usd", 0),
                "change_24h_pct": round(d.get("usd_24h_change", 0), 2),
                "volume_24h": d.get("usd_24h_vol", 0),
                "market_cap": d.get("usd_market_cap", 0),
            }

    return {
        "source": "coingecko",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols": symbol_list,
        "data": data,
        "_agent": agent_id or "anonymous",
        "_x402_notice": "This data was served behind an x402 payment gate",
    }


@router.get("/news")
async def news_headlines(
    topic: str = Query("AI", description="News topic"),
    limit: int = Query(5, ge=1, le=20),
    agent_id: str = Header("", alias="x-agent-id"),
):
    """News headlines via web search.

    In production, wire up NewsAPI, GNews, or web scraping via Firecrawl.
    Returns top headlines for the given topic.
    """
    # Real: use a free news API or web search
    # For now, we use structured data that agents actually find useful
    try:
        # Try Hacker News API for real tech/AI news
        resp = await httpx.AsyncClient(timeout=5.0).get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": topic,
                "tags": "story",
                "hitsPerPage": limit,
                "numericFilters": "created_at_i>" + str(int(time.time()) - 86400 * 7),
            },
        )
        resp.raise_for_status()
        hn_data = resp.json()

        headlines = []
        for hit in hn_data.get("hits", [])[:limit]:
            headlines.append({
                "title": hit.get("title", ""),
                "source": "Hacker News",
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "points": hit.get("points", 0),
                "comments": hit.get("num_comments", 0),
                "published": hit.get("created_at", ""),
            })

        if not headlines:
            raise ValueError("No HN results")

        return {
            "source": "hackernews",
            "topic": topic,
            "count": len(headlines),
            "headlines": headlines,
            "_agent": agent_id or "anonymous",
        }

    except Exception as e:
        # Fallback: curated headlines
        return {
            "source": "curated (fallback)",
            "topic": topic,
            "count": min(limit, 3),
            "headlines": [
                {
                    "title": f"Latest developments in {topic}",
                    "source": "curated",
                    "url": f"https://news.ycombinator.com/",
                    "published": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "note": f"Live fetch failed: {e}",
            "_agent": agent_id or "anonymous",
        }
