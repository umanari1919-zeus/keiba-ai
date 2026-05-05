"""
FastAPI メインアプリケーション

うまなり地蔵AI REST API バックエンド
"""
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

# CORS 設定（localhost・VPN アクセス許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost のみ推奨環境で制限
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
