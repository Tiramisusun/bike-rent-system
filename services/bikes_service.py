import os
import requests


JCDECAUX_URL = "https://api.jcdecaux.com/vls/v1/stations"


def fetch_jcdecaux_stations() -> list:
    api_key = os.getenv("JCDECAUX_API_KEY")
    contract_name = os.getenv("JCDECAUX_CONTRACT_NAME", "dublin")

    if not api_key:
        raise ValueError("Missing JCDECAUX_API_KEY in .env")

    params = {"contract": contract_name, "apiKey": api_key}
    r = requests.get(JCDECAUX_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()