#!/usr/bin/env python3
"""Test script to make a real x402 payment to the phone-info endpoint"""
import os
import json
import requests
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402 import x402Client, PaymentPayload

# CDP credentials  
CDP_API_KEY = "29de2b4d-3e88-4268-9614-f842b43aa0cf"
CDP_API_SECRET = "kyh9XHwHTjO98flQeJU4UAHjK+sCBhluawIPThtwQl2Efkm2HeqvdqHi9QFwuKJxcThZsDTwA7/aAutTVSTUfQ=="

# Your service endpoint
SERVICE_URL = "https://x402-telecom-intelligence.onrender.com/api/v1/tools/phone-info"

# Your wallet address (from environment)
PAY_TO_ADDRESS = "0xD333941784201caC6C3c082D9BEef22EFefe4750"

def test_real_payment():
    """Test making a real x402 payment"""
    
    # Test data
    payload = {
        "phone_number": "+14155552671"
    }
    
    print(f"Making real x402 payment to {SERVICE_URL}")
    print(f"Payload: {payload}")
    print(f"Pay to: {PAY_TO_ADDRESS}")
    
    try:
        # First, make the initial request to get payment requirements
        response = requests.post(SERVICE_URL, json=payload)
        print(f"Initial response status: {response.status_code}")
        print(f"Response text: {response.text[:200]}")
        
        if response.status_code == 402:
            print("Payment required response received")
            payment_required = response.headers.get('payment-required')
            if payment_required:
                print(f"Payment required header: {payment_required[:100]}...")
                
                # Parse the payment requirements
                from x402 import parse_payment_required
                payment_req = parse_payment_required(payment_required)
                print(f"Payment requirements: {payment_req}")
                
                # For now, just show what we got
                print("This is a 402 Payment Required response")
                print("To complete the payment, we need to sign and submit payment")
                print("This requires a wallet with funds on Base Mainnet")
                return payment_req
            else:
                print("No payment-required header found")
                return None
        elif response.status_code == 500:
            print("Internal Server Error - Render deployment may not have CDP keys configured")
            print("Check Render environment variables")
            return None
        else:
            print(f"Unexpected response: {response.status_code}")
            return response.text
        
    except Exception as e:
        print(f"❌ Payment failed: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    test_real_payment()