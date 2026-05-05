"""
Settings API ルーター

/api/settings/* エンドポイント:
- GET    /api/settings/parameters       パラメータ取得
- PUT    /api/settings/parameters       パラメータ更新
- POST   /api/settings/reset            デフォルトリセット
"""
from fastapi import APIRouter, HTTPException
from ..models import ParametersRequest, ParametersResponse
from ..services.config_service import ConfigService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/parameters", response_model=ParametersResponse)
async def get_parameters():
    """
    現在の設定パラメータを取得

    Returns:
        ParametersResponse (EV_THRESHOLD, KELLY_FRACTION, MIN_ODDS, MIN_ODDS_BACKTEST, updated_at)
    """
    try:
        params = ConfigService.get_parameters()
        return ParametersResponse(**params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/parameters")
async def update_parameters(request: ParametersRequest):
    """
    設定パラメータを更新

    Args:
        request: ParametersRequest (EV_THRESHOLD, KELLY_FRACTION, MIN_ODDS, MIN_ODDS_BACKTEST)

    Returns:
        更新結果

    Raises:
        HTTPException: パラメータ無効・更新失敗の場合
    """
    try:
        # 更新対象を抽出（None でないもの）
        updates = {k: v for k, v in request.dict().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No parameters to update")

        # 各パラメータを更新
        for key, value in updates.items():
            ConfigService.set_parameter(key, value)

        # 更新後の値を返す
        params = ConfigService.get_parameters()
        return {
            "message": f"Updated {len(updates)} parameter(s)",
            "parameters": params,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Config write error: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Config reload error: {e}")


@router.post("/reset")
async def reset_parameters():
    """
    すべてのパラメータをデフォルト値にリセット

    Returns:
        リセット結果

    Raises:
        HTTPException: リセット失敗の場合
    """
    try:
        ConfigService.reset_parameters()
        params = ConfigService.get_parameters()
        return {
            "message": "All parameters reset to defaults",
            "parameters": params,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
