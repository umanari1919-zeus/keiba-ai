"""
bankroll_agent.py — 高度資金管理エージェント
============================================
pipeline/bankroll_advanced_24.py をラップし、
ドローダウン管理・ケリー最適化・相関リスク管理を実行する。

manifest: bankroll-agent v1.0.0
  purpose : ドローダウン監視 + ポートフォリオリスク上限適用
  inputs  : bets (list, optional)
  outputs : bankroll, peak, drawdown, multiplier, adjusted_bets,
            stop_betting (bool)
"""

from __future__ import annotations

import importlib.util
import logging
import os
import pathlib
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))


class BankrollAgent(BaseAgent):
    """
    bankroll.json を読み込んでドローダウンを評価し、
    ベット額に乗数を適用してリスク上限を守る。

    multiplier=0.0 の場合 stop_betting=True を返す（ベット停止）。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="bankroll-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        bets: list[dict] = payload.get("bets", payload.get("adjusted_bets", []))

        mod = self._load_module()
        if mod is None:
            log.warning("bankroll_advanced_24.py なし — 乗数 1.0 でパス")
            return self._passthrough(bets)

        # ─── ① ドローダウン状態取得 ───────────────────────────────
        try:
            dd_info = mod.manage_drawdown(verbose=False)
        except Exception as exc:
            log.warning("manage_drawdown 失敗: %s", exc)
            return self._passthrough(bets)

        bankroll   = dd_info.get("bankroll",   100_000)
        peak       = dd_info.get("peak",       bankroll)
        drawdown   = dd_info.get("drawdown",   0.0)
        multiplier = dd_info.get("multiplier", 1.0)

        log.info(
            "バンクロール状態: bankroll=%.0f peak=%.0f drawdown=%.1f%% multiplier=%.2f",
            bankroll, peak, drawdown * 100, multiplier,
        )

        stop_betting = multiplier == 0.0
        if stop_betting:
            log.error("[BANKROLL] ドローダウン %.1f%% → ベット停止", drawdown * 100)
            return {
                "bankroll":      bankroll,
                "peak":          peak,
                "drawdown":      drawdown,
                "multiplier":    0.0,
                "stop_betting":  True,
                "adjusted_bets": [],
            }

        # ─── ② ベット額に乗数適用 ────────────────────────────────
        if not bets:
            return {
                "bankroll":      bankroll,
                "peak":          peak,
                "drawdown":      drawdown,
                "multiplier":    multiplier,
                "stop_betting":  False,
                "adjusted_bets": [],
            }

        # ─── ③ portfolio_risk_management で上限適用 ──────────────
        try:
            risk_bets = mod.portfolio_risk_management(bets, bankroll)
        except Exception as exc:
            log.debug("portfolio_risk_management スキップ: %s", exc)
            risk_bets = bets

        # 乗数をベット額に反映
        result_bets = []
        for b in risk_bets:
            amt = int(b.get("finalized_bet_amount",
                         b.get("recommended_bet",
                               b.get("stake_amount", 1000))))
            adjusted = max(100, round(amt * multiplier / 100) * 100)
            result_bets.append({**b, "finalized_bet_amount": adjusted,
                                 "bankroll_multiplier": round(multiplier, 4)})

        log.info("バンクロール調整完了: %d件 multiplier=%.2f", len(result_bets), multiplier)

        return {
            "bankroll":      bankroll,
            "peak":          peak,
            "drawdown":      round(drawdown, 4),
            "multiplier":    round(multiplier, 4),
            "stop_betting":  False,
            "adjusted_bets": result_bets,
        }

    # ─────────────────────────────────────────────────────────────

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "bankroll_advanced_24.py"
        if not script.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("bankroll_advanced_24", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("bankroll_advanced_24 ロード失敗: %s", exc)
            return None

    @staticmethod
    def _passthrough(bets: list) -> dict[str, Any]:
        return {
            "bankroll":      100_000,
            "peak":          100_000,
            "drawdown":      0.0,
            "multiplier":    1.0,
            "stop_betting":  False,
            "adjusted_bets": bets,
        }
