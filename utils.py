import time
import datetime
import requests
import traceback

def wait_until_target_time():
    """
    Calculates the time needed to sleep until the next target time
    (65 seconds to the 5-minute o'clock, i.e., at 4:55, 9:55, etc.).
    """
    while True:
        # Get the current time
        now = datetime.datetime.now()

        # Calculate the next 5-minute interval mark (e.g., 00:05:00, 00:10:00)
        # The modulo operation here ensures we get the next 5-minute mark
        minutes_to_next_interval = 5 - (now.minute % 5)
        
        # Determine the exact time of the next interval mark
        # Add a buffer of a few seconds to avoid edge case issues with execution time
        next_interval_time = now + datetime.timedelta(minutes=minutes_to_next_interval, seconds=-now.second, microseconds=-now.microsecond)

        # The target time is 65 seconds *before* the next 5-minute mark
        # which is 5 seconds *after* the current 5-minute mark
        target_time = next_interval_time - datetime.timedelta(seconds=130)

        # If the target time is in the past, add 5 minutes to find the next valid target time
        if target_time <= now:
            target_time += datetime.timedelta(minutes=5)
            
        # Calculate the time to sleep until the target time
        sleep_seconds = (target_time - now).total_seconds()
        
        if sleep_seconds > 0:
            print(f"Current time: {now.strftime('%H:%M:%S')}")
            print(f"Target time: {target_time.strftime('%H:%M:%S')}")
            print(f"Sleeping for {sleep_seconds:.2f} seconds...")
            # Use time.sleep() to pause execution
            time.sleep(sleep_seconds)
            print("Execution resumed at the target time. Running code now.")
            break
        else:
            # If the calculated sleep time is non-positive (due to system clock nuances), 
            # sleep for a short duration and recalculate
            time.sleep(0.1)


# === TELEGRAM CONFIG ===
TELEGRAM_BOT_TOKEN = "7969780210:AAHni9u5X4H9EDjYynhGr3u3XxcEEoezBnw"
TELEGRAM_CHAT_ID = "1376299836"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }

    try:
        res = requests.post(url, json=payload, timeout=5)

        if res.status_code != 200:
            print("Telegram failed:", res.status_code, res.text)
        else:
            print("Telegram sent:", text)

    except Exception as e:
        traceback.print_exc()
        print("Telegram exception:", e)