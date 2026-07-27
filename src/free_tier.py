"""Free tier middleware for x402 agent service.

Provides a daily free allowance for testing and development.
Tracks usage by IP address and allows up to FREE_CALLS_PER_DAY requests.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Free tier configuration - DISABLED since phone-normalize is completely free
FREE_CALLS_PER_DAY = 0  # Disabled
FREE_TIER_PATHS = set()  # No paths use free tier


class FreeTierTracker:
    """Tracks free tier usage by IP address with daily reset."""
    
    def __init__(self, storage_dir: str = "./data/free_tier"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._usage_file = self.storage_dir / "usage.json"
        self._usage_data = self._load_usage()
    
    def _load_usage(self) -> dict:
        """Load usage data from disk."""
        if self._usage_file.exists():
            try:
                return json.loads(self._usage_file.read_text())
            except Exception:
                return {}
        return {}
    
    def _save_usage(self) -> None:
        """Save usage data to disk."""
        self._usage_file.write_text(json.dumps(self._usage_data, indent=2))
    
    def _get_today_key(self) -> str:
        """Get today's date key for daily reset."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    def _cleanup_old_days(self) -> None:
        """Remove usage data from previous days."""
        today = self._get_today_key()
        for key in list(self._usage_data.keys()):
            if key != today:
                del self._usage_data[key]
        self._save_usage()
    
    def get_usage(self, identifier: str) -> int:
        """Get usage count for an identifier today."""
        self._cleanup_old_days()
        today = self._get_today_key()
        if today not in self._usage_data:
            self._usage_data[today] = {}
        return self._usage_data[today].get(identifier, 0)
    
    def increment_usage(self, identifier: str) -> int:
        """Increment usage count and return new count."""
        self._cleanup_old_days()
        today = self._get_today_key()
        if today not in self._usage_data:
            self._usage_data[today] = {}
        self._usage_data[today][identifier] = self._usage_data[today].get(identifier, 0) + 1
        self._save_usage()
        return self._usage_data[today][identifier]
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if identifier is within free tier limit."""
        return self.get_usage(identifier) < FREE_CALLS_PER_DAY
    
    def get_remaining(self, identifier: str) -> int:
        """Get remaining free calls for identifier."""
        return max(0, FREE_CALLS_PER_DAY - self.get_usage(identifier))


# Global tracker instance
_tracker = FreeTierTracker()


class FreeTierMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce free tier limits."""
    
    def __init__(self, app):
        super().__init__(app)
        self.tracker = _tracker
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get real IP from various headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to client host
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with free tier logic."""
        request_path = request.url.path
        
        # Only apply to paid endpoints
        if request_path not in FREE_TIER_PATHS:
            return await call_next(request)
        
        # Get client identifier
        identifier = self._get_client_identifier(request)
        
        # Check if payment is being made (skip free tier check)
        payment_header = request.headers.get("X-Payment") or request.headers.get("x-payment")
        if payment_header and payment_header != "demo":
            # Paid request, let it through to payment middleware
            return await call_next(request)
        
        # Check free tier allowance
        if self.tracker.is_allowed(identifier):
            # Within free tier, handle request directly and bypass payment middleware completely
            remaining = self.tracker.increment_usage(identifier)
            
            # Import the route handlers to call them directly
            import json
            from fastapi.responses import JSONResponse
            
            body_bytes = await request.body()
            payload = json.loads(body_bytes) if body_bytes else {}
            
            # Call the appropriate route handler directly
            if request_path == "/api/v1/tools/phone-normalize":
                from src.routes.telecom import phone_normalize, PhoneNormalizeRequest
                req_obj = PhoneNormalizeRequest(**payload)
                res_data = await phone_normalize(req_obj)
                response = JSONResponse(content=res_data)
            elif request_path == "/api/v1/tools/sip-decode":
                from src.routes.telecom import sip_decode, SipDecodeRequest
                req_obj = SipDecodeRequest(**payload)
                res_data = await sip_decode(req_obj)
                response = JSONResponse(content=res_data)
            elif request_path == "/api/v1/tools/call-diagnose":
                from src.routes.telecom import call_diagnose, CallDiagnoseRequest
                req_obj = CallDiagnoseRequest(**payload)
                res_data = await call_diagnose(req_obj)
                response = JSONResponse(content=res_data)
            elif request_path == "/api/v1/tools/phone-info":
                from src.routes.telecom import phone_info, PhoneInfoRequest
                req_obj = PhoneInfoRequest(**payload)
                res_data = await phone_info(req_obj)
                response = JSONResponse(content=res_data)
            else:
                # Not a paid endpoint, continue normally
                return await call_next(request)
            
            # Add free tier headers
            response.headers["X-Free-Tier"] = "true"
            response.headers["X-Free-Tier-Remaining"] = str(remaining - 1)
            
            return response
        else:
            # Exceeded free tier, let payment middleware handle it normally
            return await call_next(request)


def get_free_tier_stats(identifier: str) -> dict:
    """Get free tier statistics for an identifier."""
    return {
        "used": _tracker.get_usage(identifier),
        "remaining": _tracker.get_remaining(identifier),
        "limit": FREE_CALLS_PER_DAY,
        "reset_date": _tracker._get_today_key(),
    }