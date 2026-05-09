"""TradingAgent のユニットテスト。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestTradingAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.trading_agent import TradingAgent

        agent = TradingAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_quarantine_blocks_all_bets(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch, sample_predictions):
        from agents.trading_agent import TradingAgent
        import agents.trading_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        payload = {
            "predictions": sample_predictions,
            "quarantine_count": 1,  # stage-1 blocks everything
        }

        agent = TradingAgent(paper_trading=True, use_rl=False, dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        out = result.output
        assert out["candidate_bets"] == []
        assert out["skipped_stage1"] == len(sample_predictions)
        assert out["paper_trading"] is True

    def test_stage2_filtering(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.trading_agent import TradingAgent
        import agents.trading_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        predictions = [
            {  # passes stage-2: win_prob>=0.18, uncertainty<=0.35, model_agree>=2, ev>=1.05
                "race_id": "R001",
                "entry_id": "3",
                "win_prob": 0.20,
                "place_prob": 0.35,
                "expected_return": 1.20,
                "uncertainty": 0.25,
                "odds": 15.0,
                "model_agreement_count": 3,
            },
            {  # fails stage-2: win_prob too low, place_prob too low
                "race_id": "R001",
                "entry_id": "7",
                "win_prob": 0.05,
                "place_prob": 0.10,
                "expected_return": 1.10,
                "uncertainty": 0.40,
                "odds": 32.0,
                "model_agreement_count": 1,
            },
        ]
        payload = {"predictions": predictions, "quarantine_count": 0}

        # Disable RL to simplify
        agent = TradingAgent(paper_trading=True, use_rl=False, dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        out = result.output
        assert out["skipped_stage1"] == 0
        assert out["skipped_stage2"] >= 1
        # At most 1 bet passes (the first prediction)
        assert len(out["candidate_bets"]) <= 1

    def test_paper_trading_mode(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.trading_agent import TradingAgent
        import agents.trading_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        predictions = [
            {
                "race_id": "R001",
                "entry_id": "5",
                "win_prob": 0.25,
                "place_prob": 0.40,
                "expected_return": 1.50,
                "uncertainty": 0.20,
                "odds": 12.0,
                "model_agreement_count": 3,
            },
        ]
        payload = {"predictions": predictions, "quarantine_count": 0}

        agent = TradingAgent(paper_trading=True, use_rl=False, dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        assert result.output["paper_trading"] is True
        for entry in result.output["trade_log"]:
            assert entry["status"] == "simulated"
            assert entry["paper_trading"] is True

    def test_bankroll_loaded_from_file(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.trading_agent import TradingAgent
        import agents.trading_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)

        bankroll_data = {"bankroll": 200000}
        (data_dir / "bankroll.json").write_text(
            json.dumps(bankroll_data), encoding="utf-8",
        )

        agent = TradingAgent(paper_trading=True, use_rl=False, dry_run=False)
        result = agent.execute(agent_meta, {"predictions": [], "quarantine_count": 0})

        assert result.ok is True
        assert result.output["bankroll"] == 200000
