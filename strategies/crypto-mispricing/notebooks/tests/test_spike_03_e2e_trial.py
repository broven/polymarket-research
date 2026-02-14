import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "spike_03_e2e_trial.py"
    spec = importlib.util.spec_from_file_location("spike_03_e2e_trial", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_parse_target_from_question_k_notation():
    mod = _load_module()
    symbol, target, end_date = mod.parse_target_from_question(
        "Will Bitcoin hit $150k by June 30, 2026?"
    )
    assert symbol == "BTC"
    assert target == 150000
    assert end_date.isoformat() == "2026-06-30T00:00:00+00:00"


def test_best_bid_ask_handles_unsorted_book_levels():
    mod = _load_module()
    book = {
        "bids": [{"price": "0.001"}, {"price": "0.015"}, {"price": "0.010"}],
        "asks": [{"price": "0.999"}, {"price": "0.017"}, {"price": "0.021"}],
    }
    best_bid, best_ask = mod.best_bid_ask(book)
    assert best_bid == 0.015
    assert best_ask == 0.017


def test_parse_json_or_list_accepts_both_formats():
    mod = _load_module()
    assert mod.parse_json_or_list("[\"0.41\", \"0.59\"]") == ["0.41", "0.59"]
    assert mod.parse_json_or_list(["0.41", "0.59"]) == ["0.41", "0.59"]


def test_build_result_record_includes_required_fields():
    mod = _load_module()
    record = mod.build_result_record(
        market_question="Will Bitcoin hit $150k by June 30, 2026?",
        market_slug="will-bitcoin-hit-150k-by-june-30-2026",
        market_end_date="2026-07-01T04:00:00Z",
        yes_price=0.0695,
        spot=70000.0,
        target=150000.0,
        t_years=0.37,
        iv=0.49,
        model_a_prob=0.0065,
        model_a_ci=0.0007,
        model_b_prob=0.0006,
        model_b_ci=0.0002,
        combined_prob=0.0036,
        edge_gross=-0.0659,
        direction="BUY_NO",
        uncertainty=0.0004,
        total_cost=0.0208,
        edge_net=0.0448,
        verdict="GO-ish",
    )
    required = {
        "market_question",
        "yes_price",
        "combined_prob",
        "edge_net",
        "direction",
        "verdict",
    }
    assert required.issubset(record.keys())
    assert record["direction"] == "BUY_NO"


def test_write_result_files_creates_json_and_csv(tmp_path):
    mod = _load_module()
    record = {"market_question": "q", "edge_net": 0.1, "direction": "BUY_NO", "verdict": "GO-ish"}
    json_path, csv_path = mod.write_result_files(record, output_dir=tmp_path, run_id="unit")

    assert json_path.exists()
    assert csv_path.exists()

    payload = json.loads(json_path.read_text())
    assert payload["market_question"] == "q"
    assert payload["edge_net"] == 0.1

    csv_lines = csv_path.read_text().strip().splitlines()
    assert len(csv_lines) == 2
    assert "market_question" in csv_lines[0]
    assert "edge_net" in csv_lines[0]


def test_choose_markets_returns_top_n():
    mod = _load_module()
    markets = [
        {
            "question": "Will Bitcoin hit $120k by June 30, 2026?",
            "outcomePrices": ["0.40", "0.60"],
        },
        {
            "question": "Will Bitcoin hit $150k by June 30, 2026?",
            "outcomePrices": ["0.07", "0.93"],
        },
        {
            "question": "Will Bitcoin hit $110k by June 30, 2026?",
            "outcomePrices": ["0.30", "0.70"],
        },
        {
            "question": "Will Bitcoin hit $90k by December 31, 2027?",
            "outcomePrices": ["0.50", "0.50"],
        },
    ]
    selected = mod.choose_markets(
        markets,
        deribit_max_expiry=datetime(2026, 12, 25, tzinfo=timezone.utc),
        batch_size=2,
    )
    assert len(selected) == 2
    assert selected[0]["question"] == "Will Bitcoin hit $120k by June 30, 2026?"
    assert selected[1]["question"] == "Will Bitcoin hit $110k by June 30, 2026?"


def test_write_batch_files_creates_json_and_csv(tmp_path):
    mod = _load_module()
    records = [
        {"market_question": "q1", "edge_net": 0.1, "direction": "BUY_NO", "verdict": "GO-ish"},
        {"market_question": "q2", "edge_net": 0.2, "direction": "BUY_YES", "verdict": "GO-ish"},
    ]
    json_path, csv_path = mod.write_batch_files(records, output_dir=tmp_path, run_id="unitbatch")

    assert json_path.exists()
    assert csv_path.exists()
    payload = json.loads(json_path.read_text())
    assert len(payload) == 2
    assert payload[1]["market_question"] == "q2"
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_evaluate_markets_parallel_preserves_order():
    mod = _load_module()
    selected = [
        {"question": "m1"},
        {"question": "m2"},
        {"question": "m3"},
    ]

    def fake_evaluator(market, expiries, instruments):
        if market["question"] == "m1":
            time.sleep(0.05)
        return {"market_question": market["question"]}, {"verdict": "OK", "costs": {"total_cost": 0}}

    evaluated = mod.evaluate_markets(
        selected,
        expiries=[],
        instruments=[],
        workers=3,
        evaluator=fake_evaluator,
    )
    names = [record["market_question"] for record, _ in evaluated]
    assert names == ["m1", "m2", "m3"]


def test_benchmark_evaluation_reports_speedup():
    mod = _load_module()
    selected = [{"question": "m1"}, {"question": "m2"}, {"question": "m3"}]

    def fake_evaluator(market, expiries, instruments):
        time.sleep(0.03)
        return {"market_question": market["question"]}, {"verdict": "OK", "costs": {"total_cost": 0}}

    bench = mod.benchmark_evaluation(
        selected,
        expiries=[],
        instruments=[],
        evaluator=fake_evaluator,
        parallel_workers=3,
    )

    assert bench["sequential_seconds"] > 0
    assert bench["parallel_seconds"] > 0
    assert bench["parallel_seconds"] < bench["sequential_seconds"]
    assert bench["speedup"] > 1
    assert len(bench["evaluated_parallel"]) == 3
