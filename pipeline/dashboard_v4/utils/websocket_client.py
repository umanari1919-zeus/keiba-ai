"""
WebSocket クライアント

Streamlit から FastAPI WebSocket エンドポイントへ接続。
asyncio + websockets ライブラリ使用。
"""
import asyncio
import json
from typing import Callable, Optional, Dict, Any
from datetime import datetime

# WebSocket URI ベース
WS_BASE_URL = "ws://localhost:8000"


class WebSocketClient:
    """WebSocket クライアント"""

    def __init__(self, uri: str, on_message: Callable[[Dict], None]):
        """
        初期化

        Args:
            uri: WebSocket URI (ws://localhost:8000/ws/...)
            on_message: メッセージ受信時のコールバック関数
        """
        self.uri = uri
        self.on_message = on_message
        self.websocket = None
        self.is_connected = False

    async def connect(self):
        """WebSocket に接続"""
        try:
            import websockets
            self.websocket = await websockets.connect(self.uri)
            self.is_connected = True
        except Exception as e:
            raise RuntimeError(f"Failed to connect to WebSocket: {e}")

    async def disconnect(self):
        """WebSocket を切断"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False

    async def listen(self):
        """メッセージを受信し続ける"""
        if not self.is_connected:
            await self.connect()

        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.on_message(data)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            raise RuntimeError(f"WebSocket listening error: {e}")

    async def send_ping(self):
        """ハートビート送信（キープアライブ）"""
        if self.websocket:
            try:
                await self.websocket.send("ping")
            except Exception:
                pass


class StreamlitWebSocketAdapter:
    """Streamlit 用 WebSocket アダプター"""

    @staticmethod
    def create_pipeline_client(
        trace_id: str, callback: Callable[[Dict], None]
    ) -> WebSocketClient:
        """パイプラインログクライアント作成"""
        uri = f"{WS_BASE_URL}/ws/pipeline/{trace_id}"
        return WebSocketClient(uri, callback)

    @staticmethod
    def create_odds_client(
        race_code: str, callback: Callable[[Dict], None]
    ) -> WebSocketClient:
        """オッズ更新クライアント作成"""
        uri = f"{WS_BASE_URL}/ws/odds/{race_code}"
        return WebSocketClient(uri, callback)

    @staticmethod
    def create_notification_client(
        callback: Callable[[Dict], None],
    ) -> WebSocketClient:
        """全体通知クライアント作成"""
        uri = f"{WS_BASE_URL}/ws/notifications"
        return WebSocketClient(uri, callback)
