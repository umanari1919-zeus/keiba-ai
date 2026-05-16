"""EV計算の市場インパクト境界テスト。"""

from __future__ import annotations

import importlib

import pandas as pd


def test_run_ev_today_filters_by_ev_after_market_impact(tmp_path, monkeypatch):
    import pipeline.ev_engine_10 as ev_engine

    monkeypatch.setattr(ev_engine, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ev_engine, "_load_ev_boost_map", lambda: {})

    pd.DataFrame([{
        "race_code": "2026051606010101",
        "umaban": 7,
        "bamei": "テストホース",
        "win_prob": 5.0,
        "odds": 30.0,
        "stake_amount": 10_000,
        "pool_jpy": 500_000,
    }]).to_csv(tmp_path / "predictions_20260516.csv", index=False)

    result = ev_engine.run_ev_today("20260516")

    assert result.empty


def test_run_ev_today_outputs_market_impact_columns(tmp_path, monkeypatch):
    import pipeline.ev_engine_10 as ev_engine

    monkeypatch.setattr(ev_engine, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ev_engine, "_load_ev_boost_map", lambda: {})

    pd.DataFrame([{
        "race_code": "2026051606010102",
        "umaban": 3,
        "bamei": "バリューホース",
        "win_prob": 8.0,
        "odds": 30.0,
        "stake_amount": 1_000,
        "pool_jpy": 50_000_000,
    }]).to_csv(tmp_path / "predictions_20260516.csv", index=False)

    result = ev_engine.run_ev_today("20260516")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["expected_value_naive"] > row["expected_value"]
    assert row["odds_after_impact"] < row["odds_decimal"]
    assert bool(row["market_impact_applied"]) is True


def test_market_impact_module_does_not_use_takeout_twice():
    market_impact = importlib.import_module("pipeline.market_impact")

    no_takeout = market_impact.expected_value_with_impact(
        win_prob=0.05,
        old_odds=30.0,
        bet=10_000,
        takeout_rate=0.0,
        pool=50_000_000,
    )
    with_takeout_arg = market_impact.expected_value_with_impact(
        win_prob=0.05,
        old_odds=30.0,
        bet=10_000,
        takeout_rate=0.20,
        pool=50_000_000,
    )

    assert no_takeout == with_takeout_arg
