# Render Deployment Guide for Real x402 Payments

## Prerequisites

1. **CDP API Keys**: Get from https://portal.cdp.coinbase.com/settings/api-keys
2. **ETH in Wallet**: Ensure your payTo wallet has ETH for gas fees on Base Mainnet
3. **Render Account**: Active Render.com account

## Step 1: Add ETH to PayTo Wallet

Your payTo wallet needs ETH to process x402 payments on Base Mainnet:

**Wallet Address**: `0xD333941784201caC6C3c082D9BEef22EFefe4750`

**How to add ETH**:
- Bridge from Ethereum to Base
- Use Base faucet (if available)
- Exchange and transfer to Base network
- Minimum amount: 0.001 ETH

**Check balance**: 
```bash
curl -s https://mainnet.base.org \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "eth_getBalance",
    "params": ["0xD333941784201caC6C3c082D9BEef22EFefe4750", "latest"],
    "id": 1
  }'
```

## Step 2: Get CDP API Keys

1. Go to https://portal.cdp.coinbase.com/settings/api-keys
2. Create new API keys for x402 services
3. Copy the API key and secret
4. These keys enable real payment processing through CDP Facilitator

## Step 3: Configure Render Environment Variables

Go to your Render service dashboard and add these environment variables:

### Payment Configuration
- `CDP_API_KEY`: Your CDP API key from step 2
- `CDP_API_SECRET`: Your CDP API secret from step 2
- `PAY_TO_ADDRESS`: `0xD333941784201caC6C3c082D9BEef22EFefe4750`
- `NETWORK`: `eip155:8453`
- `SERVICE_URL`: `https://x402-telecom-intelligence.onrender.com`

### Server Configuration
- `PORT`: `8000`
- `LOG_LEVEL`: `info`

## Step 4: Deploy and Test

1. Deploy your service on Render with the new environment variables
2. Test the service is running: `https://x402-telecom-intelligence.onrender.com/`
3. Test health endpoint: `https://x402-telecom-intelligence.onrender.com/api/v1/tools/health`

## Step 5: Enable Bazaar Indexing

Once you have CDP API keys configured and ETH in your wallet:

1. **Test a real payment** through one of the paid endpoints
2. **Include paymentPayload.resource** in the payment payload
3. **Wait for settlement** to complete successfully
4. **Service will be automatically indexed** in CDP Bazaar discovery

### Test Payment

Use the x402 client to test a real payment:

```python
from x402 import Client

client = Client("0xD333941784201caC6C3c082D9BEef22EFefe4750")

# Test phone-info endpoint
response = client.call(
    url="https://x402-telecom-intelligence.onrender.com/api/v1/tools/phone-info",
    method="POST",
    data={"phone_number": "+14155552671"},
    network="eip155:8453",
    asset="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
```

## Step 6: Verify Bazaar Listing

After successful payment settlement, check if your service is indexed:

```bash
curl "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?payTo=0xD333941784201caC6C3c082D9BEef22EFefe4750"
```

## Troubleshooting

### Service Falls Back to Mock Facilitator
- **Issue**: CDP API keys not configured correctly
- **Solution**: Check environment variables are set correctly on Render

### Payment Fails Due to No Gas
- **Issue**: PayTo wallet has 0 ETH
- **Solution**: Add ETH to wallet address `0xD333941784201caC6C3c082D9BEef22EFefe4750`

### Not Indexed in Bazaar
- **Issue**: No successful payment settlement yet
- **Solution**: Complete at least one real payment through CDP Facilitator

### Payment Settlement Timeout
- **Issue**: Network congestion or gas price too low
- **Solution**: Wait for settlement or adjust gas price

## Network Configuration

- **Network**: Base Mainnet (eip155:8453)
- **Asset**: USDC (0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
- **Facilitator**: https://api.cdp.coinbase.com/platform/v2/x402
- **Chain ID**: 8453
- **Explorer**: https://basescan.org

## Current Pricing

- **phone-normalize**: FREE
- **sip-decode**: $0.01 USDC
- **call-diagnose**: $0.02 USDC
- **phone-info**: $0.005 USDC
- **fraud-detection**: $0.03 USDC
- **billing-intelligence**: $0.02 USDC