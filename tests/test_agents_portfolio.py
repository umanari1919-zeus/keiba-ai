"""PortfolioAgent のユニットテスト。"""

import pytest

from agents.portfolio_agent import PortfolioAgent


@pytest.mark.unit
class TestPortfolioAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        agent = PortfolioAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_normal_optimization_missing_modules(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """optimizer モジュールが無い場合のフォールバック動作。"""
        monkeypatch.setattr("agents.portfolio_agent.BASE_DIR", tmp_path)

        payload = {
            "candidate_bets": [
                {"race_id": "R001", "entry_id": "3", "win_prob": 0.12, "odds": 15.0, "stake_amount": 2000},
                {"race_id": "R001", "entry_id": "7", "win_prob": 0.08, "odds": 32.0, "stake_amount": 1500},
            ],
            "bankroll": 100_000,
        }
        agent = PortfolioAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        out = result.output
        assert len(out["finalized_bets"]) == 2
        assert out["bankroll"] == 100_000
        # フォールバック: ticket_key=tansho がデフォルト
        for bet in out["finalized_bets"]:
            assert bet["ticket_key"] == "tansho"

    def test_empty_candidates(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """候補ベットが空の場合は空結果を返す。"""
        monkeypatch.setattr("agents.portfolio_agent.BASE_DIR", tmp_path)

        agent = PortfolioAgent(dry_run=False)
        result = agent.execute(agent_meta, {"candidate_bets": [], "bankroll": 50_000})

        assert result.ok is True
        assert result.output["finalized_bets"] == []
        assert result.output["summary"]["total_bets"] == 0

    def test_bankroll_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """bankroll が payload になく bankroll.json も無い場合デフォルト値を使用。"""
        monkeypatch.setattr("agents.portfolio_agent.BASE_DIR", tmp_path)
        monkeypatch.setattr("agents.portfolio_agent.BANKROLL_FILE", tmp_path / "nonexistent.json")

        payload = {
            "candidate_bets": [
                {"race_id": "R001", "entry_id": "1", "win_prob": 0.10, "odds": 20.0, "stake_amount": 1000},
            ],
        }
        agent = PortfolioAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        assert result.output["bankroll"] == 100_000  # DEFAULT_BANKROLL
