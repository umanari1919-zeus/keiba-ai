"""NormalizerAgent のユニットテスト。"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestNormalizerAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.normalizer_agent import NormalizerAgent

        agent = NormalizerAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_normal_csv(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.normalizer_agent import NormalizerAgent
        import agents.normalizer_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        # Create a clean CSV (3 data rows, unique race_ids, 0 skipped)
        csv = (
            "race_id,horse_name,tansho_odds\n"
            "R001,HorseA,150\n"
            "R002,HorseB,320\n"
            "R003,HorseC,450\n"
        )
        (tmp_path / "keiba_data.csv").write_text(csv, encoding="utf-8")

        agent = NormalizerAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["total_lines"] == 3
        assert out["skipped_lines"] == 0
        assert out["mismatch_rate"] == 0.0
        assert out["quarantine_flags"] == []
        assert len(out["normalized_rows"]) == 3

    def test_high_mismatch_triggers_quarantine(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.normalizer_agent import NormalizerAgent
        import agents.normalizer_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        # Create a CSV where many lines have MORE columns than header to trigger
        # on_bad_lines='skip'. Lines with fewer columns get NaN-filled by pandas,
        # but lines with extra columns are actually skipped.
        lines = ["col_a,col_b,col_c\n"]
        lines.append("a,b,c\n")  # 1 good line
        for i in range(50):
            lines.append(f"x{i},y,z,extra1,extra2\n")  # 50 lines with too many columns
        (tmp_path / "keiba_data.csv").write_text("".join(lines), encoding="utf-8")

        agent = NormalizerAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["mismatch_rate"] > 0.02
        assert len(out["quarantine_flags"]) >= 1
        assert out["quarantine_flags"][0]["type"] == "high_mismatch_rate"

    def test_missing_csv_fails(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.normalizer_agent import NormalizerAgent
        import agents.normalizer_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)

        agent = NormalizerAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is False
        assert "keiba_data.csv" in result.error
