"""v2日次エージェントの失敗境界テスト。"""

from __future__ import annotations


def test_ingest_agent_fails_when_all_sources_fail(monkeypatch):
    from agents.base_agent import AgentMeta
    from agents.ingest_agent import IngestAgent

    monkeypatch.setattr(IngestAgent, "_run_script", lambda self, rel_path, meta: False)
    monkeypatch.setattr(IngestAgent, "_register_snapshot", lambda self, snap_id, files, meta: None)

    result = IngestAgent(dry_run=False).execute(AgentMeta(run_tag="run_test"), {})

    assert result.ok is False
    assert "data_fetch_01.py" in result.error
    assert "odds_scraper_36.py" in result.error


def test_ingest_agent_succeeds_when_at_least_one_source_succeeds(monkeypatch):
    from agents.base_agent import AgentMeta
    from agents.ingest_agent import IngestAgent

    def fake_run_script(self, rel_path, meta):
        return rel_path == "pipeline/data_fetch_01.py"

    monkeypatch.setattr(IngestAgent, "_run_script", fake_run_script)
    monkeypatch.setattr(IngestAgent, "_register_snapshot", lambda self, snap_id, files, meta: None)

    result = IngestAgent(dry_run=False).execute(AgentMeta(run_tag="run_test"), {})

    assert result.ok is True
    assert result.output["fetch_ok"] is True
    assert result.output["odds_ok"] is False


def test_feature_agent_fails_when_any_feature_script_errors(tmp_path, monkeypatch):
    from agents.base_agent import AgentMeta
    import agents.feature_agent as feature_module
    from agents.feature_agent import FeatureAgent

    for rel_path, _ in feature_module.FEATURE_SCRIPTS:
        script_path = tmp_path / rel_path
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("# test script\n", encoding="utf-8")
    monkeypatch.setattr(feature_module, "BASE_DIR", tmp_path)

    def fake_run_script(self, rel_path, meta):
        return not rel_path.endswith("pedigree_analysis_17.py")

    monkeypatch.setattr(FeatureAgent, "_run_script", fake_run_script)

    result = FeatureAgent(dry_run=False).execute(AgentMeta(run_tag="run_test"), {})

    assert result.ok is False
    assert "pedigree_analysis_17.py" in result.error


def test_feature_agent_returns_script_results_for_stage_logging(tmp_path, monkeypatch):
    from agents.base_agent import AgentMeta
    import agents.feature_agent as feature_module
    from agents.feature_agent import FeatureAgent

    for rel_path, _ in feature_module.FEATURE_SCRIPTS:
        script_path = tmp_path / rel_path
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("# test script\n", encoding="utf-8")
    monkeypatch.setattr(feature_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(FeatureAgent, "_run_script", lambda self, rel_path, meta: True)

    result = FeatureAgent(dry_run=False).execute(AgentMeta(run_tag="run_test"), {})

    assert result.ok is True
    assert result.output["script_results"]
    assert result.output["script_results"] == result.output["feature_manifest"]["scripts_run"]
