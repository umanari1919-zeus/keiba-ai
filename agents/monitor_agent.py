"""
monitor_agent.py — 継続監視エージェント
=========================================
anomaly_detect_16.py / roi_tracker_12.py をラップし、
マニフェストの auto_stop_conditions を評価して停止フラグを返す。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

# マニフェスト auto_stop_conditions
AUTO_STOP = {
    "mismatch_rate_gt":          0.02,
    "quarantine_24h_increase_gt": 50,
    "spearman_drop_pct":          0.20,
    "daily_loss_pct_trading_gt":  0.03,
    "consecutive_losses_gt":      5,
}


class MonitorAgent(BaseAgent):
    """
    役割: メトリクス収集 → 異常検出 → auto_stop 評価
    対応: manifest monitor-agent v1.0.0
    """

    agent_id      = "monitor-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        metrics      = self._collect_metrics(meta, payload)
        alerts       = self._check_auto_stop(metrics)
        auto_stop    = any(a["severity"] == "critical" for a in alerts)

        report = {
            "metrics":          metrics,
            "alerts":           alerts,
            "auto_stop":        auto_stop,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

        # アラート保存
        today     = datetime.now().strftime("%Y%m%d")
        alert_dir = BASE_DIR / "pipeline_v2" / "alerts"
        alert_dir.mkdir(exist_ok=True)
        (alert_dir / f"monitor_{today}_{meta.trace_id[:8]}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if auto_stop:
            log.critical("[monitor-agent] AUTO-STOP 発動! alerts=%s", alerts)
        elif alerts:
            log.warning("[monitor-agent] アラート %d 件: %s", len(alerts), alerts)
        else:
            log.info("[monitor-agent] 正常稼働中")

        return report

    # ------------------------------------------------------------------ #

    def _collect_metrics(self, meta: AgentMeta, payload: dict) -> dict:
        metrics = {
            "mismatch_rate":     payload.get("mismatch_rate", 0.0),
            "quarantine_count":  payload.get("quarantine_count", 0),
            "spearman":          payload.get("spearman", 1.0),
            "daily_roi":         payload.get("daily_roi", 0.0),
            "consecutive_losses": payload.get("consecutive_losses", 0),
        }

        # payload に roi_tracker の値がなければ RoiTrackerAgent から取得
        if metrics["daily_roi"] == 0.0 or metrics["consecutive_losses"] == 0:
            try:
                from .roi_tracker_agent import RoiTrackerAgent
                rt_result = RoiTrackerAgent(dry_run=False).execute(meta, {})
                if rt_result.ok:
                    out = rt_result.output
                    if metrics["daily_roi"] == 0.0:
                        metrics["daily_roi"] = out.get("daily_roi", 0.0)
                    if metrics["consecutive_losses"] == 0:
                        metrics["consecutive_losses"] = out.get("consecutive_losses", 0)
            except Exception as exc:
                log.debug("RoiTrackerAgent 呼び出しスキップ: %s", exc)

        return metrics

    def _check_auto_stop(self, metrics: dict) -> list[dict]:
        alerts = []

        checks = [
            ("mismatch_rate",      AUTO_STOP["mismatch_rate_gt"],          "gt", "critical"),
            ("quarantine_count",   AUTO_STOP["quarantine_24h_increase_gt"], "gt", "critical"),
            ("daily_roi",         -AUTO_STOP["daily_loss_pct_trading_gt"],  "lt", "critical"),
            ("consecutive_losses", AUTO_STOP["consecutive_losses_gt"],      "gt", "warning"),
        ]

        for metric, threshold, op, severity in checks:
            val = metrics.get(metric, 0)
            triggered = (op == "gt" and val > threshold) or (op == "lt" and val < threshold)
            if triggered:
                alerts.append({
                    "metric":    metric,
                    "value":     val,
                    "threshold": threshold,
                    "severity":  severity,
                    "message":   f"{metric}={val} {'>' if op == 'gt' else '<'} {threshold}",
                })

        return alerts
