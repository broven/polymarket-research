from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any, Callable, Iterable


def parse_json_or_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def iter_time_windows(
    start_ts: int,
    end_ts: int,
    window_seconds: int,
) -> Iterable[tuple[int, int]]:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    cursor = start_ts
    while cursor < end_ts:
        nxt = min(cursor + window_seconds, end_ts)
        yield cursor, nxt
        cursor = nxt


def paginate_trades(
    fetch_page_fn: Callable[[int, int], list[dict[str, Any]]],
    start_offset: int,
    limit: int,
    max_offset: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if start_offset < 0:
        raise ValueError("start_offset must be non-negative")

    all_rows: list[dict[str, Any]] = []
    offset = start_offset
    truncated = False

    while True:
        if offset >= max_offset:
            truncated = True
            break
        page_limit = min(limit, max_offset - offset)
        if page_limit <= 0:
            truncated = True
            break
        rows = fetch_page_fn(offset, page_limit)
        if not rows:
            break
        all_rows.extend(rows)
        offset += len(rows)
        if len(rows) < page_limit:
            break

    return all_rows, offset, truncated


def build_trade_row_hash(row: dict[str, Any]) -> str:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket history collector (v1 scaffold)")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print("Polymarket history collector scaffold is ready.")


if __name__ == "__main__":
    main()
