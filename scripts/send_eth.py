from web3 import Web3
from eth_account import Account
import os

# Read .env manually
env = {}
with open("/home/b/workspace/x402-agent-service/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

old_key = env["EVM_PRIVATE_KEY"]
old_acc = Account.from_key(old_key)
old_addr = old_acc.address

new_addr = Web3.to_checksum_address("0xD333941784201caC6C3c082D9BEef22EFefe4750")

sepolia = Web3(Web3.HTTPProvider("https://ethereum-sepolia-rpc.publicnode.com"))

bal = sepolia.eth.get_balance(old_addr)
print(f"Old wallet: {Web3.from_wei(bal, 'ether')} ETH")

nonce = sepolia.eth.get_transaction_count(old_addr)
gas_price = sepolia.eth.gas_price

tx = {
    "nonce": nonce,
    "to": new_addr,
    "value": Web3.to_wei(0.3, "ether"),
    "gas": 21000,
    "gasPrice": gas_price,
    "chainId": 11155111,
}

signed = sepolia.eth.account.sign_transaction(tx, old_key)
tx_hash = sepolia.eth.send_raw_transaction(signed.raw_transaction)
print(f"TX: {tx_hash.hex()}")
print("Confirming...")

receipt = sepolia.eth.wait_for_transaction_receipt(tx_hash)
print(f"Confirmed block {receipt['blockNumber']}")

new_bal = sepolia.eth.get_balance(new_addr)
print(f"New wallet: {Web3.from_wei(new_bal, 'ether')} ETH")
