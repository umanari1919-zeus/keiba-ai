"""FeatureAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestFeatureAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.feature_agent import FeatureAgent

        agent = FeatureAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_all_scripts_succeed(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.feature_agent import FeatureAgent, FEATURE_SCRIPTS
        import agents.feature_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        # Create all script files so they are found
        for rel_path, _ in FEATURE_SCRIPTS:
            script = tmp_path / rel_path
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("pass")

        # Create the output CSV
        feat_csv = tmp_path / "keiba_data_features.csv"
        feat_csv.write_text("col1\n1\n")

        fake_proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake_proc):
            agent = FeatureAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["feature_set_id"].startswith("fset_")
        manifest = out["feature_manifest"]
        assert all(v == "ok" for v in manifest["scripts_run"].values())

    def test_some_scripts_fail_gracefully(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        from agents.feature_agent import FeatureAgent, FEATURE_SCRIPTS
        import agents.feature_agent as mod

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "data")

        # Create only the first 3 scripts; rest are missing
        for rel_path, _ in FEATURE_SCRIPTS[:3]:
            script = tmp_path / rel_path
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("pass")

        feat_csv = tmp_path / "keiba_data_features.csv"
        feat_csv.write_text("col1\n1\n")

        # First script succeeds, second fails, third succeeds
        results_iter = iter([
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="err"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ])
        with patch("subprocess.run", side_effect=results_iter):
            agent = FeatureAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        scripts_run = result.output["feature_manifest"]["scripts_run"]
        statuses = list(scripts_run.values())
        assert "ok" in statuses
        assert "error" in statuses
        assert "missing" in statuses  # scripts not created
