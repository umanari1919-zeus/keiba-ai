"""
odds_monitor_agent.py — オッズ変動検知エージェント
====================================================
pipeline/odds_monitor_33.py の run_odds_monitor() をラップし、
SHARP / STEAM / DRIFT シグナルを検知してベット調整提案を返す。

manifest: odds-monitor-agent v1.0.0
  purpose : オッズ変動分析 → SHARP/STEAM/DRIFT シグナル検知
  inputs  : year (int, optional), race_codes (list, optional)
  outputs : signals, sharp_count, steam_count, drift_count,
            ev_adjustments, result_path
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR    = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
RESULT_FILE = BASE_DIR / "data" / "odds_monitor_result.json"


class OddsMonitorAgent(BaseAgent):
    """
    過去オッズデータから SHARP/STEAM/DRIFT を分類し、EV 補正値を出力する。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="odds-monitor-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        year = payload.get("year") or datetime.now().year

        mod = self._load_module()
        if mod is None:
            return self._empty_result("odds_monitor_33 未実装")

        try:
            result = mod.run_odds_monitor(year=year)
            if not isinstance(result, dict):
                result = {}

            signals        = result.get("signals", [])
            ev_adjustments = result.get("ev_adjustments", {})

            sharp_count = sum(1 for s in signals if s.get("movement") == "SHARP")
            steam_count = sum(1 for s in signals if s.get("movement") == "STEAM")
            drift_count = sum(1 for s in signals if s.get("movement") == "DRIFT")

            log.info(
                "オッズ監視完了: SHARP=%d STEAM=%d DRIFT=%d",
                sharp_count, steam_count, drift_count,
            )

            output = {
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "trace_id":      meta.trace_id,
                "year":          year,
                "signals":       signals[:50],
                "sharp_count":   sharp_count,
                "steam_count":   steam_count,
                "drift_count":   drift_count,
                "ev_adjustments": ev_adjustments,
            }
            RESULT_FILE.parent.mkdir(exist_ok=True)
            RESULT_FILE.write_text(
                json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            return {
                "signals":        signals,
                "sharp_count":    sharp_count,
                "steam_count":    steam_count,
                "drift_count":    drift_count,
                "ev_adjustments": ev_adjustments,
                "result_path":    str(RESULT_FILE),
            }

        except Exception as exc:
            log.warning("odds_monitor_33 実行失敗: %s", exc)
            return self._empty_result(str(exc))

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "odds_monitor_33.py"
        if not script.exists():
            log.warning("odds_monitor_33.py が存在しません")
            return None
        try:
            spec = importlib.util.spec_from_file_location("odds_monitor_33", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("odds_monitor_33 ロード失敗: %s", exc)
            return None

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "signals":        [],
            "sharp_count":    0,
            "steam_count":    0,
            "drift_count":    0,
            "ev_adjustments": {},
            "result_path":    str(RESULT_FILE),
            "skipped_reason": reason,
        }
