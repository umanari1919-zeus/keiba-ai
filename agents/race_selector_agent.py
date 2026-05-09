"""
race_selector_agent.py — レース選別エージェント
================================================
pipeline/race_selector_31.py をラップし、
EV・荒れやすさ・予測可能性の複合スコアでレースを Grade S/A/B/C に格付けして
TradingAgent が注力すべきレースを絞り込む。

manifest: race-selector-agent v1.0.0
  purpose : 日次レース価値スコアリング → Grade S/A フィルタ
  inputs  : year (int, optional)
  outputs : ranked_races (list), grade_s (list), grade_a (list),
            grade_counts (dict)
"""

from __future__ import annotations

import importlib.util
import logging
from datetime import datetime
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR

log = logging.getLogger(__name__)

class RaceSelectorAgent(BaseAgent):
    """
    当日の全レースをスコアリングし Grade S/A を推奨レースとして返す。
    dry_run=True でもスコアリング計算は実行する（DB・発注は行わない）。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="race-selector-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        year = payload.get("year") or datetime.now().year
        min_grade = payload.get("min_grade", "B")  # B 以上をベット対象に

        mod = self._load_module()
        if mod is None:
            log.warning("race_selector_31.py なし — 空ランキングを返します")
            return self._empty_result()

        try:
            import pandas as pd

            feat = BASE_DIR / "keiba_data_features.csv"
            if not feat.exists():
                log.warning("特徴量ファイルなし → 空ランキング")
                return self._empty_result()

            df = pd.read_csv(feat, encoding="utf-8-sig", low_memory=False,
                             on_bad_lines="skip")
            ranked = mod.rank_races(df, year)

            if ranked.empty:
                log.info("対象レースなし (year=%d)", year)
                return self._empty_result()

            records = ranked.to_dict(orient="records")
            grade_counts = ranked["grade"].value_counts().to_dict()

            grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
            threshold   = grade_order.get(min_grade, 2)
            recommended = [r for r in records if grade_order.get(r["grade"], 9) <= threshold]

            log.info(
                "レース選別完了: 合計=%d S=%d A=%d B=%d C=%d 推奨(%s以上)=%d",
                len(records),
                grade_counts.get("S", 0), grade_counts.get("A", 0),
                grade_counts.get("B", 0), grade_counts.get("C", 0),
                min_grade, len(recommended),
            )

            return {
                "ranked_races":  records,
                "grade_s":       [r for r in records if r["grade"] == "S"],
                "grade_a":       [r for r in records if r["grade"] == "A"],
                "recommended":   recommended,
                "grade_counts":  grade_counts,
                "year":          year,
            }

        except Exception as exc:
            log.warning("race_selector_31 実行失敗: %s", exc)
            return self._empty_result()

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "race_selector_31.py"
        if not script.exists():
            log.warning("race_selector_31.py が見つかりません: %s", script)
            return None
        try:
            spec = importlib.util.spec_from_file_location("race_selector_31", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("race_selector_31 ロード失敗: %s", exc)
            return None

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "ranked_races": [], "grade_s": [], "grade_a": [],
            "recommended": [], "grade_counts": {}, "year": datetime.now().year,
        }
