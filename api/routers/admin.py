"""
Admin API ルーター

/api/admin/* エンドポイント:
- GET    /api/admin/jobs                      ジョブ一覧
- POST   /api/admin/jobs/{job_name}/run      ジョブ手動トリガー
- GET    /api/admin/logs?pattern=&limit=100  ログ検索
- GET    /api/admin/agents                    エージェント統計
- GET    /api/admin/agents/{agent_name}/stats エージェント詳細統計
"""
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Dict, List, Any
from ..models import JobStatus, AgentStats
from ..services.scheduler_service import SchedulerService

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ログディレクトリ
LOGS_DIR = Path("logs")


@router.get("/jobs", response_model=List[JobStatus])
async def get_jobs():
    """
    スケジューラー登録ジョブの一覧を取得

    Returns:
        JobStatus リスト
    """
    try:
        jobs = SchedulerService.get_jobs()
        return [JobStatus(**job) for job in jobs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_name}/run")
async def trigger_job(job_name: str):
    """
    ジョブを手動トリガー（即座実行）

    Args:
        job_name: ジョブ名

    Returns:
        トリガー結果

    Raises:
        HTTPException: ジョブが見つからない、または実行失敗の場合
    """
    try:
        result = SchedulerService.trigger_job(job_name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def search_logs(
    pattern: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """
    ログを検索

    Args:
        pattern: 検索パターン（trace_id またはキーワード）
        limit: 取得行数

    Returns:
        マッチしたログエントリ
    """
    try:
        logs = []

        if not LOGS_DIR.exists():
            return {"pattern": pattern, "limit": limit, "logs": logs}

        for log_file in sorted(LOGS_DIR.glob("*.log"), reverse=True):
            if pattern and pattern not in log_file.stem:
                continue

            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            for line in lines[-limit:]:
                logs.append({"file": log_file.name, "line": line.rstrip("\n")})

        return {"pattern": pattern, "limit": limit, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents", response_model=List[AgentStats])
async def get_agent_stats() -> List[AgentStats]:
    """
    エージェント実行統計を取得

    Returns:
        AgentStats リスト
    """
    # TODO: agents/ ディレクトリから統計を集約
    # 暫定: 空リストを返す
    return []


@router.get("/agents/{agent_name}/stats")
async def get_agent_detail_stats(agent_name: str) -> Dict[str, Any]:
    """
    特定エージェントの詳細統計を取得

    Args:
        agent_name: エージェント名

    Returns:
        詳細統計
    """
    try:
        # TODO: agents/audit_log/{agent_name}.json から履歴を取得
        return {
            "agent_name": agent_name,
            "total_runs": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_duration_seconds": 0.0,
            "last_run": None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
