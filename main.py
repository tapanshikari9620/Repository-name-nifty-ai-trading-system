import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

instrument_key = "NSE_INDEX|Nifty 50"

url = "https://api.upstox.com/v2/market-quote/quotes"

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {access_token}"
}

params = {
    "instrument_key": instrument_key
}

while True:

    response = requests.get(
        url,
        params=params,
        headers=headers
    )

    if response.status_code == 200:

        data = response.json()

        nifty = data["data"]["NSE_INDEX:Nifty 50"]

        ltp = nifty["last_price"]

        print("NIFTY LTP:", ltp)

    else:
        print("API Error:", response.status_code)
        print(response.text)

    time.sleep(2)