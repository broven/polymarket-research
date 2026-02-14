import importlib.util
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1] / "polymarket_history_collector.py"
    )
    spec = importlib.util.spec_from_file_location(
        "polymarket_history_collector", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_parse_json_or_list_accepts_multiple_formats():
    mod = _load_module()
    assert mod.parse_json_or_list(["a", "b"]) == ["a", "b"]
    assert mod.parse_json_or_list('["a", "b"]') == ["a", "b"]
    assert mod.parse_json_or_list(None) == []


def test_iter_time_windows_includes_tail_window():
    mod = _load_module()
    windows = list(mod.iter_time_windows(0, 10, 4))
    assert windows == [(0, 4), (4, 8), (8, 10)]


def test_paginate_trades_honors_max_offset_and_reports_truncation():
    mod = _load_module()

    def fetch_page(offset, limit):
        if offset > 3000:
            raise AssertionError("offset cap violated")
        return [{"offset": offset}] * limit

    rows, next_offset, truncated = mod.paginate_trades(
        fetch_page_fn=fetch_page,
        start_offset=0,
        limit=500,
        max_offset=3000,
    )
    assert truncated is True
    assert next_offset == 3000
    assert len(rows) == 3000


def test_build_trade_row_hash_is_deterministic():
    mod = _load_module()
    row = {"conditionId": "0xabc", "price": 0.1, "size": 10, "timestamp": 123}
    assert mod.build_trade_row_hash(row) == mod.build_trade_row_hash(row)
