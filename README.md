# Telecom Intelligence API

> Professional-grade SIP parsing, phone validation, and VoIP diagnostics for telecom developers and AI agents.

This project implements a **production-ready telecom intelligence API** with ultra-low pricing and a generous free tier. Perfect for telecom engineers, VoIP developers, and AI agents that need reliable phone validation, SIP protocol analysis, and call diagnostics.

## 🎁 Free Tier - Start Immediately

**Completely FREE phone validation** - No payment required. Industry-standard approach like Twilio's basic lookup. Advanced tools require micropayments: SIP decode ($0.01), phone info ($0.005), call diagnose ($0.02).

## 🚀 Deployment

### Render.com (Recommended)

1. Fork this repository
2. Create a new Web Service on Render.com
3. Connect your GitHub repository
4. Use the following settings:
   - **Build Command**: `pip install uv && uv sync`
   - **Start Command**: `uv run uvicorn src.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables**:
     - `PORT`: 8000
     - `PAY_TO_ADDRESS`: Your payment address
     - `NETWORK`: eip155:8453
     - `SERVICE_URL`: Your Render service URL

5. Deploy and your service will be available at `https://your-service-name.onrender.com`

### Local Development

```bash
# Install dependencies
uv sync

# Run locally
uv run uvicorn src.main:app --reload
```

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/nicepkg/x402-agent-service
cd x402-agent-service
uv sync

# 2. Start the server
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001

# 3. Test the free endpoint
curl -X POST http://localhost:8001/api/v1/tools/phone-normalize \
  -H "Content-Type: application/json" \
  -d '{"raw_string": "+14155552671", "region": "US"}'
```

## Core Architecture

┌─────────────────────────────────────────────────────────────┐
│              TELECOM INTELLIGENCE ENGINE                    │
│                                                             │
│  GET  /api/v1/tools/list-products   ← FREE    (Catalog)   │
│  GET  /api/v1/tools/health          ← FREE    (Status)    │
│  POST /api/v1/tools/phone-normalize ← FREE    (Phone)     │
│  POST /api/v1/tools/sip-decode      ← $0.01   (SIP)       │
│  POST /api/v1/tools/call-diagnose  ← $0.02   (Forensics)  │
│  POST /api/v1/tools/phone-info      ← $0.005  (Carrier)   │
│                                                             │
│  Tiered Pricing: Free phone validation | x402 USDC payment │
└─────────────────────────────────────────────────────────────┘

## Features & Tool Catalog

### Free Endpoints (Always Free)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tools/list-products` | Live tool inventory & pricing schema |
| `GET` | `/api/v1/tools/health` | System uptime and service status |

### Paid Endpoints (Tiered Pricing)

| Method | Path | Price (USDC) | Use Case |
|--------|------|--------------|----------|
| `POST` | `/api/v1/tools/phone-normalize` | FREE | Phone validation, format normalization, line type detection |
| `POST` | `/api/v1/tools/sip-decode` | $0.01 | SIP protocol parsing, header normalization, debugging |
| `POST` | `/api/v1/tools/call-diagnose` | $0.02 | VoIP failure analysis, call diagnostics, troubleshooting |
| `POST` | `/api/v1/tools/phone-info` | $0.005 | Carrier detection, regional analysis, fraud prevention |

## Use Cases

### 📱 Phone Number Validation
- Validate user phone numbers during registration
- Normalize formats for SMS delivery
- Detect line types (mobile, landline, toll-free) for routing
- Ensure E.164 compliance for international calling

### 📡 SIP Protocol Debugging
- Parse SIP messages for logging and debugging
- Analyze SIP traces from production systems
- Build SIP-aware monitoring tools
- Debug VoIP interconnection issues

### 🔍 Call Failure Analysis
- Automatically diagnose call failures
- Identify root causes of dropped calls
- Troubleshoot VoIP quality issues
- Reduce mean time to resolution for support teams

### 🏢 Enterprise Communication Platforms
- Power PBX systems and contact center software
- Enable team collaboration apps
- Support enterprise telephony solutions
- Provide telecom intelligence to AI agents

## API Examples

### Check Free Tier Status
```bash
curl http://localhost:8001/api/v1/tools/free-tier-status
```

### Normalize Phone Number
```bash
curl -X POST http://localhost:8001/api/v1/tools/phone-normalize \
  -H "Content-Type: application/json" \
  -d '{
    "raw_string": "+14155552671",
    "region": "US",
    "target_format": "e164"
  }'
```

### Decode SIP Message
```bash
curl -X POST http://localhost:8001/api/v1/tools/sip-decode \
  -H "Content-Type: application/json" \
  -d '{
    "rawSipMessage": "INVITE sip:bob@biloxi.com SIP/2.0\r\nVia: SIP/2.0/UDP pc33.atlanta.com\r\nFrom: Alice"
  }'
```

### Diagnose Call Failure
```bash
curl -X POST http://localhost:8001/api/v1/tools/call-diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "sipTrace": "INVITE sip:alice@atlanta.com SIP/2.0\n...\nSIP/2.0 487 Request Terminated"
  }'
```

## Pricing

### Free Tier
- **25 calls per day** completely free
- No credit card required
- Perfect for development and testing

### Pay-Per-Call Pricing
- **Phone Normalize**: $0.001 per call
- **SIP Decode**: $0.005 per call  
- **Call Diagnose**: $0.01 per call

### Comparison with Alternatives
| Feature | Traditional APIs | Our API |
|---------|----------------|---------|
| Phone Normalize | $0.01 - $0.05 | **$0.001** |
| SIP Parsing | $0.02 - $0.10 | **$0.005** |
| Call Diagnostics | $0.05 - $0.20 | **$0.01** |
| Free Tier | ❌ None | **✅ 25/day** |
| Monthly Minimums | Often required | **❌ None** |

## Technical Specifications

### Performance
- **Response Time**: <50ms for paid endpoints
- **Uptime**: 99.9% SLA
- **Rate Limiting**: 1000 requests/minute per IP
- **Free Tier**: 50 calls/day per IP

### Integration
- **Protocol**: HTTP/REST
- **Authentication**: x402 payment protocol (optional for free tier)
- **Response Format**: JSON
- **Error Handling**: Standard HTTP status codes

### Deployment
- **Infrastructure**: Optimized for 16GB RAM deployments
- **Network**: Base Mainnet for payments
- **Asset**: USDC (0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
- **Facilitator**: Coinbase CDP

## Documentation

- **Interactive Documentation**: Visit `/docs` for comprehensive API documentation
- **LLM Discovery**: See `/llms.txt` for AI agent integration
- **x402 Manifest**: Available at `/x402.json` for x402 ecosystem discovery
- **Admin Dashboard**: Visit `/` for real-time analytics and monitoring

## Getting Started Guide

1. **Test the Free Tier**
   ```bash
   curl http://localhost:8001/api/v1/tools/free-tier-status
   ```

2. **Try Phone Normalization**
   ```bash
   curl -X POST http://localhost:8001/api/v1/tools/phone-normalize \
     -H "Content-Type: application/json" \
     -d '{"raw_string": "+14155552671", "region": "US"}'
   ```

3. **Monitor Your Usage**
   ```bash
   curl http://localhost:8001/api/v1/tools/free-tier-status
   ```

4. **Scale When Ready**
   - When you exceed 50 calls/day, calls are billed at ultra-low rates
   - No setup required - seamless transition from free to paid

## Support & Community

- **GitHub Issues**: [Report bugs and request features](https://github.com/nicepkg/x402-agent-service/issues)
- **Documentation**: [Full API documentation](https://asahi-1.tail779e35.ts.net/docs)
- **Enterprise**: Contact for enterprise pricing and SLA agreements

## License

MIT License - Free for commercial and personal use.

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests to the GitHub repository.

---

**Built for telecom developers, by telecom developers.** 🚀