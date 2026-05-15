"""
batch_inference_agent.py — バッチ推論エージェント
=================================================
model_train_03 / predict_04 / ev_engine_10 をラップし、
inference_output_v1 スキーマ準拠の predictions を生成する。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

from .base_agent import BaseAgent, AgentMeta
from .audit_logger import sha256_of
from .path_config import BASE_DIR, DATA_DIR

try:
    import pandas as pd
except ImportError:
    pd = None

log = logging.getLogger(__name__)

# マニフェスト定数
EV_THRESHOLD  = 0.15
MIN_ODDS      = 10.0
KELLY_FRACTION = 0.10

BACKTEST_ONLY_COLUMNS = {
    "kakutei_chakujun",
    "chakujun",
    "tansho_ninkijun",
    "analysis_mode",
}


def _normalize_id(value) -> str:
    if value is None:
        return ""
    try:
        if pd is not None and pd.isna(value):
            return ""
    except TypeError:
        pass
    try:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass
    return str(value)


class BatchInferenceAgent(BaseAgent):
    """
    役割: 特徴量 → 予測（win_prob, place_prob, expected_return, uncertainty）
    対応: manifest batch-inference-agent v2.0.0
    """

    agent_id           = "batch-inference-agent"
    agent_version      = "2.0.0"
    output_schema_name = "inference_output_v1"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        today = datetime.now().strftime("%Y%m%d")
        pred_args = ["--dry-run"] if self.dry_run else []
        ev_args = ["--dry-run"] if self.dry_run else ["--date", today]

        # ── 1. 予測実行 (predict_04.py) ──────────────────────────
        pred_ok, pred_msg = self._run_script("pipeline/predict_04.py", meta, extra_args=pred_args)
        if not pred_ok:
            if "当日出馬表なし" in pred_msg or "today_entries" in pred_msg:
                log.warning("当日出馬表なし。予測なしで正常終了します: %s", pred_msg.splitlines()[0])
                return {
                    "data_snapshot_id": meta.data_snapshot_id,
                    "predictions":      [],
                    "output_hash":      sha256_of([]),
                    "timestamp":        datetime.now(timezone.utc).isoformat(),
                }
            raise RuntimeError(f"predict_04.py が失敗しました: {pred_msg}")

        # ── 2. EV 計算 (ev_engine_10.py) ─────────────────────────
        ev_ok, ev_msg = self._run_script("pipeline/ev_engine_10.py", meta, extra_args=ev_args)
        if not ev_ok:
            log.warning("ev_engine_10.py が失敗しました。EV なし予測を使用します: %s", ev_msg)

        # ── 3. 予測結果を読み込み inference_output_v1 形式に変換 ──
        predictions = self._load_predictions(today)
        output_hash = sha256_of(predictions)

        return {
            "data_snapshot_id": meta.data_snapshot_id,
            "predictions":      predictions,
            "output_hash":      output_hash,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _load_predictions(self, today: str) -> list[dict]:
        # 当日用CSVだけを inference_output_v1 形式に変換する。
        candidate_paths = [
            DATA_DIR / f"ev_today_{today}.csv",
            DATA_DIR / f"predictions_{today}.csv",
        ]
        src = next((path for path in candidate_paths if path.exists()), None)

        if src is None:
            log.warning("予測CSVが見つかりません。空リストを返します。")
            return []

        if pd is None:
            log.warning("pandas 未インストールのため %s を読み込めません", src)
            return []
        try:
            df = pd.read_csv(src, on_bad_lines="skip")
        except Exception as exc:
            log.warning("CSV 読み込みエラー %s: %s", src, exc)
            return []

        predictions = []
        col_map = {
            "race_id":         ["race_id", "race_code"],
            "entry_id":        ["entry_id", "horse_id", "horse_num", "umaban"],
            "win_prob":        ["win_prob", "win_probability", "pred_win"],
            "place_prob":      ["place_prob", "place_probability"],
            "expected_return": ["expected_return", "expected_value", "ev", "ev_score"],
            "uncertainty":     ["uncertainty", "pred_std"],
        }

        for _, row in df.iterrows():
            mode = str(row.get("analysis_mode", "")).upper()
            has_result = any(
                col in df.columns and row.get(col) not in ("", None)
                for col in BACKTEST_ONLY_COLUMNS - {"analysis_mode"}
            )
            if mode == "BACKTEST_ONLY" or has_result:
                continue

            rec: dict = {}
            for field, aliases in col_map.items():
                for alias in aliases:
                    if alias in df.columns:
                        val = row.get(alias)
                        if field in {"race_id", "entry_id"}:
                            rec[field] = _normalize_id(val)
                        else:
                            rec[field] = float(val) if isinstance(val, (int, float)) else str(val)
                        break
                if field not in rec:
                    rec[field] = 0.0 if field != "race_id" and field != "entry_id" else ""

            # EV フィルタ
            if rec.get("expected_return", 0) >= (1 + EV_THRESHOLD):
                rec["model_agreement_count"] = 2  # LGB+XGB+CB の 2/3 以上
                predictions.append(rec)

        return predictions

    def _run_script(self, rel_path: str, meta: AgentMeta, extra_args: list[str] | None = None) -> tuple[bool, str]:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(BASE_DIR)}
        cmd = [
            sys.executable, "-X", "utf8", str(BASE_DIR / rel_path),
            "--trace_id", meta.trace_id,
            "--run_tag",  meta.run_tag,
        ]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(BASE_DIR), env=env,
        )
        if result.stdout:
            log.info(result.stdout.rstrip())
        stderr_msg = result.stderr.strip()
        if result.returncode != 0 and stderr_msg:
            log.error(stderr_msg[-500:])
        message = stderr_msg or result.stdout.strip() or f"returncode={result.returncode}"
        return result.returncode == 0, message
