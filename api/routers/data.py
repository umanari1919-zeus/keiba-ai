"""
Data API ルーター

/api/data/* エンドポイント:
- GET    /api/data/predictions/{date?}      予想データ取得
- GET    /api/data/roi/{year?}              ROI サマリー
- GET    /api/data/bankroll                 資金情報
- GET    /api/data/race-ranking/{year?}     レース順位ランキング
- GET    /api/data/model-performance        モデル性能統計
"""
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import json
import csv

router = APIRouter(prefix="/api/data", tags=["data"])

# データディレクトリ
DATA_DIR = Path("data")


@router.get("/predictions/{date}")
async def get_predictions(date: Optional[str] = None) -> Dict[str, Any]:
    """
    予想データを取得

    Args:
        date: 日付 (YYYYMMDD format, 省略可能で本日)

    Returns:
        予想データ (JSON)
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    try:
        pred_file = DATA_DIR / f"agent_picks_{date}.json"
        if not pred_file.exists():
            raise HTTPException(status_code=404, detail=f"No predictions for date {date}")

        with open(pred_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in predictions file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roi/{year}")
async def get_roi(year: Optional[int] = None) -> Dict[str, Any]:
    """
    ROI サマリーを取得

    Args:
        year: 年（省略可能で本年）

    Returns:
        ROI サマリー (daily/weekly/monthly)
    """
    if year is None:
        year = datetime.now().year

    try:
        roi_file = DATA_DIR / "roi_tracker.csv"
        if not roi_file.exists():
            raise HTTPException(status_code=404, detail="ROI tracker not found")

        # CSV 読み込み → 年別フィルタ → 日次/週次/月次サマリー
        roi_data = {"year": year, "daily": {}, "weekly": {}, "monthly": {}}
        return roi_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bankroll")
async def get_bankroll() -> Dict[str, Any]:
    """
    現在の資金情報を取得

    Returns:
        BankrollData (current, initial, peak, drawdown_percent)
    """
    try:
        bankroll_file = DATA_DIR / "bankroll.json"
        if not bankroll_file.exists():
            # デフォルト値を返す
            return {
                "current": 1000000,
                "initial": 1000000,
                "peak": 1000000,
                "drawdown_percent": 0.0,
            }

        with open(bankroll_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in bankroll file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/race-ranking/{year}")
async def get_race_ranking(year: Optional[int] = None, limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    """
    レース順位ランキングを取得

    Args:
        year: 年（省略可能で本年）
        limit: 取得件数

    Returns:
        レース順位ランキング (TOP N)
    """
    if year is None:
        year = datetime.now().year

    try:
        rank_file = DATA_DIR / f"race_ranking_{year}.csv"
        if not rank_file.exists():
            raise HTTPException(status_code=404, detail=f"No race ranking for year {year}")

        races = []
        with open(rank_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                races.append(row)

        return {"year": year, "limit": limit, "races": races}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-performance")
async def get_model_performance() -> Dict[str, Any]:
    """
    モデル性能統計を取得

    Returns:
        モデル性能 (accuracy, ROC-AUC, F1, etc.)
    """
    try:
        perf_file = DATA_DIR / "model_performance.json"
        if not perf_file.exists():
            # デフォルト値
            return {
                "model": "model_v8.pkl",
                "accuracy": 0.0,
                "roc_auc": 0.0,
                "f1_score": 0.0,
                "last_updated": None,
            }

        with open(perf_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in model performance file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
