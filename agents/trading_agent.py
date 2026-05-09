"""
trading_agent.py — 馬券発注エージェント
=========================================
Kelly 基準 + 2段階フィルタ + スリッページシミュレーション。
paper_trading=True の場合は実発注せず trade_log のみ記録。

マニフェスト 2-stage filters:
  Stage1: quarantine_count == 0, data_delay <= threshold
  Stage2: win_prob >= 0.18 OR place_prob >= 0.30,
          uncertainty <= 0.35, model_agreement >= 2, EV >= 1.05
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .audit_logger import sha256_of
from .market_agent import MarketAgent
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

# マニフェスト定数
KELLY_FRACTION_MULTIPLIER = 0.25
STAKE_CAP_PCT             = 0.01
INITIAL_STAKE_PCT         = 0.005
EV_THRESHOLD              = 1.05

# Stage-2 フィルタ閾値
WIN_PROB_MIN      = 0.18
PLACE_PROB_MIN    = 0.30
UNCERTAINTY_MAX   = 0.35
MODEL_AGREE_MIN   = 2

# RL アクション → ベットサイズ係数マッピング
RL_ACTION_MULTIPLIER = {
    "pass":   0.0,
    "small":  0.5,    # Kelly の 50%
    "medium": 1.0,    # Kelly そのまま
    "large":  1.5,    # Kelly の 150%（STAKE_CAP_PCT でキャップ）
}


def _rl_decision(win_prob: float, odds: float, bankroll: float,
                 bankroll0: float, peak: float) -> str:
    """rl_strategy_26.py の rl_betting_decision を呼び出す（フォールバック付き）。"""
    try:
        import sys
        if str(BASE_DIR / "pipeline") not in sys.path:
            sys.path.insert(0, str(BASE_DIR / "pipeline"))
        from rl_strategy_26 import rl_betting_decision  # type: ignore
        return rl_betting_decision(win_prob, odds, bankroll, bankroll0, peak)
    except Exception as exc:
        log.debug("RL fallback (ev-based): %s", exc)
        ev = win_prob * odds - 1
        if ev < 0.05 or odds < 10:
            return "pass"
        return "medium"


class TradingAgent(BaseAgent):
    """
    役割: llm_explanations + predictions → trade_log（実発注 or ペーパー）
    対応: manifest trading-agent v3.0.0
    """

    agent_id      = "trading-agent"
    agent_version = "3.0.0"

    def __init__(self, *, paper_trading: bool = True, use_rl: bool = True, **kwargs: Any):
        super().__init__(**kwargs)
        self.paper_trading = paper_trading
        self.use_rl        = use_rl
        if paper_trading:
            log.info("[trading-agent] ペーパートレードモードで起動")

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        predictions      = payload.get("predictions", [])
        quarantine_count = payload.get("quarantine_count", 0)
        market_signals   = payload.get("market_signals", {})   # MarketAgent 出力（任意）
        bankroll         = self._load_bankroll()

        candidate_bets = []
        skipped_s1 = 0
        skipped_s2 = 0

        for pred in predictions:
            # ── Stage-1 フィルタ ──────────────────────────────────
            if quarantine_count > 0:
                skipped_s1 += 1
                continue

            # ── Stage-2 フィルタ ──────────────────────────────────
            win_prob     = float(pred.get("win_prob", 0))
            place_prob   = float(pred.get("place_prob", 0))
            uncertainty  = float(pred.get("uncertainty", 1.0))
            ev           = float(pred.get("expected_return", 0))
            model_agree  = int(pred.get("model_agreement_count", 0))

            passes_s2 = (
                (win_prob >= WIN_PROB_MIN or place_prob >= PLACE_PROB_MIN)
                and uncertainty <= UNCERTAINTY_MAX
                and model_agree  >= MODEL_AGREE_MIN
                and ev           >= EV_THRESHOLD
            )
            if not passes_s2:
                skipped_s2 += 1
                continue

            # ── Kelly 計算 ────────────────────────────────────────
            odds          = float(pred.get("odds", 10.0))
            kelly_raw     = (win_prob * odds - 1) / max(odds - 1, 1)
            kelly_adj     = kelly_raw * KELLY_FRACTION_MULTIPLIER

            # ── RL Executor タイミング判断 ────────────────────────
            rl_action = "medium"
            if self.use_rl:
                rl_action = _rl_decision(
                    win_prob=win_prob,
                    odds=odds,
                    bankroll=bankroll,
                    bankroll0=bankroll,   # 初回は bankroll0 = bankroll と仮定
                    peak=bankroll,
                )
            rl_multiplier = RL_ACTION_MULTIPLIER.get(rl_action, 1.0)

            if rl_action == "pass":
                log.debug("RL pass: entry_id=%s win_prob=%.2f odds=%.1f",
                          pred.get("entry_id"), win_prob, odds)
                skipped_s2 += 1
                continue

            stake_pct    = min(kelly_adj * rl_multiplier, STAKE_CAP_PCT)
            stake_amount = int(bankroll * stake_pct / 100) * 100  # 100円単位

            # ── MarketAgent スリッページ推定 ──────────────────────────
            race_id = str(pred.get("race_id", ""))
            mkt     = market_signals.get(race_id, {}) if isinstance(market_signals, dict) else {}
            liquidity      = float(mkt.get("liquidity", 0.5))
            steam_detected = bool(mkt.get("steam_detected", False))

            slip = MarketAgent.estimate_slippage(
                stake=max(stake_amount, 100),
                odds=odds,
                liquidity=liquidity,
                steam_detected=steam_detected,
            )
            adjusted_odds = slip["expected_odds"]
            slippage_pct  = slip["slippage_pct"]

            # スリッページ後の EV が閾値を下回る場合はスキップ
            ev_after_slip = win_prob * adjusted_odds - 1
            if ev_after_slip < (EV_THRESHOLD - 1):
                log.debug(
                    "slippage skip: entry_id=%s ev_after_slip=%.4f adjusted_odds=%.2f",
                    pred.get("entry_id"), ev_after_slip, adjusted_odds,
                )
                skipped_s2 += 1
                continue

            candidate_bets.append({
                "race_id":               race_id,
                "entry_id":              str(pred.get("entry_id", "")),
                "bet_type":              "単勝",
                "odds":                  odds,
                "adjusted_odds":         adjusted_odds,
                "win_prob":              win_prob,
                "kelly_fraction":        kelly_adj,
                "stake_pct":             stake_pct,
                "stake_amount":          stake_amount,
                "slippage_pct":          slippage_pct,
                "ev_after_slippage":     round(ev_after_slip, 4),
                "liquidity":             liquidity,
                "steam_detected":        steam_detected,
                "rl_action":             rl_action,
                "rl_multiplier":         rl_multiplier,
            })

        trade_log = self._execute_or_simulate(candidate_bets, meta)

        return {
            "candidate_bets":     candidate_bets,
            "trade_log":          trade_log,
            "paper_trading":      self.paper_trading,
            "skipped_stage1":     skipped_s1,
            "skipped_stage2":     skipped_s2,
            "bankroll":           bankroll,
            "timestamp":          datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _load_bankroll(self) -> float:
        bankroll_path = DATA_DIR / "bankroll.json"
        if bankroll_path.exists():
            try:
                data = json.loads(bankroll_path.read_text(encoding="utf-8"))
                return float(data.get("bankroll", 100_000))
            except Exception:
                pass
        return 100_000.0

    def _execute_or_simulate(self, bets: list[dict], meta: AgentMeta) -> list[dict]:
        today    = datetime.now().strftime("%Y%m%d")
        log_path = DATA_DIR / f"trade_log_{today}.json"

        trade_log = []
        for bet in bets:
            entry = {
                **bet,
                "trace_id":     meta.trace_id,
                "run_tag":      meta.run_tag,
                "paper_trading": self.paper_trading,
                "status":       "simulated" if self.paper_trading else "executed",
                "timestamp":    datetime.now(timezone.utc).isoformat(),
            }
            trade_log.append(entry)

            if not self.paper_trading:
                log.info("【実発注】%s 単勝 ¥%d", bet["entry_id"], bet["stake_amount"])
            else:
                log.info("【ペーパー】%s 単勝 ¥%d (EV%.2f)",
                         bet["entry_id"], bet["stake_amount"], bet.get("odds", 0))

        # ログ保存
        existing = []
        if log_path.exists():
            try:
                existing = json.loads(log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        log_path.write_text(
            json.dumps(existing + trade_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return trade_log
