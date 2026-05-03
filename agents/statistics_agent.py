"""
statistics_agent.py — 統計分析エージェント
==========================================
pipeline/statistical_tools_23.py をラップし、
ベイズ特徴選択・PCA・馬クラスタリング・
生存時間分析・モンテカルロリスク解析を実行する。

manifest: statistics-agent v1.0.0
  purpose : 多角的統計分析 → 特徴量品質・リスク評価
  inputs  : year (int, optional), n_clusters (int), mc_simulations (int)
  outputs : selected_features, pca_variance_ratio, cluster_summary,
            peak_age_estimate, mc_ruin_probability, result_path
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
RESULT_FILE = BASE_DIR / "data" / "statistics_summary.json"


class StatisticsAgent(BaseAgent):
    """
    statistical_tools_23.py の各分析関数を順次実行し、
    統計サマリーを data/statistics_summary.json に保存する。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="statistics-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        year          = payload.get("year") or datetime.now().year
        n_clusters    = int(payload.get("n_clusters",    5))
        mc_sims       = int(payload.get("mc_simulations", 1000))

        mod = self._load_module()
        if mod is None:
            return self._empty_result("statistical_tools_23 未実装")

        if not FEAT_FILE.exists():
            log.warning("特徴量ファイルなし → 統計分析スキップ")
            return self._empty_result("keiba_data_features.csv 未存在")

        try:
            import pandas as pd
            df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                             on_bad_lines="skip")
        except Exception as exc:
            log.warning("CSV 読み込み失敗: %s", exc)
            return self._empty_result(str(exc))

        result: dict[str, Any] = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "trace_id":   meta.trace_id,
            "year":       year,
        }

        # ① ベイズ特徴選択
        selected_features: list[str] = []
        try:
            sel = mod.bayesian_feature_selection(df)
            selected_features = list(sel) if sel is not None else []
            log.info("ベイズ特徴選択: %d 特徴量選択", len(selected_features))
        except Exception as exc:
            log.warning("bayesian_feature_selection 失敗: %s", exc)
        result["selected_features"] = selected_features

        # ② PCA 分析
        pca_variance_ratio: list[float] = []
        try:
            pca_res = mod.run_pca_analysis(df, n_components=10)
            if pca_res is not None:
                if hasattr(pca_res, "explained_variance_ratio_"):
                    pca_variance_ratio = pca_res.explained_variance_ratio_.tolist()
                elif isinstance(pca_res, (list, tuple)):
                    pca_variance_ratio = [float(v) for v in pca_res]
            log.info("PCA: 第1主成分寄与率=%.3f", pca_variance_ratio[0] if pca_variance_ratio else 0)
        except Exception as exc:
            log.warning("run_pca_analysis 失敗: %s", exc)
        result["pca_variance_ratio"] = pca_variance_ratio

        # ③ 馬タイプクラスタリング
        cluster_summary: dict = {}
        try:
            clusters = mod.horse_type_clustering(df, n_clusters=n_clusters)
            if clusters is not None:
                if hasattr(clusters, "labels_"):
                    import collections
                    counts = collections.Counter(clusters.labels_.tolist())
                    cluster_summary = {f"cluster_{k}": v for k, v in counts.items()}
                elif isinstance(clusters, dict):
                    cluster_summary = clusters
            log.info("クラスタリング完了: %d クラスタ", len(cluster_summary))
        except Exception as exc:
            log.warning("horse_type_clustering 失敗: %s", exc)
        result["cluster_summary"] = cluster_summary

        # ④ 生存時間分析（ピーク年齢推定）
        peak_age_estimate: float = 0.0
        try:
            peak = mod.survival_analysis_peak(df)
            peak_age_estimate = float(peak) if peak is not None else 0.0
            log.info("ピーク年齢推定: %.1f 歳", peak_age_estimate)
        except Exception as exc:
            log.warning("survival_analysis_peak 失敗: %s", exc)
        result["peak_age_estimate"] = peak_age_estimate

        # ⑤ モンテカルロ資金破産確率
        mc_ruin_probability: float = 0.0
        try:
            ruin = mod.monte_carlo_risk_analysis(df, n_simulations=mc_sims)
            mc_ruin_probability = float(ruin) if ruin is not None else 0.0
            log.info("モンテカルロ破産確率: %.3f", mc_ruin_probability)
        except Exception as exc:
            log.warning("monte_carlo_risk_analysis 失敗: %s", exc)
        result["mc_ruin_probability"] = mc_ruin_probability

        RESULT_FILE.parent.mkdir(exist_ok=True)
        RESULT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "selected_features":    selected_features,
            "pca_variance_ratio":   pca_variance_ratio,
            "cluster_summary":      cluster_summary,
            "peak_age_estimate":    peak_age_estimate,
            "mc_ruin_probability":  mc_ruin_probability,
            "result_path":          str(RESULT_FILE),
        }

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "statistical_tools_23.py"
        if not script.exists():
            log.warning("statistical_tools_23.py が存在しません")
            return None
        try:
            spec = importlib.util.spec_from_file_location("statistical_tools_23", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("statistical_tools_23 ロード失敗: %s", exc)
            return None

    def _empty_result(self, reason: str) -> dict[str, Any]:
        log.info("StatisticsAgent スキップ: %s", reason)
        return {
            "selected_features":   [],
            "pca_variance_ratio":  [],
            "cluster_summary":     {},
            "peak_age_estimate":   0.0,
            "mc_ruin_probability": 0.0,
            "result_path":         str(RESULT_FILE),
            "skipped_reason":      reason,
        }
