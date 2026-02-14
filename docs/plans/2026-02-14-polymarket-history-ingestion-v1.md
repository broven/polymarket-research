# Polymarket History Ingestion V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-oriented V1 data ingestor for Polymarket historical data (markets, prices history, trades/activity) with pagination, time slicing, resume state, and CSV/SQLite outputs (optional Parquet).

**Architecture:** Implement a single Python CLI module that orchestrates three pipelines: Gamma markets snapshot, CLOB prices-history by token/time windows, Data API trades by market pagination. Persist state in JSON for resumable runs; persist datasets to CSV + SQLite; emit optional Parquet if dependencies exist.

**Tech Stack:** Python 3.10+, requests, sqlite3, csv/json, argparse, hashlib, pandas(optional for parquet)

---

### Task 1: Create test scaffold and core failing tests

**Files:**
- Create: `strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py`
- Test: `strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py`

**Step 1: Write failing tests**
- `iter_time_windows` generates contiguous windows and includes final partial window.
- `paginate_trades` stops at `max_offset` and surfaces truncation.
- `parse_json_or_list` handles list/string/empty.
- `build_trade_row_hash` is deterministic.

**Step 2: Run tests to verify fail**
Run: `python3 -m pytest strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py -q`
Expected: FAIL (`module not found` / missing functions).

**Step 3: Commit**
```bash
git add strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py
git commit -m "test: add failing tests for polymarket history collector core"
```

### Task 2: Implement collector module (minimal to pass tests)

**Files:**
- Create: `strategies/crypto-mispricing/pipeline/polymarket_history_collector.py`
- Modify: `strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py`

**Step 1: Implement minimal functions**
- `parse_json_or_list`
- `iter_time_windows`
- `paginate_trades(fetch_page_fn, start_offset, limit, max_offset)`
- `build_trade_row_hash`

**Step 2: Run tests**
Run: `python3 -m pytest strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py -q`
Expected: PASS.

**Step 3: Commit**
```bash
git add strategies/crypto-mispricing/pipeline/polymarket_history_collector.py strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py
git commit -m "feat: add polymarket history collector core utilities"
```

### Task 3: Add end-to-end pipeline and storage adapters

**Files:**
- Modify: `strategies/crypto-mispricing/pipeline/polymarket_history_collector.py`
- Modify: `strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py`

**Step 1: Add API clients and orchestrator**
- Gamma markets fetch with paging (`limit/offset`, closed filter).
- CLOB prices-history fetch by token and time windows.
- Data API trades fetch by conditionId with offset paging + cap guard.

**Step 2: Add storage/resume**
- CSV append writers for markets/prices/trades.
- SQLite tables + upsert/ignore constraints.
- `state.json` load/save for prices cursor and trades offset.
- Optional parquet export (`--write-parquet`) guarded by dependency detection.

**Step 3: Add tests**
- Resume state update behavior.
- Trades pagination cap behavior.
- CSV write idempotency for headers.

**Step 4: Run tests**
Run: `python3 -m pytest strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py -q`
Expected: PASS.

**Step 5: Commit**
```bash
git add strategies/crypto-mispricing/pipeline/polymarket_history_collector.py strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py
git commit -m "feat: implement resumable polymarket history ingestion pipeline"
```

### Task 4: Smoke run and docs update

**Files:**
- Modify: `strategies/crypto-mispricing/docs/feasibility-spike.md`
- Create: `strategies/crypto-mispricing/pipeline/README.md`

**Step 1: Smoke run command**
Run:
```bash
python3 strategies/crypto-mispricing/pipeline/polymarket_history_collector.py \
  --output-dir strategies/crypto-mispricing/pipeline/output \
  --market-mode closed \
  --max-markets 3 \
  --start-ts 1735689600 \
  --end-ts 1736294400 \
  --price-window-days 1
```
Expected: Generates `markets.csv`, `prices_history.csv`, `trades.csv`, `polymarket_history.db`, `state.json`.

**Step 2: Update docs**
- Add quickstart and caveats (`trades offset<=3000`, use time slicing).

**Step 3: Verification**
Run:
```bash
python3 -m pytest strategies/crypto-mispricing/pipeline/tests/test_polymarket_history_collector.py -q
python3 strategies/crypto-mispricing/pipeline/polymarket_history_collector.py --help
```
Expected: tests pass, help shows all flags.

**Step 4: Commit**
```bash
git add strategies/crypto-mispricing/pipeline/README.md strategies/crypto-mispricing/docs/feasibility-spike.md

git commit -m "docs: add ingestion v1 usage and operational constraints"
```
