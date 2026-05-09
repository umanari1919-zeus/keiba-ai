"""RaceSelectorAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestRaceSelectorAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.race_selector_agent import RaceSelectorAgent

        agent = RaceSelectorAgent(dry_run=True)
        result = agent.execute(agent_meta, {"year": 2025})

        assert result.ok is True
        out = result.output
        assert out["dry_run"] is True
        assert out["agent_id"] == "race-selector-agent"

    def test_normal_ranking(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import pandas as pd
        import agents.race_selector_agent as mod
        from agents.race_selector_agent import RaceSelectorAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)

        # Create features CSV
        feat = tmp_path / "keiba_data_features.csv"
        feat.write_text(
            "race_code,horse_num\n202509050811,3\n",
            encoding="utf-8",
        )

        # Mock module with rank_races returning a DataFrame
        ranked_df = pd.DataFrame([
            {"race_code": "202509050811", "grade": "S", "score": 0.95},
            {"race_code": "202509050812", "grade": "A", "score": 0.80},
            {"race_code": "202509050813", "grade": "B", "score": 0.60},
            {"race_code": "202509050814", "grade": "C", "score": 0.30},
        ])
        fake_mod = MagicMock()
        fake_mod.rank_races.return_value = ranked_df

        monkeypatch.setattr(RaceSelectorAgent, "_load_module", lambda self: fake_mod)

        agent = RaceSelectorAgent(dry_run=False)
        result = agent.execute(agent_meta, {"year": 2025, "min_grade": "B"})

        assert result.ok is True
        out = result.output
        assert len(out["ranked_races"]) == 4
        assert len(out["grade_s"]) == 1
        assert len(out["grade_a"]) == 1
        # recommended = S + A + B (min_grade="B" => threshold=2)
        assert len(out["recommended"]) == 3
        assert out["year"] == 2025

    def test_grade_filtering_strict(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import pandas as pd
        import agents.race_selector_agent as mod
        from agents.race_selector_agent import RaceSelectorAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)

        feat = tmp_path / "keiba_data_features.csv"
        feat.write_text("race_code,horse_num\n202509050811,3\n", encoding="utf-8")

        ranked_df = pd.DataFrame([
            {"race_code": "202509050811", "grade": "S", "score": 0.95},
            {"race_code": "202509050812", "grade": "A", "score": 0.80},
            {"race_code": "202509050813", "grade": "B", "score": 0.60},
        ])
        fake_mod = MagicMock()
        fake_mod.rank_races.return_value = ranked_df

        monkeypatch.setattr(RaceSelectorAgent, "_load_module", lambda self: fake_mod)

        agent = RaceSelectorAgent(dry_run=False)
        # min_grade="S" means only S is recommended
        result = agent.execute(agent_meta, {"year": 2025, "min_grade": "S"})

        assert result.ok is True
        assert len(result.output["recommended"]) == 1
        assert result.output["recommended"][0]["grade"] == "S"

    def test_missing_module(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.race_selector_agent as mod
        from agents.race_selector_agent import RaceSelectorAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(RaceSelectorAgent, "_load_module", lambda self: None)

        agent = RaceSelectorAgent(dry_run=False)
        result = agent.execute(agent_meta, {"year": 2025})

        assert result.ok is True
        assert result.output["ranked_races"] == []
        assert result.output["recommended"] == []
