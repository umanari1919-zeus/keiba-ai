"""
normalizer_agent.py — データ正規化エージェント
===============================================
pipeline/feature_eng_02.py + バリデーションをラップ。
破損行の検出・quarantine_flags 生成。
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import sys

from .base_agent import BaseAgent, AgentMeta
from .audit_logger import sha256_of
from .path_config import BASE_DIR, DATA_DIR

try:
    import pandas as pd
except ImportError:
    pd = None

log = logging.getLogger(__name__)

class NormalizerAgent(BaseAgent):
    """
    役割: raw CSV → 正規化済み行 + quarantine_flags
    対応: manifest normalizer-agent v1.0.0
    """

    agent_id      = "normalizer-agent"
    agent_version = "1.0.0"

    # auto_stop 条件（マニフェスト準拠）
    MISMATCH_RATE_THRESHOLD = 0.02

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        if pd is None:
            raise RuntimeError("pandas が未インストールのため normalizer を実行できません")

        csv_path = BASE_DIR / "keiba_data.csv"

        if not csv_path.exists():
            raise FileNotFoundError(f"keiba_data.csv が見つかりません: {csv_path}")

        # ── 1. CSV 読み込み（破損行スキップ） ──────────────────────
        df_raw = pd.read_csv(csv_path, on_bad_lines="skip", low_memory=False)
        total_lines = self._count_lines(csv_path)
        skipped     = total_lines - len(df_raw)
        mismatch_rate = skipped / max(total_lines, 1)

        quarantine_flags = []
        if mismatch_rate > self.MISMATCH_RATE_THRESHOLD:
            msg = f"mismatch_rate={mismatch_rate:.4f} > {self.MISMATCH_RATE_THRESHOLD}"
            log.warning("[normalizer] %s", msg)
            quarantine_flags.append({"type": "high_mismatch_rate", "detail": msg})
            self.quarantine(meta, msg)

        # ── 2. 日付正規化 ───────────────────────────────────────────
        for col in ["kaisai_date", "race_date"]:
            if col in df_raw.columns:
                df_raw[col] = pd.to_datetime(df_raw[col], errors="coerce").dt.strftime("%Y-%m-%d")

        # ── 3. ID 一意性チェック ─────────────────────────────────────
        if "race_id" in df_raw.columns:
            dup_rate = df_raw["race_id"].duplicated().mean()
            if dup_rate > 0.30:
                msg = f"race_id 重複率={dup_rate:.2%}"
                quarantine_flags.append({"type": "high_duplicate_id", "detail": msg})
                log.warning("[normalizer] %s", msg)

        # ── 4. 正規化済み行をサマリとして返す ────────────────────────
        normalized_rows = df_raw.head(5).to_dict(orient="records")  # サンプル（全量はCSVに）
        out_path = DATA_DIR / "keiba_data_normalized.csv"
        df_raw.to_csv(out_path, index=False, encoding="utf-8-sig")

        return {
            "normalized_rows":  normalized_rows,
            "quarantine_flags": quarantine_flags,
            "total_lines":      total_lines,
            "skipped_lines":    skipped,
            "mismatch_rate":    mismatch_rate,
            "output_path":      str(out_path),
        }

    @staticmethod
    def _count_lines(path: pathlib.Path) -> int:
        count = 0
        with open(path, "rb") as f:
            for _ in f:
                count += 1
        return max(count - 1, 0)  # ヘッダー除く
