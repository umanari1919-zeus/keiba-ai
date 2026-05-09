"""BankrollAgent のユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from agents.bankroll_agent import BankrollAgent


@pytest.mark.unit
class TestBankrollAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        agent = BankrollAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_normal_drawdown(self, agent_meta, mock_psycopg2, monkeypatch):
        """通常のドローダウン (< CRITICAL) では multiplier < 1.0 だがベット継続。"""
        fake_mod = MagicMock()
        fake_mod.manage_drawdown.return_value = {
            "bankroll": 90_000,
            "peak": 100_000,
            "drawdown": 0.10,
            "multiplier": 0.50,
        }
        fake_mod.portfolio_risk_management.side_effect = lambda bets, br: bets

        monkeypatch.setattr(BankrollAgent, "_load_module", lambda self: fake_mod)

        bets = [{"race_id": "R001", "entry_id": "3", "finalized_bet_amount": 2000}]
        agent = BankrollAgent(dry_run=False)
        result = agent.execute(agent_meta, {"bets": bets})

        assert result.ok is True
        out = result.output
        assert out["stop_betting"] is False
        assert out["drawdown"] == 0.10
        assert out["multiplier"] == 0.50
        # ベット額が multiplier=0.50 で縮小されている
        assert len(out["adjusted_bets"]) == 1
        assert out["adjusted_bets"][0]["finalized_bet_amount"] < 2000

    def test_critical_drawdown_stops_betting(self, agent_meta, mock_psycopg2, monkeypatch):
        """CRITICAL ドローダウン (multiplier=0.0) でベット停止。"""
        fake_mod = MagicMock()
        fake_mod.manage_drawdown.return_value = {
            "bankroll": 70_000,
            "peak": 100_000,
            "drawdown": 0.30,
            "multiplier": 0.0,
        }

        monkeypatch.setattr(BankrollAgent, "_load_module", lambda self: fake_mod)

        bets = [{"race_id": "R001", "entry_id": "1", "finalized_bet_amount": 5000}]
        agent = BankrollAgent(dry_run=False)
        result = agent.execute(agent_meta, {"bets": bets})

        assert result.ok is True
        out = result.output
        assert out["stop_betting"] is True
        assert out["multiplier"] == 0.0
        assert out["adjusted_bets"] == []

    def test_missing_module_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """bankroll_advanced_24.py が無い場合は multiplier=1.0 でパススルー。"""
        monkeypatch.setattr("agents.bankroll_agent.BASE_DIR", tmp_path)

        bets = [{"race_id": "R001", "entry_id": "5", "stake_amount": 1000}]
        agent = BankrollAgent(dry_run=False)
        result = agent.execute(agent_meta, {"bets": bets})

        assert result.ok is True
        out = result.output
        assert out["stop_betting"] is False
        assert out["multiplier"] == 1.0
        assert out["adjusted_bets"] == bets
