import json
import re

import requests

GAMMA_URL = "https://gamma-api.polymarket.com"


def parse_json_or_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return []


def fetch_all_active_markets(max_pages=20, page_size=500):
    markets = []
    for page in range(max_pages):
        params = {
            "limit": page_size,
            "offset": page * page_size,
            "active": "true",
            "closed": "false",
        }
        resp = requests.get(f"{GAMMA_URL}/markets", params=params, timeout=20)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        markets.extend(batch)
        if len(batch) < page_size:
            break
    return markets


def find_target_market(keyword=r"(bitcoin|btc).*(reach|hit)| (reach|hit).*(bitcoin|btc)"):
    print(f"Searching by pattern: {keyword}")
    markets = fetch_all_active_markets(max_pages=20, page_size=500)
    print(f"Fetched {len(markets)} total active markets.")

    pattern = re.compile(keyword, re.IGNORECASE)
    candidates = [m for m in markets if pattern.search(m.get("question", ""))]
    print(f"Found {len(candidates)} candidates.")

    for m in candidates[:50]:
        clob_ids = parse_json_or_list(m.get("clobTokenIds"))
        prices = parse_json_or_list(m.get("outcomePrices"))
        print("\n" + "=" * 40)
        print(f"Question: {m.get('question')}")
        print(f"Market ID: {m.get('id')}")
        print(f"Condition ID: {m.get('conditionId')}")
        print(f"Slug: {m.get('slug')}")
        print(f"End Date: {m.get('endDate')}")
        print(f"Outcome Prices: {prices}")
        print(f"CLOB Token IDs: {clob_ids}")


if __name__ == "__main__":
    find_target_market()
