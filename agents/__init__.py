"""
うまなり地蔵AI — agents パッケージ
マニフェスト umanari_unified_manifest_v1 に基づく統合エージェント層。
"""
from .base_agent import BaseAgent, AgentMeta, AgentResult
from .schema_registry import SchemaRegistry, SCHEMAS
from .audit_logger import AuditLogger
from .rag_store import RAGStore, get_default_store
from .market_agent import MarketAgent
from .train_agent import TrainAgent
from .ops_agent import OpsAgent
from .knowledge_agent import KnowledgeAgent
from .backtest_agent import BacktestAgent
from .anomaly_agent import AnomalyAgent
from .roi_tracker_agent import RoiTrackerAgent
from .portfolio_agent import PortfolioAgent
from .race_selector_agent import RaceSelectorAgent
from .condition_adjuster_agent import ConditionAdjusterAgent
from .auto_learn_agent import AutoLearnAgent
from .bankroll_agent import BankrollAgent
from .backtest_engine_agent import BacktestEngineAgent
from .statistics_agent import StatisticsAgent
from .multi_agent_v2_agent import MultiAgentV2Agent
from .social_bot_agent import SocialBotAgent
from .odds_scraper_agent import OddsScraperAgent
from .odds_monitor_agent import OddsMonitorAgent

__all__ = [
    "BaseAgent", "AgentMeta", "AgentResult",
    "SchemaRegistry", "SCHEMAS",
    "AuditLogger",
    "RAGStore", "get_default_store",
    "MarketAgent",
    "TrainAgent",
    "OpsAgent",
    "KnowledgeAgent",
    "BacktestAgent",
    "AnomalyAgent",
    "RoiTrackerAgent",
    "PortfolioAgent",
    "RaceSelectorAgent",
    "ConditionAdjusterAgent",
    "AutoLearnAgent",
    "BankrollAgent",
    "BacktestEngineAgent",
    "StatisticsAgent",
    "MultiAgentV2Agent",
    "SocialBotAgent",
    "OddsScraperAgent",
    "OddsMonitorAgent",
]
