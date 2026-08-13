import os

from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# ACCESS TOKEN
# ============================================================

ACCESS_TOKEN = os.getenv(
    "UPSTOX_ACCESS_TOKEN"
)

if not ACCESS_TOKEN:
    raise RuntimeError(
        "UPSTOX_ACCESS_TOKEN not found in .env"
    )


# ============================================================
# UPSTOX CONFIGURATION
# ============================================================

INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"

OPTION_CHAIN_URL = (
    "https://api.upstox.com/v2/option/chain"
)

OPTION_CONTRACT_URL = (
    "https://api.upstox.com/v2/option/contract"
)