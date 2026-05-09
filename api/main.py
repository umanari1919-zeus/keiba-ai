"""
FastAPI メインアプリケーション

うまなり地蔵AI REST API バックエンド
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import pipeline_router, data_router, settings_router, admin_router
from .routers.ws import router as ws_router
from .models import ErrorDetail

# FastAPI インスタンス化
app = FastAPI(
    title="うまなり地蔵AI Pipeline API",
    description="Pipeline 実行・データ取得・設定管理・管理者機能・WebSocket リアルタイム更新",
    version="2.0.0",
)

_default_origins = ",".join([
    "http://localhost:8501",
    "http://localhost:3000",
    "http://127.0.0.1:8501",
    "http://127.0.0.1:3000",
])
_allowed_origins = os.getenv("KEIBA_CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター マウント
app.include_router(pipeline_router)
app.include_router(data_router)
app.include_router(settings_router)
app.include_router(admin_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    """API ルート情報"""
    return {
        "name": "うまなり地蔵AI Pipeline API",
        "version": "2.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/health")
async def health():
    """ヘルスチェック"""
    return {"status": "ok"}
