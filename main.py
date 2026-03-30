import time
import json
import websocket
import traceback
import requests
from utils import send_telegram_message,wait_until_target_time
import threading
from client import client,redeem,generate_market_buy_order,generate_market_sl_order  

from py_clob_client.clob_types import MarketOrderArgs, OrderType

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


# ✅ Reusable connection with retry
def connect_ws(payload):
    delay = 1
    while True:
        try:
            print("Connecting to WebSocket...")
            ws = websocket.create_connection(WS_URL, timeout=30)
            ws.send(json.dumps(payload))
            print("Connected & subscribed!")
            return ws
        except Exception as e:
            traceback.print_exc()
            print("Connection failed:", e)
            print(f"Retrying in {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, 30)


while True:
    try:
        # === FETCH MARKET ===
        ts = int(time.time() // 300) * 300
        slug = f"btc-updown-5m-{ts}"
        print(slug)

        start_time = time.time()
        market_url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"
        market = requests.get(market_url).json()

        token_ids = json.loads(market["clobTokenIds"])
        print("Time taken:", time.time() - start_time, "seconds")

        payload = {
            "assets_ids": [token_ids[0], token_ids[1]],
            "type": "market",
            "custom_feature_enabled": True,
            "initial_dump": False,
        }

        # === STATE ===
        global shares, buy_up_market_order, buy_down_market_order #This is global so that it can be updated in the main loop and also used in the generate_market_sl_order function
        btc_up = False
        btc_down = False
        market_resolved = False
        picked_trade = False
        trade = True
        trigger = False
        generate_buy_up_bool = False #if a buy is generated it turns to true
        generate_buy_down_bool = False #if a sell is generated it turns to true
        buy_up_market_order = None
        buy_down_market_order = None
        sl_order = None #SL order will be prepared later and stored here
        shares = None #This stores the number of shares gotten so as to sell via sell order
        shares_lock = threading.Lock() #Lock to synchronize access to shares variable
        triggers = {'enter_trade':False,
                    'begin_buy_trade':False,
                    'begin_buy_trade_two':False,
                    'trigger_sl':False,
                    'sl_down':False,
                    'enter_up_trade':False,
                    'enter_down_trade':False,
                    'sl_down_two':False
                    } #this triggers is for each order so that they can trigger once
        def post_buy_down_order_operation(token_id,side):
            try:
                global sl_order
                global client
                with shares_lock:
                    response = client.post_order(buy_down_market_order,orderType=OrderType.FAK)
                    # get response and update shaares value
                    shares = round(float(response['takingAmount']),1)

                    sl_order = generate_market_sl_order(token_id,shares)
            except Exception as e:
                traceback.print_exc()
                print(e)
                send_telegram_message(e)
        
        def post_buy_up_order_operation(token_id,side):
            try:
                global sl_order
                global client
                with shares_lock:
                    response = client.post_order(buy_up_market_order,orderType=OrderType.FAK)
                    # get response and update shares value and also prepare sl order using the shares value and store in sl_order variable
                    shares = round(float(response['takingAmount']),1)

                    sl_order = generate_market_sl_order(token_id,shares)
            except Exception as e:
                traceback.print_exc()
                print(e)
                send_telegram_message("error detected in post_buy_up_order_operation")
                send_telegram_message(e)


        def post_sl_order(retries=0):
            try:
                global sl_order
                global shares
                global client
                # prepare sl order using the shares value and store in sl_order variable
                with shares_lock:
                    response = client.post_order(sl_order,orderType=OrderType.FAK)
            except Exception as e:
                traceback.print_exc()
                print("Exception found in post_sl_order")
                print(e)
                send_telegram_message("Exxception foun din post_sl__order")
                send_telegram_message(e)
                if retries == 0: #Retry only once
                    send_telegram_message("error detected in post_sl_order, retrying...")
                    post_sl_order(retries=1)
                
        price = {
            'up': {'bid': 0.0, 'ask': 0.0},
            'down': {'bid': 0.0, 'ask': 0.0}
        }
        #wait_until_target_time() #Waits till about 2 mins to 5min o'clock
        # === CONNECT WS ===
        ws = connect_ws(payload)

        now = int(time.time())
        current_interval_start = (now // 300) * 300
        market_end_ts = current_interval_start + 300

        msg = f"Market connected\n\n\nMarket ends at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(market_end_ts))}"
        send_telegram_message(msg)
        print(msg)

        # === LISTEN LOOP ===
        while True:
            try:
                raw = ws.recv()
                data = json.loads(raw)

            except Exception as e:
                traceback.print_exc()
                print("WebSocket disconnected:", e)
                ws.close()
                print("Reconnecting...")
                ws = connect_ws(payload)
                continue  # resume listening with new connection

            updates_list = data if isinstance(data, list) else [data]

            for update_item in updates_list:

                # === MARKET RESOLUTION ===
                if (update_item.get("event_type") == "market_resolved"):
                    if not market_resolved:
                        send_telegram_message("Market Just Resolved!")
                        print("Market Just Resolved redeeming tokens!")
                        thread_1 = threading.Thread(target=redeem)
                        thread_1.start()
                        market_resolved = True
                        

                # === PRICE UPDATES ===
                for change in update_item.get("price_changes", []):
                    asset_id = change.get("asset_id")

                    if asset_id not in token_ids:
                        continue

                    best_bid = float(change.get("best_bid"))
                    best_ask = float(change.get("best_ask"))

                    # ===== UP SIDE =====
                    if asset_id == token_ids[0]:
                        price['up']['ask'] = best_ask
                        price['up']['bid'] = best_bid
                        if generate_buy_up_bool == False:
                            buy_up_market_order = generate_market_buy_order(token_ids[0], "BUY")  # Update the buy order with the new price
                            
                            generate_buy_up_bool = True #Generated this is to make it do it once and avoid rate limiting
                        else:
                            pass
                        if picked_trade:
                            if btc_up and (0.35 < best_bid < 0.43 and trade):
                                if not triggers['enter_trade']:
                                    send_telegram_message("Stop Loss Triggered for BTC UP!")
                                    print("Stop Loss Triggered for BTC UP!")
                                    sl_up = threading.Thread(target=post_sl_order)
                                    sl_up.start()
                                    triggers['enter_trade'] = True #This makes sure it is triggered once

                                trade = False
                                picked_trade = False

                                if not triggers['begin_buy_trade']:
                                    begin_buy_trade = threading.Thread(target=post_buy_down_order_operation,args=(asset_id,"BUY",))
                                    begin_buy_trade.start()
                                    triggers['begin_buy_trade'] = False #This makes sure it is triggered once

                                begin_buy_trade = threading.Thread(target=post_buy_down_order_operation,args=(asset_id,"BUY",))
                                begin_buy_trade.start()
                                #Get return response and get shares and use it to update the shares variable
                                #and also prepare sl order
                                btc_up = False
                                btc_down = True

                                send_telegram_message("Reentered in opposite direction")
                            continue

                        elif (0.77 < best_ask < 0.9 and trade):
                            btc_up = True
                            picked_trade = True
                            send_telegram_message("Opportunity in BTC UP")
                            print("Opportunity in BTC UP")

                            if not triggers['begin_buy_trade']:
                                begin_buy_trade = threading.Thread(target=post_buy_up_order_operation,args=(asset_id,"BUY",))
                                begin_buy_trade.start()
                                triggers['begin_buy_trade'] = True #This makes sure it is triggered once

                            #Get return response and get shares and use it to update the shares variabe so we can prepare an sl transaction
                            # and also prepare sl order
                        elif (not picked_trade and not trade and not trigger): #This is for second stop loss while trigger makes it trigger once
                            if btc_up and (0.17<best_bid<0.23):
                                send_telegram_message("STOP LOSS TRIGGERED AGAIN FOR BTC UP!")
                                print("stop loss was triggeered for btc up")

                                if not triggers['trigger_sl']:
                                    sl_up = threading.Thread(target=post_sl_order)
                                    sl_up.start()
                                    triggers['trigger_sl'] = True #This makes sure it is triggered once
                                
                                
                                picked_trade = False
                                btc_up = False
                                btc_down = False
                                trigger = True #this makes sure it is triggered once
                                send_telegram_message('NO MORE ENTERING AGAIN')
                    
                    # ===== DOWN SIDE =====
                    elif asset_id == token_ids[1]:
                        price['down']['ask'] = best_ask
                        price['down']['bid'] = best_bid
                        if generate_buy_down_bool == False:
                        
                            buy_down_market_order = generate_market_buy_order(token_ids[1], "BUY")  # Update the buy order with the new price
                             
                            generate_buy_down_bool = True #Generated this is to make it do it on and avoid rate limiting
                        else:
                            pass
                        if picked_trade:
                            if btc_down and (0.35 < best_bid < 0.43 and trade):
                                send_telegram_message("Stop Loss Triggered for BTC DOWN!")
                                print("Stop Loss Triggered for BTC DOWN!")

                                if not triggers['sl_down']:
                                     sl_down = threading.Thread(target=post_sl_order)
                                     sl_down.start()
                                     triggers['sl_down'] = True #This makes sure it is triggered once
                                

                                picked_trade = False
                                trade = False

                                if not triggers['enter_up_tradde']:    
                                    enter_up_trade = threading.Thread(target=post_buy_up_order_operation,args=(asset_id,"BUY",))
                                    enter_up_trade.start()
                                    triggers['enter_up_tradde'] = True #This makes sure it is triggered once
                                # get response data and get shares
                                #prepare sl order
                                btc_up = True
                                btc_down = False

                                send_telegram_message("Reentered in opposite direction")
                            continue

                        elif (0.77 < best_ask < 0.9 and trade):
                            btc_down = True
                            picked_trade = True
                            send_telegram_message("Opportunity in BTC DOWN")
                            print("Opportunity in BTC DOWN")

                            if not triggers['enter_down_trade']:
                                enter_down_trade = threading.Thread(target=post_buy_down_order_operation, args=(asset_id,"BUY",))
                                enter_down_trade.start()
                                triggers['enter_down_trade'] = True #This makes sure it is triggered once
                            #get response and get shares value and use in preparing sl order

                        elif (not picked_trade and not trade and not trigger): #This is for second stop loss while trigger makes it trigger once
                            if btc_down and (0.17<best_bid<0.23):
                                send_telegram_message("Stop loss triggered again for BTC DOWN!")
                                print("Stop Loss triggeredd for BTC DOWN!")
                                if not triggers['sl_down_two']:
                                    sl_down = threading.Thread(target=post_sl_order)
                                    sl_down.start()
                                    triggers['sl_down_two'] = True
                                
                                picked_trade = False
                                btc_up = False #no need to make any of them true cause we'll not be resolving the market again at this point
                                btc_down = False
                                trigger = True
                                send_telegram_message("No more entering again")
            if market_resolved:
                ws.close()
                print("Cycle complete. Moving to next market...\n")
                break

    except Exception as e:
        traceback.print_exc()
        print("Fatal error in main loop:", e)
        print("Restarting cycle in 5 seconds...\n")
        time.sleep(5)