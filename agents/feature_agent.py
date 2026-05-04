"""
feature_agent.py — 特徴量生成エージェント
=========================================
pipeline/ の各特徴量スクリプトを順次実行し、
feature_vector_manifest を生成する。
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import sys
import uuid

from .base_agent import BaseAgent, AgentMeta
from .audit_logger import sha256_of

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR = BASE_DIR / "data"

# 実行するスクリプトと説明（順序保証）
FEATURE_SCRIPTS: list[tuple[str, str]] = [
    ("pipeline/feature_eng_02.py",             "基本特徴量"),
    ("pipeline/feature_advanced_19.py",        "高度特徴量（ペース・展開）"),
    ("pipeline/pace_training_analysis_20.py",  "ペース・調教タイム分析"),
    ("pipeline/training_analysis_37.py",       "調教分析（速度Zスコア）"),
    ("pipeline/trainer_analysis_38.py",        "調教師特性"),
    ("pipeline/debut_analysis_39.py",          "新馬戦強化"),
    ("pipeline/shogai_analysis_40.py",         "障害戦強化"),
    ("pipeline/pedigree_analysis_17.py",       "血統分析（5代）"),
    ("pipeline/jockey_trainer_analysis_21.py", "騎手・調教師分析"),
    ("pipeline/pedigree_merge_42.py",          "血統指標 CSV マージ"),
]


class FeatureAgent(BaseAgent):
    """
    役割: 正規化データ → 特徴量セット（97+列）
    対応: manifest feature-agent v1.0.0
    """

    agent_id      = "feature-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        feature_set_id = f"fset_{meta.data_snapshot_id or uuid.uuid4().hex[:8]}"
        results        = {}

        for script_rel, desc in FEATURE_SCRIPTS:
            script_path = BASE_DIR / script_rel
            if not script_path.exists():
                log.warning("特徴量スクリプト未実装: %s (%s)", script_rel, desc)
                results[script_rel] = "missing"
                continue

            ok = self._run_script(script_rel, meta)
            results[script_rel] = "ok" if ok else "error"
            log.info("  %-45s → %s", desc, results[script_rel])

        # keiba_data_features.csv の SHA-256
        feat_csv = BASE_DIR / "keiba_data_features.csv"
        feature_manifest = {
            "feature_set_id":  feature_set_id,
            "scripts_run":     results,
            "output_csv":      str(feat_csv),
            "output_sha256":   sha256_of(str(feat_csv.stat().st_size) if feat_csv.exists() else ""),
            "feature_registry": "fset_master",
        }

        return {
            "feature_set_id":     feature_set_id,
            "feature_manifest":   feature_manifest,
            "training_snapshot_id": meta.data_snapshot_id,
        }

    def _run_script(self, rel_path: str, meta: AgentMeta) -> bool:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(BASE_DIR)}
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(BASE_DIR / rel_path),
             "--trace_id", meta.trace_id,
             "--run_tag",  meta.run_tag],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(BASE_DIR), env=env,
        )
        if result.stdout:
            log.debug(result.stdout.rstrip())
        if result.returncode != 0 and result.stderr:
            log.error(result.stderr[-500:])
        return result.returncode == 0
