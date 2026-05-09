"""AutoLearnAgent のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestAutoLearnAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2, monkeypatch):
        from agents.auto_learn_agent import AutoLearnAgent

        agent = AutoLearnAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        # BaseAgent.execute returns dry_run envelope without calling _run
        assert out["dry_run"] is True
        assert out["agent_id"] == "auto-learn-agent"

    def test_no_retrain_needed(self, agent_meta, mock_psycopg2, monkeypatch):
        from agents.auto_learn_agent import AutoLearnAgent

        fake_mod = MagicMock()
        fake_mod.should_retrain.return_value = (False, "Performance OK")
        monkeypatch.setattr(AutoLearnAgent, "_load_module", lambda self: fake_mod)

        agent = AutoLearnAgent(dry_run=False)
        result = agent.execute(agent_meta, {"force": False})

        assert result.ok is True
        out = result.output
        assert out["retrain_triggered"] is False
        assert out["reason"] == "Performance OK"
        assert out["model_id"] is None

    def test_force_retrain(self, agent_meta, mock_psycopg2, monkeypatch):
        from agents.auto_learn_agent import AutoLearnAgent
        from agents.base_agent import AgentResult

        fake_mod = MagicMock()
        fake_mod.should_retrain.return_value = (False, "Performance OK")
        monkeypatch.setattr(AutoLearnAgent, "_load_module", lambda self: fake_mod)

        # Mock TrainAgent to succeed — patched at module level where it's imported
        mock_train_result = AgentResult(
            ok=True,
            output={"model_id": "model_v8_retrained", "metrics": {"accuracy": 0.70}},
        )
        mock_train_cls = MagicMock()
        mock_train_cls.return_value.execute.return_value = mock_train_result

        with patch.dict("sys.modules", {}):
            with patch("agents.train_agent.TrainAgent", mock_train_cls, create=True):
                agent = AutoLearnAgent(dry_run=False)
                result = agent.execute(agent_meta, {"force": True})

        assert result.ok is True
        out = result.output
        assert out["retrain_triggered"] is True
        assert out["model_id"] == "model_v8_retrained"
        assert out["train_metrics"]["accuracy"] == 0.70

    def test_train_failure_handling(self, agent_meta, mock_psycopg2, monkeypatch):
        from agents.auto_learn_agent import AutoLearnAgent
        from agents.base_agent import AgentResult

        fake_mod = MagicMock()
        fake_mod.should_retrain.return_value = (True, "ROI dropped")
        monkeypatch.setattr(AutoLearnAgent, "_load_module", lambda self: fake_mod)

        # Mock TrainAgent to fail
        mock_train_result = AgentResult(ok=False, error="Training data insufficient")
        mock_train_cls = MagicMock()
        mock_train_cls.return_value.execute.return_value = mock_train_result

        with patch("agents.train_agent.TrainAgent", mock_train_cls, create=True):
            agent = AutoLearnAgent(dry_run=False)
            result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["retrain_triggered"] is True
        assert out["model_id"] is None
        assert out["train_error"] == "Training data insufficient"

    def test_missing_module(self, agent_meta, mock_psycopg2, monkeypatch):
        from agents.auto_learn_agent import AutoLearnAgent

        monkeypatch.setattr(AutoLearnAgent, "_load_module", lambda self: None)

        agent = AutoLearnAgent(dry_run=False)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        out = result.output
        assert out["retrain_triggered"] is False
        assert out["model_id"] is None
