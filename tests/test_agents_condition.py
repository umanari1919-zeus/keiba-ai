"""ConditionAdjusterAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestConditionAdjusterAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.condition_adjuster_agent import ConditionAdjusterAgent

        agent = ConditionAdjusterAgent(dry_run=True)
        result = agent.execute(agent_meta, {"bets": []})

        assert result.ok is True
        out = result.output
        assert out["dry_run"] is True
        assert out["agent_id"] == "condition-adjuster-agent"

    def test_coefficient_application(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.condition_adjuster_agent as mod
        from agents.condition_adjuster_agent import ConditionAdjusterAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)

        # Mock module: apply_condition_coefficient returns adjusted values
        fake_mod = MagicMock()
        fake_mod.apply_condition_coefficient.return_value = (1200, 1.2, "A")

        monkeypatch.setattr(ConditionAdjusterAgent, "_load_module", lambda self: fake_mod)

        bets = [
            {
                "race_id": "2025090508110301",  # positions 8-9 => "11"
                "kyori": 1600,
                "track_code": "1",
                "finalized_bet_amount": 1000,
            },
        ]

        agent = ConditionAdjusterAgent(dry_run=False)
        result = agent.execute(agent_meta, {"bets": bets})

        assert result.ok is True
        out = result.output
        assert len(out["adjusted_bets"]) == 1
        assert out["adjusted_bets"][0]["finalized_bet_amount"] == 1200
        assert out["adjusted_bets"][0]["condition_coeff"] == 1.2
        assert out["adjusted_bets"][0]["condition_grade"] == "A"
        assert out["coeff_applied"] == 1
        assert out["avg_coeff"] == 1.2

    def test_missing_module_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.condition_adjuster_agent as mod
        from agents.condition_adjuster_agent import ConditionAdjusterAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(ConditionAdjusterAgent, "_load_module", lambda self: None)

        bets = [
            {
                "race_id": "2025090508110301",
                "kyori": 1600,
                "track_code": "1",
                "finalized_bet_amount": 1000,
            },
        ]

        agent = ConditionAdjusterAgent(dry_run=False)
        result = agent.execute(agent_meta, {"bets": bets})

        assert result.ok is True
        out = result.output
        # Without module, coeff stays 1.0 (no adjustment)
        assert out["adjusted_bets"][0]["condition_coeff"] == 1.0
        assert out["coeff_applied"] == 0
        assert out["avg_coeff"] == 1.0

    def test_keibajo_extraction(self, agent_meta, mock_psycopg2):
        from agents.condition_adjuster_agent import ConditionAdjusterAgent

        # Test _extract_keibajo with race_id: [8:10] = "05"
        #   index: 0123456789...
        #   value: 2025050105110301
        result = ConditionAdjusterAgent._extract_keibajo("2025050105110301", {})
        assert result == "05"

        # Test _extract_keibajo with keibajo in bet dict
        result = ConditionAdjusterAgent._extract_keibajo("", {"keibajo": "05"})
        assert result == "05"

        # Test short race_id fallback
        result = ConditionAdjusterAgent._extract_keibajo("short", {})
        assert result == ""
