"""x402 Agent Service — Configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is loaded from environment / .env file."""

    # --- x402 / Wallet ---
    evm_private_key: str = ""
    pay_to_address: str = ""
    network: str = "eip155:8453"  # Base Sepolia default
    facilitator_url: str = "https://x402.org/facilitator"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    # --- Dashboard ---
    dashboard_secret: str = "changeme"

    # --- Pricing (USDC) ---
    price_data: str = "$0.001"
    price_analysis: str = "$0.01"
    price_search: str = "$0.005"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
