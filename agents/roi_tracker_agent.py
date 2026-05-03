"""
roi_tracker_agent.py — 回収率追跡エージェント
================================================
pipeline/roi_tracker_12.py をラップし、日次・週次・月次の
損益サマリーと連敗数を算出して MonitorAgent へ渡すメトリクスを返す。

manifest: roi-tracker-agent v1.0.0
  purpose : 損益集計 → auto_stop 判断材料の提供
  inputs  : (なし)
  outputs : daily_roi, weekly_roi, monthly_roi, consecutive_losses,
            daily_summary, alerts
"""

from __future__ import annotations

import importlib.util
import logging
import os
import pathlib
from datetime import datetime
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR     = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
TRACKER_FILE = BASE_DIR / "data" / "roi_tracker.csv"


class RoiTrackerAgent(BaseAgent):
    """
    roi_tracker.csv の個別ベット記録から期間別損益を集計する。

    dry_run=True の場合はファイルが空でも安全に 0 を返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="roi-tracker-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        mod = self._load_module()

        # ─── ファイルなし / モジュールなし時は安全にゼロ返し ────
        if mod is None or not TRACKER_FILE.exists():
            log.info("roi_tracker.csv なし → ゼロサマリーを返します")
            return self._zero_summary()

        # ─── 期間別サマリー取得 ───────────────────────────────────
        daily   = self._safe_summary(mod, "daily")
        weekly  = self._safe_summary(mod, "weekly")
        monthly = self._safe_summary(mod, "monthly")
        cumul   = self._safe_summary(mod, "all")

        daily_roi   = daily.get("roi",  0.0)   if daily   else 0.0
        weekly_roi  = weekly.get("roi", 0.0)   if weekly  else 0.0
        monthly_roi = monthly.get("roi", 0.0)  if monthly else 0.0

        # ─── 連敗数を計算 ────────────────────────────────────────
        consecutive_losses = self._calc_consecutive_losses()

        # ─── ROI アラート取得 ─────────────────────────────────────
        try:
            roi_alerts = mod.check_alerts()
        except Exception as exc:
            log.debug("check_alerts スキップ: %s", exc)
            roi_alerts = []

        log.info(
            "ROI 集計: daily=%.1f%% weekly=%.1f%% monthly=%.1f%% losses=%d",
            daily_roi * 100, weekly_roi * 100, monthly_roi * 100, consecutive_losses,
        )
        for a in roi_alerts:
            level = a.get("level", "INFO")
            if level == "CRITICAL":
                log.error("  [ROI CRITICAL] %s", a.get("message", ""))
            else:
                log.warning("  [ROI WARNING] %s", a.get("message", ""))

        return {
            "daily_roi":          daily_roi,
            "weekly_roi":         weekly_roi,
            "monthly_roi":        monthly_roi,
            "consecutive_losses": consecutive_losses,
            "daily_summary":      daily   or {},
            "weekly_summary":     weekly  or {},
            "monthly_summary":    monthly or {},
            "cumulative_summary": cumul   or {},
            "alerts":             roi_alerts,
        }

    # ─────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "roi_tracker_12.py"
        if not script.exists():
            log.warning("roi_tracker_12.py が見つかりません: %s", script)
            return None
        try:
            spec = importlib.util.spec_from_file_location("roi_tracker_12", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("roi_tracker_12 ロード失敗: %s", exc)
            return None

    def _safe_summary(self, mod, period: str) -> dict | None:
        try:
            return mod.get_summary(period)
        except Exception as exc:
            log.debug("get_summary(%s) 失敗: %s", period, exc)
            return None

    def _calc_consecutive_losses(self) -> int:
        """roi_tracker.csv の末尾から連続外れ数を数える。"""
        if not TRACKER_FILE.exists():
            return 0
        try:
            import pandas as pd
            df = pd.read_csv(TRACKER_FILE, encoding="utf-8-sig", on_bad_lines="skip",
                             dtype={"race_code": str})
            if "hit" not in df.columns or len(df) == 0:
                return 0
            streak = 0
            for hit in reversed(df["hit"].tolist()):
                if int(hit) == 0:
                    streak += 1
                else:
                    break
            return streak
        except Exception as exc:
            log.debug("連敗数算出スキップ: %s", exc)
            return 0

    @staticmethod
    def _zero_summary() -> dict[str, Any]:
        empty: dict = {}
        return {
            "daily_roi":          0.0,
            "weekly_roi":         0.0,
            "monthly_roi":        0.0,
            "consecutive_losses": 0,
            "daily_summary":      empty,
            "weekly_summary":     empty,
            "monthly_summary":    empty,
            "cumulative_summary": empty,
            "alerts":             [],
        }
