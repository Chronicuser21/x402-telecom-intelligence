"""x402 manifest and service discovery."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import json
from pathlib import Path

router = APIRouter()

# Load manifest once at startup
_manifest_path = Path(__file__).parent.parent.parent / "x402.json"
_manifest = json.loads(_manifest_path.read_text()) if _manifest_path.exists() else {}


@router.get("/x402.json")
async def serve_manifest():
    """Serve the x402 manifest at the root (standard discovery path)."""
    return JSONResponse(content=_manifest)


@router.get("/.well-known/x402.json")
async def well_known_manifest():
    """Standard well-known path for x402 discovery."""
    return JSONResponse(content=_manifest)


@router.get("/api/v1/services")
async def list_services():
    """List available paid services with prices and descriptions."""
    endpoints = []
    for ep in _manifest.get("endpoints", []):
        endpoints.append({
            "path": ep["path"],
            "method": ep["method"],
            "description": ep["description"],
            "price": ep["price"],
            "network": _manifest["network"],
            "asset": _manifest["asset"]["symbol"],
            "payTo": _manifest["payTo"],
        })
    return {
        "name": _manifest.get("name"),
        "description": _manifest.get("description"),
        "version": _manifest.get("version"),
        "network": _manifest["network"],
        "facilitator": _manifest["facilitator"],
        "endpoints": endpoints,
    }
