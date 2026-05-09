"""
market_agent.py — Market AI エージェント
=========================================
オッズスナップショットから市場シグナルを抽出。
  - liquidity_index: 流動性スコア（プール推定）
  - steam_detected:  急激なオッズ下落（プロ資金流入）
  - drift_detected:  緩やかなオッズ上昇（一般人気離散）
  - slippage_model:  ベット額 × 流動性 → 実効スリッページ推定

manifest: market_ai
  purpose: 流動性予測/スリッページ推定/投票者行動解析
  inputs:  odds_time_series, board_volume, top_bettor_flow
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
from datetime import datetime, timezone

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR = BASE_DIR / "data"

# 閾値定数（manifest auto_stop_conditions に連動）
STEAM_DROP_PCT   = 0.15   # 15% 以上のオッズ下落 → STEAM
DRIFT_RISE_PCT   = 0.20   # 20% 以上のオッズ上昇 → DRIFT
MIN_POOL_EST     = 1_000_000  # 最低プール規模（円）


class MarketAgent(BaseAgent):
    """
    役割: オッズスナップショット → 市場シグナル + スリッページ推定
    対応: manifest market_ai
    """

    agent_id      = "market-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        today      = datetime.now().strftime("%Y%m%d")
        snap_path  = DATA_DIR / f"odds_snapshot_{today}.json"

        # スナップショット読み込み（当日 or 最新）
        snapshots = self._load_snapshots(snap_path)

        market_signals = {}
        for race_id, entries in snapshots.items():
            signals = self._analyze_race(race_id, entries)
            market_signals[race_id] = signals

        # 全体の流動性インデックス
        liquidity_index = self._global_liquidity(market_signals)

        return {
            "market_signals":  market_signals,
            "liquidity_index": liquidity_index,
            "snapshot_date":   today,
            "races_analyzed":  len(market_signals),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _load_snapshots(self, path: pathlib.Path) -> dict:
        """odds_snapshot_YYYYMMDD.json を読み込む。"""
        if not path.exists():
            # 最新スナップショットを探す
            snaps = sorted(DATA_DIR.glob("odds_snapshot_*.json"), reverse=True)
            if not snaps:
                log.warning("オッズスナップショットが見つかりません。空辞書を返します。")
                return {}
            path = snaps[0]
            log.info("最新スナップショット使用: %s", path.name)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # 形式: {"race_id": [{"horse_id": ..., "odds": ..., "time": ...}, ...]}
            # または odds_scraper_36.py の出力形式に応じて調整
            if isinstance(data, list):
                # リスト形式: [{race_id, entries:[{horse_num, odds}]}]
                return {item.get("race_id", str(i)): item.get("entries", [])
                        for i, item in enumerate(data)}
            return data
        except Exception as exc:
            log.warning("スナップショット読み込みエラー: %s", exc)
            return {}

    def _analyze_race(self, race_id: str, entries: list[dict]) -> dict:
        """1レース分のエントリーリストから市場シグナルを抽出。"""
        if not entries:
            return self._empty_signal()

        # オッズのリストを取得（時系列 or 単一スナップ）
        odds_list = []
        for entry in entries:
            o = entry.get("odds") or entry.get("tansho_odds")
            if o:
                try:
                    odds_list.append(float(o) / (10 if float(o) > 100 else 1))
                except (TypeError, ValueError):
                    pass

        if not odds_list:
            return self._empty_signal()

        # プール推定（単純推定: Σ(1/odds) ≈ take_rate, pool ≈ bet_total）
        inv_sum   = sum(1.0 / max(o, 0.1) for o in odds_list)
        pool_est  = inv_sum * 100_000  # 粗推定

        # 統計指標
        mean_odds = sum(odds_list) / len(odds_list)
        std_odds  = math.sqrt(sum((o - mean_odds) ** 2 for o in odds_list) / max(len(odds_list), 1))
        min_odds  = min(odds_list)
        max_odds  = max(odds_list)

        # STEAM/DRIFT 検出（時系列が複数ある場合のみ有効）
        steam_detected = False
        drift_detected = False
        if len(entries) >= 2 and "odds_history" in entries[0]:
            first_odds = entries[0]["odds_history"][0]
            last_odds  = entries[0]["odds_history"][-1]
            change_pct = (last_odds - first_odds) / max(first_odds, 0.1)
            steam_detected = change_pct < -STEAM_DROP_PCT
            drift_detected = change_pct > DRIFT_RISE_PCT

        # 流動性インデックス (0〜1)
        liquidity = min(1.0, pool_est / 10_000_000)

        return {
            "race_id":        race_id,
            "pool_est":       round(pool_est),
            "liquidity":      round(liquidity, 4),
            "mean_odds":      round(mean_odds, 2),
            "odds_std":       round(std_odds, 2),
            "min_odds":       round(min_odds, 2),
            "max_odds":       round(max_odds, 2),
            "steam_detected": steam_detected,
            "drift_detected": drift_detected,
            "entry_count":    len(entries),
        }

    @staticmethod
    def _empty_signal() -> dict:
        return {
            "pool_est": 0, "liquidity": 0.5,
            "mean_odds": 0, "odds_std": 0,
            "steam_detected": False, "drift_detected": False,
            "entry_count": 0,
        }

    @staticmethod
    def _global_liquidity(signals: dict) -> float:
        """全レースの平均流動性インデックス。"""
        if not signals:
            return 0.5
        vals = [v["liquidity"] for v in signals.values() if isinstance(v, dict)]
        return round(sum(vals) / max(len(vals), 1), 4)

    # ------------------------------------------------------------------ #
    # 公開ユーティリティ
    # ------------------------------------------------------------------ #

    @staticmethod
    def estimate_slippage(
        stake: int,
        odds: float,
        liquidity: float,
        steam_detected: bool = False,
    ) -> dict:
        """
        ベット額・オッズ・流動性からスリッページを推定する。

        Parameters
        ----------
        stake          : ベット額（円）
        odds           : 現在オッズ
        liquidity      : 流動性インデックス (0〜1)
        steam_detected : STEAM シグナルあり (True → スリッページ増大)

        Returns
        -------
        dict: {slippage_pct, expected_odds, confidence}
        """
        # プール推定
        pool_est = max(liquidity * 10_000_000, MIN_POOL_EST)

        # 市場インパクト = stake / pool の平方根モデル（Kyle's lambda）
        impact_base = math.sqrt(stake / pool_est)

        # STEAM 時はスリッページ 1.5 倍
        impact = impact_base * (1.5 if steam_detected else 1.0)

        # オッズへの影響（オッズ低いほど影響大）
        slippage_pct   = impact * 0.3 / max(math.log(odds + 1), 0.1)
        expected_odds  = max(1.01, odds * (1 - slippage_pct))
        confidence     = max(0.5, min(0.95, liquidity))

        return {
            "slippage_pct":  round(slippage_pct, 6),
            "expected_odds": round(expected_odds, 2),
            "confidence":    round(confidence, 3),
        }
