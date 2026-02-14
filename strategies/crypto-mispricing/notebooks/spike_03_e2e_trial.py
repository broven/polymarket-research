"""
Spike 3: End-to-end trial on one live BTC barrier market.

This is an exploratory script:
- picks one active BTC barrier market (closest to 50/50, with Deribit coverage)
- estimates barrier probability with:
  A) flat-IV risk-neutral GBM Monte Carlo (fallback for Model A)
  B) historical jump-diffusion Monte Carlo (Model B)
- compares with Polymarket price and computes a rough edge_net
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Iterable

import numpy as np
import requests

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DERIBIT_URL = "https://www.deribit.com/api/v2/public"
UTC = timezone.utc


def parse_json_or_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return []


def build_result_record(
    market_question: str,
    market_slug: str,
    market_end_date: str,
    yes_price: float,
    spot: float,
    target: float,
    t_years: float,
    iv: float,
    model_a_prob: float,
    model_a_ci: float,
    model_b_prob: float,
    model_b_ci: float,
    combined_prob: float,
    edge_gross: float,
    direction: str,
    uncertainty: float,
    total_cost: float,
    edge_net: float,
    verdict: str,
):
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "market_question": market_question,
        "market_slug": market_slug,
        "market_end_date": market_end_date,
        "yes_price": yes_price,
        "spot": spot,
        "target": target,
        "t_years": t_years,
        "iv": iv,
        "model_a_prob": model_a_prob,
        "model_a_ci": model_a_ci,
        "model_b_prob": model_b_prob,
        "model_b_ci": model_b_ci,
        "combined_prob": combined_prob,
        "edge_gross": edge_gross,
        "direction": direction,
        "uncertainty": uncertainty,
        "total_cost": total_cost,
        "edge_net": edge_net,
        "verdict": verdict,
    }


def write_result_files(record: dict, output_dir: str | Path, run_id: str | None = None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    json_path = out / f"spike_03_{run_id}.json"
    csv_path = out / f"spike_03_{run_id}.csv"

    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(record.keys()))
        writer.writeheader()
        writer.writerow(record)
    return json_path, csv_path


def write_batch_files(records: list[dict], output_dir: str | Path, run_id: str | None = None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    json_path = out / f"spike_03_batch_{run_id}.json"
    csv_path = out / f"spike_03_batch_{run_id}.csv"

    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    fieldnames = list(records[0].keys()) if records else []
    with csv_path.open("w", newline="") as f:
        if fieldnames:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record)
    return json_path, csv_path


def parse_target_from_question(question: str):
    q = question.strip()
    q_lower = q.lower()
    symbol = "BTC" if ("bitcoin" in q_lower or "btc" in q_lower) else "ETH"

    target_match = re.search(r"\$([\d,]+(?:\.\d+)?)(\s*[kK])?", q)
    if not target_match:
        raise ValueError(f"Cannot parse target price from: {question}")
    target = float(target_match.group(1).replace(",", ""))
    if target_match.group(2):
        target *= 1000.0

    date_match = re.search(r"\bby\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\??$", q)
    if not date_match:
        raise ValueError(f"Cannot parse end date from: {question}")
    date_raw = date_match.group(1)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            end_date = datetime.strptime(date_raw, fmt).replace(tzinfo=UTC)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Cannot parse date format from: {date_raw}")

    return symbol, int(target) if target.is_integer() else target, end_date


def best_bid_ask(book: dict):
    bids = [float(x["price"]) for x in book.get("bids", []) if "price" in x]
    asks = [float(x["price"]) for x in book.get("asks", []) if "price" in x]
    if not bids or not asks:
        raise ValueError("Order book missing bids/asks")
    return max(bids), min(asks)


def gamma_get_markets(offset: int, limit: int = 500):
    resp = requests.get(
        f"{GAMMA_URL}/markets",
        params={"limit": limit, "offset": offset, "active": "true", "closed": "false"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def deribit_call(method: str, params: dict):
    resp = requests.get(f"{DERIBIT_URL}/{method}", params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"Deribit error: {payload['error']}")
    return payload["result"]


def parse_deribit_expiry(code: str):
    return datetime.strptime(code, "%d%b%y").replace(tzinfo=UTC)


def fetch_all_active_markets(max_pages: int = 15):
    markets = []
    for page in range(max_pages):
        batch = gamma_get_markets(offset=page * 500, limit=500)
        if not batch:
            break
        markets.extend(batch)
        if len(batch) < 500:
            break
    return markets


def is_btc_barrier_market(question: str):
    q = question.lower()
    has_asset = ("bitcoin" in q) or ("btc" in q)
    has_barrier_word = any(x in q for x in (" hit ", " reach ", " above ", " exceed "))
    return has_asset and has_barrier_word and " by " in q and "$" in q


def fetch_deribit_expiry_dates(symbol: str):
    instruments = deribit_call(
        "get_instruments", {"currency": symbol, "kind": "option", "expired": "false"}
    )
    expiries = sorted({x["instrument_name"].split("-")[1] for x in instruments}, key=parse_deribit_expiry)
    return expiries, instruments


def choose_market(markets: Iterable[dict], deribit_max_expiry: datetime):
    ranked = rank_markets(markets, deribit_max_expiry)
    if not ranked:
        raise RuntimeError("No eligible BTC barrier market found with Deribit coverage")
    return ranked[0][1]


def choose_markets(markets: Iterable[dict], deribit_max_expiry: datetime, batch_size: int):
    ranked = rank_markets(markets, deribit_max_expiry)
    if not ranked:
        raise RuntimeError("No eligible BTC barrier market found with Deribit coverage")
    n = max(1, batch_size)
    return [m for _, m in ranked[:n]]


def rank_markets(markets: Iterable[dict], deribit_max_expiry: datetime):
    now = datetime.now(UTC)
    ranked = []
    for m in markets:
        q = m.get("question", "")
        if not is_btc_barrier_market(q):
            continue
        try:
            _, _, end_date = parse_target_from_question(q)
        except ValueError:
            continue
        if not (now < end_date <= deribit_max_expiry):
            continue
        prices = parse_json_or_list(m.get("outcomePrices"))
        if not prices:
            continue
        try:
            yes_price = float(prices[0])
        except ValueError:
            continue
        ranked.append((abs(yes_price - 0.5), m))
    ranked.sort(key=lambda x: x[0])
    return ranked


def fetch_yes_token_book(market: dict):
    token_ids = parse_json_or_list(market.get("clobTokenIds"))
    if not token_ids:
        raise RuntimeError("Missing token ids")
    yes_idx = 0
    outcomes = parse_json_or_list(market.get("outcomes"))
    for i, outcome in enumerate(outcomes):
        if str(outcome).lower() == "yes":
            yes_idx = i
            break
    yes_idx = min(yes_idx, len(token_ids) - 1)
    token_id = token_ids[yes_idx]
    resp = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}, timeout=20)
    resp.raise_for_status()
    return token_id, resp.json()


def estimate_taker_cost(book: dict, fee_rate: float, notional_usd: float = 500.0):
    best_bid, best_ask = best_bid_ask(book)
    spread_cost = (best_ask - best_bid) / 2

    asks = sorted(
        ((float(x["price"]), float(x["size"])) for x in book.get("asks", []) if "price" in x and "size" in x),
        key=lambda x: x[0],
    )
    remaining_notional = notional_usd
    shares_filled = 0.0
    spent = 0.0
    for price, size in asks:
        level_notional = price * size
        take_notional = min(level_notional, remaining_notional)
        if take_notional <= 0:
            continue
        shares = take_notional / price
        spent += take_notional
        shares_filled += shares
        remaining_notional -= take_notional
        if remaining_notional <= 1e-9:
            break
    if shares_filled <= 0:
        raise RuntimeError("Cannot fill from asks")
    avg_fill_price = spent / shares_filled
    slippage = max(0.0, avg_fill_price - best_ask)

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_cost": spread_cost,
        "slippage": slippage,
        "fee": fee_rate,
        "total_cost": fee_rate + spread_cost + slippage,
        "avg_fill_price": avg_fill_price,
    }


def fetch_btc_spot():
    result = deribit_call("get_index_price", {"index_name": "btc_usd"})
    return float(result["index_price"])


def choose_deribit_expiry_for_market(market_end: datetime, expiries: list[str]):
    expiry_dates = [(e, parse_deribit_expiry(e)) for e in expiries]
    later = [(e, d) for e, d in expiry_dates if d >= market_end]
    if later:
        return min(later, key=lambda x: x[1])[0]
    return max(expiry_dates, key=lambda x: x[1])[0]


def fetch_atm_iv(expiry_code: str, spot: float, instruments: list[dict]):
    calls = []
    for item in instruments:
        name = item["instrument_name"]
        parts = name.split("-")
        if len(parts) != 4:
            continue
        if parts[1] != expiry_code or parts[3] != "C":
            continue
        strike = float(parts[2])
        calls.append((abs(strike - spot), strike, name))
    if not calls:
        raise RuntimeError(f"No call instruments found for expiry {expiry_code}")
    _, strike, instrument_name = min(calls, key=lambda x: x[0])
    book = deribit_call("get_order_book", {"instrument_name": instrument_name})
    mark_iv = book.get("mark_iv")
    if not mark_iv:
        bid_iv = book.get("bid_iv", 0.0)
        ask_iv = book.get("ask_iv", 0.0)
        mark_iv = (bid_iv + ask_iv) / 2 if bid_iv and ask_iv else max(bid_iv, ask_iv)
    if not mark_iv:
        raise RuntimeError(f"No IV available for {instrument_name}")
    iv = float(mark_iv)
    iv = iv / 100.0 if iv > 1 else iv
    return iv, instrument_name, strike


def fetch_hourly_returns(days: int = 120):
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    start_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
    result = deribit_call(
        "get_tradingview_chart_data",
        {
            "instrument_name": "BTC-PERPETUAL",
            "start_timestamp": start_ms,
            "end_timestamp": end_ms,
            "resolution": "60",
        },
    )
    closes = np.array(result.get("close", []), dtype=float)
    closes = closes[np.isfinite(closes)]
    if closes.size < 100:
        raise RuntimeError("Not enough close data for jump-diffusion estimation")
    log_returns = np.diff(np.log(closes))
    return log_returns


def estimate_jump_params(log_returns: np.ndarray, steps_per_year: int = 24 * 365):
    mu_r = float(np.mean(log_returns))
    sigma_r = float(np.std(log_returns, ddof=1))

    threshold = 2.5 * sigma_r
    jumps = log_returns[np.abs(log_returns - mu_r) > threshold]
    lam = float(len(jumps) / len(log_returns) * steps_per_year)
    if len(jumps) > 1:
        mu_j = float(np.mean(jumps))
        sigma_j = float(np.std(jumps, ddof=1))
    elif len(jumps) == 1:
        mu_j = float(jumps[0])
        sigma_j = 1e-8
    else:
        mu_j = 0.0
        sigma_j = 1e-8

    return {
        "mu": mu_r * steps_per_year,
        "sigma": sigma_r * math.sqrt(steps_per_year),
        "lambda": lam,
        "mu_j": mu_j,
        "sigma_j": sigma_j,
    }


def simulate_barrier_prob_jump_diffusion(
    s0: float,
    target: float,
    t_years: float,
    params: dict,
    n_paths: int = 50000,
    n_steps: int = 240,
    seed: int = 42,
):
    rng = np.random.default_rng(seed)
    dt = t_years / n_steps
    s = np.full(n_paths, s0, dtype=float)
    touched = np.zeros(n_paths, dtype=bool)

    mu = params["mu"]
    sigma = max(params["sigma"], 1e-6)
    lam = max(params["lambda"], 0.0)
    mu_j = params["mu_j"]
    sigma_j = max(params["sigma_j"], 1e-8)
    k = math.exp(mu_j + 0.5 * sigma_j * sigma_j) - 1.0
    drift = (mu - 0.5 * sigma * sigma - lam * k) * dt
    vol = sigma * math.sqrt(dt)

    for _ in range(n_steps):
        z = rng.standard_normal(n_paths)
        jump_count = rng.poisson(lam * dt, n_paths) if lam > 0 else np.zeros(n_paths, dtype=int)
        jump_term = np.zeros(n_paths, dtype=float)
        jump_mask = jump_count > 0
        if np.any(jump_mask):
            means = jump_count[jump_mask] * mu_j
            stds = np.sqrt(jump_count[jump_mask]) * sigma_j
            jump_term[jump_mask] = rng.normal(means, stds)
        s *= np.exp(drift + vol * z + jump_term)
        touched |= s >= target

    p = float(np.mean(touched))
    ci = 1.96 * math.sqrt(max(p * (1.0 - p), 1e-12) / n_paths)
    return p, ci


def simulate_barrier_prob_flat_iv(
    s0: float,
    target: float,
    t_years: float,
    iv: float,
    n_paths: int = 50000,
    n_steps: int = 240,
    seed: int = 7,
):
    rng = np.random.default_rng(seed)
    dt = t_years / n_steps
    s = np.full(n_paths, s0, dtype=float)
    touched = np.zeros(n_paths, dtype=bool)

    sigma = max(iv, 1e-6)
    drift = -0.5 * sigma * sigma * dt
    vol = sigma * math.sqrt(dt)

    for _ in range(n_steps):
        z = rng.standard_normal(n_paths)
        s *= np.exp(drift + vol * z)
        touched |= s >= target

    p = float(np.mean(touched))
    ci = 1.96 * math.sqrt(max(p * (1.0 - p), 1e-12) / n_paths)
    return p, ci


def evaluate_market(market: dict, expiries: list[str], instruments: list[dict]):
    symbol, target, market_end = parse_target_from_question(market["question"])
    yes_price = float(parse_json_or_list(market["outcomePrices"])[0])

    token_id, book = fetch_yes_token_book(market)
    fee_rate = 0.0 if not market.get("feesEnabled") else 0.0156
    costs = estimate_taker_cost(book, fee_rate=fee_rate, notional_usd=500.0)

    s0 = fetch_btc_spot()
    t_years = max((market_end - datetime.now(UTC)).total_seconds(), 1.0) / (365.25 * 24 * 3600)
    expiry_code = choose_deribit_expiry_for_market(market_end, expiries)
    iv, iv_instrument, iv_strike = fetch_atm_iv(expiry_code, spot=s0, instruments=instruments)

    p_a, ci_a = simulate_barrier_prob_flat_iv(s0=s0, target=float(target), t_years=t_years, iv=iv)
    log_returns = fetch_hourly_returns(days=120)
    jump_params = estimate_jump_params(log_returns)
    p_b, ci_b = simulate_barrier_prob_jump_diffusion(
        s0=s0, target=float(target), t_years=t_years, params=jump_params
    )

    p_combined = 0.5 * p_a + 0.5 * p_b
    uncertainty = 0.5 * max(ci_a, ci_b)
    edge_gross = p_combined - yes_price
    edge_net = abs(edge_gross) - costs["total_cost"] - uncertainty
    direction = "BUY_NO" if edge_gross < 0 else "BUY_YES"
    verdict = "GO-ish" if edge_net > 0.03 else ("THIN" if edge_net > 0 else "NO-GO")

    record = build_result_record(
        market_question=market["question"],
        market_slug=market.get("slug", ""),
        market_end_date=market.get("endDate", ""),
        yes_price=yes_price,
        spot=s0,
        target=float(target),
        t_years=t_years,
        iv=iv,
        model_a_prob=p_a,
        model_a_ci=ci_a,
        model_b_prob=p_b,
        model_b_ci=ci_b,
        combined_prob=p_combined,
        edge_gross=edge_gross,
        direction=direction,
        uncertainty=uncertainty,
        total_cost=costs["total_cost"],
        edge_net=edge_net,
        verdict=verdict,
    )
    details = {
        "token_id": token_id,
        "target": target,
        "market_end": market_end,
        "costs": costs,
        "expiry_code": expiry_code,
        "iv_instrument": iv_instrument,
        "iv_strike": iv_strike,
        "p_a": p_a,
        "ci_a": ci_a,
        "p_b": p_b,
        "ci_b": ci_b,
        "p_combined": p_combined,
        "edge_gross": edge_gross,
        "direction": direction,
        "uncertainty": uncertainty,
        "edge_net": edge_net,
        "verdict": verdict,
    }
    return record, details


def evaluate_market_with_optional_jump(
    market: dict,
    expiries: list[str],
    instruments: list[dict],
    jump_params: dict | None = None,
):
    if jump_params is None:
        return evaluate_market(market, expiries=expiries, instruments=instruments)

    symbol, target, market_end = parse_target_from_question(market["question"])
    yes_price = float(parse_json_or_list(market["outcomePrices"])[0])

    token_id, book = fetch_yes_token_book(market)
    fee_rate = 0.0 if not market.get("feesEnabled") else 0.0156
    costs = estimate_taker_cost(book, fee_rate=fee_rate, notional_usd=500.0)

    s0 = fetch_btc_spot()
    t_years = max((market_end - datetime.now(UTC)).total_seconds(), 1.0) / (365.25 * 24 * 3600)
    expiry_code = choose_deribit_expiry_for_market(market_end, expiries)
    iv, iv_instrument, iv_strike = fetch_atm_iv(expiry_code, spot=s0, instruments=instruments)

    p_a, ci_a = simulate_barrier_prob_flat_iv(s0=s0, target=float(target), t_years=t_years, iv=iv)
    p_b, ci_b = simulate_barrier_prob_jump_diffusion(
        s0=s0, target=float(target), t_years=t_years, params=jump_params
    )

    p_combined = 0.5 * p_a + 0.5 * p_b
    uncertainty = 0.5 * max(ci_a, ci_b)
    edge_gross = p_combined - yes_price
    edge_net = abs(edge_gross) - costs["total_cost"] - uncertainty
    direction = "BUY_NO" if edge_gross < 0 else "BUY_YES"
    verdict = "GO-ish" if edge_net > 0.03 else ("THIN" if edge_net > 0 else "NO-GO")

    record = build_result_record(
        market_question=market["question"],
        market_slug=market.get("slug", ""),
        market_end_date=market.get("endDate", ""),
        yes_price=yes_price,
        spot=s0,
        target=float(target),
        t_years=t_years,
        iv=iv,
        model_a_prob=p_a,
        model_a_ci=ci_a,
        model_b_prob=p_b,
        model_b_ci=ci_b,
        combined_prob=p_combined,
        edge_gross=edge_gross,
        direction=direction,
        uncertainty=uncertainty,
        total_cost=costs["total_cost"],
        edge_net=edge_net,
        verdict=verdict,
    )
    details = {
        "token_id": token_id,
        "target": target,
        "market_end": market_end,
        "costs": costs,
        "expiry_code": expiry_code,
        "iv_instrument": iv_instrument,
        "iv_strike": iv_strike,
        "p_a": p_a,
        "ci_a": ci_a,
        "p_b": p_b,
        "ci_b": ci_b,
        "p_combined": p_combined,
        "edge_gross": edge_gross,
        "direction": direction,
        "uncertainty": uncertainty,
        "edge_net": edge_net,
        "verdict": verdict,
    }
    return record, details


def evaluate_markets(
    selected: list[dict],
    expiries: list[str],
    instruments: list[dict],
    workers: int = 1,
    evaluator=evaluate_market,
):
    if workers <= 1 or len(selected) <= 1:
        return [evaluator(market, expiries, instruments) for market in selected]

    results: list[tuple[dict, dict] | None] = [None] * len(selected)
    max_workers = min(workers, len(selected))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(evaluator, market, expiries, instruments): idx
            for idx, market in enumerate(selected)
        }
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
    return [x for x in results if x is not None]


def benchmark_evaluation(
    selected: list[dict],
    expiries: list[str],
    instruments: list[dict],
    evaluator=evaluate_market,
    parallel_workers: int = 2,
):
    seq_t0 = time.perf_counter()
    evaluated_sequential = evaluate_markets(
        selected,
        expiries=expiries,
        instruments=instruments,
        workers=1,
        evaluator=evaluator,
    )
    sequential_seconds = time.perf_counter() - seq_t0

    workers = min(len(selected), max(2, parallel_workers))
    par_t0 = time.perf_counter()
    evaluated_parallel = evaluate_markets(
        selected,
        expiries=expiries,
        instruments=instruments,
        workers=workers,
        evaluator=evaluator,
    )
    parallel_seconds = time.perf_counter() - par_t0

    speedup = (sequential_seconds / parallel_seconds) if parallel_seconds > 0 else float("inf")
    return {
        "parallel_workers": workers,
        "sequential_seconds": sequential_seconds,
        "parallel_seconds": parallel_seconds,
        "speedup": speedup,
        "evaluated_sequential": evaluated_sequential,
        "evaluated_parallel": evaluated_parallel,
    }


def main(
    output_dir: str | Path,
    run_id: str | None = None,
    batch_size: int = 1,
    workers: int = 1,
    benchmark: bool = False,
):
    print("=" * 72)
    print("SPIKE 3 - E2E TRIAL")
    print("=" * 72)

    expiries, instruments = fetch_deribit_expiry_dates("BTC")
    deribit_max_expiry = parse_deribit_expiry(expiries[-1])
    print(f"Deribit max expiry: {deribit_max_expiry.date()} ({len(expiries)} expiries)")

    markets = fetch_all_active_markets(max_pages=20)
    selected = choose_markets(markets, deribit_max_expiry=deribit_max_expiry, batch_size=batch_size)
    effective_workers = max(1, workers)
    print(f"Selected {len(selected)} market(s), workers={effective_workers}")

    log_returns = fetch_hourly_returns(days=120)
    jump_params = estimate_jump_params(log_returns)
    evaluator = partial(evaluate_market_with_optional_jump, jump_params=jump_params)

    if benchmark and len(selected) > 1:
        benchmark_workers = effective_workers if effective_workers > 1 else min(2, len(selected))
        bench = benchmark_evaluation(
            selected,
            expiries=expiries,
            instruments=instruments,
            evaluator=evaluator,
            parallel_workers=benchmark_workers,
        )
        print(
            "\nBenchmark:\n"
            f"  sequential(1 worker): {bench['sequential_seconds']:.3f}s\n"
            f"  parallel({bench['parallel_workers']} workers): {bench['parallel_seconds']:.3f}s\n"
            f"  speedup: {bench['speedup']:.2f}x"
        )
        evaluated = bench["evaluated_parallel"] if effective_workers > 1 else bench["evaluated_sequential"]
    else:
        if benchmark:
            print("\nBenchmark skipped: requires at least 2 selected markets.")
        evaluated = evaluate_markets(
            selected,
            expiries=expiries,
            instruments=instruments,
            workers=effective_workers,
            evaluator=evaluator,
        )

    records: list[dict] = []
    for i, (market, (record, details)) in enumerate(zip(selected, evaluated), start=1):
        print(f"\n[{i}/{len(selected)}] Selected market: {market['question']}")
        print(
            f"Market end: {details['market_end'].date()} | Yes price: {record['yes_price']:.4f}\n"
            f"Yes token id: {details['token_id'][:18]}...\n"
            "Cost model (taker): "
            f"fee={details['costs']['fee']:.4f}, spread_cost={details['costs']['spread_cost']:.4f}, "
            f"slippage={details['costs']['slippage']:.4f}, total={details['costs']['total_cost']:.4f}\n"
            f"Deribit mapping: expiry={details['expiry_code']}, instrument={details['iv_instrument']}, "
            f"ATM strike={details['iv_strike']:,.0f}, IV={record['iv']:.4f}\n"
            f"Spot={record['spot']:,.2f}, Target={details['target']:,.0f}, T={record['t_years']:.3f}y"
        )
        print("\nModel outputs:")
        print(f"  Model A (Q, flat-IV): p={details['p_a']:.4f} ± {details['ci_a']:.4f}")
        print(f"  Model B (P, jump-diff): p={details['p_b']:.4f} ± {details['ci_b']:.4f}")
        print(f"  Combined: p={details['p_combined']:.4f}")
        print("\nEdge:")
        print(f"  Market yes price: {record['yes_price']:.4f}")
        print(f"  edge_gross = {details['edge_gross']:.4f}")
        print(f"  direction = {details['direction']}")
        print(f"  uncertainty buffer = {details['uncertainty']:.4f}")
        print(f"  total_cost = {details['costs']['total_cost']:.4f}")
        print(f"  edge_net = {details['edge_net']:.4f}")
        print(f"  verdict = {details['verdict']}")
        records.append(record)

    if len(records) == 1:
        json_path, csv_path = write_result_files(records[0], output_dir=output_dir, run_id=run_id)
    else:
        json_path, csv_path = write_batch_files(records, output_dir=output_dir, run_id=run_id)
    print("\nArtifacts:")
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Spike 3 end-to-end trial")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "output"),
        help="Directory to write JSON/CSV artifacts.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run id used in output filename.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Number of markets to run and aggregate.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker threads for parallel market evaluation.",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Print sequential vs parallel timing comparison.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        output_dir=args.output_dir,
        run_id=args.run_id,
        batch_size=args.batch_size,
        workers=args.workers,
        benchmark=args.benchmark,
    )
