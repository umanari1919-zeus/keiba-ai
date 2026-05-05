"""
Pydantic request/response スキーマ定義

Pipeline API, Data API, Settings API のリクエスト・レスポンスモデル。
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


# ── Pipeline API Models ──────────────────────────────

class PipelineRunRequest(BaseModel):
    """Pipeline 実行リクエスト"""
    pattern: str = Field(default="v2", description="実行パターン: v2, morning, weekly, results")


class PipelineStatus(BaseModel):
    """Pipeline 実行ステータス"""
    trace_id: str
    status: str = Field(description="実行状態: running, completed, failed, cancelled")
    exit_code: Optional[int] = Field(None, description="終了コード (null = 実行中)")
    elapsed_seconds: Optional[float] = Field(None, description="経過秒数")
    start_time: Optional[datetime] = Field(None, description="開始時刻")
    end_time: Optional[datetime] = Field(None, description="終了時刻")


class PipelineRunResponse(BaseModel):
    """Pipeline 実行開始レスポンス"""
    trace_id: str
    status: str = "running"
    message: str = "Pipeline execution started"


class PipelineLog(BaseModel):
    """Pipeline 実行ログ"""
    trace_id: str
    lines: list[str] = Field(description="ログ行")
    total_lines: int = Field(description="総行数")


class PipelineHistory(BaseModel):
    """Pipeline 実行履歴"""
    trace_id: str
    pattern: str
    status: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    exit_code: Optional[int]


# ── Data API Models ─────────────────────────────────

class BankrollData(BaseModel):
    """資金情報"""
    current: float = Field(description="現在資金")
    initial: float = Field(description="初期資金")
    peak: float = Field(description="ピーク資金")
    drawdown_percent: float = Field(description="ドローダウン %")


class ROISummary(BaseModel):
    """ROI サマリー"""
    period: str = Field(description="期間: daily, weekly, monthly")
    roi_percent: float = Field(description="ROI %")
    hit_count: int = Field(description="的中数")
    total_bets: int = Field(description="総ベット数")
    win_amount: float = Field(description="勝利額")
    loss_amount: float = Field(description="損失額")


class PredictionData(BaseModel):
    """予想データ"""
    date: str
    race_count: int = Field(description="レース数")
    bet_count: int = Field(description="ベット数")
    predictions: list[Dict[str, Any]] = Field(description="予想詳細")


# ── Settings API Models ──────────────────────────────

class ParametersRequest(BaseModel):
    """パラメータ更新リクエスト"""
    EV_THRESHOLD: Optional[float] = None
    KELLY_FRACTION: Optional[float] = None
    MIN_ODDS: Optional[float] = None
    MIN_ODDS_BACKTEST: Optional[float] = None


class ParametersResponse(BaseModel):
    """パラメータ応答"""
    EV_THRESHOLD: float
    KELLY_FRACTION: float
    MIN_ODDS: float
    MIN_ODDS_BACKTEST: float
    updated_at: Optional[datetime] = None


# ── Admin API Models ─────────────────────────────────

class JobStatus(BaseModel):
    """スケジューラー ジョブステータス"""
    name: str
    next_run: Optional[datetime]
    last_run: Optional[datetime]
    interval_seconds: Optional[float]


class AgentStats(BaseModel):
    """エージェント実行統計"""
    agent_name: str
    total_runs: int = Field(description="総実行数")
    success_count: int = Field(description="成功数")
    error_count: int = Field(description="エラー数")
    avg_duration_seconds: float = Field(description="平均実行時間")
    last_run: Optional[datetime]


# ── Error Models ─────────────────────────────────────

class ErrorDetail(BaseModel):
    """エラーレスポンス"""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
