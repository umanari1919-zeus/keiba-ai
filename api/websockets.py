"""
WebSocket ハンドラー

パイプライン実行ログ、オッズ更新、全体通知をリアルタイム配信。
"""
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Set, Dict
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket コネクション管理"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "pipeline": set(),
            "odds": set(),
            "notifications": set(),
        }

    async def connect(self, websocket: WebSocket, channel: str):
        """クライアントを接続"""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        """クライアントを切断"""
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)

    async def broadcast(self, message: Dict, channel: str):
        """チャネルのすべてのクライアントにメッセージ配信"""
        if channel not in self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # 切断されたコネクションを削除
        for conn in disconnected:
            self.active_connections[channel].discard(conn)


manager = ConnectionManager()


class LogStreamer:
    """パイプライン実行ログをストリーミング"""

    @staticmethod
    async def stream_pipeline_logs(trace_id: str, manager: ConnectionManager):
        """
        logs/{trace_id}.log をリアルタイムで配信

        Args:
            trace_id: 実行識別子
            manager: コネクションマネージャー
        """
        log_path = Path("logs") / f"{trace_id}.log"
        last_position = 0

        while True:
            try:
                if log_path.exists():
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_position)
                        new_lines = f.readlines()

                        if new_lines:
                            for line in new_lines:
                                message = {
                                    "type": "log",
                                    "trace_id": trace_id,
                                    "line": line.rstrip("\n"),
                                    "timestamp": datetime.now().isoformat(),
                                }
                                await manager.broadcast(message, "pipeline")

                            last_position = f.tell()

                # ループを100msごとに実行（CPU使用率を抑える）
                await asyncio.sleep(0.1)

            except Exception as e:
                error_msg = {
                    "type": "error",
                    "trace_id": trace_id,
                    "message": f"Log streaming error: {e}",
                    "timestamp": datetime.now().isoformat(),
                }
                await manager.broadcast(error_msg, "pipeline")
                break


class OddsUpdater:
    """オッズ更新をストリーミング"""

    @staticmethod
    async def stream_odds_updates(race_code: str, manager: ConnectionManager):
        """
        data/odds_snapshot_{YYYYMMDD}.json をリアルタイム監視して配信

        Args:
            race_code: レースコード
            manager: コネクションマネージャー
        """
        odds_dir = Path("data")
        last_update = None

        while True:
            try:
                # 最新のオッズスナップショットを取得
                odds_files = list(odds_dir.glob("odds_snapshot_*.json"))
                if odds_files:
                    latest_file = max(odds_files, key=lambda p: p.stat().st_mtime)

                    # ファイルが更新されたか確認
                    current_update = latest_file.stat().st_mtime
                    if last_update is None or current_update > last_update:
                        try:
                            with open(latest_file, "r", encoding="utf-8") as f:
                                odds_data = json.load(f)

                            # レース別フィルタ
                            if isinstance(odds_data, dict):
                                race_odds = odds_data.get(race_code, {})
                            elif isinstance(odds_data, list):
                                race_odds = next(
                                    (item for item in odds_data if item.get("race_code") == race_code),
                                    {},
                                )
                            else:
                                race_odds = {}

                            if race_odds:
                                message = {
                                    "type": "odds",
                                    "race_code": race_code,
                                    "odds": race_odds,
                                    "timestamp": datetime.now().isoformat(),
                                }
                                await manager.broadcast(message, "odds")

                            last_update = current_update
                        except json.JSONDecodeError:
                            pass

                # 1秒ごとに確認
                await asyncio.sleep(1)

            except Exception as e:
                error_msg = {
                    "type": "error",
                    "race_code": race_code,
                    "message": f"Odds streaming error: {e}",
                    "timestamp": datetime.now().isoformat(),
                }
                await manager.broadcast(error_msg, "odds")
                break


class NotificationBroadcaster:
    """全体通知を配信"""

    @staticmethod
    async def broadcast_notification(
        notification_type: str,
        message: str,
        manager: ConnectionManager,
        data: Dict = None,
    ):
        """
        全クライアントに通知を配信

        Args:
            notification_type: 通知タイプ (alert, info, warning, success)
            message: 通知メッセージ
            manager: コネクションマネージャー
            data: 追加データ
        """
        notification = {
            "type": "notification",
            "notification_type": notification_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        }
        await manager.broadcast(notification, "notifications")
