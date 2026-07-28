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
# Force use of specified address for payment recipient (override environment variable)
PAY_TO = "0xCd1219753686FD4f0f2DBEa80896ba2716138F95"  # Force new address
NETWORK = os.getenv("NETWORK", "eip155:8453")  # Base Mainnet
SERVICE_URL = os.getenv("SERVICE_URL", "https://x402-telecom-intelligence.onrender.com")


# ── Build real x402 resource server with CDP auth ──────────
from src.cdp_facilitator import CDPFacilitatorClient

def build_server() -> x402ResourceServer:
    cdp_key = os.getenv("CDP_API_KEY", "")
    cdp_secret = os.getenv("CDP_API_SECRET", "")
    if cdp_key and cdp_secret:
        try:
            facilitator = CDPFacilitatorClient(
                api_key=cdp_key,
                api_secret_b64=cdp_secret,
            )
            print(f"CDP Facilitator initialized successfully")
        except Exception as e:
            print(f"CDP Facilitator failed: {e}")
            from src.mock_facilitator import MockFacilitatorClient
            facilitator = MockFacilitatorClient()
    else:
        print("No CDP keys found, using mock facilitator")
        from src.mock_facilitator import MockFacilitatorClient
        facilitator = MockFacilitatorClient()
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


from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

class DemoBypassMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        is_demo = request.headers.get("x-pay") == "demo" or request.headers.get("x-payment") == "demo"
        
        if is_demo:
            path = request.url.path
            # Demo bypass for paid tools (phone-normalize is free so doesn't need bypass)
            if path in ("/api/v1/tools/sip-decode", "/api/v1/tools/call-diagnose", "/api/v1/tools/phone-info", "/api/v1/tools/fraud-detection", "/api/v1/tools/billing-intelligence"):
                import json
                from fastapi.responses import JSONResponse

                body_bytes = await request.body()
                payload = json.loads(body_bytes) if body_bytes else {}

                if path == "/api/v1/tools/sip-decode":
                    from src.routes.telecom import sip_decode, SipDecodeRequest
                    req_obj = SipDecodeRequest(**payload)
                    res_data = await sip_decode(req_obj)
                    response = JSONResponse(content=res_data)
                elif path == "/api/v1/tools/call-diagnose":
                    from src.routes.telecom import call_diagnose, CallDiagnoseRequest
                    req_obj = CallDiagnoseRequest(**payload)
                    res_data = await call_diagnose(req_obj)
                    response = JSONResponse(content=res_data)
                elif path == "/api/v1/tools/phone-info":
                    from src.routes.telecom import phone_info, PhoneInfoRequest
                    req_obj = PhoneInfoRequest(**payload)
                    res_data = await phone_info(req_obj)
                    response = JSONResponse(content=res_data)
                elif path == "/api/v1/tools/fraud-detection":
                    from src.routes.telecom import fraud_detection, FraudDetectionRequest
                    req_obj = FraudDetectionRequest(**payload)
                    res_data = await fraud_detection(req_obj)
                    response = JSONResponse(content=res_data)
                elif path == "/api/v1/tools/billing-intelligence":
                    from src.routes.telecom import billing_intelligence, BillingIntelligenceRequest
                    req_obj = BillingIntelligenceRequest(**payload)
                    res_data = await billing_intelligence(req_obj)
                    response = JSONResponse(content=res_data)

                if is_demo:
                    response.headers["x-payment-received"] = "demo"
                    response.headers["x-payment-mode"] = "demo"
                return response

        return await call_next(request)

# ── Routes config — typed RouteConfig with Bazaar discovery ──
routes_config: dict[str, RouteConfig] = {
    # phone-normalize is completely free - not included in payment middleware
    "POST /api/v1/tools/sip-decode": RouteConfig(
        accepts=_pay("$0.01"),  # Increased - SIP parsing is advanced telecom intelligence
        resource=f"{SERVICE_URL}/api/v1/tools/sip-decode",
        description="Advanced SIP protocol parsing with telecom domain expertise. Extract headers, methods, URIs, SDP content, and response code classification. Essential for NOC agents analyzing SIP traces and VoIP monitoring systems.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["sip", "telecom", "parser", "advanced"],
        # Temporarily disable Bazaar to test payment processing first
        # extensions=declare_discovery_extension(
        #     input={"type": "http", "method": "POST", "rawSipMessage": "INVITE sip:bob@biloxi.com SIP/2.0..."},
        #     input_schema={
        #         "type": "object",
        #         "properties": {
        #             "type": {"type": "string", "const": "http"},
        #             "method": {"type": "string", "enum": ["POST"]},
        #             "rawSipMessage": {"type": "string", "description": "Raw SIP header string content"}
        #         },
        #         "required": ["type", "method", "rawSipMessage"],
        #     },
        #     body_type="json",
        #     output=OutputConfig(
        #         example={
        #             "status": "success",
        #             "data": {
        #                 "method": "INVITE",
        #                 "headers": {"From": "Alice", "To": "Bob"}
        #             }
        #         }
        #     )
        # )
    ),

    "POST /api/v1/tools/call-diagnose": RouteConfig(
        accepts=_pay("$0.02"),  # Premium - VoIP diagnostics is specialized telecom expertise
        resource=f"{SERVICE_URL}/api/v1/tools/call-diagnose",
        description="Premium VoIP call diagnostics with telecom domain expertise. Analyzes SIP traces, identifies failure patterns, provides root cause hypotheses and specific troubleshooting steps. Essential for NOC automation agents and incident response systems.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["forensics", "voip", "debug", "premium"],
        # Temporarily disable Bazaar to test payment processing first
        # extensions=declare_discovery_extension(
        #     input={"type": "http", "method": "POST", "sipTrace": "INVITE ... \nSIP/2.0 487 Request Terminated"},
        #     input_schema={
        #         "type": "object",
        #         "properties": {
        #             "type": {"type": "string", "const": "http"},
        #             "method": {"type": "string", "enum": ["POST"]},
        #             "sipTrace": {"type": "string", "description": "Sequential SIP trace lines tied to a singular Call-ID"}
        #         },
        #         "required": ["type", "method", "sipTrace"],
        #     },
        #     body_type="json",
        #     output=OutputConfig(
        #         example={
        #             "status": "success",
        #             "data": {
        #                 "hypotheses": ["Normal user hangup sequence encountered"],
        #                 "remediation": "No infrastructure fix required"
        #             }
        #         }
        #     )
        # )
    ),

    "POST /api/v1/tools/phone-info": RouteConfig(
        accepts=_pay("$0.005"),  # Mid-tier - carrier detection is valuable but not premium
        resource=f"{SERVICE_URL}/api/v1/tools/phone-info",
        description="Phone intelligence with carrier detection and line type analysis. Provides carrier type, confidence levels, and regional data. Essential for NOC agents doing call routing analysis and fraud detection.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "phone", "carrier", "intelligence"],
        # Temporarily disable Bazaar to test payment processing first
        # extensions=declare_discovery_extension(
        #     input={"type": "http", "method": "POST", "phone_number": "+14155552671", "region": "US"},
        #     input_schema={
        #         "type": "object",
        #         "properties": {
        #             "type": {"type": "string", "const": "http"},
        #             "method": {"type": "string", "enum": ["POST"]},
        #             "phone_number": {"type": "string", "description": "Raw phone number string"},
        #             "region": {"type": "string", "description": "ISO country code hint (default: US)"}
        #         },
        #         "required": ["type", "method", "phone_number"],
        #     },
        #     body_type="json",
        #     output=OutputConfig(
        #         example={
        #             "status": "success",
        #             "phone_analysis": {
        #                 "e164": "+14155552671",
        #                 "line_type": "MOBILE",
        #                 "carrier": {"name": "Mobile Carrier (US/CA)", "type": "mobile"}
        #             }
        #         }
        #     )
        # )
    ),

    "POST /api/v1/tools/fraud-detection": RouteConfig(
        accepts=_pay("$0.03"),  # Premium Plus - advanced fraud analysis
        resource=f"{SERVICE_URL}/api/v1/tools/fraud-detection",
        description="Advanced fraud detection for call patterns. Detect suspicious call patterns, spikes, misroutes, and anomalies. Essential for NOC agents preventing toll fraud and revenue sharing abuse.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "fraud", "security", "premium-plus"],
        # Temporarily disable Bazaar to test payment processing first
        # extensions=declare_discovery_extension(
        #     input={"type": "http", "method": "POST", "call_patterns": [{"status": "success", "destination": "+1234567890"}]},
        #     input_schema={
        #         "type": "object",
        #         "properties": {
        #             "type": {"type": "string", "const": "http"},
        #             "method": {"type": "string", "enum": ["POST"]},
        #             "call_patterns": {"type": "array", "items": {"type": "object"}, "description": "List of call records for fraud analysis"},
        #             "analysis_window": {"type": "string", "description": "Time window for analysis (default: 1h)"},
        #             "threshold_config": {"type": "object", "description": "Custom fraud detection thresholds"}
        #         },
        #         "required": ["type", "method", "call_patterns"],
        #     },
        #     body_type="json",
        #     output=OutputConfig(
        #         example={
        #             "status": "success",
        #             "fraud_analysis": {
        #                 "risk_level": "low",
        #                 "risk_score": 0,
        #                 "indicators": []
        #             }
        #         }
        #     )
        # )
    ),

    "POST /api/v1/tools/billing-intelligence": RouteConfig(
        accepts=_pay("$0.02"),  # Premium - cost analysis
        resource=f"{SERVICE_URL}/api/v1/tools/billing-intelligence",
        description="Billing intelligence and cost impact analysis. Summarize call outcomes, failed attempts, and cost impacting issues. Essential for NOC agents optimizing telecom costs and identifying revenue loss.",
        mime_type="application/json",
        service_name="Telecom SIP Intelligence",
        tags=["telecom", "billing", "cost-analysis", "premium"],
        # Temporarily disable Bazaar to test payment processing first
        # extensions=declare_discovery_extension(
        #     input={"type": "http", "method": "POST", "call_records": [{"status": "success", "cost": 0.05}]},
        #     input_schema={
        #         "type": "object",
        #         "properties": {
        #             "type": {"type": "string", "const": "http"},
        #             "method": {"type": "string", "enum": ["POST"]},
        #             "call_records": {"type": "array", "items": {"type": "object"}, "description": "Call records with duration, status, and cost"},
        #             "analysis_period": {"type": "string", "description": "Analysis period: daily, weekly, monthly (default: daily)"},
        #             "cost_threshold": {"type": "number", "description": "Cost alert threshold for budget monitoring"}
        #         },
        #         "required": ["type", "method", "call_records"],
        #     },
        #     body_type="json",
        #     output=OutputConfig(
        #         example={
        #             "status": "success",
        #             "billing_analysis": {
        #                 "total_cost": 100.50,
        #                 "success_rate": "95.5%",
        #                 "cost_issues": []
        #             }
        #         }
        #     )
        # )
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    resource_server.initialize()
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

# Landing page (public, no auth required)
@app.get("/")
async def landing_page():
    from fastapi.responses import FileResponse
    return FileResponse("static/landing.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ObservabilityMiddleware)

# Payment middleware (registered last, executed first) - only applies if not free tier
app.add_middleware(
    PaymentMiddlewareASGI,
    server=resource_server,
    routes=routes_config,
)

# Demo bypass middleware (registered first, executed last) - for demo testing
app.add_middleware(DemoBypassMiddleware)


# ── Discovery endpoints ──────────────────────────────────

@app.get("/", response_class=FileResponse, tags=["Discovery"])
async def service_root():
    """Serve the main landing page."""
    landing_path = Path(__file__).parent.parent / "static" / "index.html"
    if landing_path.exists():
        return FileResponse(landing_path, media_type="text/html")
    # Fallback to landing.html if index.html doesn't exist
    landing_path = Path(__file__).parent.parent / "static" / "landing.html"
    if landing_path.exists():
        return FileResponse(landing_path, media_type="text/html")
    # Fallback to simple info if no HTML files exist
    return JSONResponse(content={
        "name": "Telecom SIP Intelligence for AI Agents",
        "description": "Specialized telecom/SIP intelligence tools for AI agents in NOC operations, VoIP monitoring, and telecom automation.",
        "endpoints": {
            "health": "/api/v1/tools/health",
            "catalog": "/api/v1/tools/list-products",
            "phone_normalize": "/api/v1/tools/phone-normalize (FREE)",
            "sip_decode": "/api/v1/tools/sip-decode ($0.01)",
            "call_diagnose": "/api/v1/tools/call-diagnose ($0.02)",
            "phone_info": "/api/v1/tools/phone-info ($0.005)",
            "billing_intelligence": "/api/v1/tools/billing-intelligence ($0.02)",
            "fraud_detection": "/api/v1/tools/fraud-detection ($0.03)"
        },
        "documentation": "/docs",
        "x402_manifest": "/x402.json"
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


@app.get("/", response_class=FileResponse, tags=["Discovery"])
async def landing_page():
    """Serve the main landing page."""
    landing_path = Path(__file__).parent.parent / "static" / "index.html"
    if landing_path.exists():
        return FileResponse(landing_path, media_type="text/html")
    # Fallback to simple info if landing page doesn't exist
    return JSONResponse(content={
        "name": "Telecom SIP Intelligence for AI Agents",
        "description": "Specialized telecom/SIP intelligence tools for AI agents in NOC operations, VoIP monitoring, and telecom automation.",
        "endpoints": {
            "health": "/api/v1/tools/health",
            "catalog": "/api/v1/tools/list-products",
            "phone_normalize": "/api/v1/tools/phone-normalize (FREE)",
            "sip_decode": "/api/v1/tools/sip-decode ($0.01)",
            "call_diagnose": "/api/v1/tools/call-diagnose ($0.02)",
            "phone_info": "/api/v1/tools/phone-info ($0.005)"
        },
        "documentation": "/docs",
        "x402_manifest": "/x402.json"
    })


@app.get("/.well-known/x402", tags=["Discovery"])
async def well_known_x402():
    """x402 discovery path without .json suffix (used by crawlers and agents)."""
    manifest_path = Path(__file__).parent.parent / "x402.json"
    if manifest_path.exists():
        return JSONResponse(content=json.loads(manifest_path.read_text()))
    return JSONResponse(content={"error": "manifest not found"}, status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon to suppress browser 404s."""
    favicon_path = Path(__file__).parent.parent / "static" / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    """Standard robots.txt for crawlers."""
    robots_path = Path(__file__).parent.parent / "static" / "robots.txt"
    if robots_path.exists():
        return FileResponse(robots_path, media_type="text/plain")
    return Response(content="User-agent: *\nAllow: /\n", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    """XML sitemap for search engines."""
    sitemap_path = Path(__file__).parent.parent / "static" / "sitemap.xml"
    if sitemap_path.exists():
        return FileResponse(sitemap_path, media_type="application/xml")
    return Response(status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon."""
    favicon_path = Path(__file__).parent.parent / "static" / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=404)


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
        "description": "SIP decode, phone normalization, and VoIP call diagnostics — paid via x402 USDC micropayments on Base Sepolia.",
        "version": "1.0.0",
        "network": NETWORK,
        "facilitator": "https://x402.org/facilitator",
        "endpoints": endpoints,
    }
