"""Local mock facilitator and EVM scheme for testing x402 without real chain."""
from x402.facilitator import (
    VerifyResponse,
    SettleResponse,
)
from x402.http.facilitator_client_base import FacilitatorClient
from x402.schemas import SupportedResponse, SupportedKind
from x402 import SchemeNetworkServer, AssetAmount, PaymentRequirements
import os
from web3 import Web3


class MockFacilitatorClient(FacilitatorClient):
    """Always-valid facilitator for local testing."""

    def __init__(self):
        self._supported = SupportedResponse(
            kinds=[
                SupportedKind(
                    x402_version=2,
                    scheme="exact",
                    network="eip155:31337",
                )
            ]
        )

    def get_supported(self) -> SupportedResponse:
        return self._supported

    def verify(self, payload, requirements) -> VerifyResponse:
        print(f"[MockFacilitator] verify: {payload}")
        return VerifyResponse(
            is_valid=True,
            payer="0x0000000000000000000000000000000000000001",
        )

    def settle(self, payload, requirements) -> SettleResponse:
        print(f"[MockFacilitator] settle: {payload}")
        return SettleResponse(
            success=True,
            transaction="0x0000000000000000000000000000000000000000000000000000000000000001",
            network="eip155:31337",
            amount="0.001",
            payer="0x0000000000000000000000000000000000000001",
        )


class LocalExactSchemeNetworkServer:
    """Simple EVM exact scheme for local Anvil chain."""

    @property
    def scheme(self) -> str:
        return "exact"

    def parse_price(self, price, network) -> AssetAmount:
        """Parse a USDC price string (e.g., '0.001') into AssetAmount."""
        return AssetAmount(
            amount=price,
            asset="0x036CbD53842c5426634c4998352F8713727a1804",  # USDC address
        )

    def enhance_payment_requirements(
        self, requirements, supported_kind, extensions
    ) -> PaymentRequirements:
        """Enhance payment requirements with EVM-specific fields."""
        return requirements
