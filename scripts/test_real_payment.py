#!/usr/bin/env python3
"""Real x402 payment test — Base Mainnet with actual USDC.

Tests the live telecom forensics gateway via x402 HTTP payment flow.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

BASE_URL = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8001")
PRIVATE_KEY = os.getenv("EVM_PRIVATE_KEY", "80b241a71f4389eaaa64689490bcec0af31232286af89e8742ba45ecc7628d46")
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base Mainnet USDC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("test-payment")


def check_balance():
    from eth_account import Account
    from web3 import Web3
    account = Account.from_key(PRIVATE_KEY)
    w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))

    eth_bal = float(Web3.from_wei(w3.eth.get_balance(account.address), "ether"))

    erc20 = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]')
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=erc20)
    usdc_bal = usdc.functions.balanceOf(account.address).call() / 1e6

    return account.address, eth_bal, usdc_bal


async def make_payment_request(client, method, path, body=None):
    url = f"{BASE_URL}{path}"
    resp = await client.request(method, url, json=body)

    if resp.status_code == 402:
        log.info("402 received — signing payment...")
        from x402 import x402Client
        from x402.http import x402HTTPClient
        from eth_account import Account
        from x402.mechanisms.evm.exact import register_exact_evm_client

        account = Account.from_key(PRIVATE_KEY)
        x_client = x402Client()
        register_exact_evm_client(x_client, signer=account)
        x_http = x402HTTPClient(x_client)

        payment_headers, _ = await x_http.handle_402_response(
            headers=dict(resp.headers),
            body=resp.content,
        )

        headers = {"Content-Type": "application/json"}
        headers.update(payment_headers)
        resp = await client.request(method, url, json=body, headers=headers)

        settle = x_http.get_payment_settle_response(
            get_header=lambda name: resp.headers.get(name)
        )
        if settle:
            log.info("Settlement: success=%s, tx=%s", settle.success,
                     (settle.transaction[:20] + "...") if settle.transaction else "pending")

    return resp


async def main():
    address, eth, usdc = check_balance()
    print(f"\nWallet: {address}")
    print(f"  ETH:  {eth:.6f}")
    print(f"  USDC: {usdc:.6f}")

    if eth < 0.0001:
        print("\nNeed ETH for gas!")
        sys.exit(1)
    if usdc < 0.05:
        print("\nNeed USDC for payments!")
        sys.exit(1)

    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n--- Phone Normalize ($0.001) ---")
        resp = await make_payment_request(client, "POST", "/api/v1/tools/phone-normalize",
                                          {"phone": "+15551234567"})
        print(f"Status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2)[:300])

        print("\n--- SIP Decode ($0.02) ---")
        resp = await make_payment_request(client, "POST", "/api/v1/tools/sip-decode",
                                          {"rawSipMessage": "INVITE sip:bob@biloxi.com SIP/2.0\r\nVia: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK776asdhds\r\nTo: <sip:bob@biloxi.com>\r\nFrom: <sip:alice@atlanta.com>;tag=1928301774\r\nCall-ID: a84b4c76e66710@pc33.atlanta.com\r\nCSeq: 314159 INVITE\r\nContact: <sip:alice@pc33.atlanta.com>\r\nContent-Type: application/sdp\r\nContent-Length: 142\r\n\r\nv=0\r\no=- 53655765 2353687637 IN IP4 pc33.atlanta.com\r\ns=-\r\nc=IN IP4 pc33.atlanta.com\r\nt=0 0\r\nm=audio 49170 RTP/AVP 0 97\r\na=rtpmap:0 PCMU/8000\r\n"})
        print(f"Status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2)[:500])

    print("\nDone! Real USDC spent on Base Mainnet.")


if __name__ == "__main__":
    asyncio.run(main())
