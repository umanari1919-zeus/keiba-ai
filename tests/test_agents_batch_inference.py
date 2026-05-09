"""BatchInferenceAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestBatchInferenceAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.batch_inference_agent import BatchInferenceAgent

        agent = BatchInferenceAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_successful_prediction(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.batch_inference_agent import BatchInferenceAgent
        import agents.batch_inference_agent as mod
        from datetime import datetime

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)

        # Create scripts
        (tmp_path / "pipeline").mkdir()
        (tmp_path / "pipeline" / "predict_04.py").write_text("pass")
        (tmp_path / "pipeline" / "ev_engine_10.py").write_text("pass")

        # Create ev_analysis CSV with one entry above EV threshold (>=1.15)
        year = datetime.now().strftime("%Y")
        ev_csv = data_dir / f"ev_analysis_{year}.csv"
        ev_csv.write_text(
            "race_code,horse_num,win_probability,ev,odds\n"
            "R001,3,0.20,1.30,15.0\n"   # passes EV filter (1.30 >= 1.15)
            "R001,7,0.05,0.80,32.0\n",  # fails EV filter
            encoding="utf-8",
        )

        fake_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake_proc):
            agent = BatchInferenceAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["data_snapshot_id"] == agent_meta.data_snapshot_id
        assert len(out["predictions"]) == 1
        assert out["predictions"][0]["win_prob"] == 0.20
        assert "timestamp" in out

    def test_ev_engine_failure_is_non_fatal(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.batch_inference_agent import BatchInferenceAgent
        import agents.batch_inference_agent as mod
        from datetime import datetime

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)

        (tmp_path / "pipeline").mkdir()
        (tmp_path / "pipeline" / "predict_04.py").write_text("pass")
        (tmp_path / "pipeline" / "ev_engine_10.py").write_text("pass")

        # Create simulation CSV (used when ev_analysis is absent)
        year = datetime.now().strftime("%Y")
        sim_csv = tmp_path / f"simulation_{year}.csv"
        sim_csv.write_text(
            "race_id,entry_id,win_prob,place_prob,expected_return,uncertainty\n"
            "R001,3,0.20,0.35,1.25,0.20\n",
            encoding="utf-8",
        )

        # predict_04 succeeds (rc=0), ev_engine fails (rc=1)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="ev error")

        with patch("subprocess.run", side_effect=side_effect):
            agent = BatchInferenceAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        # predictions may be loaded from simulation CSV
        assert isinstance(result.output["predictions"], list)

    def test_predict_failure_raises(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.batch_inference_agent import BatchInferenceAgent
        import agents.batch_inference_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "pipeline").mkdir()
        (tmp_path / "pipeline" / "predict_04.py").write_text("pass")

        fake_proc = MagicMock(returncode=1, stdout="", stderr="predict crash")
        with patch("subprocess.run", return_value=fake_proc):
            agent = BatchInferenceAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is False
        assert "predict_04.py" in result.error
