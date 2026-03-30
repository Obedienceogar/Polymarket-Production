#import modules for the program
import traceback

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import MarketOrderArgs, OrderType, BalanceAllowanceParams, AssetType, PartialCreateOrderOptions
from pathlib import Path
import time
import json
import requests
import threading
from web3 import Web3
from allowance import set_allowances
from utils import send_telegram_message

#Constants and variables defined here
HOST='https://clob.polymarket.com'
WALLET_PRIVATE_KEY = "48975b563ddc674d11d7c94b5341ccd4f8469f40af542f43dccbba96e9a7cd5f" #Private key hardcoded here
BUILDER_API_KEY = "4ecceedd-1c16-2f6d-dda2-2fd859d5db09"
BUILDER_SECRET = "hVpznPTqqEWTOUzKC5jJpqBtxgW-2hzSpKicwAbsD2Y="
BUILDER_PASSPHRASE = "a8cace49e160f121be1b8831823574f1c2c7350261fb5faab201dc967c910141"
WALLET_ADDRESS = "0x775Dc5F22e43a86157b74fe166Bc81d4A4718991"
POLYGON_RPC = "https://polygon-bor-rpc.publicnode.com"

set_allowance = True

chain_id = POLYGON


creds = ApiCreds(
    api_key=BUILDER_API_KEY,
    api_secret=BUILDER_SECRET,
    api_passphrase=BUILDER_PASSPHRASE
)


client = ClobClient(host=HOST, key=WALLET_PRIVATE_KEY, chain_id=POLYGON,creds=creds,signature_type=0)

#initialize and set token allowances
if set_allowance == False: #this is meant to run once
    set_allowances()
else:
    pass

#All functions here

def generate_market_buy_order(token_id,side):
    try:
        market_order = MarketOrderArgs(
        token_id=token_id,
        amount=1,  # Dollar amount to spend
        side = side,
        order_type=OrderType.FAK,  # Fill-and-Kill
    )
        options = PartialCreateOrderOptions(
            tick_size=0.01,  # Set tick size to 0.1 for more competitive pricing
            neg_risk=False,
        )

        signed_market_order = client.create_market_order(market_order)

        return signed_market_order
    except Exception as e:
        traceback.print_exc()
        print(e)
        send_telegram_message(e)

def generate_market_sl_order(token_id,shares=None):
    try:
        sell_order = MarketOrderArgs(
            token_id=token_id,
            amount=1 if shares is None else shares,
            side = "SELL",
            order_type=OrderType.FAK,
        )
        options = PartialCreateOrderOptions(
            tick_size=0.01,
            neg_risk=False,
        )
        signed_market_order = client.create_market_order(sell_order,options=options)
        return signed_market_order
    except Exception as e:
        traceback.print_exc()
        print(f"Error occurred while generating stop-loss order: {e}")
        send_telegram_message("error occured in generate_market_sl_order function")
        send_telegram_message(e)
        

# -------------------------------
# 1️⃣ Check redeemable positions
# -------------------------------
def redeem():
    try:
        resp = requests.get(
            "https://data-api.polymarket.com/positions",
            params={"user": WALLET_ADDRESS}
        )
        resp.raise_for_status()
        positions = resp.json()
        redeemable_list = [p for p in positions if p.get('redeemable')]
        if not redeemable_list:
            print("No redeemable positions found.")
        else:
            print(f"Found {len(redeemable_list)} redeemable positions:")
            for p in redeemable_list:
                print(f"- Market: {p['title']}, Outcome: {p['outcome']}, Size: {p['size']}, PnL: {p['cashPnl']}")
        
        redeem_tokens(redeemable_list)
        #for i in redeemable_list:
            #print(i['title'], i['outcome'], i['size'], i['cashPnl'])
    except Exception as e:
        traceback.print_exc()
        print(e)
        send_telegram_message("Error in redeem function")
        send_telegram_message(e)


# -------------------------------
# 2️⃣ Redeem all positions
# -------------------------------
def redeem_tokens(redeemable_list):
    try:
        redeem_abi = [{
            "name": "redeemPositions",
            "type": "function",
            "inputs": [
                {"name": "collateralToken", "type": "address"},
                {"name": "parentCollectionId", "type": "bytes32"},
                {"name": "conditionId", "type": "bytes32"},
                {"name": "indexSets", "type": "uint256[]"}
            ],
            "outputs": []
        }]

        CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045" 
        USDCE_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        ctf = w3.eth.contract(address=CTF_ADDRESS, abi=redeem_abi)
        if not redeemable_list:
            return

        tx_hashes = []  # store tx hashes for later confirmation

        # fetch the next pending nonce once
        nonce = w3.eth.get_transaction_count(WALLET_ADDRESS, "pending")

        for pos in redeemable_list:
            condition_id = Web3.to_bytes(hexstr=pos['conditionId'])
            index_sets = [1, 2]  # redeem both outcomes (winner + loser, safe for Polymarket)

            # build transaction with EIP-1559 gas fields
            tx = ctf.functions.redeemPositions(
                USDCE_ADDRESS,
                bytes(32),  # parentCollectionId = 32 zero bytes
                condition_id,
                index_sets
            ).build_transaction({
                "from": WALLET_ADDRESS,
                "nonce": nonce,
                "gas": 500_000,
                "maxFeePerGas": w3.to_wei("200", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("200", "gwei"),
                "chainId": 137
            })

            # sign and send transaction
            signed_tx = w3.eth.account.sign_transaction(tx, WALLET_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"Sent redeem for {pos['title']} | TX hash: {tx_hash.hex()}")
            tx_hashes.append((pos['title'], tx_hash))

            nonce += 1  # increment nonce for next tx

        # ✅ Wait for all txs to confirm after sending
        for title, tx_hash in tx_hashes:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=100)
            print(f"Transaction confirmed for {title} in block {receipt.blockNumber}\n")
    except Exception as e:
        traceback.print_exc()
        print("Excepiton occured")
        print(e)
        send_telegram_message("Error occured in web3 claim rewards function ")
        send_telegram_message(e)
#redeem()

if __name__ == "__main__":
    balance = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    usdc_balance = int(balance['balance'])/1e6
    print(f"USDC Balance: ${usdc_balance:.2f}")
    ts = int(time.time() // 300) * 300
    slug = f"btc-updown-5m-{ts}"
    print(slug)

    start_time = time.time()
    market_url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"
    market = requests.get(market_url).json()

    token_ids = json.loads(market["clobTokenIds"])
    print("Time taken:", time.time() - start_time, "seconds")
    tokenid = token_ids[int(input("enter 0 for up and 1 for down: "))]
    
    # Execute market order

    resp = client.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    print(resp)
    client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    start_time = time.time()
    sides = ["BUY","SELL"]
    side = int(input("Enter 0 for buy and 1 for sell side: "))
    side = sides[side]
    buy_order = generate_market_buy_order(tokenid,side)
    start_time = time.time()
    response = client.post_order(buy_order, OrderType.FAK)
    try:
        if response['success'] == False:
            print("Market order failed, retrying...")
            response = client.post_order(buy_order, OrderType.FAK)
        else:
            shares = round(float(response['takingAmount']),1)
    except:
        traceback.print_exc()
        response = client.post_order(buy_order, OrderType.FAK)
    print("Shares")
    print(shares)
    print("Market order executed!")
    print(response)
    print(f"Total time taken to execuute order: {start_time-time.time()}")


    resp = client.get_balance_allowance(BalanceAllowanceParams(AssetType.CONDITIONAL,tokenid))
    print(resp)
    
    response = input("hit enter to trigger sl")

    sell_order = generate_market_sl_order(tokenid,side)
    print(sell_order)
    response = client.post_order(sell_order,OrderType.FAK)

    print("Stop loss was executed")

    print(response)
