"""
X402 Agent Service — Real x402 SDK Integration
Telecom Intelligence & Forensics Gateway.
Sells SIP decode, phone analysis, and VoIP diagnostics via USDC micropayments on Base Sepolia.
Registered in the x402 Bazaar for agent auto-discovery.
"""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

load_dotenv()

# ── x402 SDK Imports ──────────────────────────────────────
from x402 import x402ResourceServer
from x402.extensions.bazaar import OutputConfig, declare_discovery_extension
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig

# ── Local imports ──────────────────────────────────────────
from src.config import settings
from src.observability.middleware import ObservabilityMiddleware
from src.routes.telecom import router as telecom_router

# ── Payment recipient ──────────────────────────────────────
import os

PAY_TO = os.getenv("PAY_TO_ADDRESS", "0xD333941784201caC6C3c082D9BEef22EFefe4750")
NETWORK = os.getenv("NETWORK", "eip155:8453")  # Base Mainnet
SERVICE_URL = os.getenv("SERVICE_URL", "https://x402-telecom-intelligence.onrender.com")

# ── CDP facilitator constants (Base Mainnet) ───────────────
# https://docs.cdp.coinbase.com/x402/quickstart-for-sellers#facilitator-urls
_CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"
_CDP_HOST = "api.cdp.coinbase.com"
_CDP_BASE_PATH = "/platform/v2/x402"

# ── Build real x402 resource server with CDP facilitator ──────────
from x402.http import HTTPFacilitatorClient, FacilitatorConfig, CreateHeadersAuthProvider
from cdp.x402.x402 import create_cdp_auth_headers, create_cdp_unauth_headers


def build_server() -> x402ResourceServer:
    key_id = os.getenv("CDP_API_KEY_ID") or os.getenv("CDP_API_KEY")
    key_secret = os.getenv("CDP_API_KEY_SECRET") or os.getenv("CDP_API_SECRET")

    if key_id and key_secret:
        create_headers = create_cdp_auth_headers(key_id, key_secret)
        print(f"CDP Facilitator ready — Base Mainnet ({_CDP_FACILITATOR_URL})")
    else:
        create_headers = create_cdp_unauth_headers()
        print("WARNING: No CDP API keys — using unauthenticated facilitator")

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(
            url=_CDP_FACILITATOR_URL,
            auth_provider=CreateHeadersAuthProvider(create_headers),
        )
    )

    server = x402ResourceServer(facilitator_clients=[facilitator])
    from x402.mechanisms.evm.exact import register_exact_evm_server
    register_exact_evm_server(server, networks=[NETWORK])
    return server


resource_server = build_server()


def _pay(price: str) -> PaymentOption:
    """Shorthand for a standard USDC payment option on Base Sepolia."""
    return PaymentOption(
        scheme="exact",
        pay_to=PAY_TO,
        price=price,
        network=NETWORK,
    )


# ── Routes config — typed RouteConfig with Bazaar discovery ──
routes_config: dict[str, RouteConfig] = {
    # phone-normalize is completely free - not included in payment middleware
    "POST /api/v1/tools/sip-decode": RouteConfig(
        accepts=_pay("$0.01"),  # Increased - SIP parsing is advanced telecom intelligence
        resource="https://x402-telecom-intelligence.onrender.com/api/v1/tools/sip-decode",
        description="Advanced SIP protocol parsing with telecom domain expertise. Extract headers, methods, URIs, SDP content, and response code classification. Essential for NOC agents analyzing SIP traces and VoIP monitoring systems.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["sip", "telecom", "parser", "advanced"],
        extensions=declare_discovery_extension(
            input={"rawSipMessage": "INVITE sip:bob@biloxi.com SIP/2.0\r\nVia: SIP/2.0/UDP pc33.atlanta.com\r\nFrom: Alice"},
            input_schema={
                "type": "object",
                "properties": {
                    "rawSipMessage": {"type": "string", "description": "Raw SIP message string"}
                },
                "required": ["rawSipMessage"],
            },
            body_type="json",
            output=OutputConfig(
                example={"status": "success", "data": {"method": "INVITE", "headers": {"From": "Alice", "To": "Bob"}}}
            )
        )
    ),

    "POST /api/v1/tools/call-diagnose": RouteConfig(
        accepts=_pay("$0.02"),  # Premium - VoIP diagnostics is specialized telecom expertise
        resource="https://x402-telecom-intelligence.onrender.com/api/v1/tools/call-diagnose",
        description="Premium VoIP call diagnostics with telecom domain expertise. Analyzes SIP traces, identifies failure patterns, provides root cause hypotheses and specific troubleshooting steps. Essential for NOC automation agents and incident response systems.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["forensics", "voip", "debug", "premium"],
        extensions=declare_discovery_extension(
            input={"sipTrace": "INVITE sip:alice@atlanta.com SIP/2.0\nSIP/2.0 487 Request Terminated"},
            input_schema={
                "type": "object",
                "properties": {
                    "sipTrace": {"type": "string", "description": "Sequential SIP trace lines for a single Call-ID"}
                },
                "required": ["sipTrace"],
            },
            body_type="json",
            output=OutputConfig(
                example={"status": "success", "data": {"hypotheses": ["Normal user hangup"], "remediation": "No fix required"}}
            )
        )
    ),

    "POST /api/v1/tools/phone-info": RouteConfig(
        accepts=_pay("$0.005"),  # Mid-tier - carrier detection is valuable but not premium
        resource="https://x402-telecom-intelligence.onrender.com/api/v1/tools/phone-info",
        description="Phone intelligence with carrier detection and line type analysis. Provides carrier type, confidence levels, and regional data. Essential for NOC agents doing call routing analysis and fraud detection.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "phone", "carrier", "intelligence"],
        extensions=declare_discovery_extension(
            input={"phone_number": "+14155552671", "region": "US"},
            input_schema={
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Phone number to look up"},
                    "region": {"type": "string", "description": "ISO country code hint (default: US)"}
                },
                "required": ["phone_number"],
            },
            body_type="json",
            output=OutputConfig(
                example={"status": "success", "phone_analysis": {"e164": "+14155552671", "line_type": "MOBILE", "carrier": {"name": "Mobile Carrier (US/CA)", "type": "mobile"}}}
            )
        )
    ),

    "POST /api/v1/tools/fraud-detection": RouteConfig(
        accepts=_pay("$0.03"),
        resource="https://x402-telecom-intelligence.onrender.com/api/v1/tools/fraud-detection",
        description="Advanced fraud detection for call patterns. Detect suspicious call patterns, spikes, misroutes, and anomalies. Essential for NOC agents preventing toll fraud and revenue sharing abuse.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "fraud", "security", "premium-plus"],
        extensions=declare_discovery_extension(
            input={"call_patterns": [{"status": "success", "destination": "+1234567890", "duration_s": 60}]},
            input_schema={
                "type": "object",
                "properties": {
                    "call_patterns": {"type": "array", "items": {"type": "object"}, "description": "List of call records for fraud analysis"},
                    "analysis_window": {"type": "string", "description": "Time window for analysis (default: 1h)"},
                    "threshold_config": {"type": "object", "description": "Custom fraud detection thresholds"},
                },
                "required": ["call_patterns"],
            },
            body_type="json",
            output=OutputConfig(
                example={"status": "success", "fraud_analysis": {"risk_level": "low", "risk_score": 0, "indicators": []}}
            )
        )
    ),

    "POST /api/v1/tools/billing-intelligence": RouteConfig(
        accepts=_pay("$0.02"),
        resource="https://x402-telecom-intelligence.onrender.com/api/v1/tools/billing-intelligence",
        description="Billing intelligence and cost impact analysis. Summarize call outcomes, failed attempts, and cost impacting issues. Essential for NOC agents optimizing telecom costs and identifying revenue loss.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "billing", "cost-analysis", "premium"],
        extensions=declare_discovery_extension(
            input={"call_records": [{"status": "success", "cost": 0.05, "duration_s": 120}]},
            input_schema={
                "type": "object",
                "properties": {
                    "call_records": {"type": "array", "items": {"type": "object"}, "description": "Call records with duration, status, and cost"},
                    "analysis_period": {"type": "string", "description": "Analysis period: daily, weekly, monthly (default: daily)"},
                    "cost_threshold": {"type": "number", "description": "Cost alert threshold for budget monitoring"},
                },
                "required": ["call_records"],
            },
            body_type="json",
            output=OutputConfig(
                example={"status": "success", "billing_analysis": {"total_cost": 100.50, "success_rate": "95.5%", "cost_issues": []}}
            )
        )
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio, concurrent.futures
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, resource_server.initialize),
            timeout=10.0
        )
    except Exception as e:
        print(f"WARNING: initialize() failed ({e}), continuing anyway")
    yield


app = FastAPI(
    title="Telecom Intelligence x402 Server",
    version="1.0.0",
    lifespan=lifespan,
)

# 💡 CRITICAL: Mount routers FIRST before adding processing middleware layers
app.include_router(telecom_router)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ObservabilityMiddleware)

# Payment middleware — enforces x402 on all routes_config entries
app.add_middleware(
    PaymentMiddlewareASGI,
    server=resource_server,
    routes=routes_config,
)


# ── Discovery endpoints ──────────────────────────────────

@app.get("/", response_class=FileResponse, tags=["Discovery"])
async def service_root():
    """Serve the main landing page."""
    for name in ("index.html", "landing.html"):
        p = Path(__file__).parent.parent / "static" / name
        if p.exists():
            return FileResponse(p, media_type="text/html")
    return JSONResponse(content={
        "name": "Telecom SIP Intelligence for AI Agents",
        "endpoints": {
            "health": "/api/v1/tools/health",
            "catalog": "/api/v1/tools/list-products",
            "phone_normalize": "/api/v1/tools/phone-normalize (FREE)",
            "sip_decode": "/api/v1/tools/sip-decode ($0.01)",
            "call_diagnose": "/api/v1/tools/call-diagnose ($0.02)",
            "phone_info": "/api/v1/tools/phone-info ($0.005)",
            "billing_intelligence": "/api/v1/tools/billing-intelligence ($0.02)",
            "fraud_detection": "/api/v1/tools/fraud-detection ($0.03)",
        },
        "documentation": "/docs",
        "x402_manifest": "/x402.json",
    })


@app.get("/x402.json", tags=["Discovery"])
async def serve_manifest():
    """Serve the x402 manifest (standard discovery path)."""
    manifest_path = Path(__file__).parent.parent / "x402.json"
    if manifest_path.exists():
        return JSONResponse(content=json.loads(manifest_path.read_text()))
    return JSONResponse(content={"error": "manifest not found"}, status_code=404)


@app.get("/.well-known/x402.json", tags=["Discovery"])
async def well_known_manifest():
    """Standard well-known path for x402 agent discovery."""
    manifest_path = Path(__file__).parent.parent / "x402.json"
    if manifest_path.exists():
        return JSONResponse(content=json.loads(manifest_path.read_text()))
    return JSONResponse(content={"error": "manifest not found"}, status_code=404)


@app.get("/.well-known/x402", tags=["Discovery"])
async def well_known_x402():
    """x402 discovery path without .json suffix (used by crawlers and agents)."""
    manifest_path = Path(__file__).parent.parent / "x402.json"
    if manifest_path.exists():
        return JSONResponse(content=json.loads(manifest_path.read_text()))
    return JSONResponse(content={"error": "manifest not found"}, status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon."""
    for name, mime in (("favicon.ico", "image/x-icon"), ("favicon.svg", "image/svg+xml")):
        p = Path(__file__).parent.parent / "static" / name
        if p.exists():
            return FileResponse(p, media_type=mime)
    return Response(status_code=204)


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    """LLM-readable service description for AI agent discovery."""
    llms_path = Path(__file__).parent.parent / "static" / "llms.txt"
    if llms_path.exists():
        return FileResponse(llms_path, media_type="text/plain")
    return Response(status_code=404)


@app.get("/docs", response_class=FileResponse, tags=["Discovery"])
async def documentation():
    """Serve the comprehensive API documentation."""
    docs_path = Path(__file__).parent.parent / "static" / "docs.html"
    return FileResponse(docs_path, media_type="text/html")


@app.get("/api/v1/services", tags=["Discovery"])
async def list_services():
    """Human-readable list of all available paid services with prices."""
    endpoints = []
    for ep_key, rc in routes_config.items():
        parts = ep_key.split(" ", 1)
        method = parts[0] if len(parts) > 1 else "GET"
        path = parts[1] if len(parts) > 1 else parts[0]
        endpoints.append({
            "method": method,
            "path": path,
            "description": rc.description,
            "price": rc.accepts[0].price if isinstance(rc.accepts, list) else (rc.accepts.price if rc.accepts else "free"),
            "network": NETWORK,
            "asset": "USDC",
            "payTo": PAY_TO,
        })
    return {
        "name": "Telecom Intelligence Forensics Gateway",
        "description": "SIP decode, phone normalization, and VoIP call diagnostics — paid via x402 USDC micropayments on Base Mainnet.",
        "version": "1.0.0",
        "network": NETWORK,
        "facilitator": _CDP_FACILITATOR_URL,
        "endpoints": endpoints,
    }
