"""
Pipeline API ルーター

/api/pipeline/* エンドポイント:
- POST   /api/pipeline/run              実行開始
- GET    /api/pipeline/status/{trace_id} 実行状態確認
- GET    /api/pipeline/log/{trace_id}    ログ取得
- GET    /api/pipeline/history           実行履歴取得
- POST   /api/pipeline/cancel/{trace_id} 実行キャンセル
"""
from fastapi import APIRouter, HTTPException, Query
from ..models import (
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
    PipelineLog,
    PipelineHistory,
)
from ..services import PipelineExecutor

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(request: PipelineRunRequest):
    """
    Pipeline を非同期実行開始

    Args:
        request: PipelineRunRequest (pattern: v2, morning, weekly, results)

    Returns:
        PipelineRunResponse (trace_id, status, message)

    Raises:
        HTTPException: パターン無効・実行失敗の場合
    """
    try:
        trace_id = await PipelineExecutor.run_pipeline(pattern=request.pattern)
        return PipelineRunResponse(
            trace_id=trace_id,
            status="running",
            message="Pipeline execution started",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{trace_id}", response_model=PipelineStatus)
async def get_status(trace_id: str):
    """
    Pipeline 実行状態を確認

    Args:
        trace_id: 実行識別子

    Returns:
        PipelineStatus (trace_id, status, exit_code, elapsed_seconds, etc.)

    Raises:
        HTTPException: trace_id が見つからない場合
    """
    try:
        status = await PipelineExecutor.get_status(trace_id)
        return PipelineStatus(**status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/log/{trace_id}", response_model=PipelineLog)
async def get_log(trace_id: str, tail: int = Query(100, ge=0)):
    """
    Pipeline 実行ログを取得

    Args:
        trace_id: 実行識別子
        tail: 取得する末尾行数（0 = すべて）

    Returns:
        PipelineLog (trace_id, lines, total_lines)

    Raises:
        HTTPException: trace_id が見つからない場合
    """
    try:
        log = await PipelineExecutor.get_log(trace_id, tail=tail)
        return PipelineLog(**log)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/history", response_model=list[PipelineHistory])
async def get_history(limit: int = Query(50, ge=1, le=100)):
    """
    Pipeline 実行履歴を取得

    Args:
        limit: 取得件数（最大 100）

    Returns:
        PipelineHistory リスト（新しい順）
    """
    history = await PipelineExecutor.get_history(limit=limit)
    return [PipelineHistory(**item) for item in history]


@router.post("/cancel/{trace_id}")
async def cancel_pipeline(trace_id: str):
    """
    Pipeline 実行をキャンセル（graceful shutdown）

    Args:
        trace_id: 実行識別子

    Returns:
        キャンセル結果

    Raises:
        HTTPException: trace_id が見つからない、またはキャンセル失敗の場合
    """
    try:
        result = await PipelineExecutor.cancel_pipeline(trace_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
