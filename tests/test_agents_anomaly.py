"""AnomalyAgent のユニットテスト。"""

from unittest.mock import MagicMock

import pytest

from agents.anomaly_agent import AnomalyAgent, CRITICAL_STOP_THRESHOLD


@pytest.mark.unit
class TestAnomalyAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        agent = AnomalyAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_no_alerts(self, agent_meta, mock_psycopg2, monkeypatch):
        """アラートゼロの場合 auto_stop=False。"""
        fake_mod = MagicMock()
        fake_mod.run_anomaly_detection.return_value = []

        monkeypatch.setattr(AnomalyAgent, "_load_module", lambda self: fake_mod)

        agent = AnomalyAgent(dry_run=False)
        result = agent.execute(agent_meta, {"year": 2026})

        assert result.ok is True
        out = result.output
        assert out["alerts"] == []
        assert out["critical_count"] == 0
        assert out["warning_count"] == 0
        assert out["auto_stop"] is False

    def test_critical_threshold_triggers_auto_stop(self, agent_meta, mock_psycopg2, monkeypatch):
        """CRITICAL アラートが閾値以上で auto_stop=True。"""
        alerts = [
            {"level": "CRITICAL", "message": f"alert_{i}"} for i in range(CRITICAL_STOP_THRESHOLD)
        ] + [
            {"level": "WARNING", "message": "minor issue"},
        ]
        fake_mod = MagicMock()
        fake_mod.run_anomaly_detection.return_value = alerts

        monkeypatch.setattr(AnomalyAgent, "_load_module", lambda self: fake_mod)

        agent = AnomalyAgent(dry_run=False)
        result = agent.execute(agent_meta, {"year": 2026})

        assert result.ok is True
        out = result.output
        assert out["critical_count"] == CRITICAL_STOP_THRESHOLD
        assert out["warning_count"] == 1
        assert out["auto_stop"] is True

    def test_below_threshold_no_auto_stop(self, agent_meta, mock_psycopg2, monkeypatch):
        """CRITICAL アラートが閾値未満では auto_stop=False。"""
        alerts = [
            {"level": "CRITICAL", "message": "one critical"},
            {"level": "WARNING", "message": "a warning"},
        ]
        fake_mod = MagicMock()
        fake_mod.run_anomaly_detection.return_value = alerts

        monkeypatch.setattr(AnomalyAgent, "_load_module", lambda self: fake_mod)

        agent = AnomalyAgent(dry_run=False)
        result = agent.execute(agent_meta, {"year": 2026})

        assert result.ok is True
        assert result.output["critical_count"] == 1
        assert result.output["auto_stop"] is False

    def test_missing_module_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """anomaly_detect_16.py が無い場合は空アラートを返す。"""
        monkeypatch.setattr("agents.anomaly_agent.BASE_DIR", tmp_path)

        agent = AnomalyAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["alerts"] == []
        assert result.output["auto_stop"] is False
