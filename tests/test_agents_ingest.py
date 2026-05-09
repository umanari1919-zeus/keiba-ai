"""IngestAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestIngestAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.ingest_agent import IngestAgent

        agent = IngestAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_successful_execution(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.ingest_agent import IngestAgent
        import agents.ingest_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "PIPELINE", tmp_path / "pipeline")
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        # Create the scripts so _run_script finds them
        (tmp_path / "pipeline").mkdir()
        (tmp_path / "pipeline" / "data_fetch_01.py").write_text("pass")
        (tmp_path / "pipeline" / "odds_scraper_36.py").write_text("pass")

        # Create output files the agent expects
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "keiba_data.csv").write_text("col1,col2\n1,2\n")

        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        (data_dir / f"odds_snapshot_{today}.json").write_text('{"odds": []}')

        fake_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake_proc):
            agent = IngestAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["fetch_ok"] is True
        assert out["odds_ok"] is True
        assert out["data_snapshot_id"].startswith("snap_")
        assert len(out["raw_files"]) == 2

    def test_subprocess_failure(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.ingest_agent import IngestAgent
        import agents.ingest_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "PIPELINE", tmp_path / "pipeline")
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        (tmp_path / "pipeline").mkdir()
        (tmp_path / "pipeline" / "data_fetch_01.py").write_text("pass")
        (tmp_path / "pipeline" / "odds_scraper_36.py").write_text("pass")
        (tmp_path / "data").mkdir(exist_ok=True)

        fake_proc = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=fake_proc):
            agent = IngestAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True  # agent still succeeds, just records failures
        assert result.output["fetch_ok"] is False
        assert result.output["odds_ok"] is False
        assert result.output["raw_files"] == []
