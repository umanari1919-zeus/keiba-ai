"""
test_integration.py — エージェント統合テスト（canary_run.py の pytest 化）
=========================================================================
各エージェントを dry_run モードで実行し、result.ok を検証する。
DB は conftest.py の mock_psycopg2 でモック済み。

実行:
  pytest tests/test_integration.py -v -m integration
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def meta(agent_meta, tmp_path):
    """canary 用の AgentMeta（conftest の agent_meta を流用）。"""
    agent_meta.data_snapshot_id = "canary_pytest"
    (tmp_path / "pipeline_v2" / "alerts").mkdir(parents=True, exist_ok=True)
    return agent_meta


# ================================================================== #
#  SchemaRegistry
# ================================================================== #

@pytest.mark.integration
def test_schema_registry(mock_psycopg2, meta):
    from agents.schema_registry import SchemaRegistry
    reg = SchemaRegistry(strict=True)
    reg.register_to_db()


# ================================================================== #
#  IngestAgent
# ================================================================== #

@pytest.mark.integration
def test_ingest_agent(mock_psycopg2, meta):
    from agents.ingest_agent import IngestAgent
    agent = IngestAgent(dry_run=True)
    result = agent.execute(meta, {"source": "canary"})
    assert result.ok is True


# ================================================================== #
#  NormalizerAgent
# ================================================================== #

@pytest.mark.integration
def test_normalizer_agent(mock_psycopg2, meta):
    from agents.normalizer_agent import NormalizerAgent
    agent = NormalizerAgent(dry_run=True)
    result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
    assert result.ok is True


# ================================================================== #
#  FeatureAgent
# ================================================================== #

@pytest.mark.integration
def test_feature_agent(mock_psycopg2, meta):
    from agents.feature_agent import FeatureAgent
    agent = FeatureAgent(dry_run=True)
    result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
    assert result.ok is True


# ================================================================== #
#  TrainAgent (skip_train mode)
# ================================================================== #

@pytest.mark.integration
def test_train_agent_skip(mock_psycopg2, meta):
    from agents.train_agent import TrainAgent
    agent = TrainAgent(dry_run=False)
    result = agent.execute(meta, {"skip_train": True})
    assert result.ok is True


# ================================================================== #
#  RAGStore
# ================================================================== #

@pytest.mark.integration
def test_rag_store_search(mock_psycopg2, meta):
    from agents.rag_store import get_default_store
    store = get_default_store()
    hits = store.search({"win_probability": 0.15, "tansho_odds": 2500}, top_k=3)
    assert isinstance(hits, list)


# ================================================================== #
#  BatchInferenceAgent
# ================================================================== #

@pytest.mark.integration
def test_batch_inference_agent(mock_psycopg2, meta):
    from agents.batch_inference_agent import BatchInferenceAgent
    agent = BatchInferenceAgent(dry_run=True)
    result = agent.execute(meta, {"data_snapshot_id": meta.data_snapshot_id})
    assert result.ok is True


# ================================================================== #
#  MarketAgent (static method)
# ================================================================== #

@pytest.mark.integration
def test_market_agent_slippage(mock_psycopg2):
    from agents.market_agent import MarketAgent
    slip = MarketAgent.estimate_slippage(
        stake=10000, odds=15.0, liquidity=0.6, steam_detected=False,
    )
    assert "slippage_pct" in slip
    assert "expected_odds" in slip


# ================================================================== #
#  LLMExplainAgent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_llm_explain_agent(mock_psycopg2, meta, sample_predictions):
    from agents.llm_explain_agent import LLMExplainAgent
    agent = LLMExplainAgent(dry_run=True)
    result = agent.execute(meta, {"predictions": sample_predictions[:2]})
    assert result.ok is True


# ================================================================== #
#  TradingAgent (paper_trading)
# ================================================================== #

@pytest.mark.integration
def test_trading_agent_paper(mock_psycopg2, meta, sample_predictions):
    from agents.trading_agent import TradingAgent
    agent = TradingAgent(paper_trading=True, dry_run=True)
    result = agent.execute(meta, {
        "predictions": sample_predictions[:2],
        "quarantine_count": 0,
    })
    assert result.ok is True


# ================================================================== #
#  MonitorAgent — auto_stop 未発動を検証
# ================================================================== #

@pytest.mark.integration
def test_monitor_agent_no_auto_stop(mock_psycopg2, meta):
    from agents.monitor_agent import MonitorAgent
    agent = MonitorAgent(dry_run=False)
    result = agent.execute(meta, {
        "mismatch_rate": 0.005,
        "quarantine_count": 0,
        "spearman": 0.72,
        "daily_roi": 0.01,
        "consecutive_losses": 1,
    })
    assert result.ok is True
    assert result.output.get("auto_stop") is False


# ================================================================== #
#  OpsAgent
# ================================================================== #

@pytest.mark.integration
def test_ops_agent(mock_psycopg2, meta):
    from agents.ops_agent import OpsAgent
    agent = OpsAgent(dry_run=False)
    result = agent.execute(meta, {})
    assert result.ok is True
    assert "checks" in result.output


# ================================================================== #
#  KnowledgeAgent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_knowledge_agent(mock_psycopg2, meta):
    from agents.knowledge_agent import KnowledgeAgent
    agent = KnowledgeAgent(dry_run=True)
    result = agent.execute(meta, {"days": 7})
    assert result.ok is True


# ================================================================== #
#  AnomalyAgent (no-db)
# ================================================================== #

@pytest.mark.integration
def test_anomaly_agent(mock_psycopg2, meta):
    from agents.anomaly_agent import AnomalyAgent
    agent = AnomalyAgent(dry_run=True)
    result = agent.execute(meta, {"use_db": False})
    assert result.ok is True


# ================================================================== #
#  RaceSelectorAgent
# ================================================================== #

@pytest.mark.integration
def test_race_selector_agent(mock_psycopg2, meta):
    from agents.race_selector_agent import RaceSelectorAgent
    agent = RaceSelectorAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  PortfolioAgent
# ================================================================== #

@pytest.mark.integration
def test_portfolio_agent(mock_psycopg2, meta, sample_predictions):
    from agents.portfolio_agent import PortfolioAgent
    agent = PortfolioAgent(dry_run=True)
    result = agent.execute(meta, {"candidate_bets": sample_predictions[:2]})
    assert result.ok is True


# ================================================================== #
#  ConditionAdjusterAgent
# ================================================================== #

@pytest.mark.integration
def test_condition_adjuster_agent(mock_psycopg2, meta):
    from agents.condition_adjuster_agent import ConditionAdjusterAgent
    agent = ConditionAdjusterAgent(dry_run=True)
    result = agent.execute(meta, {"finalized_bets": []})
    assert result.ok is True


# ================================================================== #
#  AutoLearnAgent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_auto_learn_agent(mock_psycopg2, meta):
    from agents.auto_learn_agent import AutoLearnAgent
    agent = AutoLearnAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  BankrollAgent
# ================================================================== #

@pytest.mark.integration
def test_bankroll_agent(mock_psycopg2, meta):
    from agents.bankroll_agent import BankrollAgent
    agent = BankrollAgent(dry_run=True)
    result = agent.execute(meta, {"adjusted_bets": []})
    assert result.ok is True


# ================================================================== #
#  RoiTrackerAgent
# ================================================================== #

@pytest.mark.integration
def test_roi_tracker_agent(mock_psycopg2, meta):
    from agents.roi_tracker_agent import RoiTrackerAgent
    agent = RoiTrackerAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  BacktestAgent (skip_backtest)
# ================================================================== #

@pytest.mark.integration
def test_backtest_agent_skip(mock_psycopg2, meta):
    from agents.backtest_agent import BacktestAgent
    agent = BacktestAgent(dry_run=False)
    result = agent.execute(meta, {"skip_backtest": True})
    assert result.ok is True


# ================================================================== #
#  BacktestEngineAgent
# ================================================================== #

@pytest.mark.integration
def test_backtest_engine_agent(mock_psycopg2, meta):
    from agents.backtest_engine_agent import BacktestEngineAgent
    agent = BacktestEngineAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  StatisticsAgent
# ================================================================== #

@pytest.mark.integration
def test_statistics_agent(mock_psycopg2, meta):
    from agents.statistics_agent import StatisticsAgent
    agent = StatisticsAgent(dry_run=True)
    result = agent.execute(meta, {"n_clusters": 3, "mc_simulations": 100})
    assert result.ok is True


# ================================================================== #
#  SocialBotAgent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_social_bot_agent(mock_psycopg2, meta):
    from agents.social_bot_agent import SocialBotAgent
    agent = SocialBotAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  OddsScraperAgent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_odds_scraper_agent(mock_psycopg2, meta):
    from agents.odds_scraper_agent import OddsScraperAgent
    agent = OddsScraperAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  OddsMonitorAgent
# ================================================================== #

@pytest.mark.integration
def test_odds_monitor_agent(mock_psycopg2, meta):
    from agents.odds_monitor_agent import OddsMonitorAgent
    agent = OddsMonitorAgent(dry_run=True)
    result = agent.execute(meta, {})
    assert result.ok is True


# ================================================================== #
#  MultiAgentV2Agent (dry-run)
# ================================================================== #

@pytest.mark.integration
def test_multi_agent_v2_agent(mock_psycopg2, meta):
    from agents.multi_agent_v2_agent import MultiAgentV2Agent
    agent = MultiAgentV2Agent(dry_run=True)
    result = agent.execute(meta, {"mode": "pipeline"})
    assert result.ok is True


# ================================================================== #
#  SchemaRegistry validate
# ================================================================== #

@pytest.mark.integration
def test_schema_validate_inference_output(mock_psycopg2, meta):
    from datetime import datetime, timezone
    from agents.schema_registry import SchemaRegistry

    reg = SchemaRegistry()
    dummy = {
        "trace_id": meta.trace_id,
        "run_tag": meta.run_tag,
        "agent_id": "batch-inference-agent",
        "agent_version": "2.0.0",
        "data_snapshot_id": meta.data_snapshot_id,
        "predictions": [{
            "race_id": "2026050301",
            "entry_id": "12",
            "win_prob": 0.22,
            "place_prob": 0.45,
            "expected_return": 1.18,
            "uncertainty": 0.25,
        }],
        "output_hash": "abc123",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    ok, errs = reg.validate("inference_output_v1", dummy)
    assert ok is True, f"Validation errors: {errs}"
