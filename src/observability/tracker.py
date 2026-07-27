"""Request tracking and cost observability for the x402 agent service.

Tracks every request with agent identity, cost, latency, and status.
This is the "sell the shovels" layer — observability that agents need.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class RequestRecord:
    """A single tracked request."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    method: str = ""
    path: str = ""
    agent_id: str = ""
    agent_wallet: str = ""
    status_code: int = 0
    price: str = "free"
    cost_usdc: float = 0.0
    latency_ms: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class RequestTracker:
    """In-memory + file-backed request tracker.

    Logs every request to a JSONL file for analysis.
    In production, swap for ClickHouse/Postgres.
    """

    def __init__(self, log_dir: str = "./data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._log_file = self.log_dir / f"requests-{self._today}.jsonl"
        self._request_count = 0
        self._total_cost = 0.0

    def _rotate_if_needed(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._today:
            self._today = today
            self._log_file = self.log_dir / f"requests-{self._today}.jsonl"

    def record(self, req: RequestRecord) -> None:
        """Append a request record to the log."""
        self._rotate_if_needed()
        self._request_count += 1
        self._total_cost += req.cost_usdc

        with open(self._log_file, "a") as f:
            f.write(json.dumps(asdict(req), default=str) + "\n")

        log.info(
            "[tracker] %s %s → %d (%.3fms, %s USDC, agent=%s)",
            req.method,
            req.path,
            req.status_code,
            req.latency_ms,
            req.cost_usdc,
            req.agent_id or "anonymous",
        )

    def get_summary(self, hours: int = 24) -> dict[str, Any]:
        """Aggregate stats from today's logs."""
        self._rotate_if_needed()
        records = []
        if self._log_file.exists():
            for line in self._log_file.read_text().splitlines():
                if line.strip():
                    records.append(json.loads(line))

        # Filter to last N hours
        cutoff = time.time() - (hours * 3600)
        recent = []
        for r in records:
            try:
                ts = datetime.fromisoformat(r["timestamp"]).timestamp()
                if ts >= cutoff:
                    recent.append(r)
            except Exception:
                recent.append(r)

        total_cost = sum(r.get("cost_usdc", 0) for r in recent)
        paths = {}
        agents = {}
        for r in recent:
            p = r.get("path", "unknown")
            paths[p] = paths.get(p, 0) + 1
            a = r.get("agent_id") or "anonymous"
            agents[a] = agents.get(a, 0) + 1

        return {
            "period_hours": hours,
            "total_requests": len(recent),
            "total_cost_usdc": round(total_cost, 6),
            "avg_latency_ms": round(
                sum(r.get("latency_ms", 0) for r in recent)
                / max(len(recent), 1),
                1,
            ),
            "top_endpoints": dict(
                sorted(paths.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "top_agents": dict(
                sorted(agents.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }


# Global singleton — import and use from anywhere
tracker = RequestTracker()
