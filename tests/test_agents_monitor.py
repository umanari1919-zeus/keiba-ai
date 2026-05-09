"""MonitorAgent のユニットテスト。"""

import pytest

from agents.monitor_agent import MonitorAgent


@pytest.mark.unit
class TestMonitorAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        agent = MonitorAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_clean_metrics_no_alerts(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """全メトリクスが正常範囲ならアラートなし。"""
        monkeypatch.setattr("agents.monitor_agent.BASE_DIR", tmp_path)
        (tmp_path / "pipeline_v2" / "alerts").mkdir(parents=True, exist_ok=True)

        payload = {
            "mismatch_rate": 0.01,
            "quarantine_count": 10,
            "daily_roi": 0.05,
            "consecutive_losses": 2,
        }
        agent = MonitorAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        out = result.output
        assert out["alerts"] == []
        assert out["auto_stop"] is False

    def test_threshold_breaches_trigger_alerts(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """閾値超過で対応するアラートが発生する。"""
        monkeypatch.setattr("agents.monitor_agent.BASE_DIR", tmp_path)
        (tmp_path / "pipeline_v2" / "alerts").mkdir(parents=True, exist_ok=True)

        payload = {
            "mismatch_rate": 0.05,       # > 0.02 → critical
            "quarantine_count": 100,     # > 50 → critical
            "daily_roi": -0.05,          # < -0.03 → critical
            "consecutive_losses": 8,     # > 5 → warning
        }
        agent = MonitorAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        out = result.output
        assert len(out["alerts"]) == 4
        alert_metrics = {a["metric"] for a in out["alerts"]}
        assert "mismatch_rate" in alert_metrics
        assert "quarantine_count" in alert_metrics
        assert "daily_roi" in alert_metrics
        assert "consecutive_losses" in alert_metrics

    def test_critical_alert_triggers_auto_stop(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """critical アラートが1件でも auto_stop=True。"""
        monkeypatch.setattr("agents.monitor_agent.BASE_DIR", tmp_path)
        (tmp_path / "pipeline_v2" / "alerts").mkdir(parents=True, exist_ok=True)

        payload = {
            "mismatch_rate": 0.05,       # > 0.02 → critical
            "quarantine_count": 0,
            "daily_roi": 0.0,
            "consecutive_losses": 0,
        }
        agent = MonitorAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        assert result.output["auto_stop"] is True
        assert any(a["severity"] == "critical" for a in result.output["alerts"])

    def test_warning_only_no_auto_stop(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        """warning のみでは auto_stop=False。"""
        monkeypatch.setattr("agents.monitor_agent.BASE_DIR", tmp_path)
        (tmp_path / "pipeline_v2" / "alerts").mkdir(parents=True, exist_ok=True)

        payload = {
            "mismatch_rate": 0.01,
            "quarantine_count": 0,
            "daily_roi": 0.0,
            "consecutive_losses": 8,     # > 5 → warning (not critical)
        }
        agent = MonitorAgent(dry_run=False)
        result = agent.execute(agent_meta, payload)

        assert result.ok is True
        assert len(result.output["alerts"]) == 1
        assert result.output["alerts"][0]["severity"] == "warning"
        assert result.output["auto_stop"] is False
