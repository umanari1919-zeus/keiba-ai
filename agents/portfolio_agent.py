"""
portfolio_agent.py — ポートフォリオ最適化エージェント
======================================================
TradingAgent が出力した candidate_bets を受け取り、
① ticket_optimizer_30.py で馬券種を選択し
② bet_portfolio_29.py で多点買い最適配分を算出する。

manifest: portfolio-agent v1.0.0
  purpose : 馬券種選択 + 多点買いポートフォリオ最適化
  inputs  : candidate_bets (list), bankroll (float)
  outputs : finalized_bets (list), summary (dict)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

BANKROLL_FILE = DATA_DIR / "bankroll.json"
DEFAULT_BANKROLL = 100_000  # 初期資金 10 万円


class PortfolioAgent(BaseAgent):
    """
    TradingAgent → PortfolioAgent の連携で馬券種・配分を確定する。

    dry_run=True の場合は計算のみ行い発注せず、finalized_bets を返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="portfolio-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        candidate_bets: list[dict] = payload.get("candidate_bets", [])
        bankroll: float = payload.get("bankroll") or self._load_bankroll()

        if not candidate_bets:
            log.info("候補ベットなし → ポートフォリオ最適化をスキップ")
            return {
                "finalized_bets": [],
                "summary": {"total_bets": 0, "total_amount": 0, "portfolio_ratio": 0.0},
            }

        log.info("ポートフォリオ最適化開始: candidates=%d bankroll=%.0f", len(candidate_bets), bankroll)

        # ─── ① 馬券種選択（ticket_optimizer_30）────────────────
        ticket_mod = self._load_module("ticket_optimizer_30.py")
        ticket_picks = self._apply_ticket_optimizer(ticket_mod, candidate_bets, bankroll)

        # ─── ② 多点買いポートフォリオ最適化（bet_portfolio_29）──
        portfolio_mod = self._load_module("bet_portfolio_29.py")
        finalized_bets, summary = self._apply_portfolio_optimizer(
            portfolio_mod, ticket_picks, bankroll
        )

        log.info(
            "ポートフォリオ最適化完了: finalized=%d total_amount=%d ratio=%.3f",
            len(finalized_bets),
            summary.get("total_amount", 0),
            summary.get("portfolio_ratio", 0.0),
        )

        return {
            "finalized_bets": finalized_bets,
            "summary":        summary,
            "bankroll":       bankroll,
        }

    # ─────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────

    def _load_bankroll(self) -> float:
        """bankroll.json から現在の残高を読み込む。なければデフォルト値。"""
        if BANKROLL_FILE.exists():
            try:
                data = json.loads(BANKROLL_FILE.read_text(encoding="utf-8"))
                return float(data.get("current_bankroll", data.get("bankroll", DEFAULT_BANKROLL)))
            except Exception as exc:
                log.debug("bankroll.json 読み込みスキップ: %s", exc)
        return DEFAULT_BANKROLL

    def _load_module(self, filename: str):
        script = BASE_DIR / "pipeline" / filename
        if not script.exists():
            log.warning("%s が見つかりません: %s", filename, script)
            return None
        try:
            mod_name = filename.replace(".py", "")
            spec = importlib.util.spec_from_file_location(mod_name, script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("%s ロード失敗: %s", filename, exc)
            return None

    def _apply_ticket_optimizer(
        self, mod, candidate_bets: list[dict], bankroll: float
    ) -> list[dict]:
        """
        ticket_optimizer_30.select_optimal_ticket() を各レースに適用し、
        推奨馬券種と bet 額を candidate_bets に追記して返す。
        モジュールがない場合はデフォルト「単勝」を使用。
        """
        if mod is None:
            for b in candidate_bets:
                b.setdefault("ticket_key", "tansho")
                b.setdefault("recommended_bet", b.get("stake_amount", 1000))
            return candidate_bets

        # レースごとにグループ化
        races: dict[str, list[dict]] = {}
        for b in candidate_bets:
            races.setdefault(b.get("race_id", ""), []).append(b)

        result = []
        for race_id, bets in races.items():
            # ticket_optimizer が期待するフォーマットに変換
            candidates = [
                {
                    "race_code": race_id,
                    "umaban":    b.get("entry_id", ""),
                    "win_prob":  b.get("win_prob", 0.0),
                    "win_probability": b.get("win_prob", 0.0),
                    "tansho_odds": b.get("adjusted_odds", b.get("odds", 10.0)),
                    "odds": b.get("adjusted_odds", b.get("odds", 10.0)),
                    "expected_value": b.get("ev_after_slippage", b.get("expected_return", 0.0)),
                }
                for b in bets
            ]
            n_horses = max(len(candidates), 8)  # 最低 8 頭想定
            try:
                ticket = mod.select_optimal_ticket(candidates, bankroll, race_id, n_horses)
                for b in bets:
                    b["ticket_key"]      = ticket.get("ticket_key", "tansho")
                    b["ticket_label"]    = ticket.get("ticket_label", "単勝")
                    b["recommended_bet"] = ticket.get("recommended_bet", b.get("stake_amount", 1000))
                    b["ticket_ev"]       = ticket.get("ev", 0.0)
                    b["ticket_reason"]   = ticket.get("reason", "")
            except Exception as exc:
                log.debug("select_optimal_ticket 失敗 race=%s: %s", race_id, exc)
                for b in bets:
                    b.setdefault("ticket_key", "tansho")
                    b.setdefault("recommended_bet", b.get("stake_amount", 1000))
            result.extend(bets)

        return result

    def _apply_portfolio_optimizer(
        self, mod, ticket_picks: list[dict], bankroll: float
    ) -> tuple[list[dict], dict]:
        """
        bet_portfolio_29.portfolio_optimize_all() を適用して最終配分を算出する。
        モジュールがない場合は ticket_picks をそのまま finalized_bets として返す。
        """
        if mod is None:
            total = sum(b.get("recommended_bet", 0) for b in ticket_picks)
            return ticket_picks, {
                "total_bets":      len(ticket_picks),
                "total_amount":    int(total),
                "portfolio_ratio": round(total / max(bankroll, 1), 4),
                "avg_per_bet":     round(total / max(len(ticket_picks), 1)),
            }

        # bet_portfolio_29 が期待するフォーマットに変換
        picks = [
            {
                "race_code": b.get("race_id", ""),
                "umaban":    b.get("entry_id", ""),
                "win_prob":  b.get("win_prob", 0.0),
                "win_probability": b.get("win_prob", 0.0),
                "odds":      b.get("adjusted_odds", b.get("odds", 10.0)),
                "ev":        b.get("ev_after_slippage", b.get("ticket_ev", 0.0)),
                "expected_value": b.get("ev_after_slippage", b.get("ticket_ev", 0.0)),
                **{k: v for k, v in b.items()},  # 元の全フィールドを保持
            }
            for b in ticket_picks
        ]

        try:
            optimized, summary = mod.portfolio_optimize_all(picks, bankroll)
            # portfolio_bet を finalized_bet_amount として標準化
            for b in optimized:
                b["finalized_bet_amount"] = b.get("portfolio_bet", b.get("recommended_bet", 1000))
            return optimized, summary
        except Exception as exc:
            log.warning("portfolio_optimize_all 失敗: %s — フォールバック", exc)
            total = sum(b.get("recommended_bet", 0) for b in ticket_picks)
            for b in ticket_picks:
                b["finalized_bet_amount"] = b.get("recommended_bet", 1000)
            return ticket_picks, {
                "total_bets":      len(ticket_picks),
                "total_amount":    int(total),
                "portfolio_ratio": round(total / max(bankroll, 1), 4),
                "avg_per_bet":     round(total / max(len(ticket_picks), 1)),
            }
