"""
backtest_agent.py — ウォークフォワード・バックテスト エージェント
================================================================
pipeline/backtest_walkforward_35.py をラップし、検証結果を
data/walkforward_result.json に保存、model_registry に記録する。

manifest: backtest-agent v1.0.0
  purpose : 時系列ウォークフォワード検証 → 汎化性能評価
  inputs  : retrain (bool, default False), test_years (list, optional)
  outputs : avg_roi, avg_hit_rate, avg_max_dd, n_positive_folds,
            verdict, result_path
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR   = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
FEAT_FILE  = BASE_DIR / "keiba_data_features.csv"
MODEL_FILE = BASE_DIR / "model_v8.pkl"
RESULT_FILE = BASE_DIR / "data" / "walkforward_result.json"
DB_URL = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")


class BacktestAgent(BaseAgent):
    """
    ウォークフォワード・バックテストを実行し、汎化性能を評価する。

    dry_run=True の場合は実際のバックテストをスキップし、
    既存の walkforward_result.json を読み込んで返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="backtest-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        retrain    = payload.get("retrain", False)
        test_years = payload.get("test_years")  # None = 自動検出（最後2年）

        # ─── 既存結果の読み込み（dry_run または skip_backtest）───
        if payload.get("skip_backtest", False):
            return self._load_existing_result()

        # ─── ファイル存在確認 ────────────────────────────────────
        if not FEAT_FILE.exists():
            raise FileNotFoundError(f"特徴量ファイルなし: {FEAT_FILE}")
        if not MODEL_FILE.exists():
            raise FileNotFoundError(f"モデルファイルなし: {MODEL_FILE}")

        # ─── バックテスト実行 ────────────────────────────────────
        log.info("ウォークフォワード・バックテスト開始 retrain=%s", retrain)
        results = self._run_walkforward(retrain=retrain, test_years=test_years)

        if not results:
            raise RuntimeError("バックテスト結果が空（データ不足の可能性）")

        # ─── サマリー算出 ────────────────────────────────────────
        avg_roi  = sum(r["roi"]      for r in results) / len(results)
        avg_hit  = sum(r["hit_rate"] for r in results) / len(results)
        avg_dd   = sum(r["max_dd"]   for r in results) / len(results)
        n_pos    = sum(1 for r in results if r["roi"] > 0)

        verdict = self._judge(avg_roi, avg_dd, n_pos, len(results))
        log.info(
            "バックテスト結果: avg_roi=%.1f%% avg_hit=%.1f%% avg_dd=%.1f%% positive=%d/%d",
            avg_roi, avg_hit, avg_dd, n_pos, len(results)
        )
        log.info("判定: %s", verdict)

        # ─── 結果ファイル保存 ────────────────────────────────────
        output = {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "trace_id":        meta.trace_id,
            "run_tag":         meta.run_tag,
            "avg_roi":         round(avg_roi, 2),
            "avg_hit_rate":    round(avg_hit, 2),
            "avg_max_dd":      round(avg_dd, 2),
            "n_positive_folds": n_pos,
            "n_total_folds":   len(results),
            "verdict":         verdict,
            "fold_results":    results,
            "retrain":         retrain,
        }
        RESULT_FILE.parent.mkdir(exist_ok=True)
        RESULT_FILE.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("結果保存: %s", RESULT_FILE)

        # ─── model_registry に性能指標を記録 ─────────────────────
        self._upsert_backtest_metrics(meta, output)

        return {
            "avg_roi":           avg_roi,
            "avg_hit_rate":      avg_hit,
            "avg_max_dd":        avg_dd,
            "n_positive_folds":  n_pos,
            "n_total_folds":     len(results),
            "verdict":           verdict,
            "result_path":       str(RESULT_FILE),
        }

    # ─────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────

    def _run_walkforward(self, retrain: bool, test_years) -> list[dict]:
        """backtest_walkforward_35 の walk_forward_backtest を直接呼び出す。"""
        try:
            script_dir = BASE_DIR / "pipeline"
            if str(script_dir) not in sys.path:
                sys.path.insert(0, str(script_dir))

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "backtest_walkforward_35",
                script_dir / "backtest_walkforward_35.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            import pickle
            import pandas as pd

            df = pd.read_csv(
                FEAT_FILE, encoding="utf-8-sig", low_memory=False, on_bad_lines="skip"
            )
            with open(MODEL_FILE, "rb") as f:
                template = pickle.load(f)

            results = mod.walk_forward_backtest(
                df, template,
                test_years=test_years,
                retrain=retrain,
            )
            return results or []

        except Exception as exc:
            log.warning("backtest_walkforward_35 直接呼び出し失敗: %s — subprocess 経由に切り替え", exc)
            return self._run_walkforward_subprocess(retrain)

    def _run_walkforward_subprocess(self, retrain: bool) -> list[dict]:
        """subprocess 経由でバックテストを実行し、結果 JSON を読み込む。"""
        script = BASE_DIR / "pipeline" / "backtest_walkforward_35.py"
        cmd    = [sys.executable, "-X", "utf8", str(script)]
        if not retrain:
            cmd.append("--fast")

        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800,
        )
        if proc.returncode != 0:
            log.warning("backtest subprocess stderr: %s", proc.stderr[-300:])

        if RESULT_FILE.exists():
            data = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
            return data.get("fold_results", [])
        return []

    def _load_existing_result(self) -> dict[str, Any]:
        """既存の walkforward_result.json を読み込んで返す（skip_backtest 用）。"""
        if not RESULT_FILE.exists():
            log.warning("walkforward_result.json が存在しません。空の結果を返します")
            return {
                "avg_roi": 0.0, "avg_hit_rate": 0.0, "avg_max_dd": 0.0,
                "n_positive_folds": 0, "n_total_folds": 0,
                "verdict": "データなし（skip_backtest=True）",
                "result_path": str(RESULT_FILE),
            }
        data = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
        log.info(
            "既存バックテスト結果読み込み: avg_roi=%.1f%% verdict=%s",
            data.get("avg_roi", 0), data.get("verdict", ""),
        )
        return {k: data[k] for k in (
            "avg_roi", "avg_hit_rate", "avg_max_dd",
            "n_positive_folds", "n_total_folds", "verdict", "result_path",
        ) if k in data}

    @staticmethod
    def _judge(avg_roi: float, avg_dd: float, n_pos: int, n_total: int) -> str:
        if avg_roi > 5 and n_pos >= n_total * 0.6 and avg_dd < 50:
            return "PASS: 汎化性能良好 — 実運用可能レベル"
        if avg_roi > 5 and avg_dd >= 50:
            return "WARN: ROI良好だが最大DD過大 — Kelly係数を引き下げ推奨"
        if avg_roi > 0:
            return "BORDERLINE: プラス収支だが安定性要確認"
        return "FAIL: 平均ROIマイナス — モデル再学習推奨"

    def _upsert_backtest_metrics(self, meta: AgentMeta, output: dict) -> None:
        """model_registry の最新モデルに backtest 結果を追記する。"""
        try:
            import psycopg2
            conn = psycopg2.connect(DB_URL)
            cur  = conn.cursor()
            cur.execute(
                """
                UPDATE model_registry
                SET    metrics = COALESCE(metrics, '{}'::jsonb) || %s::jsonb,
                       updated_at = NOW()
                WHERE  status = 'active'
                AND    purpose = 'publishing'
                ORDER  BY created_at DESC
                LIMIT  1
                """,
                (json.dumps({
                    "backtest_avg_roi":    output["avg_roi"],
                    "backtest_avg_hit":    output["avg_hit_rate"],
                    "backtest_avg_dd":     output["avg_max_dd"],
                    "backtest_verdict":    output["verdict"],
                    "backtest_timestamp":  output["timestamp"],
                }),)
            )
            conn.commit()
            conn.close()
            log.info("model_registry に backtest 結果を記録しました")
        except Exception as exc:
            log.debug("model_registry 更新スキップ: %s", exc)
