"""
condition_adjuster_agent.py — 条件別ベット係数調整エージェント
=============================================================
pipeline/condition_adjuster_34.py をラップし、
競馬場×距離×馬場×季節の実績 ROI テーブルからベット係数を算出して
finalized_bets の bet_amount を補正する。

manifest: condition-adjuster-agent v1.0.0
  purpose : 条件別ベット係数による賭け金調整
  inputs  : bets (list[dict] with keibajo/kyori/track_code fields)
  outputs : adjusted_bets (list), coeff_applied (int), avg_coeff (float)
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

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))


class ConditionAdjusterAgent(BaseAgent):
    """
    各ベット候補に競馬場×距離×季節の係数を適用してベット額を補正する。
    条件テーブルが存在しない場合は係数 1.0（無補正）で通過させる。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="condition-adjuster-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        bets: list[dict] = payload.get("bets", payload.get("finalized_bets", []))

        if not bets:
            return {"adjusted_bets": [], "coeff_applied": 0, "avg_coeff": 1.0}

        mod = self._load_module()
        adjusted_bets = []
        coeffs_applied = []

        month = datetime.now().month

        for bet in bets:
            # レースコードから競馬場・距離・馬場を取得（なければデフォルト）
            race_id   = str(bet.get("race_id", bet.get("race_code", "")))
            keibajo   = self._extract_keibajo(race_id, bet)
            kyori     = int(bet.get("kyori", bet.get("distance", 0)) or 0)
            track_code = bet.get("track_code", "1")  # 1=芝, 2=ダート

            adj_amount = int(bet.get("finalized_bet_amount",
                                     bet.get("recommended_bet",
                                     bet.get("stake_amount", 1000))))
            coeff = 1.0
            grade = "B"

            if mod and keibajo and kyori > 0:
                try:
                    adj_amount, coeff, grade = mod.apply_condition_coefficient(
                        adj_amount, keibajo, kyori, track_code, month
                    )
                except Exception as exc:
                    log.debug("apply_condition_coefficient スキップ: %s", exc)

            adjusted = {
                **bet,
                "finalized_bet_amount": adj_amount,
                "condition_coeff":      round(coeff, 4),
                "condition_grade":      grade,
            }
            adjusted_bets.append(adjusted)
            coeffs_applied.append(coeff)

        avg_coeff = sum(coeffs_applied) / max(len(coeffs_applied), 1)
        n_adjusted = sum(1 for c in coeffs_applied if c != 1.0)

        log.info(
            "条件係数適用完了: %d/%d件 調整 avg_coeff=%.3f",
            n_adjusted, len(bets), avg_coeff,
        )

        return {
            "adjusted_bets": adjusted_bets,
            "coeff_applied": n_adjusted,
            "avg_coeff":     round(avg_coeff, 4),
        }

    # ─────────────────────────────────────────────────────────────

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "condition_adjuster_34.py"
        if not script.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("condition_adjuster_34", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("condition_adjuster_34 ロード失敗: %s", exc)
            return None

    @staticmethod
    def _extract_keibajo(race_id: str, bet: dict) -> str:
        """
        レースコードまたは bet dict から競馬場コードを抽出する。
        JRA race_code 16桁 → 8〜9桁目が競馬場コード (01=札幌...10=東京...)
        """
        if "keibajo" in bet:
            return str(bet["keibajo"])
        if len(race_id) >= 10:
            return race_id[8:10]
        return ""
