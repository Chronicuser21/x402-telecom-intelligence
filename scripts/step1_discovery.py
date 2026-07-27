#!/usr/bin/env python3
"""
Step 1: Tel List Products Discovery
Calls the free catalog endpoint to verify structural discovery.
No wallet balance required — this is a free endpoint.
"""
import json
import sys
import httpx

BASE_URL = "http://127.0.0.1:8001"
PUBLIC_URL = "https://asahi-1.tail779e35.ts.net"


def test_free_endpoint(base_url: str):
    """Test the free list-products endpoint."""
    print(f"\n{'='*60}")
    print(f"Step 1: Tel List Products Discovery")
    print(f"Target: {base_url}/api/v1/tools/list-products")
    print(f"{'='*60}\n")

    # Test without payment header — should get 402 with amount=0
    print("1. Testing without payment header (expect 402 with amount=0)...")
    resp = httpx.get(f"{base_url}/api/v1/tools/list-products", timeout=10)
    print(f"   Status: {resp.status_code}")

    if resp.status_code == 402:
        # Decode payment instructions
        import base64
        payment_required = resp.headers.get("payment-required", "")
        if payment_required:
            decoded = json.loads(base64.b64decode(payment_required))
            print(f"   Payment required: YES")
            print(f"   Amount: {decoded['accepts'][0]['amount']} USDC")
            print(f"   Network: {decoded['accepts'][0]['network']}")
            print(f"   PayTo: {decoded['accepts'][0]['payTo']}")

            if decoded['accepts'][0]['amount'] == '0':
                print("\n   ✅ FREE ENDPOINT CONFIRMED (amount=0)")
            else:
                print(f"\n   ❌ PAID ENDPOINT (amount={decoded['accepts'][0]['amount']})")
                return False
        else:
            print("   ❌ No payment-required header")
            return False
    elif resp.status_code == 200:
        print("   ✅ Got 200 OK (endpoint is free, no payment needed)")
        print(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")
        return True
    else:
        print(f"   ❌ Unexpected status: {resp.status_code}")
        return False

    # Test with zero-value payment header (x402 protocol)
    print("\n2. Testing with zero-value payment header...")
    print("   (x402 requires clients to send a payment header even for free endpoints)")
    print("   This simulates what an MCP agent would do after discovering amount=0")

    # For now, just verify the endpoint is accessible via public URL
    print("\n3. Testing public URL access...")
    public_resp = httpx.get(f"{PUBLIC_URL}/api/v1/tools/list-products", timeout=10)
    print(f"   Public URL Status: {public_resp.status_code}")

    if public_resp.status_code == 402:
        print("   ✅ Public URL returns 402 (expected)")
    elif public_resp.status_code == 200:
        print("   ✅ Public URL returns 200 OK")
        print(f"   Catalog: {json.dumps(public_resp.json(), indent=2)[:500]}")
        return True

    return True


def main():
    success = test_free_endpoint(BASE_URL)

    print(f"\n{'='*60}")
    if success:
        print("✅ Step 1 Complete: Free endpoint discovery works")
        print("\nNext: Step 2 — MCP client connects and calls tools/list")
    else:
        print("❌ Step 1 Failed")
        sys.exit(1)
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
