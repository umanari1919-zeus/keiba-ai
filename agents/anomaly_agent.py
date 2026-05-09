"""
anomaly_agent.py — 異常検知エージェント
=========================================
pipeline/anomaly_detect_16.py をラップし、
① モデル精度劣化 ② オッズ異常変動 ③ レースパターン不正兆候
の3種を実行して CRITICAL アラートを auto_stop シグナルに昇格する。

manifest: anomaly-agent v1.0.0
  purpose : 日次異常検知 → MonitorAgent へのフィード
  inputs  : year (int, optional), use_db (bool, default True)
  outputs : alerts (list), critical_count (int), warning_count (int),
            auto_stop (bool)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

ALERT_FILE = DATA_DIR / "anomaly_alerts.json"

# CRITICAL アラートが CRITICAL_STOP_THRESHOLD 件以上で auto_stop を発動
CRITICAL_STOP_THRESHOLD = 3


class AnomalyAgent(BaseAgent):
    """
    3種の異常検知を実行し、結果を AuditLogger に記録する。

    CRITICAL アラートが CRITICAL_STOP_THRESHOLD 件以上の場合、
    output["auto_stop"] = True を返してオーケストレーターに通知する。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="anomaly-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        year   = payload.get("year") or datetime.now().year
        use_db = payload.get("use_db", True)

        # ─── anomaly_detect_16 をロード ──────────────────────────
        mod = self._load_module()

        if mod is None:
            # モジュールが読み込めない場合はモデル劣化検知のみ実施
            log.warning("anomaly_detect_16.py 読み込み失敗 — フォールバック: 空アラートを返す")
            return {
                "alerts":         [],
                "critical_count": 0,
                "warning_count":  0,
                "auto_stop":      False,
            }

        # ─── 3種の検知を実行 ─────────────────────────────────────
        alerts: list[dict] = []
        try:
            alerts = mod.run_anomaly_detection(year=year, use_db=use_db)
        except Exception as exc:
            log.warning("run_anomaly_detection 失敗: %s — 個別実行に切り替え", exc)
            try:
                alerts.extend(mod.detect_model_degradation())
            except Exception as e:
                log.debug("detect_model_degradation スキップ: %s", e)
            if use_db:
                try:
                    alerts.extend(mod.detect_odds_anomaly(year=year))
                except Exception as e:
                    log.debug("detect_odds_anomaly スキップ: %s", e)
                try:
                    alerts.extend(mod.detect_race_pattern_anomaly(year=year))
                except Exception as e:
                    log.debug("detect_race_pattern_anomaly スキップ: %s", e)

        # ─── 集計 ─────────────────────────────────────────────────
        critical_count = sum(1 for a in alerts if a.get("level") == "CRITICAL")
        warning_count  = sum(1 for a in alerts if a.get("level") == "WARNING")
        auto_stop      = critical_count >= CRITICAL_STOP_THRESHOLD

        for a in alerts:
            level = a.get("level", "INFO")
            msg   = a.get("message", "")
            if level == "CRITICAL":
                log.error("  [CRITICAL] %s", msg)
            elif level == "WARNING":
                log.warning("  [WARNING] %s", msg)
            else:
                log.info("  [INFO] %s", msg)

        if auto_stop:
            log.error(
                "[AUTO-STOP 候補] CRITICAL アラート %d 件 (閾値: %d)",
                critical_count, CRITICAL_STOP_THRESHOLD,
            )

        # ─── アラートをファイルに追記 ─────────────────────────────
        self._append_alerts(alerts, meta)

        return {
            "alerts":         alerts,
            "critical_count": critical_count,
            "warning_count":  warning_count,
            "auto_stop":      auto_stop,
        }

    # ─────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "anomaly_detect_16.py"
        if not script.exists():
            log.warning("anomaly_detect_16.py が見つかりません: %s", script)
            return None
        try:
            spec = importlib.util.spec_from_file_location("anomaly_detect_16", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("anomaly_detect_16 ロード失敗: %s", exc)
            return None

    def _append_alerts(self, alerts: list[dict], meta: AgentMeta) -> None:
        if not alerts:
            return
        try:
            ALERT_FILE.parent.mkdir(exist_ok=True)
            history: list = []
            if ALERT_FILE.exists():
                try:
                    history = json.loads(ALERT_FILE.read_text(encoding="utf-8"))
                except Exception:
                    history = []
            # trace_id を付与してから追記
            for a in alerts:
                a.setdefault("trace_id", meta.trace_id)
            history.extend(alerts)
            history = history[-500:]   # 最大500件
            ALERT_FILE.write_text(
                json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.debug("アラートファイル書き込みスキップ: %s", exc)
