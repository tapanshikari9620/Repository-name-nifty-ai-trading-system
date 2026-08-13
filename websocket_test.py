import os
import upstox_client
from dotenv import load_dotenv

load_dotenv()

access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

if not access_token:
    print("ERROR: UPSTOX_ACCESS_TOKEN not found.")
    exit()

print("Access token loaded successfully.")

# Create Upstox configuration
configuration = upstox_client.Configuration()
configuration.access_token = access_token

# Create WebSocket streamer V3
streamer = upstox_client.MarketDataStreamerV3(
    upstox_client.ApiClient(configuration)
)


def on_open():
    print("WebSocket connected!")

    # Subscribe to NIFTY 50
    streamer.subscribe(
        ["NSE_INDEX|Nifty 50"],
        "ltpc"
    )

    print("Subscribed to NIFTY 50")


def on_message(message):

    feeds = message.get("feeds", {})

    nifty_data = feeds.get("NSE_INDEX|Nifty 50")

    if nifty_data:

        ltpc = nifty_data.get("ltpc", {})

        ltp = ltpc.get("ltp")

        if ltp is not None:
            print(f"NIFTY LTP: {ltp}")


def on_error(error):
    print("WebSocket error:")
    print(error)


def on_close():
    print("WebSocket connection closed.")


# Register event handlers
streamer.on("open", on_open)
streamer.on("message", on_message)
streamer.on("error", on_error)
streamer.on("close", on_close)

# Start WebSocket
print("Starting WebSocket...")
streamer.connect()