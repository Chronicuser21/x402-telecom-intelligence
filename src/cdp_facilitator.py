"""
CDP Facilitator Client with Ed25519 JWT auth.

Wraps HTTPFacilitatorClient and injects CDP JWT auth headers.
Transforms CDP response format to match x402 SupportedResponse schema.
"""

import base64
import json
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from x402.http.facilitator_client import HTTPFacilitatorClient, FacilitatorConfig
from x402.schemas.responses import SupportedResponse, SupportedKind


CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _generate_jwt(
    api_key: str,
    private_key: Ed25519PrivateKey,
    host: str,
    path: str,
    method: str = "POST",
    ttl: int = 120,
) -> str:
    """Generate Ed25519 JWT for CDP API auth."""
    now = int(time.time())
    nonce = os.urandom(16).hex()

    header = {"alg": "EdDSA", "kid": api_key, "typ": "JWT", "nonce": nonce}
    claims = {
        "sub": api_key,
        "iss": "cdp",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + ttl,
        "iat": now,
        "uris": [f"{method} {host}{path}"],
    }

    h = _b64url(json.dumps(header).encode())
    p = _b64url(json.dumps(claims).encode())
    sig = private_key.sign(f"{h}.{p}".encode())
    return f"{h}.{p}.{_b64url(sig)}"


def _transform_cdp_supported(raw: dict) -> SupportedResponse:
    """Transform CDP 'networks' response into x402 'kinds' SupportedResponse."""
    kinds = []
    for net in raw.get("networks", []):
        chain_id = net.get("chainId")
        network = f"eip155:{chain_id}" if chain_id else net.get("network", "unknown")
        for asset in net.get("assets", []):
            kinds.append(SupportedKind(
                x402_version=2,
                scheme="exact",
                network=network,
            ))
    # Also include raw 'kinds' if present (some CDP responses use x402 format)
    for k in raw.get("kinds", []):
        kinds.append(SupportedKind(
            x402_version=k.get("x402Version", 2),
            scheme=k.get("scheme", "exact"),
            network=k.get("network", "unknown"),
        ))
    return SupportedResponse(kinds=kinds)


class CDPFacilitatorClient(HTTPFacilitatorClient):
    """HTTP Facilitator Client with CDP JWT authentication.

    Inherits from HTTPFacilitatorClient and overrides header methods
    to inject CDP JWT auth headers per-endpoint.
    """

    def __init__(self, api_key: str, api_secret_b64: str, url: str = CDP_FACILITATOR_URL):
        # Parse Ed25519 key FIRST (needed by _jwt_headers)
        decoded = base64.b64decode(api_secret_b64)
        if len(decoded) != 64:
            raise ValueError(f"Expected 64-byte Ed25519 key, got {len(decoded)}")
        self._private_key = Ed25519PrivateKey.from_private_bytes(decoded[:32])
        self._api_key = api_key

        # Parse URL
        parsed = urlparse(url)
        self._cdp_host = parsed.hostname or "api.cdp.coinbase.com"
        self._cdp_base_path = parsed.path.rstrip("/")

        # Init parent (no config.auth_provider — we inject headers ourselves)
        config = FacilitatorConfig(url=url, timeout=30.0)
        super().__init__(config)

        # Pre-fetch supported (required by resource server init)
        self._supported = self.get_supported()

    def _jwt_headers(self, endpoint: str, method: str = "POST") -> dict[str, str]:
        """Generate auth headers for a specific CDP endpoint."""
        path = f"{self._cdp_base_path}/{endpoint}"
        jwt = _generate_jwt(self._api_key, self._private_key, self._cdp_host, path, method)
        return {
            "Authorization": f"Bearer {jwt}",
            "Correlation-Context": "sdkLanguage=python,source=cdp-sdk",
        }

    def get_supported(self) -> SupportedResponse:
        """Get supported payment schemes with CDP auth.

        CDP returns {'networks': [...]} format.
        We transform to {'kinds': [...]} for x402 compatibility.
        """
        headers = self._jwt_headers("supported", "GET")
        r = httpx.get(
            f"{self._url}/supported",
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
        )
        r.raise_for_status()
        raw = r.json()
        return _transform_cdp_supported(raw)

    def _get_verify_headers(self) -> dict[str, str]:
        """Override: CDP auth for verify requests."""
        base = {"Content-Type": "application/json"}
        base.update(self._jwt_headers("verify"))
        return base

    def _get_settle_headers(self) -> dict[str, str]:
        """Override: CDP auth for settle requests."""
        base = {"Content-Type": "application/json"}
        base.update(self._jwt_headers("settle"))
        return base
