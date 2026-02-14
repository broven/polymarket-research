"""
Spike 2: Deribit Options Data Coverage
=======================================
Validates:
2.1 Options chain structure (expiries, strikes, depth)
2.2 IV surface data quality
2.3 Coverage match with Polymarket markets
"""

import json
import requests
import numpy as np
from datetime import datetime, timezone

DERIBIT_URL = "https://www.deribit.com/api/v2/public"

# ============================================================
# 2.1 Options chain structure
# ============================================================
print("=" * 60)
print("2.1 BTC OPTIONS CHAIN STRUCTURE")
print("=" * 60)

def get_instruments(currency="BTC", kind="option"):
    """Fetch all available option instruments."""
    resp = requests.get(f"{DERIBIT_URL}/get_instruments", params={
        "currency": currency,
        "kind": kind,
        "expired": "false",
    })
    resp.raise_for_status()
    return resp.json()["result"]

def get_order_book(instrument_name):
    """Fetch order book for an instrument."""
    resp = requests.get(f"{DERIBIT_URL}/get_order_book", params={
        "instrument_name": instrument_name,
    })
    resp.raise_for_status()
    return resp.json()["result"]

def get_index_price(currency="BTC"):
    """Fetch current index price."""
    resp = requests.get(f"{DERIBIT_URL}/get_index_price", params={
        "index_name": f"{currency.lower()}_usd",
    })
    resp.raise_for_status()
    return resp.json()["result"]["index_price"]

# Get current BTC price
btc_price = get_index_price("BTC")
print(f"\nCurrent BTC price: ${btc_price:,.2f}")

# Fetch all BTC options
btc_options = get_instruments("BTC", "option")
print(f"Total BTC option instruments: {len(btc_options)}")

# Parse expiry dates and strikes
expiries = set()
strikes_by_expiry = {}
for opt in btc_options:
    name = opt["instrument_name"]
    parts = name.split("-")
    # Format: BTC-26FEB26-100000-C
    expiry = parts[1]
    strike = float(parts[2])
    opt_type = parts[3]  # C or P

    expiries.add(expiry)
    if expiry not in strikes_by_expiry:
        strikes_by_expiry[expiry] = {"calls": [], "puts": [], "strikes": set()}
    strikes_by_expiry[expiry]["strikes"].add(strike)
    if opt_type == "C":
        strikes_by_expiry[expiry]["calls"].append(opt)
    else:
        strikes_by_expiry[expiry]["puts"].append(opt)

# Sort expiries by date
def parse_expiry(exp_str):
    """Parse Deribit expiry string like '26FEB26' to datetime."""
    try:
        return datetime.strptime(exp_str, "%d%b%y")
    except ValueError:
        return datetime.max

sorted_expiries = sorted(expiries, key=parse_expiry)

print(f"\nAvailable expiry dates: {len(sorted_expiries)}")
print(f"Nearest: {sorted_expiries[0] if sorted_expiries else 'N/A'}")
print(f"Farthest: {sorted_expiries[-1] if sorted_expiries else 'N/A'}")

# Days to each expiry
now = datetime.now()
print(f"\nExpiry details:")
print(f"{'Expiry':<12} {'Days':>6} {'Strikes':>8} {'Calls':>6} {'Puts':>6} {'Strike Range':>25}")
print("-" * 70)
for exp in sorted_expiries:
    exp_date = parse_expiry(exp)
    days = (exp_date - now).days
    info = strikes_by_expiry[exp]
    strikes = sorted(info["strikes"])
    strike_range = f"${strikes[0]:,.0f} - ${strikes[-1]:,.0f}" if strikes else "N/A"
    print(f"{exp:<12} {days:>6}d {len(strikes):>8} {len(info['calls']):>6} {len(info['puts']):>6} {strike_range:>25}")

# ============================================================
# 2.1b ETH OPTIONS
# ============================================================
print("\n" + "=" * 60)
print("2.1b ETH OPTIONS CHAIN STRUCTURE")
print("=" * 60)

eth_price = get_index_price("ETH")
print(f"\nCurrent ETH price: ${eth_price:,.2f}")

eth_options = get_instruments("ETH", "option")
print(f"Total ETH option instruments: {len(eth_options)}")

eth_expiries = set()
for opt in eth_options:
    parts = opt["instrument_name"].split("-")
    eth_expiries.add(parts[1])

sorted_eth_expiries = sorted(eth_expiries, key=parse_expiry)
print(f"Available expiry dates: {len(sorted_eth_expiries)}")
print(f"Nearest: {sorted_eth_expiries[0] if sorted_eth_expiries else 'N/A'}")
print(f"Farthest: {sorted_eth_expiries[-1] if sorted_eth_expiries else 'N/A'}")

# ============================================================
# 2.2 IV Surface data quality
# ============================================================
print("\n" + "=" * 60)
print("2.2 IV SURFACE DATA QUALITY")
print("=" * 60)

# Pick a mid-term expiry for analysis
mid_idx = len(sorted_expiries) // 3  # ~1/3 of the way out
target_expiry = sorted_expiries[mid_idx] if sorted_expiries else None

if target_expiry:
    print(f"\nAnalyzing IV smile for expiry: {target_expiry}")
    info = strikes_by_expiry[target_expiry]
    calls = info["calls"]

    # Fetch order book data for each call to get IV
    iv_data = []
    print(f"Fetching IVs for {len(calls)} calls...")
    for call in calls:
        name = call["instrument_name"]
        strike = float(name.split("-")[2])
        try:
            book = get_order_book(name)
            iv = book.get("mark_iv", 0)
            mark_price = book.get("mark_price", 0)
            bid_iv = book.get("bid_iv", 0)
            ask_iv = book.get("ask_iv", 0)
            open_interest = book.get("open_interest", 0)
            volume = book.get("stats", {}).get("volume", 0)

            if iv and iv > 0:
                iv_data.append({
                    "strike": strike,
                    "iv": iv,
                    "bid_iv": bid_iv or 0,
                    "ask_iv": ask_iv or 0,
                    "mark_price": mark_price,
                    "open_interest": open_interest,
                    "volume": volume,
                    "moneyness": strike / btc_price,
                })
        except Exception as e:
            pass  # Skip illiquid instruments

    print(f"Got IV data for {len(iv_data)} strikes")

    if iv_data:
        iv_data.sort(key=lambda x: x["strike"])
        print(f"\n{'Strike':>10} {'Moneyness':>10} {'Mark IV':>8} {'Bid IV':>8} {'Ask IV':>8} {'IV Spread':>10} {'OI':>10}")
        print("-" * 75)
        for d in iv_data:
            iv_spread = d["ask_iv"] - d["bid_iv"] if d["ask_iv"] and d["bid_iv"] else 0
            print(f"${d['strike']:>9,.0f} {d['moneyness']:>10.3f} {d['iv']:>7.1f}% {d['bid_iv']:>7.1f}% {d['ask_iv']:>7.1f}% {iv_spread:>9.1f}% {d['open_interest']:>10.1f}")

        # Check for arbitrage violations
        print("\n--- NO-ARBITRAGE CHECKS ---")

        # Butterfly check: adjacent strikes should satisfy convexity
        violations = 0
        for i in range(1, len(iv_data) - 1):
            # For calls: C(K-dK) + C(K+dK) >= 2*C(K)
            # We use mark prices as proxy
            p_low = iv_data[i-1]["mark_price"]
            p_mid = iv_data[i]["mark_price"]
            p_high = iv_data[i+1]["mark_price"]
            if p_low + p_high < 2 * p_mid - 0.0001:  # small tolerance
                violations += 1
        print(f"  Butterfly violations: {violations} / {len(iv_data) - 2}")

        # IV statistics
        ivs = [d["iv"] for d in iv_data]
        print(f"\n  IV stats: min={min(ivs):.1f}%, max={max(ivs):.1f}%, mean={np.mean(ivs):.1f}%, std={np.std(ivs):.1f}%")

        # ATM region quality (0.9 - 1.1 moneyness)
        atm_data = [d for d in iv_data if 0.85 <= d["moneyness"] <= 1.15]
        print(f"  ATM strikes (0.85-1.15 moneyness): {len(atm_data)}")
        if atm_data:
            atm_spreads = [d["ask_iv"] - d["bid_iv"] for d in atm_data if d["ask_iv"] and d["bid_iv"]]
            if atm_spreads:
                print(f"  ATM IV bid-ask spreads: mean={np.mean(atm_spreads):.1f}%, max={max(atm_spreads):.1f}%")

# ============================================================
# 2.3 Coverage match with Polymarket
# ============================================================
print("\n" + "=" * 60)
print("2.3 COVERAGE MATCH WITH POLYMARKET")
print("=" * 60)

# Get farthest Deribit expiry in days
farthest_btc_days = (parse_expiry(sorted_expiries[-1]) - now).days if sorted_expiries else 0
farthest_eth_days = (parse_expiry(sorted_eth_expiries[-1]) - now).days if sorted_eth_expiries else 0

# Get strike range
all_btc_strikes = set()
for exp_info in strikes_by_expiry.values():
    all_btc_strikes.update(exp_info["strikes"])
btc_strike_min = min(all_btc_strikes) if all_btc_strikes else 0
btc_strike_max = max(all_btc_strikes) if all_btc_strikes else 0

print(f"\nDeribit BTC coverage:")
print(f"  Expiry range: now to {farthest_btc_days} days out")
print(f"  Strike range: ${btc_strike_min:,.0f} - ${btc_strike_max:,.0f}")
print(f"  Current price: ${btc_price:,.0f}")

print(f"\nDeribit ETH coverage:")
print(f"  Expiry range: now to {farthest_eth_days} days out")

print(f"""
\n--- COVERAGE ASSESSMENT ---
To match Polymarket markets, we need:
  1. Deribit expiry >= Polymarket market end date
  2. Deribit strikes include Polymarket target price

BTC max expiry: {farthest_btc_days} days
BTC strike range: ${btc_strike_min:,.0f} - ${btc_strike_max:,.0f}
ETH max expiry: {farthest_eth_days} days

NOTE: Actual coverage match requires cross-referencing with
      Spike 1 Polymarket market list (target prices + end dates).
      This will be done in Spike 3.
""")

# ============================================================
# SUMMARY
# ============================================================
print("=" * 60)
print("SPIKE 2 SUMMARY")
print("=" * 60)
print(f"""
BTC Options:
  Total instruments:    {len(btc_options)}
  Expiry dates:         {len(sorted_expiries)}
  Farthest expiry:      {sorted_expiries[-1] if sorted_expiries else 'N/A'} ({farthest_btc_days} days)
  Strike range:         ${btc_strike_min:,.0f} - ${btc_strike_max:,.0f}

ETH Options:
  Total instruments:    {len(eth_options)}
  Expiry dates:         {len(sorted_eth_expiries)}
  Farthest expiry:      {sorted_eth_expiries[-1] if sorted_eth_expiries else 'N/A'} ({farthest_eth_days} days)

IV Surface Quality ({target_expiry or 'N/A'}):
  Strikes with IV data: {len(iv_data) if target_expiry else 'N/A'}
  Butterfly violations: {violations if target_expiry else 'N/A'}
""")
