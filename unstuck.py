from web3 import Web3
import time

# --- CONFIG ---
POLYGON_RPC = "https://polygon-bor-rpc.publicnode.com"  # or any fast RPC
WALLET_ADDRESS = "0x775Dc5F22e43a86157b74fe166Bc81d4A4718991"
WALLET_PRIVATE_KEY = "48975b563ddc674d11d7c94b5341ccd4f8469f40af542f43dccbba96e9a7cd5f"


w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

latest_nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, "latest")
pending_nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, "pending")

print(f"Latest: {latest_nonce}, Pending: {pending_nonce}")

# Start with high gas
priority_fee = 200  # gwei
max_fee = 200      # gwei

for nonce in range(latest_nonce, pending_nonce):
    while True:
        try:
            tx = {
                "from": WALLET_ADDRESS,
                "to": WALLET_ADDRESS,
                "value": 0,
                "nonce": nonce,
                "gas": 500000,
                "maxPriorityFeePerGas": w3.to_wei(priority_fee, "gwei"),
                "maxFeePerGas": w3.to_wei(max_fee, "gwei"),
                "chainId": 137
            }

            signed_tx = w3.eth.account.sign_transaction(tx, WALLET_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            

            print(f"✅ Cancel sent for nonce {nonce}: {tx_hash.hex()}")
            break

        except Exception as e:
            if "already known" in str(e):
                # 🔥 bump gas and retry
                priority_fee += 10
                max_fee += 20
                print(f"⏫ Increasing gas → priority: {priority_fee} gwei")
                time.sleep(1)
            else:
                print(f"❌ Error for nonce {nonce}: {e}")
                break