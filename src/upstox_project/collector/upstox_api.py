import requests

from .config import (
    ACCESS_TOKEN,
    INSTRUMENT_KEY,
    OPTION_CHAIN_URL,
    OPTION_CONTRACT_URL
)


def get_headers():

    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }


def get_option_contracts():

    try:

        response = requests.get(
            OPTION_CONTRACT_URL,
            params={
                "instrument_key": INSTRUMENT_KEY
            },
            headers=get_headers(),
            timeout=10
        )

    except requests.RequestException as error:

        raise RuntimeError(
            f"Option contract API failed: {error}"
        )

    if response.status_code != 200:

        raise RuntimeError(
            f"Option contract API returned "
            f"{response.status_code}: "
            f"{response.text}"
        )

    try:

        response_data = response.json()

    except ValueError:

        raise RuntimeError(
            "Option contract API returned invalid JSON."
        )

    contracts = response_data.get(
        "data",
        []
    )

    if not contracts:

        raise RuntimeError(
            "No NIFTY option contracts found."
        )

    return contracts


def get_nearest_expiry():

    contracts = get_option_contracts()

    expiries = sorted(
        {
            contract.get("expiry")
            for contract in contracts
            if contract.get("expiry")
        }
    )

    if not expiries:

        raise RuntimeError(
            "No valid NIFTY expiry found."
        )

    nearest_expiry = expiries[0]

    print(
        f"Nearest NIFTY expiry: {nearest_expiry}"
    )

    return nearest_expiry


def get_option_chain():

    expiry_date = get_nearest_expiry()

    print()
    print("Calling Upstox Option Chain API...")
    print("Instrument :", INSTRUMENT_KEY)
    print("Expiry     :", expiry_date)

    params = {
        "instrument_key": INSTRUMENT_KEY,
        "expiry_date": expiry_date
    }

    try:

        response = requests.get(
            OPTION_CHAIN_URL,
            params=params,
            headers=get_headers(),
            timeout=10
        )

    except requests.RequestException as error:

        raise RuntimeError(
            f"Upstox API connection failed: {error}"
        )

    print(
        "HTTP Status:",
        response.status_code
    )

    if response.status_code != 200:

        raise RuntimeError(
            f"Upstox API returned "
            f"{response.status_code}: "
            f"{response.text}"
        )

    try:

        response_data = response.json()

    except ValueError:

        raise RuntimeError(
            "Upstox returned invalid JSON."
        )

    option_chain = response_data.get(
        "data",
        []
    )

    if not option_chain:

        raise RuntimeError(
            "Upstox returned an empty option chain."
        )

    print(
        f"Option chain received: "
        f"{len(option_chain)} strikes"
    )

    return option_chain
