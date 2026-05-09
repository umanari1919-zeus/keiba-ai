"""KnowledgeAgent のユニットテスト。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestKnowledgeAgent:
    def test_dry_run(self, agent_meta, mock_psycopg2):
        from agents.knowledge_agent import KnowledgeAgent

        agent = KnowledgeAgent(dry_run=True)
        result = agent.execute(agent_meta, {"days": 3})

        assert result.ok is True
        out = result.output
        assert out["dry_run"] is True
        assert out["agent_id"] == "knowledge-agent"

    def test_successful_curator_run(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.knowledge_agent as mod
        from agents.knowledge_agent import KnowledgeAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        kb_dir = tmp_path / "data" / "knowledge_base"
        monkeypatch.setattr(mod, "KB_DIR", kb_dir)
        kb_dir.mkdir(parents=True, exist_ok=True)

        # Create LATEST.json with knowledge entries
        latest_data = {
            "insight_001": {"status": "active", "confidence": 0.75},
            "insight_002": {"status": "active", "confidence": 0.30},
            "insight_003": {"status": "pending", "confidence": 0.40},
            "insight_004": {"status": "deprecated", "confidence": 0.10},
            "version": "v2",
        }
        (kb_dir / "LATEST.json").write_text(
            json.dumps(latest_data, ensure_ascii=False), encoding="utf-8"
        )

        # Create the script so _run_curator finds it
        pipeline_dir = tmp_path / "pipeline"
        pipeline_dir.mkdir(exist_ok=True)
        (pipeline_dir / "knowledge_curator_41.py").write_text("pass")

        fake_proc = MagicMock(returncode=0, stdout="done", stderr="")
        with patch("subprocess.run", return_value=fake_proc):
            agent = KnowledgeAgent(dry_run=False)
            result = agent.execute(agent_meta, {"days": 7})

        assert result.ok is True
        out = result.output
        assert out["curator_ok"] is True
        assert out["active_count"] == 2
        assert out["pending_count"] == 1
        assert out["deprecated_count"] == 1
        assert out["ev_boost_entries"] == 1  # only insight_001 has confidence >= 0.50
        assert out["version"] == "v2"

    def test_missing_latest_json_fallback(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import agents.knowledge_agent as mod
        from agents.knowledge_agent import KnowledgeAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        kb_dir = tmp_path / "data" / "knowledge_base"
        monkeypatch.setattr(mod, "KB_DIR", kb_dir)
        # Do NOT create LATEST.json

        # Script also missing => curator_ok=False
        agent = KnowledgeAgent(dry_run=False)
        result = agent.execute(agent_meta, {"days": 5})

        assert result.ok is True
        out = result.output
        assert out["curator_ok"] is False
        assert out["active_count"] == 0
        assert out["ev_boost_entries"] == 0
        assert out["version"] == "N/A"

    def test_curator_timeout(self, agent_meta, mock_psycopg2, tmp_path, monkeypatch):
        import subprocess
        import agents.knowledge_agent as mod
        from agents.knowledge_agent import KnowledgeAgent

        monkeypatch.setattr(mod, "BASE_DIR", tmp_path)
        kb_dir = tmp_path / "data" / "knowledge_base"
        monkeypatch.setattr(mod, "KB_DIR", kb_dir)

        pipeline_dir = tmp_path / "pipeline"
        pipeline_dir.mkdir(exist_ok=True)
        (pipeline_dir / "knowledge_curator_41.py").write_text("pass")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="", timeout=600)):
            agent = KnowledgeAgent(dry_run=False)
            result = agent.execute(agent_meta, {"days": 7})

        assert result.ok is True
        assert result.output["curator_ok"] is False
