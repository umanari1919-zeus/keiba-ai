"""
leak_audit.py — バックテストリーク検出ツール　(P0-#1)
=========================================================================

「WF検証で ROI +841%」の正体を暴くためのツール。
以下の3種類のリークを検出する:

1. 未来データ漏洩 (temporal leak)
   「race_id の発走時刻以降のデータ」を特徴量計算で使っていないかをチェック。

2. オッズリーク (odds leak)
   「最終確定オッズ（レース結果後を含む）」を使っていないかをチェック。

3. 生存バイアス (survivor bias)
   「NaN ドロップされたレコード」と「残存レコード」で勝率に長げれだしがないかをチェック。

Usage:
    python tools/leak_audit.py --temporal --sample 100
    python tools/leak_audit.py --odds
    python tools/leak_audit.py --survivor
    python tools/leak_audit.py --all
」
ステータス: 初期スケルトン。全誫実装は W1 タスクとして、monkey-patchトレース閨部を追加していく。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline.native_runtime import ensure_native_runtime

FEATURES_CSV = BASE_DIR / "keiba_data_features.csv"
DATA_CSV = BASE_DIR / "keiba_data.csv"

SUSPICIOUS_RESULT_AGGREGATE_FEATURES = {
    "sogo_1chaku",
    "sogo_2chaku",
    "sogo_3chaku",
    "sogo_total",
    "sogo_win_rate",
    "shiba_ryo_1chaku",
    "shiba_ryo_2chaku",
    "shiba_ryo_3chaku",
    "dirt_ryo_1chaku",
    "dirt_ryo_2chaku",
    "dirt_ryo_3chaku",
    "shiba_short_1chaku",
    "shiba_middle_1chaku",
    "shiba_long_1chaku",
    "dirt_short_1chaku",
    "dirt_middle_1chaku",
    "dirt_long_1chaku",
    "shiba_win_rate",
    "dirt_win_rate",
    "short_win_rate",
    "middle_win_rate",
    "long_win_rate",
}


def _load_features(nrows: Optional[int] = None) -> pd.DataFrame:
    """特徴量CSVを読む。339766行目が破損しているため on_bad_lines='skip'。"""
    return pd.read_csv(FEATURES_CSV, nrows=nrows, on_bad_lines="skip", low_memory=False)


def audit_odds_leak(df: pd.DataFrame) -> dict:
    """オッズ関連の特徴量がモデルに使われていないことを検証。

    `pipeline/config.py` に LEAKY_DERIVED_FEATURE_COLUMNS があるはずなので、
    それと model_v8.pkl の features リストを照合し、オッズや人気が含まれていないかチェック。
    """
    model_path = BASE_DIR / "model_v8.pkl"
    if not model_path.exists():
        return {"status": "skipped", "reason": "model_v8.pkl not found"}

    ensure_native_runtime()
    import pickle

    with open(model_path, "rb") as f:
        model_data = pickle.load(f)

    features = model_data.get("features", [])
    leaky_keywords = ["odds", "ninki", "tansho", "fukusho", "popularity"]
    suspicious = [f for f in features if any(kw in f.lower() for kw in leaky_keywords)]
    result_aggregates = [f for f in features if f in SUSPICIOUS_RESULT_AGGREGATE_FEATURES]

    return {
        "status": "checked",
        "n_features": len(features),
        "suspicious_count": len(suspicious),
        "suspicious_features": suspicious,
        "result_aggregate_count": len(result_aggregates),
        "result_aggregate_features": result_aggregates,
        "verdict": "LEAK" if suspicious else ("SUSPICIOUS_RETRAIN_REQUIRED" if result_aggregates else "SHALLOW_OK"),
        "warning": (
            "このチェックは特徴量名のキーワード grep のみ。"
            "`last_finishing_position` のような潜在リークは検出しません。"
            " result_aggregate_features は現在時点通算成績の可能性があるため、"
            "次回学習で除外して再学習してください。"
            "本格検証には特徴量計算コードを手動レビューしてください。"
        ),
    }


def audit_survivor_bias(df: pd.DataFrame) -> dict:
    """生存バイアス検証。列単位で NaN ローと非 NaN ローの勝率差を見る。

    code-reviewer 指摘: 161特徴量モデルだと df.isna().any(axis=1) ではほぼ全行 True になるため、
    「完全レコード vs NaN ありレコード」の二分法は使えない。列ごとに見るように修正。
    """
    if "kakutei_chakujun" not in df.columns and "chakujun" not in df.columns:
        return {"status": "skipped", "reason": "no chakujun column"}

    chakujun_col = "kakutei_chakujun" if "kakutei_chakujun" in df.columns else "chakujun"
    df = df.copy()
    df["_is_winner"] = (
        pd.to_numeric(df[chakujun_col], errors="coerce") == 1
    ).astype(int)
    overall_win_rate = float(df["_is_winner"].mean())

    suspicious_cols = []
    for col in df.columns:
        if col in ("_is_winner", chakujun_col):
            continue
        nan_mask = df[col].isna()
        n_nan = int(nan_mask.sum())
        if n_nan < 50 or n_nan > len(df) - 50:
            continue  # サンプル不足はスキップ
        wr_with = float(df.loc[~nan_mask, "_is_winner"].mean())
        wr_without = float(df.loc[nan_mask, "_is_winner"].mean())
        diff = wr_with - wr_without
        if abs(diff) > 0.05:  # 5pp 以上の差は警告
            suspicious_cols.append({
                "col": col, "nan_rate": round(n_nan / len(df), 4),
                "win_rate_with": round(wr_with, 4),
                "win_rate_without": round(wr_without, 4),
                "diff": round(diff, 4),
            })

    suspicious_cols.sort(key=lambda x: abs(x["diff"]), reverse=True)
    verdict = "BIAS_SUSPECTED" if suspicious_cols else "OK"
    return {
        "status": "checked",
        "n_total": int(len(df)),
        "overall_win_rate": round(overall_win_rate, 4),
        "suspicious_columns": suspicious_cols[:10],
        "n_suspicious_columns": len(suspicious_cols),
        "verdict": verdict,
    }


def audit_temporal_leak_skeleton(sample_n: int = 10) -> dict:
    """未来データ漏洩検証のスケルトン。

    本格的な実装には pandas.read_sql と read_csv を monkey-patch して、
    読み込まれたデータの race_date が 「ターゲット race_id の発走日」
    より後だったら警告を出す仕組みが必要。

    現状はスケルトンのみを返す。
    """
    return {
        "status": "skeleton",
        "verdict": "NOT_IMPLEMENTED",
        "message": (
            "未実装。本格的な temporal leak 検出には pandas read_sql / read_csv の "
            "monkey-patch と、トーケン化された race_id の発走時刻を現在コンテキストとして "
            "スタックに保持し、参照されたデータの race_date と比較する仕組みが必要。"
        ),
        "sample_n": sample_n,
        "next_action": "W1 タスクとしてフル実装する。docs/roadmap_2026.md の P0-#1 参照。",
    }


def main():
    parser = argparse.ArgumentParser(description="バックテストリーク監査ツール")
    parser.add_argument("--temporal", action="store_true", help="未来データ漏洩検証（スケルトン）")
    parser.add_argument("--odds", action="store_true", help="オッズリーク検証")
    parser.add_argument("--survivor", action="store_true", help="生存バイアス検証")
    parser.add_argument("--all", action="store_true", help="全て実行")
    parser.add_argument("--sample", type=int, default=10000, help="サンプル行数")
    args = parser.parse_args()

    if not (args.temporal or args.odds or args.survivor or args.all):
        parser.print_help()
        return

    print("=" * 70)
    print("バックテストリーク監査スタート")
    print("=" * 70)

    if args.odds or args.all:
        print("\n[1] オッズリーク検証 (model_v8.pkl の特徴量リストチェック)")
        print("-" * 70)
        result = audit_odds_leak(pd.DataFrame())
        for k, v in result.items():
            if isinstance(v, list) and len(v) > 5:
                print(f"  {k}: {v[:5]} ... ({len(v)} 件)")
            else:
                print(f"  {k}: {v}")

    if args.survivor or args.all:
        print("\n[2] 生存バイアス検証 (特徴量 CSV を読み込み)")
        print("-" * 70)
        if FEATURES_CSV.exists():
            df = _load_features(nrows=args.sample)
            result = audit_survivor_bias(df)
            for k, v in result.items():
                print(f"  {k}: {v}")
        else:
            print(f"  SKIP: {FEATURES_CSV} が見つかりません")

    if args.temporal or args.all:
        print("\n[3] 未来データ漏洩検証（スケルトン・本格実装は W1 タスク）")
        print("-" * 70)
        result = audit_temporal_leak_skeleton(sample_n=args.sample)
        for k, v in result.items():
            print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("完了。詳細は docs/roadmap_2026.md の P0-#1 を参照。")
    print("=" * 70)


if __name__ == "__main__":
    main()
