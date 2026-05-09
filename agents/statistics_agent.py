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
import pickle
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

FEAT_FILE   = BASE_DIR / "keiba_data_features.csv"
MODEL_FILE  = BASE_DIR / "model_v8.pkl"
RESULT_FILE = DATA_DIR / "statistics_summary.json"
DEFAULT_MAX_ROWS = int(os.getenv("KEIBA_STATISTICS_MAX_ROWS", "50000"))
LEAKY_FEATURE_TOKENS = ("odds", "ninki", "popular")


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

        features = self._load_model_features(df)
        if not features:
            log.warning("統計分析対象の特徴量なし")
            return self._empty_result("features unavailable")

        work_df = df
        if DEFAULT_MAX_ROWS > 0 and len(work_df) > DEFAULT_MAX_ROWS:
            work_df = work_df.sample(n=DEFAULT_MAX_ROWS, random_state=42).reset_index(drop=True)
            log.info("統計分析サンプル適用: %d/%d 行", len(work_df), len(df))

        result: dict[str, Any] = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "trace_id":   meta.trace_id,
            "year":       year,
        }

        # ① ベイズ特徴選択
        selected_features: list[str] = []
        try:
            trial_count = int(payload.get("feature_trials", 10))
            feature_subset = features[: min(len(features), int(payload.get("feature_selection_max_features", 40)))]
            sel = mod.bayesian_feature_selection(work_df, feature_subset, n_trials=trial_count)
            selected_features = list(sel) if sel is not None else []
            log.info("ベイズ特徴選択: %d 特徴量選択", len(selected_features))
        except Exception as exc:
            log.warning("bayesian_feature_selection 失敗: %s", exc)
        result["selected_features"] = selected_features

        # ② PCA 分析
        pca_variance_ratio: list[float] = []
        try:
            pca_res = mod.run_pca_analysis(work_df, features, n_components=10)
            if pca_res is not None:
                if hasattr(pca_res, "explained_variance_ratio_"):
                    pca_variance_ratio = pca_res.explained_variance_ratio_.tolist()
                elif hasattr(pca_res, "attrs") and pca_res.attrs.get("explained_variance_ratio"):
                    pca_variance_ratio = [float(v) for v in pca_res.attrs["explained_variance_ratio"]]
                elif isinstance(pca_res, (list, tuple)):
                    pca_variance_ratio = [float(v) for v in pca_res]
            log.info("PCA: 第1主成分寄与率=%.3f", pca_variance_ratio[0] if pca_variance_ratio else 0)
        except Exception as exc:
            log.warning("run_pca_analysis 失敗: %s", exc)
        result["pca_variance_ratio"] = pca_variance_ratio

        # ③ 馬タイプクラスタリング
        cluster_summary: dict = {}
        try:
            clusters = mod.horse_type_clustering(work_df.copy(), n_clusters=n_clusters)
            if clusters is not None:
                if hasattr(clusters, "labels_"):
                    import collections
                    counts = collections.Counter(clusters.labels_.tolist())
                    cluster_summary = {f"cluster_{k}": v for k, v in counts.items()}
                elif isinstance(clusters, dict):
                    cluster_summary = clusters
                elif hasattr(clusters, "columns") and "horse_cluster" in clusters.columns:
                    counts = clusters["horse_cluster"].value_counts().sort_index()
                    cluster_summary = {f"cluster_{int(k)}": int(v) for k, v in counts.items()}
            log.info("クラスタリング完了: %d クラスタ", len(cluster_summary))
        except Exception as exc:
            log.warning("horse_type_clustering 失敗: %s", exc)
        result["cluster_summary"] = cluster_summary

        # ④ 生存時間分析（ピーク年齢推定）
        peak_age_estimate: float = 0.0
        try:
            peak = mod.survival_analysis_peak(work_df.copy())
            if hasattr(peak, "attrs") and peak.attrs.get("peak_age") is not None:
                peak_age_estimate = float(peak.attrs["peak_age"])
            elif hasattr(peak, "columns") and {"barei", "is_peak_age"}.issubset(set(peak.columns)):
                peak_rows = peak[peak["is_peak_age"] == 1]
                if not peak_rows.empty:
                    peak_age_estimate = float(peak_rows["barei"].mode().iloc[0])
            elif peak is not None:
                peak_age_estimate = float(peak)
            log.info("ピーク年齢推定: %.1f 歳", peak_age_estimate)
        except Exception as exc:
            log.warning("survival_analysis_peak 失敗: %s", exc)
        result["peak_age_estimate"] = peak_age_estimate

        # ⑤ モンテカルロ資金破産確率
        mc_ruin_probability: float = 0.0
        try:
            ruin = mod.monte_carlo_risk_analysis(n_simulations=mc_sims)
            if isinstance(ruin, dict):
                mc_ruin_probability = float(ruin.get("ruin_rate", 0.0))
                result["mc_summary"] = ruin
            elif ruin is not None:
                mc_ruin_probability = float(ruin)
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

    def _load_model_features(self, df) -> list[str]:
        if MODEL_FILE.exists():
            try:
                with MODEL_FILE.open("rb") as f:
                    saved = pickle.load(f)
                features = saved.get("features", [])
                if features:
                    return [
                        str(f) for f in features
                        if f in df.columns and not self._is_leaky_feature(str(f))
                    ]
            except Exception as exc:
                log.warning("モデル特徴量読み込み失敗: %s", exc)

        numeric_cols = []
        for col in df.columns:
            name = str(col)
            if name in {"kakutei_chakujun", "race_code"} or self._is_leaky_feature(name):
                continue
            try:
                if str(df[col].dtype).startswith(("int", "float", "bool")):
                    numeric_cols.append(name)
            except Exception:
                continue
        return numeric_cols[:200]

    @staticmethod
    def _is_leaky_feature(name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in LEAKY_FEATURE_TOKENS)
