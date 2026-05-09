"""RoiTrackerAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestRoiTrackerAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.roi_tracker_agent import RoiTrackerAgent

        agent = RoiTrackerAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["dry_run"] is True
        assert out["agent_id"] == "roi-tracker-agent"

    def test_normal_summary(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.roi_tracker_agent as mod
        from agents.roi_tracker_agent import RoiTrackerAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        tracker_file = tmp_path / "data" / "roi_tracker.csv"
        monkeypatch.setattr(mod, "TRACKER_FILE", tracker_file)

        # Create roi_tracker.csv with some data
        tracker_file.parent.mkdir(parents=True, exist_ok=True)
        tracker_file.write_text(
            "race_code,bet_amount,payout,hit\n"
            "202509050811,1000,3200,1\n"
            "202509050812,1000,0,0\n"
            "202509050813,1000,0,0\n",
            encoding="utf-8",
        )

        # Mock the module loader to return a fake module
        fake_mod = MagicMock()
        fake_mod.get_summary.side_effect = lambda period: {
            "daily":  {"roi": 0.05, "profit": 500},
            "weekly": {"roi": 0.12, "profit": 1200},
            "monthly": {"roi": -0.03, "profit": -300},
            "all":    {"roi": 0.08, "profit": 800},
        }.get(period, {})
        fake_mod.check_alerts.return_value = []

        monkeypatch.setattr(RoiTrackerAgent, "_load_module", lambda self: fake_mod)

        agent = RoiTrackerAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["daily_roi"] == 0.05
        assert out["weekly_roi"] == 0.12
        assert out["monthly_roi"] == -0.03
        assert out["consecutive_losses"] == 2  # last 2 rows are hit=0

    def test_missing_module_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.roi_tracker_agent as mod
        from agents.roi_tracker_agent import RoiTrackerAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "TRACKER_FILE", tmp_path / "data" / "roi_tracker.csv")

        # Module not found => returns None
        monkeypatch.setattr(RoiTrackerAgent, "_load_module", lambda self: None)

        agent = RoiTrackerAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["daily_roi"] == 0.0
        assert out["weekly_roi"] == 0.0
        assert out["consecutive_losses"] == 0
