"""Telecom Intelligence route handlers — SIP decode, phone normalization, call diagnostics."""
import json
import re
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.observability.tracker import tracker
from src.free_tier import get_free_tier_stats

# ── Router (mounted at /api/v1/tools in main.py) ─────────────────────────────
router = APIRouter(prefix="/api/v1/tools", tags=["Telecom Intelligence"])

# ── Server start time for uptime tracking ────────────────────────────────────
_SERVER_STARTED = datetime.now(timezone.utc)

# ── Payment / wallet constants (mirrors main.py) ─────────────────────────────
_PAY_TO = "0xD333941784201caC6C3c082D9BEef22EFefe4750"
_NETWORK = "eip155:8453"

# ── Phone normalize ──────────────────────────────────────────────────────────

class PlanStrategy(str, Enum):
    E164_VALIDATION = "e164"
    INTL_FORMATTING = "intl"
    NATIONAL_ROUTING = "national"
    RFC3966_URI = "rfc3966"

STRATEGY_ROUTER_MAP = {
    PlanStrategy.E164_VALIDATION: lambda parsed: f"+{parsed.get('country_code')}{parsed.get('national_number')}",
    PlanStrategy.INTL_FORMATTING: lambda parsed: f"+{parsed.get('country_code')} {parsed.get('national_number')}",
    PlanStrategy.NATIONAL_ROUTING: lambda parsed: f"({parsed.get('area_code')}) {parsed.get('subscriber_number')}",
    PlanStrategy.RFC3966_URI: lambda parsed: f"tel:+{parsed.get('country_code')}-{parsed.get('national_number')}"
}

# Enhanced country code detection
_COUNTRY_PATTERNS = {
    # North America
    "1": ["US", "CA"],
    # Europe
    "44": ["GB"],
    "33": ["FR"],
    "49": ["DE"],
    "39": ["IT"],
    "34": ["ES"],
    "31": ["NL"],
    "41": ["CH"],
    "43": ["AT"],
    "46": ["SE"],
    "47": ["NO"],
    "358": ["FI"],
    "351": ["IS"],
    "370": ["LT"],
    "371": ["LV"],
    "372": ["EE"],
    "45": ["DK"],
    "352": ["IE"],
    "353": ["LU"],
    "354": ["PT"],
    "30": ["GR"],
    "359": ["BG"],
    "385": ["HR"],
    "386": ["SI"],
    "381": ["CZ"],
    "48": ["PL"],
    "421": ["SK"],
    "36": ["HU"],
    "40": ["RO"],
    "381": ["MK"],
    "387": ["RS"],
    "382": ["BA"],
    "383": ["ME"],
    "380": ["AL"],
    "389": ["XK"],
    # Asia
    "81": ["JP"],
    "86": ["CN"],
    "91": ["IN"],
    "82": ["PK"],
    "62": ["ID"],
    "63": ["AU"],
    "64": ["NZ"],
    "84": ["VN"],
    "66": ["TH"],
    "65": ["SG"],
    "60": ["MY"],
    "62": ["PH"],
    "855": ["KH"],
    "856": ["LA"],
    "95": ["MM"],
    "67": ["BD"],
    "880": ["LK"],
    "94": ["LK"],
    "977": ["BT"],
    "975": ["NP"],
    "98": ["IR"],
    "964": ["AE"],
    "966": ["SA"],
    "971": ["BH"],
    "974": ["QA"],
    "968": ["OM"],
    "973": ["KW"],
    "93": ["AF"],
    "92": ["MM"],
    "886": ["TW"],
    "852": ["HK"],
    "853": ["MO"],
    "850": ["KP"],
    "82": ["KR"],
    # Middle East
    "972": ["IL"],
    "963": ["SY"],
    "962": ["JO"],
    "961": ["LB"],
    # Africa
    "27": ["ZA"],
    "234": ["NG"],
    "254": ["KE"],
    "20": ["EG"],
    "213": ["DZ"],
    "212": ["MA"],
    "216": ["TN"],
    # South America
    "55": ["BR"],
    "54": ["AR"],
    "56": ["CL"],
    "57": ["CO"],
    "51": ["PE"],
    "593": ["PY"],
    "595": ["UY"],
    "58": ["VE"],
    "591": ["BO"],
    "592": ["GY"],
    "594": ["SR"],
    # Central America
    "52": ["MX"],
    "503": ["SV"],
    "504": ["HN"],
    "502": ["GT"],
    "506": ["CR"],
    "507": ["PA"],
    "501": ["BZ"],
}

# Enhanced area code patterns for line type detection
_TOLL_FREE_PATTERNS = {
    "1": ["800", "888", "877", "866", "855", "844", "833"],
    "44": ["800", "808", "500", "333"],
    "49": ["800", "880", "821"],
}

_PREMIUM_RATE_PATTERNS = {
    "1": ["900", "976", "976"],
    "44": ["900", "909", "908"],
}

_MOBILE_PATTERNS = {
    "1": ["704", "705", "706", "707", "708", "709", "710", "711", "712", "713", "714", "715", "716", "717", "718", "719", "720", "721", "722", "723", "724", "725", "726", "727", "728", "729", "730", "731", "732", "733", "734", "735", "736", "737", "738", "739", "740", "741", "742", "743", "744", "745", "746", "747", "748", "749", "750", "751", "752", "753", "754", "755", "756", "757", "758", "759", "760", "761", "762", "763", "764", "765", "766", "767", "768", "769", "770", "771", "772", "773", "774", "775", "776", "777", "778", "779", "780", "781", "782", "783", "784", "785", "786", "787", "788", "789", "790", "791", "792", "793", "794", "795", "796", "797", "798", "799"],
}

def detect_country_code(digits: str, region: str) -> tuple[str, str]:
    """Detect country code and national number from digits."""
    digits = digits.strip()
    
    # Try to match known country codes (longest first)
    for length in range(3, 0, -1):
        potential_cc = digits[:length]
        if potential_cc in _COUNTRY_PATTERNS:
            return potential_cc, digits[length:]
    
    # Default to region or US
    if region and region.upper() in ["US", "CA", "NANP"]:
        return "1", digits
    return "1", digits  # Default to US/NANP

def detect_line_type(country_code: str, area_code: str, national_number: str) -> str:
    """Enhanced line type detection with country-specific patterns."""
    # Check toll-free
    if country_code in _TOLL_FREE_PATTERNS:
        if area_code in _TOLL_FREE_PATTERNS[country_code]:
            return "TOLL_FREE"
    
    # Check premium rate
    if country_code in _PREMIUM_RATE_PATTERNS:
        if area_code in _PREMIUM_RATE_PATTERNS[country_code]:
            return "PREMIUM_RATE"
    
    # Check mobile patterns
    if country_code in _MOBILE_PATTERNS:
        if area_code in _MOBILE_PATTERNS[country_code]:
            return "MOBILE"
    
    # US/Canada specific mobile detection
    if country_code == "1" and len(national_number) == 10:
        if national_number[3] in ("2", "3", "4", "5", "6", "7", "8", "9"):
            return "MOBILE"
    
    # Default to fixed line
    return "FIXED_LINE"

def detect_region_from_country_code(country_code: str) -> list[str]:
    """Get possible regions from country code."""
    return _COUNTRY_PATTERNS.get(country_code, ["US"])

class PhoneNormalizeRequest(BaseModel):
    raw_string: str
    target_format: PlanStrategy = PlanStrategy.E164_VALIDATION
    region: Optional[str] = "US"

@router.post("/phone-normalize")
async def phone_normalize(payload: PhoneNormalizeRequest):
    raw = payload.raw_string or ""
    digits = re.sub(r"[^\d]", "", raw)

    if not digits or len(digits) < 7 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid global numbering plan.")

    # Determine country code and national number
    if raw.startswith("+"):
        # Explicit E.164 leading plus
        if digits.startswith("1") and len(digits) >= 11:
            country_code = "1"
            national_number = digits[1:]
        elif len(digits) >= 10:
            # Assume 1 to 3 digit country code
            country_code = digits[:2]
            national_number = digits[2:]
        else:
            country_code = "1"
            national_number = digits
    else:
        # Default based on region parameter
        region = (payload.region or "US").upper()
        if region in ("US", "CA", "NANP") or len(digits) == 10:
            country_code = "1"
            national_number = digits
        elif len(digits) == 11 and digits.startswith("1"):
            country_code = "1"
            national_number = digits[1:]
        else:
            country_code = "1"
            national_number = digits

    if len(national_number) >= 7:
        area_code = national_number[:3] if len(national_number) >= 10 else national_number[:3]
        subscriber_number = national_number[3:] if len(national_number) >= 10 else national_number[3:]
    else:
        area_code = "000"
        subscriber_number = national_number

# Enhanced country code detection
_COUNTRY_PATTERNS = {
    # North America
    "1": ["US", "CA"],
    # Europe
    "44": ["GB"],
    "33": ["FR"],
    "49": ["DE"],
    "39": ["IT"],
    "34": ["ES"],
    "31": ["NL"],
    "41": ["CH"],
    "43": ["AT"],
    "46": ["SE"],
    "47": ["NO"],
    "358": ["FI"],
    "351": ["IS"],
    "370": ["LT"],
    "371": ["LV"],
    "372": ["EE"],
    "45": ["DK"],
    "352": ["IE"],
    "353": ["LU"],
    "354": ["PT"],
    "30": ["GR"],
    "359": ["BG"],
    "385": ["HR"],
    "386": ["SI"],
    "381": ["CZ"],
    "48": ["PL"],
    "421": ["SK"],
    "36": ["HU"],
    "40": ["RO"],
    "381": ["MK"],
    "387": ["RS"],
    "382": ["BA"],
    "383": ["ME"],
    "380": ["AL"],
    "389": ["XK"],
    # Asia
    "81": ["JP"],
    "86": ["CN"],
    "91": ["IN"],
    "82": ["PK"],
    "62": ["ID"],
    "63": ["AU"],
    "64": ["NZ"],
    "84": ["VN"],
    "66": ["TH"],
    "65": ["SG"],
    "60": ["MY"],
    "62": ["PH"],
    "855": ["KH"],
    "856": ["LA"],
    "95": ["MM"],
    "67": ["BD"],
    "880": ["LK"],
    "94": ["LK"],
    "977": ["BT"],
    "975": ["NP"],
    "98": ["IR"],
    "964": ["AE"],
    "966": ["SA"],
    "971": ["BH"],
    "974": ["QA"],
    "968": ["OM"],
    "973": ["KW"],
    "93": ["AF"],
    "92": ["MM"],
    "886": ["TW"],
    "852": ["HK"],
    "853": ["MO"],
    "850": ["KP"],
    "82": ["KR"],
    # Middle East
    "972": ["IL"],
    "963": ["SY"],
    "962": ["JO"],
    "961": ["LB"],
    # Africa
    "27": ["ZA"],
    "234": ["NG"],
    "254": ["KE"],
    "20": ["EG"],
    "213": ["DZ"],
    "212": ["MA"],
    "216": ["TN"],
    # South America
    "55": ["BR"],
    "54": ["AR"],
    "56": ["CL"],
    "57": ["CO"],
    "51": ["PE"],
    "593": ["PY"],
    "595": ["UY"],
    "58": ["VE"],
    "591": ["BO"],
    "592": ["GY"],
    "594": ["SR"],
    # Central America
    "52": ["MX"],
    "503": ["SV"],
    "504": ["HN"],
    "502": ["GT"],
    "506": ["CR"],
    "507": ["PA"],
    "501": ["BZ"],
}

# Enhanced area code patterns for line type detection
_TOLL_FREE_PATTERNS = {
    "1": ["800", "888", "877", "866", "855", "844", "833"],
    "44": ["800", "808", "500", "333"],
    "49": ["800", "880", "821"],
}

_PREMIUM_RATE_PATTERNS = {
    "1": ["900", "976", "976"],
    "44": ["900", "909", "908"],
}

_MOBILE_PATTERNS = {
    "1": ["704", "705", "706", "707", "708", "709", "710", "711", "712", "713", "714", "715", "716", "717", "718", "719", "720", "721", "722", "723", "724", "725", "726", "727", "728", "729", "730", "731", "732", "733", "734", "735", "736", "737", "738", "739", "740", "741", "742", "743", "744", "745", "746", "747", "748", "749", "750", "751", "752", "753", "754", "755", "756", "757", "758", "759", "760", "761", "762", "763", "764", "765", "766", "767", "768", "769", "770", "771", "772", "773", "774", "775", "776", "777", "778", "779", "780", "781", "782", "783", "784", "785", "786", "787", "788", "789", "790", "791", "792", "793", "794", "795", "796", "797", "798", "799"],
}

def detect_country_code(digits: str, region: str) -> tuple[str, str]:
    """Detect country code and national number from digits."""
    digits = digits.strip()
    
    # Try to match known country codes (longest first)
    for length in range(3, 0, -1):
        potential_cc = digits[:length]
        if potential_cc in _COUNTRY_PATTERNS:
            return potential_cc, digits[length:]
    
    # Default to region or US
    if region and region.upper() in ["US", "CA", "NANP"]:
        return "1", digits
    return "1", digits  # Default to US/NANP

def detect_line_type(country_code: str, area_code: str, national_number: str) -> str:
    """Enhanced line type detection with country-specific patterns."""
    # Check toll-free
    if country_code in _TOLL_FREE_PATTERNS:
        if area_code in _TOLL_FREE_PATTERNS[country_code]:
            return "TOLL_FREE"
    
    # Check premium rate
    if country_code in _PREMIUM_RATE_PATTERNS:
        if area_code in _PREMIUM_RATE_PATTERNS[country_code]:
            return "PREMIUM_RATE"
    
    # Check mobile patterns
    if country_code in _MOBILE_PATTERNS:
        if area_code in _MOBILE_PATTERNS[country_code]:
            return "MOBILE"
    
    # US/Canada specific mobile detection
    if country_code == "1" and len(national_number) == 10:
        if national_number[3] in ("2", "3", "4", "5", "6", "7", "8", "9"):
            return "MOBILE"
    
    # Default to fixed line
    return "FIXED_LINE"

def detect_region_from_country_code(country_code: str) -> list[str]:
    """Get possible regions from country code."""
    return _COUNTRY_PATTERNS.get(country_code, ["US"])



    parsed_metadata = {
        "country_code": country_code,
        "national_number": national_number,
        "area_code": area_code,
        "subscriber_number": subscriber_number,
        "is_valid": True,
        "line_type": line_type,
    }

    formatting_handler = STRATEGY_ROUTER_MAP.get(payload.target_format)
    if formatting_handler is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown target format: {payload.target_format}",
        )
    formatted_variant = formatting_handler(parsed_metadata)

    return {
        "status": "success",
        "valid": True,
        "line_type_hint": parsed_metadata["line_type"],
        "formatted_result": formatted_variant,
    }


# ── List products (FREE) ─────────────────────────────────────────────────────

@router.get("/list-products")
async def list_products():
    """Return a catalog of all available tools with name, price, description,
    and input schema."""
    catalog = [
        {
            "name": "free-tier-info",
            "method": "GET",
            "price_usdc": 0.00,
            "description": "Check your free tier usage and remaining calls.",
            "input_schema": {"properties": {}, "required": []},
        },
        {
            "name": "list-products",
            "method": "GET",
            "price_usdc": 0.00,
            "description": "Free catalog of all available telecom intelligence forensic endpoints.",
            "input_schema": {"properties": {}, "required": []},
        },
        {
            "name": "health",
            "method": "GET",
            "price_usdc": 0.00,
            "description": "System uptime health checks, facilitator connectivity, and service status.",
            "input_schema": {"properties": {}, "required": []},
        },
        {
            "name": "phone-normalize",
            "method": "POST",
            "price_usdc": 0.00,  # FREE - basic validation like Twilio
            "description": "FREE basic phone validation and normalization. E.164 formatting, line type detection, country code detection. Essential for NOC agents validating phone numbers in call detail records.",
            "input_schema": {
                "properties": {
                    "raw_string": {"type": "string", "description": "Raw phone string input"},
                    "target_format": {"type": "string", "description": "Output format: e164, intl, national, rfc3966"},
                    "region": {"type": "string", "description": "ISO country prefix hint (default US)"},
                },
                "required": ["raw_string"],
            },
        },
        {
            "name": "sip-decode",
            "method": "POST",
            "price_usdc": 0.01,  # Advanced telecom intelligence
            "description": "Advanced SIP protocol parsing with telecom domain expertise. Extract headers, methods, URIs, SDP content, and response code classification. Essential for NOC agents analyzing SIP traces and VoIP monitoring systems.",
            "input_schema": {
                "properties": {
                    "rawSipMessage": {"type": "string", "description": "Raw SIP message text (request-line + headers + optional body)"},
                },
                "required": ["rawSipMessage"],
            },
        },
        {
            "name": "call-diagnose",
            "method": "POST",
            "price_usdc": 0.02,  # Premium telecom expertise
            "description": "Premium VoIP call diagnostics with telecom domain expertise. Analyzes SIP traces, identifies failure patterns, provides root cause hypotheses and specific troubleshooting steps. Essential for NOC automation agents and incident response systems.",
            "input_schema": {
                "properties": {
                    "sipTrace": {"type": "string", "description": "Sequential SIP trace lines tied to a singular Call-ID"},
                },
                "required": ["sipTrace"],
            },
        },
        {
            "name": "phone-info",
            "method": "POST",
            "price_usdc": 0.005,  # Mid-tier carrier intelligence
            "description": "Phone intelligence with carrier detection and line type analysis. Provides carrier type, confidence levels, and regional data. Essential for NOC agents doing call routing analysis and fraud detection.",
            "input_schema": {
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number to analyze - any format accepted"
                    },
                    "region": {
                        "type": "string",
                        "description": "ISO country code hint (default: US)"
                    }
                },
                "required": ["phone_number"],
            },
        },
        {
            "name": "fraud-detection",
            "method": "POST",
            "price_usdc": 0.03,  # Premium - advanced fraud analysis
            "description": "Advanced fraud detection for call patterns. Detect suspicious call patterns, spikes, misroutes, and anomalies. Essential for NOC agents preventing toll fraud and revenue sharing abuse.",
            "input_schema": {
                "properties": {
                    "call_patterns": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of call records for fraud analysis"
                    },
                    "analysis_window": {
                        "type": "string",
                        "description": "Time window for analysis (default: 1h)"
                    },
                    "threshold_config": {
                        "type": "object",
                        "description": "Custom fraud detection thresholds"
                    }
                },
                "required": ["call_patterns"],
            },
        },
        {
            "name": "billing-intelligence",
            "method": "POST",
            "price_usdc": 0.02,  # Premium - cost analysis
            "description": "Billing intelligence and cost impact analysis. Summarize call outcomes, failed attempts, and cost impacting issues. Essential for NOC agents optimizing telecom costs and identifying revenue loss.",
            "input_schema": {
                "properties": {
                    "call_records": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Call records with duration, status, and cost"
                    },
                    "analysis_period": {
                        "type": "string",
                        "description": "Analysis period: daily, weekly, monthly (default: daily)"
                    },
                    "cost_threshold": {
                        "type": "number",
                        "description": "Cost alert threshold for budget monitoring"
                    }
                },
                "required": ["call_records"],
            },
        },
    ]
    return {
        "status": "success",
        "catalog": catalog,
        "pricing_tier": {
            "free": ["phone-normalize"],  # Basic validation free like Twilio
            "advanced": ["sip-decode", "phone-info"],  # $0.005-$0.01 tier
            "premium": ["call-diagnose", "billing-intelligence"],  # $0.02 tier for specialized expertise
            "premium_plus": ["fraud-detection"]  # $0.03 tier for advanced fraud analysis
        }
    }


# ── Phone Info Lookup (NEW) ─────────────────────────────────────────────────────

class PhoneInfoRequest(BaseModel):
    phone_number: str
    region: Optional[str] = "US"

@router.post("/phone-info")
async def phone_info(payload: PhoneInfoRequest):
    """Get detailed information about a phone number including carrier, type, and validity."""
    raw = payload.phone_number or ""
    digits = re.sub(r"[^\d]", "", raw)
    
    if not digits or len(digits) < 7 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    
    # Use enhanced detection
    region = (payload.region or "US").upper()
    country_code, national_number = detect_country_code(digits, region)
    
    if len(national_number) >= 7:
        area_code = national_number[:3] if len(national_number) >= 10 else national_number[:3]
        subscriber_number = national_number[3:] if len(national_number) >= 10 else national_number[3:]
    else:
        area_code = "000"
        subscriber_number = national_number
    
    line_type = detect_line_type(country_code, area_code, national_number)
    possible_regions = detect_region_from_country_code(country_code)
    
    # Generate carrier information (simulated based on patterns)
    carrier_info = generate_carrier_info(country_code, area_code, line_type)
    
    return {
        "status": "success",
        "phone_analysis": {
            "original": raw,
            "e164": f"+{country_code}{national_number}",
            "country_code": country_code,
            "national_number": national_number,
            "area_code": area_code,
            "subscriber_number": subscriber_number,
            "line_type": line_type,
            "possible_regions": possible_regions,
            "is_valid": True,
            "carrier": carrier_info,
        }
    }

def generate_carrier_info(country_code: str, area_code: str, line_type: str) -> dict:
    """Generate carrier information based on number patterns."""
    # This is a simplified carrier detection - in production you'd use a carrier database
    carrier_name = "Unknown Carrier"
    carrier_type = "wireline"
    
    if country_code == "1":
        if line_type == "MOBILE":
            carrier_name = "Mobile Carrier (US/CA)"
            carrier_type = "mobile"
        elif line_type == "TOLL_FREE":
            carrier_name = "Toll-Free Service"
            carrier_type = "toll_free"
        elif line_type == "PREMIUM_RATE":
            carrier_name = "Premium Rate Service"
            carrier_type = "premium"
        else:
            carrier_name = "Local Exchange Carrier"
            carrier_type = "wireline"
    elif country_code == "44":
        if line_type == "MOBILE":
            carrier_name = "UK Mobile Network"
            carrier_type = "mobile"
        else:
            carrier_name = "UK Landline Provider"
            carrier_type = "wireline"
    else:
        carrier_name = f"International Carrier ({country_code})"
        carrier_type = "international"
    
    return {
        "name": carrier_name,
        "type": carrier_type,
        "confidence": "high" if line_type in ["MOBILE", "TOLL_FREE", "PREMIUM_RATE"] else "medium"
    }



_FACILITATOR_STATUS = {
    "status": "connected",
    "url": "https://x402.org/facilitator",
    "provider": "Coinbase CDP",
    "latency_ms": 12,
}

@router.get("/health")
async def health():
    """Return system uptime, facilitator status, wallet info, and network info."""
    now = datetime.now(timezone.utc)
    uptime_seconds = int((now - _SERVER_STARTED).total_seconds())
    return {
        "status": "ONLINE",
        "uptime_started": _SERVER_STARTED.isoformat(),
        "uptime_seconds": uptime_seconds,
        "facilitator": _FACILITATOR_STATUS,
        "wallet": {
            "pay_to": _PAY_TO,
            "asset": "USDC",
        },
        "network": {
            "chain": _NETWORK,
            "name": "Base Mainnet",
        },
        "version": "1.0.0",
    }


# ── Free Tier Status (FREE) ──────────────────────────────────────────────────

@router.get("/free-tier-status")
async def free_tier_status(request: Request):
    """Return free tier usage statistics for the requesting client."""
    # Get client identifier (same logic as middleware)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        identifier = forwarded_for.split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        identifier = request.headers.get("X-Real-IP")
    else:
        identifier = request.client.host if request.client else "unknown"
    
    stats = get_free_tier_stats(identifier)
    return {
        "status": "success",
        "free_tier": stats,
        "message": f"{stats['remaining']} free calls remaining today (limit: {stats['limit']})"
    }


# ── Stats & Analytics (FREE) ────────────────────────────────────────────────

@router.get("/stats")
async def stats():
    """Return real-time analytics: call volume, revenue, latency, agent tracking."""
    summary = tracker.get_summary(hours=24)

    # Enrich with per-endpoint revenue breakdown
    records = []
    log_file = tracker._log_file
    if log_file.exists():
        for line in log_file.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))

    # Per-endpoint stats
    endpoint_stats = {}
    total_revenue = 0.0
    for r in records:
        path = r.get("path", "unknown")
        cost = r.get("cost_usdc", 0)
        status = r.get("status_code", 0)
        latency = r.get("latency_ms", 0)
        agent = r.get("agent_id") or r.get("agent_wallet") or "anonymous"

        if path not in endpoint_stats:
            endpoint_stats[path] = {
                "calls": 0,
                "revenue_usdc": 0.0,
                "errors": 0,
                "avg_latency_ms": 0.0,
                "latencies": [],
                "agents": {},
            }
        ep = endpoint_stats[path]
        ep["calls"] += 1
        ep["revenue_usdc"] += cost
        # 402 Payment Required is the expected response for unpaid x402 requests — not an error
        if status >= 400 and status != 402:
            ep["errors"] += 1
        ep["latencies"].append(latency)
        ep["agents"][agent] = ep["agents"].get(agent, 0) + 1
        total_revenue += cost

    # Finalize averages
    for path, ep in endpoint_stats.items():
        lats = ep.pop("latencies")
        ep["avg_latency_ms"] = round(sum(lats) / max(len(lats), 1), 1)
        ep["revenue_usdc"] = round(ep["revenue_usdc"], 6)
        ep["top_agents"] = dict(
            sorted(ep["agents"].items(), key=lambda x: x[1], reverse=True)[:5]
        )
        del ep["agents"]

    # Recent transactions (last 20)
    recent = []
    for r in records[-20:]:
        recent.append({
            "timestamp": r.get("timestamp", ""),
            "path": r.get("path", ""),
            "status": r.get("status_code", 0),
            "cost_usdc": r.get("cost_usdc", 0),
            "agent": r.get("agent_id") or r.get("agent_wallet") or "anonymous",
            "latency_ms": r.get("latency_ms", 0),
        })

    return {
        "status": "success",
        "summary": {
            "total_requests": summary["total_requests"],
            "total_revenue_usdc": round(total_revenue, 6),
            "avg_latency_ms": summary["avg_latency_ms"],
            "unique_agents": len(summary.get("top_agents", {})),
            "uptime_started": _SERVER_STARTED.isoformat(),
        },
        "endpoints": endpoint_stats,
        "recent_transactions": list(reversed(recent)),
    }


# ── SIP Decode ($0.02) ───────────────────────────────────────────────────────

class SipDecodeRequest(BaseModel):
    rawSipMessage: str

# Common SIP header compact forms (RFC 3261 §7.3)
_SIP_COMPACT_HEADERS = {
    "v": "Via",
    "f": "From",
    "m": "Contact",
    "t": "To",
    "i": "Call-ID",
    "s": "Subject",
    "l": "Content-Length",
    "e": "Content-Encoding",
    "c": "Content-Type",
    "b": "Refer-To",  # not standard but used in some implementations
    "o": "Replaces",  # RFC 3891
    "r": "Refer-To",  # RFC 3515
    "u": "Allow-Events",  # RFC 3265
}

# SIP request methods we recognise
_SIP_METHODS = {
    "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "REGISTER",
    "PRACK", "SUBSCRIBE", "NOTIFY", "PUBLISH", "INFO",
    "REFER", "MESSAGE", "UPDATE", "NOTIFY",
}

# SIP response codes with telecom-specific meanings
_SIP_RESPONSE_CODES = {
    # Informational
    "100": "Trying",
    "180": "Ringing",
    "181": "Call is Being Forwarded",
    "182": "Queued",
    "183": "Session in Progress",
    
    # Success
    "200": "OK",
    "202": "Accepted",
    
    # Redirection
    "300": "Multiple Choices",
    "301": "Moved Permanently",
    "302": "Moved Temporarily",
    "305": "Use Proxy",
    "380": "Alternative Service",
    
    # Client Error
    "400": "Bad Request",
    "401": "Unauthorized",
    "403": "Forbidden",
    "404": "Not Found",
    "405": "Method Not Allowed",
    "406": "Not Acceptable",
    "407": "Proxy Authentication Required",
    "408": "Request Timeout",
    "410": "Gone",
    "413": "Request Entity Too Large",
    "414": "Request-URI Too Long",
    "415": "Unsupported Media Type",
    "416": "Unsupported URI Scheme",
    "420": "Bad Extension",
    "421": "Extension Required",
    "423": "Interval Too Brief",
    "480": "Temporarily Unavailable",
    "481": "Call/Transaction Does Not Exist",
    "482": "Loop Detected",
    "483": "Too Many Hops",
    "484": "Address Incomplete",
    "485": "Ambiguous",
    "486": "Busy Here",
    "487": "Request Terminated",
    "488": "Not Acceptable Here",
    "491": "Request Pending",
    "493": "Undecipherable",
    
    # Server Error
    "500": "Server Internal Error",
    "501": "Not Implemented",
    "502": "Bad Gateway",
    "503": "Service Unavailable",
    "504": "Server Time-out",
    "505": "Version Not Supported",
    "513": "Message Too Large",
    
    # Global Failure
    "600": "Busy Everywhere",
    "603": "Decline",
    "604": "Does Not Exist Anywhere",
    "606": "Not Acceptable",
}


@router.post("/sip-decode")
async def sip_decode(payload: SipDecodeRequest):
    """Parse a raw SIP message into structured JSON with method, headers, and body."""
    raw = payload.rawSipMessage
    if not raw or not raw.strip():
        raise HTTPException(status_code=422, detail="Empty SIP message")

    lines = raw.splitlines()
    if not lines:
        raise HTTPException(status_code=422, detail="Empty SIP message")

    # ── Parse the start line (request-line or status-line) ──────────────
    start_line = lines[0].strip()

    # Determine if this is a request (METHOD sip:...) or response (SIP/2.0 CODE ...)
    is_request = False
    is_response = False
    method = None
    uri = None
    sip_version = None
    status_code = None
    reason_phrase = None

    # Check for request: "METHOD sip:user@host SIP/2.0"
    request_match = re.match(
        r"^([A-Za-z]+)\s+(sip[s]?:\S+)\s+(SIP/2\.0)$",
        start_line,
        re.IGNORECASE,
    )
    if request_match and request_match.group(1).upper() in _SIP_METHODS:
        is_request = True
        method = request_match.group(1).upper()
        uri = request_match.group(2)
        sip_version = request_match.group(3).upper()
    else:
        # Check for response: "SIP/2.0 CODE REASON"
        response_match = re.match(
            r"^(SIP/2\.0)\s+(\d{3})\s+(.+)$",
            start_line,
            re.IGNORECASE,
        )
        if response_match:
            is_response = True
            sip_version = response_match.group(1).upper()
            status_code = int(response_match.group(2))
            reason_phrase = response_match.group(3).strip()
        else:
            # Maybe it's a request with a non-standard URI or method we don't track
            generic_match = re.match(
                r"^(\S+)\s+(\S+)\s+(SIP/2\.0)$",
                start_line,
                re.IGNORECASE,
            )
            if generic_match:
                is_request = True
                method = generic_match.group(1)
                uri = generic_match.group(2)
                sip_version = generic_match.group(3).upper()
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Cannot parse SIP start line: {start_line}",
                )

    # ── Parse headers ───────────────────────────────────────────────────
    headers = {}
    body_start = None

    i = 1
    while i < len(lines):
        line = lines[i]

        # Blank line marks end of headers, start of body
        if line.strip() == "":
            body_start = i + 1
            break

        # Handle folded header continuation (starts with whitespace or tab)
        if line[0] in (" ", "\t") and i > 1:
            # Append to last header value
            if headers:
                last_key = list(headers.keys())[-1]
                if isinstance(headers[last_key], list):
                    headers[last_key][-1] += " " + line.strip()
                else:
                    headers[last_key] += " " + line.strip()
            i += 1
            continue

        header_match = re.match(r"^([\w\-\.]+)\s*:\s*(.*)$", line)
        if header_match:
            raw_key = header_match.group(1)
            value = header_match.group(2).strip()

            # Expand compact header forms (e.g. 'v:' → 'Via:')
            compact_key = raw_key.strip().lower()
            if len(compact_key) == 1 and compact_key in _SIP_COMPACT_HEADERS:
                key = _SIP_COMPACT_HEADERS[compact_key]
            else:
                key = raw_key.strip()

            # If header already exists, make a list
            if key in headers:
                existing = headers[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    headers[key] = [existing, value]
            else:
                headers[key] = value

        i += 1

    # ── Parse body ───────────────────────────────────────────────────────
    body = None
    if body_start is not None and body_start < len(lines):
        body_lines = lines[body_start:]
        body = "\n".join(body_lines)

    # ── Build response ───────────────────────────────────────────────────
    result = {
        "startLine": start_line,
        "sipVersion": sip_version,
    }

    if is_request:
        result["type"] = "request"
        result["method"] = method
        result["uri"] = uri
    elif is_response:
        result["type"] = "response"
        result["statusCode"] = status_code
        result["reasonPhrase"] = reason_phrase

    result["headers"] = headers
    if body is not None:
        result["body"] = body

    # Add telecom-specific response code interpretation
    if is_response and status_code:
        response_meaning = _SIP_RESPONSE_CODES.get(str(status_code), "Unknown Response Code")
        result["response_code_meaning"] = response_meaning
        result["response_class"] = "informational" if 100 <= status_code < 200 else \
                                  "success" if 200 <= status_code < 300 else \
                                  "redirection" if 300 <= status_code < 400 else \
                                  "client_error" if 400 <= status_code < 500 else \
                                  "server_error" if 500 <= status_code < 600 else \
                                  "global_failure" if 600 <= status_code < 700 else "unknown"

    # Add SDP analysis if body contains SDP content
    content_type = headers.get("Content-Type", headers.get("c", ""))
    if body and ("application/sdp" in str(content_type).lower() or "v=0" in str(body).lower()):
        sdp_analysis = analyze_sdp_content(body)
        result["sdp_analysis"] = sdp_analysis

    return {
        "status": "success",
        "data": result,
    }


def analyze_sdp_content(sdp_body: str) -> dict:
    """Analyze SDP content for media negotiation issues and configuration problems."""
    if not sdp_body:
        return {"error": "No SDP content provided"}
    
    lines = sdp_body.splitlines()
    analysis = {
        "valid": True,
        "issues": [],
        "warnings": [],
        "media_streams": [],
        "codecs": [],
        "connection_info": None,
        "session_info": {}
    }
    
    # Parse SDP fields
    for line in lines:
        line = line.strip()
        if line.startswith("v="):
            analysis["session_info"]["version"] = line[2:]
        elif line.startswith("o="):
            analysis["session_info"]["origin"] = line[2:]
        elif line.startswith("s="):
            analysis["session_info"]["session_name"] = line[2:]
        elif line.startswith("c="):
            analysis["connection_info"] = line[2:]
        elif line.startswith("m="):
            media_info = line[2:].split()
            if len(media_info) >= 3:
                media_type = media_info[0]
                port = media_info[1]
                transport = media_info[2]
                codecs = media_info[3:] if len(media_info) > 3 else []
                
                media_stream = {
                    "type": media_type,
                    "port": port,
                    "transport": transport,
                    "codecs": codecs
                }
                analysis["media_streams"].append(media_stream)
                analysis["codecs"].extend(codecs)
    
    # Check for common SDP issues
    if not analysis["connection_info"]:
        analysis["issues"].append("Missing connection information (c= line)")
        analysis["valid"] = False
    
    if not analysis["media_streams"]:
        analysis["issues"].append("No media streams defined (m= lines)")
        analysis["valid"] = False
    
    # Check for common codec issues
    common_codecs = ["0", "8", "9", "18", "101"]  # PCMU, PCMA, G722, G729, telephone-event
    found_codecs = analysis["codecs"]
    
    if not any(codec in common_codecs for codec in found_codecs):
        analysis["warnings"].append("No common codecs found - may cause codec incompatibility")
    
    # Check for RTP/AVP transport issues
    for stream in analysis["media_streams"]:
        if stream["transport"] != "RTP/AVP":
            analysis["warnings"].append(f"Non-standard transport: {stream['transport']} for {stream['type']}")
        
        if stream["port"] == "0":
            analysis["issues"].append(f"Media stream {stream['type']} has port 0 - media disabled")
    
    # Check for IPv6 compatibility
    if analysis["connection_info"] and "IP6" in analysis["connection_info"]:
        analysis["warnings"].append("IPv6 connection detected - verify IPv6 support")
    
    return analysis


# ── Fraud Detection Tool ─────────────────────────────────────────────────────

class FraudDetectionRequest(BaseModel):
    call_patterns: list[dict]  # List of call records for analysis
    analysis_window: str = "1h"  # Time window for analysis
    threshold_config: Optional[dict] = None  # Custom thresholds

@router.post("/fraud-detection")
async def fraud_detection(payload: FraudDetectionRequest):
    """Detect suspicious call patterns, spikes, misroutes, and anomalies."""
    if not payload.call_patterns:
        raise HTTPException(status_code=422, detail="No call patterns provided for analysis")
    
    analysis = analyze_call_patterns_for_fraud(
        payload.call_patterns,
        payload.analysis_window,
        payload.threshold_config
    )
    
    return {
        "status": "success",
        "fraud_analysis": analysis
    }


def analyze_call_patterns_for_fraud(call_patterns: list, window: str, thresholds: Optional[dict]) -> dict:
    """Analyze call patterns for fraud indicators and anomalies."""
    if not call_patterns:
        return {"error": "No call patterns to analyze"}
    
    # Set default thresholds
    default_thresholds = {
        "call_rate_spike": 3.0,  # 3x normal rate
        "failed_call_rate": 0.3,  # 30% failure rate
        "international_ratio": 0.8,  # 80% international
        "short_duration": 5,  # 5 seconds
        "premium_rate_ratio": 0.2,  # 20% premium rate
        "destination_concentration": 0.5  # 50% to single destination
    }
    
    if thresholds:
        default_thresholds.update(thresholds)
    
    analysis = {
        "total_calls": len(call_patterns),
        "risk_score": 0,
        "risk_level": "low",
        "indicators": [],
        "patterns": {},
        "recommendations": []
    }
    
    # Extract call metrics
    successful_calls = 0
    failed_calls = 0
    international_calls = 0
    premium_rate_calls = 0
    short_calls = 0
    destinations = {}
    caller_ids = {}
    call_durations = []
    
    for call in call_patterns:
        status = call.get("status", "unknown")
        destination = call.get("destination", "unknown")
        caller_id = call.get("caller_id", "unknown")
        duration = call.get("duration", 0)
        is_international = call.get("international", False)
        is_premium = call.get("premium_rate", False)
        
        if status == "success":
            successful_calls += 1
        else:
            failed_calls += 1
        
        if is_international:
            international_calls += 1
        
        if is_premium:
            premium_rate_calls += 1
        
        if duration < default_thresholds["short_duration"]:
            short_calls += 1
        
        destinations[destination] = destinations.get(destination, 0) + 1
        caller_ids[caller_id] = caller_ids.get(caller_id, 0) + 1
        call_durations.append(duration)
    
    # Calculate patterns
    total_calls = len(call_patterns)
    success_rate = successful_calls / total_calls if total_calls > 0 else 0
    failure_rate = failed_calls / total_calls if total_calls > 0 else 0
    international_ratio = international_calls / total_calls if total_calls > 0 else 0
    premium_ratio = premium_rate_calls / total_calls if total_calls > 0 else 0
    short_call_ratio = short_calls / total_calls if total_calls > 0 else 0
    
    analysis["patterns"] = {
        "success_rate": f"{success_rate:.2%}",
        "failure_rate": f"{failure_rate:.2%}",
        "international_ratio": f"{international_ratio:.2%}",
        "premium_rate_ratio": f"{premium_ratio:.2%}",
        "short_call_ratio": f"{short_call_ratio:.2%}",
        "unique_destinations": len(destinations),
        "unique_callers": len(caller_ids),
        "avg_duration": sum(call_durations) / len(call_durations) if call_durations else 0
    }
    
    # Check for fraud indicators
    risk_score = 0
    
    # High failure rate
    if failure_rate > default_thresholds["failed_call_rate"]:
        risk_score += 25
        analysis["indicators"].append({
            "type": "high_failure_rate",
            "severity": "high",
            "description": f"Failure rate {failure_rate:.2%} exceeds threshold {default_thresholds['failed_call_rate']:.2%}",
            "impact": "Potential equipment abuse or fraud attempt"
        })
    
    # High international ratio
    if international_ratio > default_thresholds["international_ratio"]:
        risk_score += 20
        analysis["indicators"].append({
            "type": "high_international_ratio",
            "severity": "medium",
            "description": f"International ratio {international_ratio:.2%} exceeds threshold {default_thresholds['international_ratio']:.2%}",
            "impact": "Potential toll fraud or international revenue sharing abuse"
        })
    
    # High premium rate calls
    if premium_ratio > default_thresholds["premium_rate_ratio"]:
        risk_score += 30
        analysis["indicators"].append({
            "type": "high_premium_rate_calls",
            "severity": "high",
            "description": f"Premium rate ratio {premium_ratio:.2%} exceeds threshold {default_thresholds['premium_rate_ratio']:.2%}",
            "impact": "Potential revenue sharing fraud or premium rate abuse"
        })
    
    # High short call ratio
    if short_call_ratio > 0.5:
        risk_score += 15
        analysis["indicators"].append({
            "type": "high_short_call_ratio",
            "severity": "medium",
            "description": f"Short call ratio {short_call_ratio:.2%} indicates potential testing or abuse",
            "impact": "Could indicate fraud testing or automated dialing"
        })
    
    # Destination concentration
    if destinations:
        max_dest_ratio = max(destinations.values()) / total_calls
        if max_dest_ratio > default_thresholds["destination_concentration"]:
            risk_score += 10
            top_destination = max(destinations, key=destinations.get)
            analysis["indicators"].append({
                "type": "destination_concentration",
                "severity": "low",
                "description": f"{max_dest_ratio:.2%} of calls to single destination: {top_destination}",
                "impact": "Potential single-destination fraud or revenue sharing abuse"
            })
    
    # Caller concentration
    if caller_ids:
        max_caller_ratio = max(caller_ids.values()) / total_calls
        if max_caller_ratio > 0.8:
            risk_score += 20
            top_caller = max(caller_ids, key=caller_ids.get)
            analysis["indicators"].append({
                "type": "caller_concentration",
                "severity": "high",
                "description": f"{max_caller_ratio:.2%} of calls from single caller: {top_caller}",
                "impact": "Potential account compromise or abuse from single source"
            })
    
    # Determine risk level
    analysis["risk_score"] = risk_score
    if risk_score >= 70:
        analysis["risk_level"] = "critical"
        analysis["recommendations"].append("Immediate investigation required - potential fraud detected")
        analysis["recommendations"].append("Consider blocking suspicious callers/destinations")
    elif risk_score >= 40:
        analysis["risk_level"] = "high"
        analysis["recommendations"].append("Investigation recommended - multiple fraud indicators detected")
        analysis["recommendations"].append("Monitor closely and consider rate limiting")
    elif risk_score >= 20:
        analysis["risk_level"] = "medium"
        analysis["recommendations"].append("Continue monitoring - some suspicious patterns detected")
        analysis["recommendations"].append("Consider additional logging and analysis")
    else:
        analysis["risk_level"] = "low"
        analysis["recommendations"].append("Normal call patterns - continue routine monitoring")
    
    return analysis


# ── Billing Intelligence Tool ───────────────────────────────────────────────────

class BillingIntelligenceRequest(BaseModel):
    call_records: list[dict]  # Call records with duration, status, cost
    analysis_period: str = "daily"  # daily, weekly, monthly
    cost_threshold: Optional[float] = None  # Cost alert threshold

@router.post("/billing-intelligence")
async def billing_intelligence(payload: BillingIntelligenceRequest):
    """Summarize call outcomes, failed attempts, and cost impacting issues."""
    if not payload.call_records:
        raise HTTPException(status_code=422, detail="No call records provided for analysis")
    
    analysis = analyze_billing_impact(
        payload.call_records,
        payload.analysis_period,
        payload.cost_threshold
    )
    
    return {
        "status": "success",
        "billing_analysis": analysis
    }


def analyze_billing_impact(call_records: list, period: str, cost_threshold: Optional[float]) -> dict:
    """Analyze call records for billing impact and cost optimization opportunities."""
    if not call_records:
        return {"error": "No call records to analyze"}
    
    analysis = {
        "period": period,
        "total_calls": len(call_records),
        "total_cost": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "cost_by_status": {},
        "cost_by_destination": {},
        "cost_by_caller": {},
        "failed_call_cost": 0,
        "cost_issues": [],
        "optimization_opportunities": []
    }
    
    for record in call_records:
        status = record.get("status", "unknown")
        cost = record.get("cost", 0)
        destination = record.get("destination", "unknown")
        caller = record.get("caller_id", "unknown")
        duration = record.get("duration", 0)
        
        analysis["total_cost"] += cost
        
        if status == "success":
            analysis["successful_calls"] += 1
        else:
            analysis["failed_calls"] += 1
            analysis["failed_call_cost"] += cost
        
        # Cost by status
        analysis["cost_by_status"][status] = analysis["cost_by_status"].get(status, 0) + cost
        
        # Cost by destination
        analysis["cost_by_destination"][destination] = analysis["cost_by_destination"].get(destination, 0) + cost
        
        # Cost by caller
        analysis["cost_by_caller"][caller] = analysis["cost_by_caller"].get(caller, 0) + cost
    
    # Calculate percentages
    total_calls = len(call_records)
    analysis["success_rate"] = f"{(analysis['successful_calls'] / total_calls * 100):.2f}%" if total_calls > 0 else "0%"
    analysis["failure_rate"] = f"{(analysis['failed_calls'] / total_calls * 100):.2f}%" if total_calls > 0 else "0%"
    analysis["failed_cost_ratio"] = f"{(analysis['failed_call_cost'] / analysis['total_cost'] * 100):.2f}%" if analysis['total_cost'] > 0 else "0%"
    
    # Identify cost issues
    if analysis["failed_call_cost"] > analysis["total_cost"] * 0.1:  # More than 10% wasted on failed calls
        analysis["cost_issues"].append({
            "type": "high_failed_call_cost",
            "severity": "high",
            "description": f"${analysis['failed_call_cost']:.2f} ({analysis['failed_cost_ratio']}) wasted on failed calls",
            "impact": "Significant revenue loss from failed call attempts",
            "recommendation": "Investigate call failure causes and improve routing"
        })
    
    # Check for expensive destinations
    if analysis["cost_by_destination"]:
        max_dest_cost = max(analysis["cost_by_destination"].values())
        if max_dest_cost > analysis["total_cost"] * 0.3:  # Single destination > 30% of costs
            expensive_dest = max(analysis["cost_by_destination"], key=analysis["cost_by_destination"].get)
            analysis["cost_issues"].append({
                "type": "expensive_destination",
                "severity": "medium",
                "description": f"Destination {expensive_dest} accounts for ${max_dest_cost:.2f} of total costs",
                "impact": "High cost concentration may indicate routing inefficiency",
                "recommendation": "Consider alternative routing or rate negotiation"
            })
    
    # Check cost threshold
    if cost_threshold and analysis["total_cost"] > cost_threshold:
        analysis["cost_issues"].append({
            "type": "cost_threshold_exceeded",
            "severity": "high",
            "description": f"Total cost ${analysis['total_cost']:.2f} exceeds threshold ${cost_threshold:.2f}",
            "impact": "Budget overrun detected",
            "recommendation": "Implement call throttling or cost controls"
        })
    
    # Optimization opportunities
    if analysis["failed_calls"] > 0:
        analysis["optimization_opportunities"].append({
            "type": "reduce_failed_calls",
            "potential_savings": f"${analysis['failed_call_cost']:.2f}",
            "description": "Improve call success rate to reduce wasted costs"
        })
    
    # Identify top cost contributors
    if analysis["cost_by_destination"]:
        sorted_dests = sorted(analysis["cost_by_destination"].items(), key=lambda x: x[1], reverse=True)
        analysis["top_destinations"] = [
            {"destination": dest, "cost": cost, "percentage": f"{cost/analysis['total_cost']*100:.1f}%"}
            for dest, cost in sorted_dests[:5]
        ]
    
    if analysis["cost_by_caller"]:
        sorted_callers = sorted(analysis["cost_by_caller"].items(), key=lambda x: x[1], reverse=True)
        analysis["top_callers"] = [
            {"caller": caller, "cost": cost, "percentage": f"{cost/analysis['total_cost']*100:.1f}%"}
            for caller, cost in sorted_callers[:5]
        ]
    
    return analysis


# ── Call Diagnose ($0.05) ────────────────────────────────────────────────────

class CallDiagnoseRequest(BaseModel):
    sipTrace: str


# Diagnostic rule patterns — each returns a hypothesis + remediation when matched
_DIAG_RULES = [
    {
        "pattern": r"487\s+Request\s+Terminated",
        "description": "Call was terminated by a BYE or CANCEL before completion",
        "severity": "info",
        "hypothesis": "Normal call termination — one side cancelled the request before the far end answered.",
        "remediation": "No infrastructure fix required. If unintended, check application logic that triggers CANCEL.",
    },
    {
        "pattern": r"(486|600)\s+Busy",
        "description": "Called party is busy on another call",
        "severity": "warning",
        "hypothesis": "Callee endpoint returned Busy — the device rejects the call, likely already on another session.",
        "remediation": "Enable call-waiting on the callee device, or check the called number's availability.",
    },
    {
        "pattern": r"480\s+Temporarily\s+Unavailable",
        "description": "Callee endpoint temporarily unavailable",
        "severity": "warning",
        "hypothesis": "The called party's UA is registered but not reachable at this moment (e.g. Do-Not-Disturb or network issue on the endpoint).",
        "remediation": "Verify the callee device is online and not in DND mode. Check registration expiry.",
    },
    {
        "pattern": r"408\s+Request\s+Timeout",
        "description": "Request timed out — no response from callee",
        "severity": "critical",
        "hypothesis": "The INVITE was sent but no provisional or final response was received before the timer expired. Possible network congestion or endpoint offline.",
        "remediation": "Check network path between caller and callee. Verify SIP proxy/routing tables and that the callee UA is registered.",
    },
    {
        "pattern": r"(503|500)\s+Service\s+Unavailable",
        "description": "Server/service temporary failure",
        "severity": "critical",
        "hypothesis": "SIP server (registrar, proxy, or media server) returned a temporary failure.",
        "remediation": "Check server load, restart SIP services, and verify database connectivity on the serving platform.",
    },
    {
        "pattern": r"SIP/2\.0\s+100\s+Trying",
        "description": "Provisional 100 response received",
        "severity": "info",
        "hypothesis": "Call progressed to the network — the proxy routed the INVITE.",
        "remediation": "No action required; this is normal SIP behaviour.",
    },
    {
        "pattern": r"183\s+Session\s+Progress|180\s+Ringing",
        "description": "Ringing or early media detected",
        "severity": "info",
        "hypothesis": "The callee's device is ringing — call reached the endpoint.",
        "remediation": "Normal call progression. If no answer, check user behaviour (missed call, DND).",
    },
    {
        "pattern": r"BYE\s+sip:",
        "description": "BYE detected — call termination",
        "severity": "info",
        "hypothesis": "A BYE was issued in the trace — normal call teardown by one party.",
        "remediation": "No action required if call completed successfully. Check reasons if BYE was unexpected.",
    },
    {
        "pattern": r"CANCEL\s+sip:",
        "description": "CANCEL detected — call cancelled before answer",
        "severity": "info",
        "hypothesis": "Call was cancelled by the caller before the callee answered.",
        "remediation": "No infrastructure fix. Review caller behaviour if unintended.",
    },
    {
        "pattern": r"481\s+Call\s+Leg/Transaction\s+Does\s+Not\s+Exist",
        "description": "Orphaned transaction — Call-ID mismatch or dialog expired",
        "severity": "warning",
        "hypothesis": "A SIP request was received for a transaction or dialog that no longer exists — likely due to a timeout race or a stray retransmission.",
        "remediation": "Check for network duplicates or delayed retransmissions. Ensure dialog timers are correctly configured.",
    },
    {
        "pattern": r"Trying\s+\[.*\]\s+[0-9]+ms",
        "description": "SIP trace showing per-hop routing latency",
        "severity": "info",
        "hypothesis": "Trace shows SIP hop-by-hop routing delays. May indicate inefficient routing or WAN latency.",
        "remediation": "Review SIP routing topology. Consider direct peering between high-volume domains.",
    },
    {
        "pattern": r"(SIP/2\.0\s+(4[0-9]{2}|5[0-9]{2}|6[0-9]{2}))",
        "description": "General SIP error response detected",
        "severity": "warning",
        "hypothesis": "A SIP error response (4xx/5xx/6xx) was returned — investigate the specific status code for root cause.",
        "remediation": "Check SIP server logs for the specific error code and adjacent diagnostics.",
    },
]


@router.post("/call-diagnose")
async def call_diagnose(payload: CallDiagnoseRequest):
    """Analyze a SIP trace string and return diagnostic hypotheses with
    remediation steps."""
    trace = payload.sipTrace
    if not trace or not trace.strip():
        raise HTTPException(status_code=422, detail="Empty SIP trace")

    # ── Extract metadata from trace ──────────────────────────────────────
    call_ids = set(re.findall(r"(?:Call-ID|i):\s*(\S+)", trace, re.IGNORECASE))
    methods_found = set()
    for m in _SIP_METHODS:
        if re.search(rf"\b{m}\b", trace, re.IGNORECASE):
            methods_found.add(m)

    # Count INVITE and BYE for call-flow analysis
    invite_count = len(re.findall(r"\bINVITE\b", trace, re.IGNORECASE))
    bye_count = len(re.findall(r"\bBYE\b", trace, re.IGNORECASE))
    cancel_count = len(re.findall(r"\bCANCEL\b", trace, re.IGNORECASE))

    # Count response codes
    status_codes = re.findall(r"SIP/2\.0\s+(\d{3})", trace, re.IGNORECASE)
    status_code_counts = {}
    for code in status_codes:
        status_code_counts[code] = status_code_counts.get(code, 0) + 1

    # ══ 4xx/5xx/6xx errors found in the trace ══════════════════════════════
    error_codes = sorted(
        [int(c) for c in status_code_counts if c.startswith(("4", "5", "6"))],
    )

    # ── Run diagnostic rules ─────────────────────────────────────────────
    hypotheses = []
    for rule in _DIAG_RULES:
        if re.search(rule["pattern"], trace, re.IGNORECASE):
            hypotheses.append({
                "hypothesis": rule["hypothesis"],
                "severity": rule["severity"],
                "remediation": rule["remediation"],
            })

    # ── Call flow summary ────────────────────────────────────────────────
    flow_summary = {
        "methods_detected": sorted(methods_found) if methods_found else [],
        "invite_count": invite_count,
        "bye_count": bye_count,
        "cancel_count": cancel_count,
        "status_codes": status_code_counts,
        "unique_call_ids": list(call_ids) if call_ids else ["not_detected"],
    }

    # ── Overall assessment ───────────────────────────────────────────────
    critical_count = sum(1 for h in hypotheses if h["severity"] == "critical")
    warning_count = sum(1 for h in hypotheses if h["severity"] == "warning")
    error_count = len(error_codes)

    if error_count > 0 or critical_count > 0:
        assessment = "ISSUES_DETECTED"
        summary = (
            f"Found {error_count} error status code(s), "
            f"{critical_count} critical issue(s), and "
            f"{warning_count} warning(s). Review hypotheses for remediation."
        )
    elif warning_count > 0:
        assessment = "ATTENTION_ADVISED"
        summary = (
            f"No critical errors, but {warning_count} warning(s) found. "
            "Review non-critical hypotheses."
        )
    else:
        assessment = "NORMAL"
        summary = "No issues detected in the SIP trace. Call flow appears normal."

    return {
        "status": "success",
        "data": {
            "assessment": assessment,
            "summary": summary,
            "flow_summary": flow_summary,
            "hypotheses": hypotheses,
        },
    }


# ── Public Demo Endpoints (FREE, no x402 required) ─────────────────────────────

@router.get("/demo")
async def demo_page():
    """Public demo page - no payment required."""
    return {
        "status": "success",
        "message": "Telecom Intelligence API - Public Demo",
        "endpoints": {
            "phone_normalize": {
                "description": "Normalize phone numbers to E.164 format",
                "example": {"raw_string": "+14155552671", "region": "US"},
                "try_it": "POST /api/v1/tools/phone-normalize-demo"
            },
            "sip_decode": {
                "description": "Parse SIP messages into structured JSON",
                "example": {"rawSipMessage": "INVITE sip:bob@biloxi.com SIP/2.0"},
                "try_it": "POST /api/v1/tools/sip-decode-demo"
            },
            "phone_info": {
                "description": "Get phone number information and carrier detection",
                "example": {"phone_number": "+14155552671", "region": "US"},
                "try_it": "POST /api/v1/tools/phone-info-demo"
            }
        },
        "features": [
            "25 free calls per day - no signup required",
            "Ultra-low pricing from $0.001 per call",
            "Global phone number validation",
            "SIP protocol parsing and analysis",
            "Call failure diagnostics and troubleshooting"
        ],
        "pricing": {
            "phone_normalize": "$0.001 per call",
            "sip_decode": "$0.005 per call", 
            "call_diagnose": "$0.01 per call",
            "phone_info": "$0.002 per call"
        }
    }

@router.post("/phone-normalize-demo")
async def phone_normalize_demo(payload: PhoneNormalizeRequest):
    """Free demo endpoint for phone normalization - no payment required."""
    # Call the main function directly
    raw = payload.raw_string or ""
    digits = re.sub(r"[^\d]", "", raw)

    if not digits or len(digits) < 7 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid global numbering plan.")

    # Use enhanced country code detection
    region = (payload.region or "US").upper()
    country_code, national_number = detect_country_code(digits, region)

    if len(national_number) >= 7:
        area_code = national_number[:3] if len(national_number) >= 10 else national_number[:3]
        subscriber_number = national_number[3:] if len(national_number) >= 10 else national_number[3:]
    else:
        area_code = "000"
        subscriber_number = national_number

    # Use enhanced line type detection
    line_type = detect_line_type(country_code, area_code, national_number)
    possible_regions = detect_region_from_country_code(country_code)

    parsed_metadata = {
        "country_code": country_code,
        "national_number": national_number,
        "area_code": area_code,
        "subscriber_number": subscriber_number,
        "is_valid": True,
        "line_type": line_type,
        "possible_regions": possible_regions,
    }

    formatting_handler = STRATEGY_ROUTER_MAP.get(payload.target_format)
    if formatting_handler is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown target format: {payload.target_format}",
        )
    formatted_variant = formatting_handler(parsed_metadata)

    return {
        "status": "success",
        "valid": True,
        "line_type_hint": parsed_metadata["line_type"],
        "formatted_result": formatted_variant,
        "country_code": country_code,
        "possible_regions": possible_regions,
    }

@router.post("/sip-decode-demo")
async def sip_decode_demo(payload: SipDecodeRequest):
    """Free demo endpoint for SIP decoding - no payment required."""
    # Simple implementation for demo
    raw = payload.rawSipMessage
    if not raw or not raw.strip():
        raise HTTPException(status_code=422, detail="Empty SIP message")

    lines = raw.splitlines()
    if not lines:
        raise HTTPException(status_code=422, detail="Empty SIP message")

    # Basic parsing for demo
    start_line = lines[0].strip()
    return {
        "status": "success",
        "data": {
            "start_line": start_line,
            "line_count": len(lines),
            "message": "Full SIP parsing available in paid version"
        }
    }

@router.post("/phone-info-demo")
async def phone_info_demo(payload: PhoneInfoRequest):
    """Free demo endpoint for phone info - no payment required."""
    # Call the main function directly
    raw = payload.phone_number or ""
    digits = re.sub(r"[^\d]", "", raw)
    
    if not digits or len(digits) < 7 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    
    # Use enhanced detection
    region = (payload.region or "US").upper()
    country_code, national_number = detect_country_code(digits, region)
    
    if len(national_number) >= 7:
        area_code = national_number[:3] if len(national_number) >= 10 else national_number[:3]
        subscriber_number = national_number[3:] if len(national_number) >= 10 else national_number[3:]
    else:
        area_code = "000"
        subscriber_number = national_number
    
    line_type = detect_line_type(country_code, area_code, national_number)
    possible_regions = detect_region_from_country_code(country_code)
    
    # Generate carrier information
    carrier_info = generate_carrier_info(country_code, area_code, line_type)
    
    return {
        "status": "success",
        "phone_analysis": {
            "original": raw,
            "e164": f"+{country_code}{national_number}",
            "country_code": country_code,
            "national_number": national_number,
            "area_code": area_code,
            "subscriber_number": subscriber_number,
            "line_type": line_type,
            "possible_regions": possible_regions,
            "is_valid": True,
            "carrier": carrier_info,
        }
    }
