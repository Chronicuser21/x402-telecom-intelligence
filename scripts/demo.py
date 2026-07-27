#!/usr/bin/env python3
"""Demo script: start server + run agent client against it.

Usage:
    # Terminal 1: Start the server
    uv run python scripts/demo.py server

    # Terminal 2: Run the agent client
    uv run python scripts/demo.py client

    # Or run both in sequence (server in background):
    uv run python scripts/demo.py both
"""
import asyncio
import json
import os
import subprocess
import sys
import time

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = os.environ.get("PORT", "8000")
BASE_URL = f"http://{HOST}:{PORT}"


def start_server():
    """Start the FastAPI server in the background."""
    print("🚀 Starting x402 Agent Service...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", HOST, "--port", PORT],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    print(f"   Server PID: {proc.pid}")
    print(f"   URL: {BASE_URL}")
    print(f"   Docs: {BASE_URL}/docs")
    time.sleep(3)
    return proc


async def run_client():
    """Run the agent client against the server."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.client.agent import X402AgentClient

    client = X402AgentClient(base_url=BASE_URL, agent_id="demo-telecom-agent", demo_mode=True)

    print("\n🤖 Running Telecom Intelligence agent client against live server...\n")

    # 1. Discover Tool Catalog (Free)
    print("📡 Discovering Tool Catalog (Free)...")
    catalog = await client.get_tool_catalog()
    print(json.dumps(catalog, indent=2))
    print()

    # 2. Engine Health Check (Free)
    print("🩺 Checking Engine Health (Free)...")
    health = await client.check_engine_health()
    print(json.dumps(health, indent=2))
    print()

    # 3. Phone Normalization ($0.01)
    print("📞 Normalizing Phone Number ($0.01)...")
    phone_res = await client.normalize_phone("+1 (415) 555-2671", region="US")
    print(json.dumps(phone_res, indent=2))
    print()

    # 4. SIP Packet Decoding ($0.05)
    print("🔍 Decoding Raw SIP Message ($0.05)...")
    sample_sip = (
        "INVITE sip:bob@biloxi.com SIP/2.0\r\n"
        "v: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK776asdhds\r\n"
        "f: Alice <sip:alice@atlanta.com>;tag=1928301774\r\n"
        "t: Bob <sip:bob@biloxi.com>\r\n"
        "i: a84b4c76e66710@pc33.atlanta.com\r\n"
        "CSeq: 314159 INVITE\r\n"
        "Content-Length: 0"
    )
    sip_res = await client.decode_sip_packet(sample_sip)
    print(json.dumps(sip_res, indent=2))
    print()

    # 5. Call Drop Diagnosis ($0.20)
    print("🩺 Running Call Drop Diagnostics ($0.20)...")
    sample_trace = (
        "INVITE sip:bob@biloxi.com SIP/2.0\r\n"
        "Call-ID: trace-9988-abc\r\n"
        "SIP/2.0 100 Trying\r\n"
        "SIP/2.0 487 Request Terminated\r\n"
    )
    diag_res = await client.diagnose_call_trace(sample_trace)
    print(json.dumps(diag_res, indent=2))
    print()

    print(f"💰 Total agent spend: ${client.total_spent:.6f} USDC")
    await client.close()


def run_both():
    """Start server, run client, stop server."""
    proc = start_server()
    try:
        asyncio.run(run_client())
    finally:
        proc.terminate()
        proc.wait()
        print("\n🛑 Server stopped")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode == "server":
        proc = start_server()
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
    elif mode == "client":
        asyncio.run(run_client())
    elif mode == "both":
        run_both()
    else:
        print(f"Usage: {sys.argv[0]} [server|client|both]")
