"""Paid analysis endpoints — text analysis, search.

These endpoints process data and return results, gated by x402 payments.
Wire up real AI models (OpenAI, Anthropic, local) in production.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["paid-analysis"])


class AnalyzeRequest(BaseModel):
    text: str
    task: str = "summarize"  # summarize | sentiment | keywords | translate
    language: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


@router.post("/analyze")
async def analyze_text(
    req: AnalyzeRequest,
    agent_id: str = Header("", alias="x-agent-id"),
):
    """Text analysis — costs {price_analysis} USDC per request.

    Supports: summarize, sentiment, keywords, translate.
    In production, call OpenAI/Anthropic/local models.
    """
    start = time.time()

    # Simulated analysis (replace with real LLM calls)
    results = {}

    if req.task == "summarize":
        words = req.text.split()
        results = {
            "summary": " ".join(words[:20]) + "..." if len(words) > 20 else req.text,
            "original_length": len(words),
            "compression_ratio": round(len(words) / max(len(words[:20]), 1), 2),
        }
    elif req.task == "sentiment":
        # Simple keyword-based sentiment (replace with real model)
        positive = sum(1 for w in ["good", "great", "amazing", "love", "excellent", "best"] if w in req.text.lower())
        negative = sum(1 for w in ["bad", "terrible", "hate", "worst", "awful", "poor"] if w in req.text.lower())
        score = (positive - negative) / max(positive + negative, 1)
        results = {
            "sentiment": "positive" if score > 0 else "negative" if score < 0 else "neutral",
            "score": round(score, 3),
            "positive_signals": positive,
            "negative_signals": negative,
        }
    elif req.task == "keywords":
        words = req.text.lower().split()
        # Simple TF-based keyword extraction
        freq = {}
        for w in words:
            w_clean = w.strip(".,!?;:()[]\"'")
            if len(w_clean) > 3:
                freq[w_clean] = freq.get(w_clean, 0) + 1
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
        results = {"keywords": [w for w, _ in top], "scores": {w: s for w, s in top}}
    else:
        results = {"error": f"Unknown task: {req.task}", "available": ["summarize", "sentiment", "keywords"]}

    elapsed = (time.time() - start) * 1000

    return {
        "source": "x402-agent-service (simulated — wire up real LLM)",
        "task": req.task,
        "results": results,
        "latency_ms": round(elapsed, 2),
        "agent": agent_id or "anonymous",
    }


@router.post("/search")
async def semantic_search(
    req: SearchRequest,
    agent_id: str = Header("", alias="x-agent-id"),
):
    """Semantic search — costs {price_search} USDC per request.

    In production, use embeddings + vector DB (Pinecone, ChromaDB, etc.)
    """
    start = time.time()

    # Simulated search results (replace with real embedding search)
    results = [
        {
            "id": hashlib.md5(f"{req.query}_{i}".encode()).hexdigest()[:8],
            "title": f"Result {i+1} for '{req.query}'",
            "snippet": f"This document discusses {req.query} in detail, covering aspects {i+1} through {i+3}.",
            "score": round(1.0 - (i * 0.15), 3),
            "source": f"doc-{i+1}.txt",
        }
        for i in range(min(req.max_results, 10))
    ]

    elapsed = (time.time() - start) * 1000

    return {
        "source": "x402-agent-service (simulated — wire up real embeddings)",
        "query": req.query,
        "count": len(results),
        "results": results,
        "latency_ms": round(elapsed, 2),
    }
