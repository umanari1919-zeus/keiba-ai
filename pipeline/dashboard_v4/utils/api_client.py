"""
FastAPI クライアント

Streamlit ページから FastAPI バックエンドへの HTTP リクエストをラップ。
requests ライブラリ使用。
"""
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

# FastAPI サーバーのベース URL
API_BASE_URL = "http://localhost:8000"


class APIClient:
    """FastAPI クライアント"""

    @staticmethod
    def _make_request(
        method: str, endpoint: str, **kwargs
    ) -> Dict[str, Any]:
        """HTTP リクエストを実行"""
        url = f"{API_BASE_URL}{endpoint}"
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            raise RuntimeError("FastAPI server is not running (http://localhost:8000)")
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"API error: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.Timeout:
            raise RuntimeError("API request timed out")

    # ── Pipeline API ──────────────────────────────────────────────────

    @staticmethod
    def run_pipeline(pattern: str = "v2") -> str:
        """
        Pipeline を実行開始

        Args:
            pattern: "v2", "morning", "weekly", "results"

        Returns:
            trace_id: 実行識別子
        """
        response = APIClient._make_request(
            "POST",
            "/api/pipeline/run",
            json={"pattern": pattern},
        )
        return response["trace_id"]

    @staticmethod
    def get_pipeline_status(trace_id: str) -> Dict[str, Any]:
        """
        Pipeline 実行状態を確認

        Args:
            trace_id: 実行識別子

        Returns:
            status: running/completed/failed/cancelled
            exit_code: int or None
            elapsed_seconds: float or None
            start_time, end_time: ISO形式の時刻文字列
        """
        return APIClient._make_request("GET", f"/api/pipeline/status/{trace_id}")

    @staticmethod
    def get_pipeline_log(trace_id: str, tail: int = 100) -> List[str]:
        """
        Pipeline 実行ログを取得

        Args:
            trace_id: 実行識別子
            tail: 末尾行数

        Returns:
            ログ行のリスト
        """
        response = APIClient._make_request(
            "GET",
            f"/api/pipeline/log/{trace_id}",
            params={"tail": tail},
        )
        return response["lines"]

    @staticmethod
    def get_pipeline_history(limit: int = 50) -> List[Dict[str, Any]]:
        """
        Pipeline 実行履歴を取得

        Args:
            limit: 取得件数

        Returns:
            実行履歴リスト
        """
        response = APIClient._make_request(
            "GET",
            "/api/pipeline/history",
            params={"limit": limit},
        )
        return response

    @staticmethod
    def cancel_pipeline(trace_id: str) -> Dict[str, str]:
        """
        Pipeline 実行をキャンセル

        Args:
            trace_id: 実行識別子

        Returns:
            キャンセル結果メッセージ
        """
        return APIClient._make_request("POST", f"/api/pipeline/cancel/{trace_id}")

    # ── Data API ──────────────────────────────────────────────────────

    @staticmethod
    def get_predictions(date: Optional[str] = None) -> Dict[str, Any]:
        """
        予想データを取得

        Args:
            date: YYYYMMDD (省略時は本日)

        Returns:
            予想データ (JSON)
        """
        endpoint = "/api/data/predictions"
        if date:
            endpoint += f"/{date}"
        return APIClient._make_request("GET", endpoint)

    @staticmethod
    def get_roi(year: Optional[int] = None) -> Dict[str, Any]:
        """
        ROI サマリーを取得

        Args:
            year: 年 (省略時は本年)

        Returns:
            ROI サマリー
        """
        endpoint = "/api/data/roi"
        if year:
            endpoint += f"/{year}"
        return APIClient._make_request("GET", endpoint)

    @staticmethod
    def get_bankroll() -> Dict[str, float]:
        """
        資金情報を取得

        Returns:
            current, initial, peak, drawdown_percent
        """
        return APIClient._make_request("GET", "/api/data/bankroll")

    @staticmethod
    def get_race_ranking(year: Optional[int] = None, limit: int = 20) -> Dict[str, Any]:
        """
        レース順位ランキングを取得

        Args:
            year: 年 (省略時は本年)
            limit: 取得件数

        Returns:
            レース順位リスト
        """
        endpoint = "/api/data/race-ranking"
        if year:
            endpoint += f"/{year}"
        return APIClient._make_request("GET", endpoint, params={"limit": limit})

    @staticmethod
    def get_model_performance() -> Dict[str, Any]:
        """
        モデル性能統計を取得

        Returns:
            accuracy, roc_auc, f1_score, last_updated
        """
        return APIClient._make_request("GET", "/api/data/model-performance")

    # ── Settings API ──────────────────────────────────────────────────

    @staticmethod
    def get_parameters() -> Dict[str, Any]:
        """
        現在の設定パラメータを取得

        Returns:
            EV_THRESHOLD, KELLY_FRACTION, MIN_ODDS, MIN_ODDS_BACKTEST, updated_at
        """
        return APIClient._make_request("GET", "/api/settings/parameters")

    @staticmethod
    def update_parameters(**kwargs) -> Dict[str, Any]:
        """
        設定パラメータを更新

        Args:
            EV_THRESHOLD: float (optional)
            KELLY_FRACTION: float (optional)
            MIN_ODDS: float (optional)
            MIN_ODDS_BACKTEST: float (optional)

        Returns:
            更新結果 + 新規パラメータ値
        """
        body = {k: v for k, v in kwargs.items() if v is not None}
        return APIClient._make_request("PUT", "/api/settings/parameters", json=body)

    @staticmethod
    def reset_parameters() -> Dict[str, Any]:
        """
        すべてのパラメータをデフォルト値にリセット

        Returns:
            リセット結果
        """
        return APIClient._make_request("POST", "/api/settings/reset")

    # ── Admin API ─────────────────────────────────────────────────────

    @staticmethod
    def get_jobs() -> List[Dict[str, Any]]:
        """
        スケジューラー登録ジョブを取得

        Returns:
            ジョブリスト (name, next_run, last_run, interval_seconds)
        """
        return APIClient._make_request("GET", "/api/admin/jobs")

    @staticmethod
    def trigger_job(job_name: str) -> Dict[str, str]:
        """
        ジョブを手動トリガー

        Args:
            job_name: ジョブ名

        Returns:
            トリガー結果
        """
        return APIClient._make_request("POST", f"/api/admin/jobs/{job_name}/run")

    @staticmethod
    def search_logs(
        pattern: Optional[str] = None, limit: int = 100
    ) -> Dict[str, Any]:
        """
        ログを検索

        Args:
            pattern: 検索パターン (trace_id またはキーワード)
            limit: 取得行数

        Returns:
            マッチしたログエントリ
        """
        params = {"limit": limit}
        if pattern:
            params["pattern"] = pattern
        return APIClient._make_request("GET", "/api/admin/logs", params=params)

    @staticmethod
    def get_agent_stats() -> List[Dict[str, Any]]:
        """
        エージェント実行統計を取得

        Returns:
            エージェント統計リスト
        """
        return APIClient._make_request("GET", "/api/admin/agents")

    @staticmethod
    def get_agent_detail_stats(agent_name: str) -> Dict[str, Any]:
        """
        特定エージェントの詳細統計を取得

        Args:
            agent_name: エージェント名

        Returns:
            詳細統計
        """
        return APIClient._make_request("GET", f"/api/admin/agents/{agent_name}/stats")
