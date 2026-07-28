#!/usr/bin/env python3
"""Final automated x402 payment using x402 httpx client with CDP facilitator"""
import asyncio
import json
from eth_account import Account
from x402 import x402Client
from x402.http import HTTPFacilitatorClient, FacilitatorConfig
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client
from x402.http.clients import x402HttpxClient

# Private key
PRIVATE_KEY = "58b8cadb5dd3b6fd76f25d08f2d103ff9fde04ad70ce0cc34a1f5c824a446b87"

SERVICE_URL = "https://x402-telecom-intelligence.onrender.com/api/v1/tools/phone-info"
PAY_TO_ADDRESS = "0xCd1219753686FD4f0f2DBEa80896ba2716138F95"

async def make_final_payment():
    """Make final automated x402 payment"""
    
    # Setup x402 client with CDP facilitator
    client = x402Client()
    
    # Setup CDP facilitator
    from src.cdp_facilitator import CDPFacilitatorClient
    facilitator = CDPFacilitatorClient(
        api_key="29de2b4d-3e88-4268-9614-f842b43aa0cf",
        api_secret_b64="kyh9XHwHTjO98flQeJU4UAHjK+sCBhluawIPThtwQl2Efkm2HeqvdqHi9QFwuKJxcThZsDTwA7/aAutTVSTUfQ=="
    )
    
    # Register EVM payments with private key signer
    account = Account.from_key(PRIVATE_KEY)
    register_exact_evm_client(client, EthAccountSigner(account))
    
    print(f"Using account: {account.address}")
    print(f"Service URL: {SERVICE_URL}")
    print(f"Payment to: {PAY_TO_ADDRESS}")
    print("CDP facilitator initialized")
    
    # Test data
    payload = {
        "phone_number": "+14155552671"
    }
    
    # Make request with automatic payment handling
    print("Making request with automatic x402 payment handling...")
    async with x402HttpxClient(client) as http:
        try:
            response = await http.post(
                SERVICE_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
            
            # Print all response headers for debugging
            print(f"Response headers: {dict(response.headers)}")
            
            return response
            
        except Exception as e:
            print(f"❌ Request failed: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == "__main__":
    asyncio.run(make_final_payment())