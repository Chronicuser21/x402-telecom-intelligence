"""Observability dashboard — live HTML UI + JSON API."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ..config import settings
from ..observability.tracker import tracker

router = APIRouter(tags=["dashboard"])

# ── Auth helper ────────────────────────────────────────────

def _check_auth(auth: str) -> None:
    if auth != settings.dashboard_secret:
        raise HTTPException(status_code=401, detail="Invalid dashboard secret. Pass x-dashboard-secret header.")


# ── Live HTML UI ───────────────────────────────────────────

@router.get("/dashboard/ui", response_class=HTMLResponse)
async def dashboard_ui(
    request: Request,
    secret: str = Query("", description="Dashboard secret (can pass in URL for browser access)"),
):
    """Live dashboard UI — auto-refreshes every 5 seconds."""
    # Accept secret via query param for browser convenience
    auth = secret or request.headers.get("x-dashboard-secret", "")
    _check_auth(auth)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>x402 Agent Service — Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
      background: #0d1117;
      color: #e6edf3;
      min-height: 100vh;
      padding: 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 28px;
      border-bottom: 1px solid #21262d;
      padding-bottom: 16px;
    }}
    h1 {{ font-size: 1.4rem; font-weight: 600; color: #58a6ff; }}
    .subtitle {{ font-size: 0.8rem; color: #8b949e; margin-top: 2px; }}
    .badge {{
      font-size: 0.72rem;
      padding: 3px 10px;
      border-radius: 20px;
      background: #1f6feb33;
      border: 1px solid #1f6feb;
      color: #58a6ff;
    }}
    .live-dot {{
      display: inline-block;
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #3fb950;
      margin-right: 6px;
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.3; }}
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .card {{
      background: #161b22;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 20px;
    }}
    .card-label {{
      font-size: 0.75rem;
      color: #8b949e;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
    }}
    .card-value {{
      font-size: 2rem;
      font-weight: 700;
      color: #e6edf3;
      line-height: 1;
    }}
    .card-value.green {{ color: #3fb950; }}
    .card-value.blue  {{ color: #58a6ff; }}
    .card-value.yellow {{ color: #d29922; }}
    .card-sub {{
      font-size: 0.75rem;
      color: #8b949e;
      margin-top: 6px;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}
    @media (max-width: 700px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    .table-card {{
      background: #161b22;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 20px;
    }}
    .table-card h2 {{
      font-size: 0.85rem;
      font-weight: 600;
      color: #8b949e;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 14px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; color: #8b949e; font-weight: 500; padding: 6px 0; border-bottom: 1px solid #21262d; }}
    td {{ padding: 8px 0; border-bottom: 1px solid #21262d22; color: #e6edf3; }}
    tr:last-child td {{ border-bottom: none; }}
    .bar {{
      height: 6px;
      background: #1f6feb;
      border-radius: 3px;
      min-width: 4px;
      transition: width 0.4s ease;
    }}
    .status-ok   {{ color: #3fb950; }}
    .status-paid {{ color: #58a6ff; }}
    .status-err  {{ color: #f85149; }}
    .recent-card {{
      background: #161b22;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .recent-card h2 {{
      font-size: 0.85rem;
      font-weight: 600;
      color: #8b949e;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 14px;
    }}
    .req-row {{
      display: flex;
      gap: 12px;
      font-size: 0.78rem;
      padding: 6px 0;
      border-bottom: 1px solid #21262d22;
      align-items: center;
    }}
    .req-row:last-child {{ border-bottom: none; }}
    .req-method {{
      font-weight: 700;
      min-width: 40px;
      color: #d29922;
    }}
    .req-path {{ color: #58a6ff; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .req-status {{ min-width: 36px; text-align: right; font-weight: 600; }}
    .req-agent  {{ color: #8b949e; min-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .req-ms     {{ color: #8b949e; min-width: 60px; text-align: right; }}
    .req-cost   {{ color: #3fb950; min-width: 70px; text-align: right; }}
    footer {{
      text-align: center;
      font-size: 0.72rem;
      color: #8b949e;
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #21262d;
    }}
    #last-updated {{ font-size: 0.72rem; color: #8b949e; }}
    .error-msg {{ color: #f85149; font-size: 0.8rem; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>⚡ x402 Agent Service</h1>
      <div class="subtitle">Revenue &amp; observability dashboard</div>
    </div>
    <div>
      <span class="badge"><span class="live-dot"></span>LIVE</span>
      <div id="last-updated" style="margin-top:6px;text-align:right"></div>
    </div>
  </header>

  <!-- KPI cards -->
  <div class="grid" id="kpi-grid">
    <div class="card"><div class="card-label">Total Requests</div><div class="card-value blue" id="kpi-requests">—</div><div class="card-sub" id="kpi-period">Last 24h</div></div>
    <div class="card"><div class="card-label">Revenue (USDC)</div><div class="card-value green" id="kpi-revenue">—</div><div class="card-sub" id="kpi-avg">avg per request</div></div>
    <div class="card"><div class="card-label">Avg Latency</div><div class="card-value yellow" id="kpi-latency">—</div><div class="card-sub">milliseconds</div></div>
    <div class="card"><div class="card-label">Unique Agents</div><div class="card-value blue" id="kpi-agents">—</div><div class="card-sub">paying clients</div></div>
  </div>

  <!-- Recent requests -->
  <div class="recent-card">
    <h2>Recent Requests</h2>
    <div id="recent-list"><div style="color:#8b949e;font-size:0.8rem">Loading...</div></div>
  </div>

  <!-- Endpoints + Agents tables -->
  <div class="two-col">
    <div class="table-card">
      <h2>Top Endpoints</h2>
      <table><thead><tr><th>Path</th><th>Hits</th><th style="width:80px">Bar</th></tr></thead>
      <tbody id="endpoints-body"><tr><td colspan="3" style="color:#8b949e">Loading...</td></tr></tbody></table>
    </div>
    <div class="table-card">
      <h2>Top Agents</h2>
      <table><thead><tr><th>Agent ID</th><th>Requests</th><th style="width:80px">Bar</th></tr></thead>
      <tbody id="agents-body"><tr><td colspan="3" style="color:#8b949e">Loading...</td></tr></tbody></table>
    </div>
  </div>

  <footer>
    x402 Agent Service &bull; Base Sepolia &bull; Payments to 0x4EA0…d5b8 &bull;
    <a href="/docs" style="color:#58a6ff">API docs</a>
  </footer>

<script>
  const SECRET = {repr(secret or "")};

  function dataUrl(path) {{
    const sep = path.includes('?') ? '&' : '?';
    return SECRET ? path + sep + 'secret=' + encodeURIComponent(SECRET) : path;
  }}

  function statusClass(code) {{
    if (code >= 500) return 'status-err';
    if (code === 402) return 'status-paid';
    if (code >= 400) return 'status-err';
    return 'status-ok';
  }}

  function barHtml(val, max) {{
    const pct = max > 0 ? Math.round((val / max) * 100) : 0;
    return `<div class="bar" style="width:${{pct}}%"></div>`;
  }}

  async function refresh() {{
    try {{
      const [summary, recent] = await Promise.all([
        fetch(dataUrl('/dashboard/data')).then(r => r.json()),
        fetch(dataUrl('/dashboard/data/recent')).then(r => r.json()),
      ]);

      // KPIs
      document.getElementById('kpi-requests').textContent = summary.total_requests.toLocaleString();
      document.getElementById('kpi-revenue').textContent  = '$' + summary.total_cost_usdc.toFixed(6);
      document.getElementById('kpi-latency').textContent  = summary.avg_latency_ms.toFixed(1) + 'ms';
      document.getElementById('kpi-agents').textContent   = Object.keys(summary.top_agents).length;
      document.getElementById('kpi-period').textContent   = 'Last ' + summary.period_hours + 'h';
      const avgPer = summary.total_requests > 0
        ? (summary.total_cost_usdc / summary.total_requests).toFixed(6) : '0.000000';
      document.getElementById('kpi-avg').textContent = '$' + avgPer + ' avg/request';

      // Endpoints table
      const eps = summary.top_endpoints;
      const maxEp = Math.max(...Object.values(eps), 1);
      document.getElementById('endpoints-body').innerHTML =
        Object.entries(eps).map(([path, count]) =>
          `<tr><td style="font-family:monospace;color:#58a6ff">${{path}}</td><td>${{count}}</td><td>${{barHtml(count, maxEp)}}</td></tr>`
        ).join('') || '<tr><td colspan="3" style="color:#8b949e">No data</td></tr>';

      // Agents table
      const ags = summary.top_agents;
      const maxAg = Math.max(...Object.values(ags), 1);
      document.getElementById('agents-body').innerHTML =
        Object.entries(ags).map(([agent, count]) =>
          `<tr><td style="color:#e6edf3;max-width:200px;overflow:hidden;text-overflow:ellipsis">${{agent}}</td><td>${{count}}</td><td>${{barHtml(count, maxAg)}}</td></tr>`
        ).join('') || '<tr><td colspan="3" style="color:#8b949e">No agents yet</td></tr>';

      // Recent requests
      const rows = recent.requests || [];
      document.getElementById('recent-list').innerHTML = rows.length === 0
        ? '<div style="color:#8b949e;font-size:0.8rem">No requests yet</div>'
        : rows.map(r => `
          <div class="req-row">
            <span class="req-method">${{r.method}}</span>
            <span class="req-path">${{r.path}}</span>
            <span class="req-status ${{statusClass(r.status_code)}}">${{r.status_code}}</span>
            <span class="req-agent">${{r.agent_id || 'anon'}}</span>
            <span class="req-ms">${{r.latency_ms}}ms</span>
            <span class="req-cost">${{r.cost_usdc > 0 ? '$' + r.cost_usdc.toFixed(6) : '—'}}</span>
          </div>`).join('');

      document.getElementById('last-updated').textContent =
        'Updated ' + new Date().toLocaleTimeString();
    }} catch(e) {{
      document.getElementById('last-updated').innerHTML =
        '<span class="error-msg">Fetch error: ' + e.message + '</span>';
    }}
  }}

  refresh();
  setInterval(refresh, 5000);
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ── Data API (polled by the UI) ────────────────────────────

@router.get("/dashboard/data")
async def dashboard_data(
    hours: int = 24,
    request: Request = None,
    secret: str = Query("", description="Dashboard secret"),
):
    """Polling endpoint for the live UI — returns summary JSON."""
    auth = secret or (request.headers.get("x-dashboard-secret", "") if request else "")
    _check_auth(auth)
    return tracker.get_summary(hours=hours)


@router.get("/dashboard/data/recent")
async def dashboard_recent(
    limit: int = 30,
    request: Request = None,
    secret: str = Query("", description="Dashboard secret"),
):
    """Last N requests for the live UI feed."""
    auth = secret or (request.headers.get("x-dashboard-secret", "") if request else "")
    _check_auth(auth)

    from ..observability.tracker import tracker as t
    import json
    from pathlib import Path

    t._rotate_if_needed()
    records = []
    if t._log_file.exists():
        lines = t._log_file.read_text().splitlines()
        for line in reversed(lines[-200:]):  # scan last 200 lines
            if line.strip():
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
            if len(records) >= limit:
                break

    return {"requests": records[:limit]}


# ── JSON API endpoints (original, kept for backwards compat) ──

@router.get("/dashboard")
async def dashboard(
    hours: int = 24,
    auth: str = Header("", alias="x-dashboard-secret"),
):
    """JSON summary — use /dashboard/ui for the live visual dashboard."""
    _check_auth(auth)
    summary = tracker.get_summary(hours=hours)
    return {
        "dashboard": "x402 Agent Service — Observability",
        "ui": "/dashboard/ui",
        "period": f"Last {hours} hours",
        **summary,
        "revenue": {
            "total_usdc": summary["total_cost_usdc"],
            "avg_per_request": round(
                summary["total_cost_usdc"] / max(summary["total_requests"], 1), 6
            ),
        },
    }


@router.get("/dashboard/agents")
async def agent_breakdown(
    hours: int = 24,
    auth: str = Header("", alias="x-dashboard-secret"),
):
    """Per-agent breakdown."""
    _check_auth(auth)
    summary = tracker.get_summary(hours=hours)
    return {
        "period": f"Last {hours} hours",
        "agents": summary.get("top_agents", {}),
        "total_agents": len(summary.get("top_agents", {})),
        "total_requests": summary["total_requests"],
    }


@router.get("/dashboard/endpoints")
async def endpoint_breakdown(
    hours: int = 24,
    auth: str = Header("", alias="x-dashboard-secret"),
):
    """Per-endpoint breakdown."""
    _check_auth(auth)
    summary = tracker.get_summary(hours=hours)
    return {
        "period": f"Last {hours} hours",
        "endpoints": summary.get("top_endpoints", {}),
        "total_cost_usdc": summary["total_cost_usdc"],
    }
