"""
WebSocket ルーター

/ws/* エンドポイント:
- /ws/pipeline/{trace_id}    パイプライン実行ログ配信
- /ws/odds/{race_code}        オッズ更新配信
- /ws/notifications           全体通知配信
"""
import asyncio
from fastapi import APIRouter, WebSocketDisconnect
from fastapi.websockets import WebSocket
from ..websockets import manager, LogStreamer, OddsUpdater

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/pipeline/{trace_id}")
async def websocket_pipeline(websocket: WebSocket, trace_id: str):
    """
    Pipeline 実行ログをリアルタイム配信

    Args:
        trace_id: 実行識別子

    クライアントは以下のメッセージを受信：
    {
        "type": "log",
        "trace_id": "run_...",
        "line": "ログ行",
        "timestamp": "ISO8601"
    }
    """
    await manager.connect(websocket, "pipeline")

    # ログストリーミングタスクを起動
    stream_task = asyncio.create_task(LogStreamer.stream_pipeline_logs(trace_id, manager))

    try:
        while True:
            # クライアントからのメッセージを受け取る（キープアライブ）
            data = await websocket.receive_text()
            # ハートビート用（特に処理しない）
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "pipeline")
        stream_task.cancel()
    except Exception:
        manager.disconnect(websocket, "pipeline")
        stream_task.cancel()


@router.websocket("/odds/{race_code}")
async def websocket_odds(websocket: WebSocket, race_code: str):
    """
    オッズ更新をリアルタイム配信

    Args:
        race_code: レースコード（例: 20260426010101）

    クライアントは以下のメッセージを受信：
    {
        "type": "odds",
        "race_code": "...",
        "odds": {...},
        "timestamp": "ISO8601"
    }
    """
    await manager.connect(websocket, "odds")

    # オッズストリーミングタスクを起動
    stream_task = asyncio.create_task(OddsUpdater.stream_odds_updates(race_code, manager))

    try:
        while True:
            # クライアントからのメッセージを受け取る（キープアライブ）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "odds")
        stream_task.cancel()
    except Exception:
        manager.disconnect(websocket, "odds")
        stream_task.cancel()


@router.websocket("/notifications")
async def websocket_notifications(websocket: WebSocket):
    """
    全体通知をリアルタイム配信

    クライアントは以下のメッセージを受信：
    {
        "type": "notification",
        "notification_type": "alert|info|warning|success",
        "message": "...",
        "data": {...},
        "timestamp": "ISO8601"
    }
    """
    await manager.connect(websocket, "notifications")

    try:
        while True:
            # クライアントからのメッセージを受け取る（キープアライブ）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "notifications")
    except Exception:
        manager.disconnect(websocket, "notifications")
