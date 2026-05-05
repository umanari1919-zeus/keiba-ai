"""
スケジューラー統合サービス

scheduler.py の 8 ジョブを管理し、
Admin API でジョブ状態取得・手動トリガーを実現する。
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


class SchedulerService:
    """scheduler.py ジョブ管理"""

    # ジョブメタデータ（scheduler.py から抽出）
    _job_specs = {
        "v2_daily": {
            "name": "v2_daily",
            "description": "日次 DAG 実行 (--v2)",
            "interval_seconds": 86400,  # 24h
            "default_hour": 8,
        },
        "v2_weekly": {
            "name": "v2_weekly",
            "description": "週次 DAG 実行 (--v2-weekly)",
            "interval_seconds": 604800,  # 7d
            "default_day": "Sunday",
        },
        "morning_mode": {
            "name": "morning_mode",
            "description": "朝モード (--morning)",
            "interval_seconds": 86400,
            "default_hour": 6,
        },
        "odds_monitor": {
            "name": "odds_monitor",
            "description": "オッズ監視 (SHARP/STEAM/DRIFT)",
            "interval_seconds": 1800,  # 30min
        },
        "auto_learn": {
            "name": "auto_learn",
            "description": "自動再学習トリガー",
            "interval_seconds": 604800,  # weekly
        },
        "results_sync": {
            "name": "results_sync",
            "description": "結果確定同期 (--results)",
            "interval_seconds": 86400,
            "default_hour": 20,
        },
        "roi_report": {
            "name": "roi_report",
            "description": "ROI レポート生成",
            "interval_seconds": 86400,
            "default_hour": 22,
        },
        "knowledge_update": {
            "name": "knowledge_update",
            "description": "知識ベース更新",
            "interval_seconds": 604800,  # weekly
        },
    }

    @classmethod
    def get_jobs(cls) -> List[Dict[str, Any]]:
        """
        スケジューラー登録ジョブの一覧を取得

        Returns:
            ジョブメタデータリスト
        """
        try:
            import scheduler
            jobs = []

            for job in scheduler.jobs:
                job_info = {
                    "name": job.tag if hasattr(job, 'tag') else "unknown",
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "interval_seconds": job.interval if hasattr(job, 'interval') else None,
                }
                jobs.append(job_info)

            return jobs
        except ImportError:
            # scheduler.py が見つからない場合はメタデータから生成
            return [
                {
                    "name": spec["name"],
                    "next_run": None,
                    "last_run": None,
                    "interval_seconds": spec.get("interval_seconds"),
                }
                for spec in cls._job_specs.values()
            ]

    @classmethod
    def get_job(cls, job_name: str) -> Optional[Dict[str, Any]]:
        """
        特定のジョブ情報を取得

        Args:
            job_name: ジョブ名

        Returns:
            ジョブ情報、またはジョブが見つからない場合は None
        """
        try:
            import scheduler

            for job in scheduler.jobs:
                if (hasattr(job, 'tag') and job.tag == job_name):
                    return {
                        "name": job_name,
                        "next_run": job.next_run.isoformat() if job.next_run else None,
                        "last_run": job.last_run.isoformat() if job.last_run else None,
                        "interval_seconds": job.interval if hasattr(job, 'interval') else None,
                    }

            return None
        except ImportError:
            return None

    @classmethod
    def trigger_job(cls, job_name: str) -> Dict[str, str]:
        """
        ジョブを手動トリガー（即座実行）

        Args:
            job_name: ジョブ名

        Returns:
            実行結果

        Raises:
            ValueError: ジョブが見つからない場合
            RuntimeError: 実行失敗の場合
        """
        try:
            import scheduler

            job = None
            for j in scheduler.jobs:
                if hasattr(j, 'tag') and j.tag == job_name:
                    job = j
                    break

            if not job:
                raise ValueError(f"Job '{job_name}' not found")

            # job.do() で即座実行（次の実行スケジュール待機をスキップ）
            try:
                job.do()
                return {
                    "job_name": job_name,
                    "message": f"Triggered job: {job_name}",
                    "triggered_at": datetime.now().isoformat(),
                }
            except Exception as e:
                raise RuntimeError(f"Failed to trigger job: {e}")

        except ImportError:
            raise RuntimeError("scheduler.py not available")

    @classmethod
    def get_job_metadata(cls, job_name: str) -> Optional[Dict[str, Any]]:
        """
        ジョブのメタデータを取得（スペック情報）

        Args:
            job_name: ジョブ名

        Returns:
            メタデータ、またはジョブが見つからない場合は None
        """
        return cls._job_specs.get(job_name)

    @classmethod
    def list_job_specs(cls) -> Dict[str, Dict[str, Any]]:
        """
        すべてのジョブスペックを取得

        Returns:
            ジョブスペック辞書
        """
        return cls._job_specs
