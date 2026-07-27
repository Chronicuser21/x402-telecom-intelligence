#!/usr/bin/env python3
"""
End-to-end test of x402 payment flow with mock facilitator.
Tests: 402 → payment creation → payment verification → resource delivery.
"""
import asyncio
import os
import sys
import json
import base64

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3
from eth_account import Account
from x402 import x402Client
from x402.http import x402HTTPClient
from x402.mechanisms.evm.exact.client import ExactEvmScheme
from x402.mechanisms.evm.signers import EthAccountSigner


async def main():
    # ── Setup ──────────────────────────────────────────────────
    ANVIL_URL = "http://127.0.0.1:8545"
    w3 = Web3(Web3.HTTPProvider(ANVIL_URL))

    if not w3.is_connected():
        print("❌ Anvil not running! Start with: anvil --port 8545")
        sys.exit(1)

    # Use Anvil's first account (pre-funded with 10,000 ETH)
    ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    agent_account = Account.from_key(ANVIL_KEY)

    print("✅ Connected to Anvil")
    print(f"   Agent wallet: {agent_account.address}")
    print(f"   Agent ETH: {Web3.from_wei(w3.eth.get_balance(agent_account.address), 'ether')}")

    # ── Create x402 client ────────────────────────────────────
    print("\n📦 Creating x402 client...")

    # Wrap account as EVM signer
    signer = EthAccountSigner(agent_account)

    # Register the exact scheme
    scheme = ExactEvmScheme(signer)

    # Create client and register scheme
    client = x402Client()
    client.register(network="eip155:31337", client=scheme)

    # Create HTTP client
    http_client = x402HTTPClient(client)

    print("✅ x402 client created")

    # ── Test 1: Hit paid endpoint without payment (expect 402) ──
    print("\n🧪 Test 1: Hit paid endpoint without payment")
    import httpx

    response = httpx.get("http://localhost:8000/api/data/market")
    print(f"   Status: {response.status_code}")
    assert response.status_code == 402, f"Expected 402, got {response.status_code}"
    print("   ✅ Got 402 Payment Required")

    # ── Test 2: Decode payment requirements ──────────────────
    print("\n🧪 Test 2: Decode payment requirements")
    payment_required_b64 = response.headers.get("payment-required")
    assert payment_required_b64, "No payment-required header"
    
    requirements = json.loads(base64.b64decode(payment_required_b64))
    print(f"   x402Version: {requirements.get('x402Version')}")
    print(f"   Accepts: {len(requirements.get('accepts', []))} schemes")
    for accept in requirements.get("accepts", []):
        print(f"     - {accept.get('scheme')} on {accept.get('network')}: {accept.get('amount')}")
    print("   ✅ Payment requirements decoded")

    # ── Test 3: Create payment and send ───────────────────────
    print("\n🧪 Test 3: Create payment and send")
    try:
        # Use handle_402_response to create payment headers
        payment_headers, payload = await http_client.handle_402_response(
            dict(response.headers),
            response.content,
        )
        print(f"   Payment headers: {list(payment_headers.keys())}")
        
        # Send request with payment headers
        response = httpx.get(
            "http://localhost:8000/api/data/market",
            headers=payment_headers,
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Source: {data.get('source')}")
            print(f"   Symbols: {data.get('symbols')}")
            print("   ✅ Got market data with payment!")
        else:
            print(f"   Response: {response.text[:300]}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # ── Test 4: Test news endpoint ─────────────────────────
    print("\n🧪 Test 4: Test news endpoint")
    try:
        response = httpx.get("http://localhost:8000/api/data/news?topic=AI")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 402:
            payment_headers, payload = await http_client.handle_402_response(
                dict(response.headers),
                response.content,
            )
            
            response = httpx.get(
                "http://localhost:8000/api/data/news?topic=AI",
                headers=payment_headers,
            )
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Headlines: {len(data.get('headlines', []))}")
                print("   ✅ Got news with payment!")
            else:
                print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "="*60)
    print("✅ X402 TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
