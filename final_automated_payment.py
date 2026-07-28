#!/usr/bin/env python3
"""Final automated x402 payment using vanilla x402 Python SDK"""
import asyncio
import json
from eth_account import Account
from x402 import x402Client
from x402.http import HTTPFacilitatorClient, FacilitatorConfig
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.http.clients import x402HttpxClient

# Private key
PRIVATE_KEY = "58b8cadb5dd3b6fd76f25d08f2d103ff9fde04ad70ce0cc34a1f5c824a446b87"

SERVICE_URL = "https://x402-telecom-intelligence.onrender.com/api/v1/tools/phone-info"
PAY_TO_ADDRESS = "0xCd1219753686FD4f0f2DBEa80896ba2716138F95"

async def make_final_payment():
    """Make final automated x402 payment using vanilla x402 SDK"""
    
    # Setup x402 client with proper scheme
    client = x402Client()
    
    # Register EVM payments with private key signer
    account = Account.from_key(PRIVATE_KEY)
    client.register("eip155:8453", ExactEvmScheme(signer=EthAccountSigner(account)))
    
    print(f"Using account: {account.address}")
    print(f"Service URL: {SERVICE_URL}")
    print(f"Payment to: {PAY_TO_ADDRESS}")
    print("x402 client initialized with ExactEvmScheme")
    
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