"""BaseAgent の基本動作テスト（conftest.py の動作検証を兼ねる）。"""

import pytest


@pytest.mark.unit
class TestBaseAgent:
    def test_execute_success(self, DummyAgent, agent_meta, mock_psycopg2):
        agent = DummyAgent(return_value={"result": 42}, dry_run=False)
        result = agent.execute(agent_meta, {"input": "test"})

        assert result.ok is True
        assert result.output["result"] == 42
        assert result.output_hash != ""

    def test_execute_dry_run(self, DummyAgent, agent_meta, mock_psycopg2):
        agent = DummyAgent(dry_run=True)
        result = agent.execute(agent_meta, {})

        assert result.ok is True
        assert result.output["dry_run"] is True

    def test_execute_failure(self, DummyAgent, agent_meta, mock_psycopg2):
        agent = DummyAgent(
            raise_error=ValueError("test error"),
            dry_run=False,
        )
        result = agent.execute(agent_meta, {})

        assert result.ok is False
        assert "test error" in result.error

    def test_agent_meta_defaults(self, agent_meta):
        assert agent_meta.trace_id.startswith("test-trace-")
        assert agent_meta.run_tag == "test_run_20260508"

    def test_agent_meta_factory(self, agent_meta_factory):
        m1 = agent_meta_factory()
        m2 = agent_meta_factory()
        assert m1.trace_id != m2.trace_id
