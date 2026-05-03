"""
backtest_engine_agent.py — EV×Kelly グリッドサーチ エージェント
=============================================================
pipeline/backtest_engine_32.py をラップし、
EV閾値×ケリー係数の全組み合わせをバックテストして
最適パラメータを求める。週次 DAG の backtest 後に実行。

manifest: backtest-engine-agent v1.0.0
  purpose : EV×Kelly グリッドサーチ → 最適パラメータ提案
  inputs  : year (int, optional), ev_thresholds (list), kelly_fractions (list)
  outputs : best_ev_threshold, best_kelly_fraction, best_roi,
            grid_results (list), result_path (str)
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
FEAT_FILE   = BASE_DIR / "keiba_data_features.csv"
RESULT_FILE = BASE_DIR / "data" / "backtest_summary.json"


class BacktestEngineAgent(BaseAgent):
    """
    EV閾値×ケリー係数のグリッドサーチで最高ROIの組み合わせを探索する。
    結果は data/backtest_summary.json に保存し、
    EV_THRESHOLD / KELLY_FRACTION の調整提案を出力する。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="backtest-engine-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        year            = payload.get("year") or datetime.now().year
        ev_thresholds   = payload.get("ev_thresholds")
        kelly_fractions = payload.get("kelly_fractions")

        mod = self._load_module()
        if mod is None:
            return self._load_existing()

        if not FEAT_FILE.exists():
            log.warning("特徴量ファイルなし → 既存結果を返します")
            return self._load_existing()

        try:
            import pandas as pd
            df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                             on_bad_lines="skip")
            df_year = df[df.get("kaisai_nen", df.get("year", 0)) == year] if len(df) > 0 else df

            log.info("グリッドサーチ開始 year=%d rows=%d", year, len(df_year))
            grid = mod.optimize_params(
                df_year,
                ev_thresholds=ev_thresholds,
                kelly_fractions=kelly_fractions,
            )

            if grid.empty:
                log.warning("グリッドサーチ結果が空")
                return self._load_existing()

            best = grid.iloc[0].to_dict()
            best_ev  = float(best.get("ev_threshold",   0.15))
            best_kf  = float(best.get("kelly_fraction", 0.10))
            best_roi = float(best.get("roi",            0.0))

            log.info(
                "グリッドサーチ完了: best_ev=%.2f best_kf=%.2f best_roi=%.1f%%",
                best_ev, best_kf, best_roi * 100,
            )

            # 現在の定数との乖離チェック
            current_ev = 0.15
            current_kf = 0.10
            if abs(best_ev - current_ev) > 0.05 or abs(best_kf - current_kf) > 0.05:
                log.warning(
                    "パラメータ調整推奨: EV %.2f→%.2f / Kelly %.2f→%.2f",
                    current_ev, best_ev, current_kf, best_kf,
                )

            output = {
                "timestamp":           datetime.now(timezone.utc).isoformat(),
                "trace_id":            meta.trace_id,
                "year":                year,
                "best_ev_threshold":   best_ev,
                "best_kelly_fraction": best_kf,
                "best_roi":            best_roi,
                "grid_results":        grid.head(20).to_dict(orient="records"),
            }
            RESULT_FILE.parent.mkdir(exist_ok=True)
            RESULT_FILE.write_text(
                json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            return {
                "best_ev_threshold":   best_ev,
                "best_kelly_fraction": best_kf,
                "best_roi":            best_roi,
                "grid_results":        output["grid_results"],
                "result_path":         str(RESULT_FILE),
            }

        except Exception as exc:
            log.warning("グリッドサーチ失敗: %s", exc)
            return self._load_existing()

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "backtest_engine_32.py"
        if not script.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("backtest_engine_32", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("backtest_engine_32 ロード失敗: %s", exc)
            return None

    def _load_existing(self) -> dict[str, Any]:
        if RESULT_FILE.exists():
            try:
                data = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
                return {
                    "best_ev_threshold":   data.get("best_ev_threshold",   0.15),
                    "best_kelly_fraction": data.get("best_kelly_fraction", 0.10),
                    "best_roi":            data.get("best_roi",            0.0),
                    "grid_results":        data.get("grid_results",        []),
                    "result_path":         str(RESULT_FILE),
                }
            except Exception:
                pass
        return {
            "best_ev_threshold":   0.15,
            "best_kelly_fraction": 0.10,
            "best_roi":            0.0,
            "grid_results":        [],
            "result_path":         str(RESULT_FILE),
        }
