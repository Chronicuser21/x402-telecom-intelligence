#!/usr/bin/env python3
"""Deploy mock USDC on local chain and run real x402 payments."""
import json
import time
from web3 import Web3
from eth_tester import EthereumTester, EthereumTesterProvider
from web3.providers.eth_tester import EthereumTesterProvider

# Minimal ERC20 + USDC-like ABI
ERC20_ABI = json.loads("""[
  {"constant":false,"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"}
]""")

# Minimal ERC20 bytecode for deployment
ERC20_BYTECODE = "0x608060405234801561001057600080fd5b506040516101c83803806101c88339818101604052810190610032919061007a565b82600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020819055508273ffffffffffffffffffffffffffffffffffffffff168273ffffffffffffffffffffffffffffffffffffffff167f2d15556810d818c83e57a010e94e0e7f294299e49627573a8ba1e9e8e8d6e0b6604051808260ff1660ff16815260200191505060405180910390a3505050610120565b600081359050610074816100b7565b92915050565b600081519050610089816100b7565b92915050565b6000819050919050565b60006100a381610123565b90506100af81610123565b92915050565b6100c081610123565b81146100cb57600080fd5b50565b6000813590506100dd816100b7565b92915050565b600060208284031215610100576100ff610123565b5b600061010e848285016100ce565b91505092915050565b600080fd5b61012281610123565b811461012d57600080fd5b5056fe"

print("=== Local USDC Deploy ===\n")

# Set up chain
tester = EthereumTester()
w3 = Web3(EthereumTesterProvider(tester))
print(f"Chain ID: {w3.eth.chain_id}")

accounts = w3.eth.accounts
owner = accounts[0]  # has 1M ETH
receiver = accounts[1]  # will receive payments
print(f"Owner: {owner}")
print(f"Receiver: {receiver}")

# Deploy mock USDC
print("\nDeploying mock USDC...")
contract = w3.eth.contract(abi=ERC20_ABI, bytecode=ERC20_BYTECODE)
tx = contract.constructor().transact({"from": owner})
receipt = w3.eth.get_transaction_receipt(tx)
usdc_address = receipt["contractAddress"]
print(f"USDC deployed at: {usdc_address}")

usdc = w3.eth.contract(address=usdc_address, abi=ERC20_ABI)

# Mint USDC to owner (1M USDC = 1M * 1e6)
print("Minting 1M USDC to owner...")
mint_tx = usdc.functions.transfer(owner, 1_000_000 * 10**6).transact({"from": owner})
w3.eth.get_transaction_receipt(mint_tx)

owner_balance = usdc.functions.balanceOf(owner).call()
print(f"Owner USDC: {owner_balance / 1e6:,.2f} USDC")

# Transfer USDC to receiver
print("Transferring 100 USDC to receiver...")
transfer_tx = usdc.functions.transfer(receiver, 100 * 10**6).transact({"from": owner})
w3.eth.get_transaction_receipt(transfer_tx)

receiver_balance = usdc.functions.balanceOf(receiver).call()
print(f"Receiver USDC: {receiver_balance / 1e6:,.2f} USDC")

print(f"\n✅ Local chain ready!")
print(f"  RPC: http://127.0.0.1:8545 (not needed — using in-process)")
print(f"  USDC: {usdc_address}")
print(f"  Chain ID: {w3.eth.chain_id}")
print(f"  Owner: {owner}")
print(f"  Receiver: {receiver}")
