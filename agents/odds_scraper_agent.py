"""
odds_scraper_agent.py — Playwright リアルタイムオッズ取得エージェント
====================================================================
pipeline/odds_scraper_36.py の run_odds_scraper() を BaseAgent 規約でラップする。
JRA 開催日の当日オッズスナップショットを取得し JSON 保存する。

manifest: odds-scraper-agent v1.0.0
  purpose : Playwright でリアルタイムオッズを取得・保存
  inputs  : date_str (str, YYYYMMDD), race_ids (list, optional)
  outputs : snapshot_path, race_count, odds_records
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

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))


class OddsScraperAgent(BaseAgent):
    """
    Playwright を使って JRA 当日オッズをスクレイピングする。
    dry_run=True 時は実際の取得を行わず空結果を返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="odds-scraper-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        if self.dry_run:
            log.info("dry_run=True → オッズ取得をスキップ")
            return self._empty_result("dry_run")

        date_str = payload.get("date_str") or datetime.now().strftime("%Y%m%d")
        race_ids = payload.get("race_ids")

        mod = self._load_module()
        if mod is None:
            return self._empty_result("odds_scraper_36 未実装")

        try:
            result = mod.run_odds_scraper(date_str=date_str, race_ids=race_ids)
            if not isinstance(result, dict):
                result = {}

            snapshot_path  = result.get("snapshot_path",  "")
            race_count     = int(result.get("race_count",  0))
            odds_records   = result.get("odds_records",   [])

            log.info(
                "オッズ取得完了: date=%s races=%d records=%d",
                date_str, race_count, len(odds_records),
            )

            return {
                "snapshot_path": snapshot_path,
                "race_count":    race_count,
                "odds_records":  odds_records,
                "date_str":      date_str,
            }

        except Exception as exc:
            log.warning("odds_scraper_36 実行失敗: %s", exc)
            return self._empty_result(str(exc))

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "odds_scraper_36.py"
        if not script.exists():
            log.warning("odds_scraper_36.py が存在しません")
            return None
        try:
            spec = importlib.util.spec_from_file_location("odds_scraper_36", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("odds_scraper_36 ロード失敗: %s", exc)
            return None

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "snapshot_path": "",
            "race_count":    0,
            "odds_records":  [],
            "date_str":      "",
            "skipped_reason": reason,
        }
