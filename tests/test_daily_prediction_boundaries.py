"""日次予測とバックテスト成果物の境界テスト。"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def load_trade_module():
    spec = importlib.util.spec_from_file_location("trade_stage_for_test", ROOT / "pipeline_v2" / "07_trade.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_batch_inference_runs_daily_prediction_and_daily_ev(monkeypatch):
    from agents.batch_inference_agent import BatchInferenceAgent
    from agents.base_agent import AgentMeta

    calls = []

    def fake_run_script(self, rel_path, meta, extra_args=None):
        calls.append((rel_path, extra_args or []))
        return True, "ok"

    monkeypatch.setattr(BatchInferenceAgent, "_run_script", fake_run_script)
    monkeypatch.setattr(BatchInferenceAgent, "_load_predictions", lambda self, today: [])

    BatchInferenceAgent(dry_run=False)._run(AgentMeta(run_tag="run_20260515_test"), {})

    assert calls[0] == ("pipeline/predict_04.py", [])
    assert calls[1] == ("pipeline/ev_engine_10.py", ["--date", datetime.now().strftime("%Y%m%d")])


def test_batch_inference_dry_run_keeps_scripts_in_dry_run(monkeypatch):
    from agents.batch_inference_agent import BatchInferenceAgent
    from agents.base_agent import AgentMeta

    calls = []

    def fake_run_script(self, rel_path, meta, extra_args=None):
        calls.append((rel_path, extra_args or []))
        return True, "ok"

    monkeypatch.setattr(BatchInferenceAgent, "_run_script", fake_run_script)
    monkeypatch.setattr(BatchInferenceAgent, "_load_predictions", lambda self, today: [])

    BatchInferenceAgent(dry_run=True)._run(AgentMeta(run_tag="run_20260515_test"), {})

    assert calls[0] == ("pipeline/predict_04.py", ["--dry-run"])
    assert calls[1] == ("pipeline/ev_engine_10.py", ["--dry-run"])


def test_batch_inference_ignores_backtest_ev_analysis_when_daily_prediction_is_missing(tmp_path, monkeypatch):
    import agents.batch_inference_agent as batch_module
    from agents.batch_inference_agent import BatchInferenceAgent

    monkeypatch.setattr(batch_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(batch_module, "DATA_DIR", tmp_path / "data")
    batch_module.DATA_DIR.mkdir(exist_ok=True)

    pd.DataFrame([{
        "race_code": "2026032906030202",
        "umaban": 3,
        "win_probability": 0.23,
        "expected_value": 54.8,
        "odds_decimal": 237.9,
        "kakutei_chakujun": 1,
        "analysis_mode": "BACKTEST_ONLY",
    }]).to_csv(batch_module.DATA_DIR / "ev_analysis_2026.csv", index=False)

    assert BatchInferenceAgent(dry_run=False)._load_predictions("20260515") == []


def test_batch_inference_loads_only_daily_ev_today_file(tmp_path, monkeypatch):
    import agents.batch_inference_agent as batch_module
    from agents.batch_inference_agent import BatchInferenceAgent

    monkeypatch.setattr(batch_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(batch_module, "DATA_DIR", tmp_path / "data")
    batch_module.DATA_DIR.mkdir(exist_ok=True)

    pd.DataFrame([{
        "race_code": "2026051506010101",
        "umaban": 7,
        "win_probability": 0.21,
        "expected_value": 1.4,
        "odds_decimal": 12.0,
    }]).to_csv(batch_module.DATA_DIR / "ev_today_20260515.csv", index=False)

    preds = BatchInferenceAgent(dry_run=False)._load_predictions("20260515")

    assert len(preds) == 1
    assert preds[0]["race_id"] == "2026051506010101"
    assert preds[0]["entry_id"] == "7"


def test_trade_ignores_backtest_ev_analysis_when_daily_prediction_is_missing(tmp_path, monkeypatch):
    trade = load_trade_module()
    monkeypatch.setattr(trade, "BASE_DIR", tmp_path)
    monkeypatch.setattr(trade, "DATA_DIR", tmp_path / "data")
    trade.DATA_DIR.mkdir(exist_ok=True)

    pd.DataFrame([{
        "race_code": "2026032906030202",
        "umaban": 3,
        "win_probability": 0.23,
        "expected_value": 54.8,
        "odds_decimal": 237.9,
        "kakutei_chakujun": 1,
        "analysis_mode": "BACKTEST_ONLY",
    }]).to_csv(tmp_path / "ev_analysis_2026.csv", index=False)

    assert trade._load_predictions("20260515") == []


def test_trade_loads_only_daily_ev_today_file(tmp_path, monkeypatch):
    trade = load_trade_module()
    monkeypatch.setattr(trade, "BASE_DIR", tmp_path)
    monkeypatch.setattr(trade, "DATA_DIR", tmp_path / "data")
    trade.DATA_DIR.mkdir(exist_ok=True)

    pd.DataFrame([{
        "race_code": "2026051506010101",
        "umaban": 7,
        "win_probability": 0.21,
        "expected_value": 1.4,
        "odds_decimal": 12.0,
    }]).to_csv(trade.DATA_DIR / "ev_today_20260515.csv", index=False)

    preds = trade._load_predictions("20260515")

    assert len(preds) == 1
    assert preds[0]["race_id"] == "2026051506010101"
    assert preds[0]["entry_id"] == "7"


def test_backtest_rows_with_result_columns_are_rejected_for_trade_predictions():
    trade = load_trade_module()

    preds = trade._rows_to_predictions([{
        "race_code": "2026032906030202",
        "umaban": 3,
        "win_probability": 0.23,
        "expected_value": 54.8,
        "odds_decimal": 237.9,
        "kakutei_chakujun": 1,
    }])

    assert preds == []
