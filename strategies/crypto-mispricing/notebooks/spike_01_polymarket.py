"""
Spike 1: Polymarket API Data Availability
==========================================
Validates:
1.1 Active crypto price markets (count, structure, classification)
1.2 Fee rates per market
1.3 Order book depth
1.4 Historical resolved market data
"""

import json
import requests
import time
from datetime import datetime

BASE_URL = "https://clob.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"

# ============================================================
# 1.1 Fetch active crypto markets
# ============================================================
print("=" * 60)
print("1.1 FETCHING ACTIVE CRYPTO MARKETS")
print("=" * 60)

# Polymarket Gamma API is better for browsing markets by tag/category
# CLOB API is for trading
def fetch_gamma_markets(tag="crypto", closed=False, limit=100):
    """Fetch markets from Gamma API with filters."""
    params = {
        "limit": limit,
        "active": "true" if not closed else "false",
        "closed": str(closed).lower(),
        "tag": tag,
    }
    resp = requests.get(f"{GAMMA_URL}/markets", params=params)
    resp.raise_for_status()
    return resp.json()

def fetch_gamma_events(tag="crypto", closed=False, limit=100):
    """Fetch events (groups of markets) from Gamma API."""
    params = {
        "limit": limit,
        "active": "true" if not closed else "false",
        "closed": str(closed).lower(),
        "tag": tag,
    }
    resp = requests.get(f"{GAMMA_URL}/events", params=params)
    resp.raise_for_status()
    return resp.json()

# Fetch active crypto markets
print("\nFetching active crypto markets...")
active_markets = fetch_gamma_markets(tag="crypto", closed=False, limit=200)
print(f"Total active crypto markets: {len(active_markets)}")

# Show sample market structure
if active_markets:
    sample = active_markets[0]
    print(f"\nSample market fields: {list(sample.keys())}")
    print(f"\nSample market:")
    print(f"  question: {sample.get('question', 'N/A')}")
    print(f"  end_date: {sample.get('endDate', 'N/A')}")
    print(f"  outcome: {sample.get('outcome', 'N/A')}")
    print(f"  outcomePrices: {sample.get('outcomePrices', 'N/A')}")
    print(f"  condition_id: {sample.get('conditionId', 'N/A')}")
    print(f"  slug: {sample.get('slug', 'N/A')}")

# Classify markets
print("\n--- MARKET CLASSIFICATION ---")
barrier_up = []
barrier_down = []
terminal_range = []
other = []

for m in active_markets:
    q = (m.get("question", "") or "").lower()
    if any(kw in q for kw in ["reach", "hit", "above", "surpass", "exceed"]):
        if any(kw in q for kw in ["below", "fall", "drop", "under"]):
            barrier_down.append(m)
        else:
            barrier_up.append(m)
    elif any(kw in q for kw in ["between", "range", "end at", "close at", "price of"]):
        terminal_range.append(m)
    else:
        other.append(m)

print(f"  barrier_up:      {len(barrier_up)}")
print(f"  barrier_down:    {len(barrier_down)}")
print(f"  terminal_range:  {len(terminal_range)}")
print(f"  other/unclassified: {len(other)}")

# Print all market questions for manual review
print("\n--- ALL CRYPTO MARKET QUESTIONS ---")
for i, m in enumerate(active_markets):
    q = m.get("question", "N/A")
    end = m.get("endDate", "N/A")
    prices = m.get("outcomePrices", "N/A")
    print(f"  [{i}] {q}")
    print(f"       end: {end} | prices: {prices}")

# ============================================================
# 1.2 Fee rates
# ============================================================
print("\n" + "=" * 60)
print("1.2 FEE RATES PER MARKET")
print("=" * 60)

# Try to get token IDs and check fees
# The CLOB API /markets endpoint returns fee info
def fetch_clob_markets(next_cursor=""):
    """Fetch markets from CLOB API (paginated)."""
    params = {"next_cursor": next_cursor} if next_cursor else {}
    resp = requests.get(f"{BASE_URL}/markets", params=params)
    resp.raise_for_status()
    return resp.json()

print("\nFetching CLOB markets for fee info...")
clob_data = fetch_clob_markets()
clob_markets = clob_data.get("data", clob_data) if isinstance(clob_data, dict) else clob_data

if isinstance(clob_markets, list) and clob_markets:
    sample_clob = clob_markets[0]
    print(f"CLOB market fields: {list(sample_clob.keys())}")
    # Look for fee-related fields
    for key in sample_clob:
        if "fee" in key.lower() or "reward" in key.lower() or "rebate" in key.lower():
            print(f"  FEE FIELD: {key} = {sample_clob[key]}")

    # Check tokens for fee info
    tokens = sample_clob.get("tokens", [])
    if tokens:
        print(f"\n  Token fields: {list(tokens[0].keys()) if tokens else 'N/A'}")
        for t in tokens[:2]:
            print(f"  Token: outcome={t.get('outcome')}, token_id={str(t.get('token_id', ''))[:30]}...")
elif isinstance(clob_markets, dict):
    print(f"CLOB response keys: {list(clob_markets.keys())}")
    if "data" in clob_markets:
        data = clob_markets["data"]
        if data:
            print(f"First item keys: {list(data[0].keys())}")

# ============================================================
# 1.3 Order book depth
# ============================================================
print("\n" + "=" * 60)
print("1.3 ORDER BOOK DEPTH")
print("=" * 60)

# Get token IDs from active markets
token_ids_to_check = []
for m in active_markets[:5]:
    clob_ids = m.get("clobTokenIds", "")
    if clob_ids:
        if isinstance(clob_ids, str):
            try:
                ids = json.loads(clob_ids)
            except json.JSONDecodeError:
                ids = [clob_ids]
        else:
            ids = clob_ids
        for tid in ids:
            if tid:
                token_ids_to_check.append((m.get("question", "?")[:60], tid))

if not token_ids_to_check:
    # Try getting from CLOB markets
    for m in (clob_markets if isinstance(clob_markets, list) else []):
        tokens = m.get("tokens", [])
        for t in tokens:
            tid = t.get("token_id")
            if tid:
                token_ids_to_check.append((m.get("question", "?")[:60], tid))
                break
        if len(token_ids_to_check) >= 3:
            break

print(f"\nChecking order books for {len(token_ids_to_check)} tokens...")
for question, tid in token_ids_to_check[:3]:
    print(f"\n  Market: {question}")
    print(f"  Token: {tid[:30]}...")
    try:
        resp = requests.get(f"{BASE_URL}/book", params={"token_id": tid})
        resp.raise_for_status()
        book = resp.json()

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        print(f"  Bids: {len(bids)} levels")
        print(f"  Asks: {len(asks)} levels")

        if bids and asks:
            best_bid = float(bids[0].get("price", 0))
            best_ask = float(asks[0].get("price", 0))
            spread = best_ask - best_bid
            print(f"  Best bid: {best_bid:.4f}")
            print(f"  Best ask: {best_ask:.4f}")
            print(f"  Spread:   {spread:.4f} ({spread*100:.2f}%)")

            # Calculate depth at various levels
            bid_depth = sum(float(b.get("size", 0)) for b in bids[:5])
            ask_depth = sum(float(a.get("size", 0)) for a in asks[:5])
            print(f"  Bid depth (top 5): ${bid_depth:.2f}")
            print(f"  Ask depth (top 5): ${ask_depth:.2f}")

            # Estimate slippage for $500
            target_size = 500
            filled = 0
            cost = 0
            for a in asks:
                p = float(a.get("price", 0))
                s = float(a.get("size", 0))
                fill = min(s, target_size - filled)
                cost += fill * p
                filled += fill
                if filled >= target_size:
                    break
            if filled > 0:
                avg_price = cost / filled
                slippage = avg_price - best_ask
                print(f"  $500 buy slippage: {slippage:.4f} ({slippage/best_ask*100:.2f}%)")
    except Exception as e:
        print(f"  ERROR: {e}")
    time.sleep(0.3)

# ============================================================
# 1.4 Historical resolved markets
# ============================================================
print("\n" + "=" * 60)
print("1.4 HISTORICAL RESOLVED CRYPTO MARKETS")
print("=" * 60)

print("\nFetching resolved crypto markets...")
resolved_markets = fetch_gamma_markets(tag="crypto", closed=True, limit=200)
print(f"Total resolved crypto markets: {len(resolved_markets)}")

if resolved_markets:
    sample_resolved = resolved_markets[0]
    print(f"\nSample resolved market:")
    print(f"  question: {sample_resolved.get('question', 'N/A')}")
    print(f"  end_date: {sample_resolved.get('endDate', 'N/A')}")
    print(f"  outcome: {sample_resolved.get('outcome', 'N/A')}")
    print(f"  outcomePrices: {sample_resolved.get('outcomePrices', 'N/A')}")

    # Check for price history fields
    history_fields = [k for k in sample_resolved.keys()
                      if any(w in k.lower() for w in ["history", "price", "volume", "trade"])]
    print(f"  Price/history fields: {history_fields}")

    # Try fetching price history for a resolved market
    resolved_slug = sample_resolved.get("slug") or sample_resolved.get("conditionId")
    resolved_cid = sample_resolved.get("conditionId")
    if resolved_cid:
        print(f"\n  Trying to fetch trade history for condition_id: {resolved_cid[:30]}...")
        try:
            resp = requests.get(f"{GAMMA_URL}/markets/{resolved_cid}/history")
            if resp.status_code == 200:
                history = resp.json()
                print(f"  History data: {type(history)}, length: {len(history) if isinstance(history, list) else 'N/A'}")
                if isinstance(history, list) and history:
                    print(f"  Sample: {history[0]}")
            else:
                print(f"  History endpoint returned {resp.status_code}")
        except Exception as e:
            print(f"  History fetch error: {e}")

    # Count resolved markets by type
    print("\n--- RESOLVED MARKET CLASSIFICATION ---")
    r_barrier = 0
    r_other = 0
    for m in resolved_markets:
        q = (m.get("question", "") or "").lower()
        if any(kw in q for kw in ["reach", "hit", "above", "surpass", "below", "fall"]):
            r_barrier += 1
        else:
            r_other += 1
    print(f"  barrier type: {r_barrier}")
    print(f"  other type: {r_other}")

    # Show some resolved questions
    print("\n--- SAMPLE RESOLVED QUESTIONS ---")
    for m in resolved_markets[:10]:
        q = m.get("question", "N/A")
        outcome = m.get("outcome", "N/A")
        print(f"  [{outcome}] {q}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SPIKE 1 SUMMARY")
print("=" * 60)
print(f"""
Active crypto markets:        {len(active_markets)}
  - barrier_up:               {len(barrier_up)}
  - barrier_down:             {len(barrier_down)}
  - terminal_range:           {len(terminal_range)}
  - other:                    {len(other)}
Resolved crypto markets:      {len(resolved_markets)}
Order books checked:          {min(3, len(token_ids_to_check))}
""")
