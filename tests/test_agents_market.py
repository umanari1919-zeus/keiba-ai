"""MarketAgent のユニットテスト。"""

import json
import math

import pytest

from agents.market_agent import MarketAgent


@pytest.mark.unit
class TestMarketAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        agent = MarketAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_snapshot_parsing(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """odds_snapshot JSON を正しく解析して market_signals を返す。"""
        monkeypatch.setattr("agents.market_agent.DATA_DIR", tmp_path)

        snapshot = {
            "R001": [
                {"horse_num": 1, "odds": 3.5},
                {"horse_num": 2, "odds": 12.0},
                {"horse_num": 3, "odds": 45.0},
            ],
        }
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        snap_file = tmp_path / f"odds_snapshot_{today}.json"
        snap_file.write_text(json.dumps(snapshot), encoding="utf-8")

        agent = MarketAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["races_analyzed"] == 1
        assert "R001" in out["market_signals"]
        sig = out["market_signals"]["R001"]
        assert sig["entry_count"] == 3
        assert sig["steam_detected"] is False
        assert sig["drift_detected"] is False

    def test_estimate_slippage_pure_math(self):
        """estimate_slippage の数値計算を検証する。"""
        res = MarketAgent.estimate_slippage(
            stake=10_000, odds=10.0, liquidity=0.5, steam_detected=False,
        )
        assert "slippage_pct" in res
        assert "expected_odds" in res
        assert res["expected_odds"] <= 10.0
        assert res["confidence"] == 0.5

        # STEAM 時はスリッページ増大
        res_steam = MarketAgent.estimate_slippage(
            stake=10_000, odds=10.0, liquidity=0.5, steam_detected=True,
        )
        assert res_steam["slippage_pct"] > res["slippage_pct"]

    def test_steam_drift_detection(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """odds_history を持つエントリーで STEAM/DRIFT を検出する。"""
        monkeypatch.setattr("agents.market_agent.DATA_DIR", tmp_path)

        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")

        # STEAM: odds_history が大幅下落 (-20%)
        steam_snapshot = {
            "STEAM_RACE": [
                {"horse_num": 1, "odds": 5.0, "odds_history": [10.0, 7.0, 5.0]},
                {"horse_num": 2, "odds": 20.0, "odds_history": [10.0, 7.0, 5.0]},
            ],
        }
        snap_file = tmp_path / f"odds_snapshot_{today}.json"
        snap_file.write_text(json.dumps(steam_snapshot), encoding="utf-8")

        agent = MarketAgent(dry_run=False)
        result = agent.execute(agent_meta, {})
        assert result.ok is True
        sig = result.output["market_signals"]["STEAM_RACE"]
        assert sig["steam_detected"] is True

        # DRIFT: odds_history が大幅上昇 (+25%)
        drift_snapshot = {
            "DRIFT_RACE": [
                {"horse_num": 1, "odds": 15.0, "odds_history": [10.0, 12.0, 15.0]},
                {"horse_num": 2, "odds": 20.0, "odds_history": [10.0, 12.0, 15.0]},
            ],
        }
        snap_file.write_text(json.dumps(drift_snapshot), encoding="utf-8")
        result2 = agent.execute(agent_meta, {})
        sig2 = result2.output["market_signals"]["DRIFT_RACE"]
        assert sig2["drift_detected"] is True
