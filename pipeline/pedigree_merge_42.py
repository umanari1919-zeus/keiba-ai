"""
pedigree_merge_42.py — 血統指標を keiba_data_features.csv にマージ
=====================================================================
pedigree_metrics テーブルの値を特徴量 CSV に結合し、
モデル精度向上に活用する列を追加する。

追加列:
  inbreeding_coeff   — Wright 近親係数 (0〜1)
  outcross_index     — アウトクロス度 (0〜1)
  true_nicks_score   — ニックススコア
  nick_sample_size   — ニックスサンプル数

実行方法:
  python pipeline/pedigree_merge_42.py
  python pipeline/pedigree_merge_42.py --dry-run   # CSV を上書きせず確認のみ
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BASE_DIR  = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
FEAT_CSV  = BASE_DIR / "keiba_data_features.csv"
DB_URL    = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")

# pedigree_metrics から取得する列
PEDIGREE_COLS = [
    "horse_id",
    "inbreeding_coeff",
    "outcross_index",
    "true_nicks_score",
    "nick_sample_size",
    "dosage_index",
    "center_of_distribution",
]


def load_pedigree_metrics() -> pd.DataFrame:
    """pedigree_metrics テーブルを DataFrame で返す。"""
    try:
        import psycopg2
    except ImportError:
        log.warning("psycopg2 未インストール。空のDataFrameを返します。")
        return pd.DataFrame(columns=PEDIGREE_COLS)

    sql = f"SELECT {', '.join(PEDIGREE_COLS)} FROM pedigree_metrics"
    try:
        conn = psycopg2.connect(DB_URL)
        df   = pd.read_sql(sql, conn)
        conn.close()
        log.info("pedigree_metrics: %d 行読み込み", len(df))
        return df
    except Exception as exc:
        log.warning("pedigree_metrics 読み込みエラー: %s", exc)
        return pd.DataFrame(columns=PEDIGREE_COLS)


def merge_pedigree_to_features(dry_run: bool = False) -> dict:
    """
    keiba_data_features.csv に pedigree_metrics を結合する。

    Returns
    -------
    dict: {"rows_before": N, "rows_after": M, "new_cols": [...], "matched": K}
    """
    if not FEAT_CSV.exists():
        log.error("keiba_data_features.csv が見つかりません: %s", FEAT_CSV)
        return {"error": "features csv not found"}

    # 特徴量 CSV 読み込み
    log.info("特徴量 CSV 読み込み中: %s", FEAT_CSV)
    df = pd.read_csv(FEAT_CSV, on_bad_lines="skip", low_memory=False)
    rows_before = len(df)
    log.info("  行数: %d", rows_before)

    # 既に pedigree 列があれば削除（再マージのため）
    drop_cols = [c for c in PEDIGREE_COLS if c != "horse_id" and c in df.columns]
    if drop_cols:
        log.info("  既存 pedigree 列を削除: %s", drop_cols)
        df = df.drop(columns=drop_cols)

    # pedigree_metrics 読み込み
    pm = load_pedigree_metrics()
    if pm.empty:
        log.warning("pedigree_metrics が空のため、マージをスキップします。")
        return {"rows_before": rows_before, "matched": 0, "new_cols": []}

    # 結合キーを探す（ketto_toroku_bango または horse_id）
    join_key_feat = next(
        (c for c in ["ketto_toroku_bango", "horse_id", "entry_id"] if c in df.columns),
        None,
    )
    if join_key_feat is None:
        log.warning("結合キーが見つかりません。マージをスキップします。")
        return {"rows_before": rows_before, "matched": 0, "new_cols": []}

    pm_renamed = pm.rename(columns={"horse_id": join_key_feat})
    pm_renamed[join_key_feat] = pm_renamed[join_key_feat].astype(str)
    df[join_key_feat]          = df[join_key_feat].astype(str)

    # LEFT JOIN
    df_merged = df.merge(pm_renamed, on=join_key_feat, how="left")
    matched   = df_merged[PEDIGREE_COLS[1]].notna().sum()  # inbreeding_coeff が埋まった行数
    new_cols  = [c for c in PEDIGREE_COLS if c != "horse_id" and c in df_merged.columns]

    log.info("  マッチ率: %d/%d (%.1f%%)", matched, rows_before, matched / max(rows_before, 1) * 100)
    log.info("  追加列: %s", new_cols)

    if dry_run:
        log.info("[DRY-RUN] CSV の上書きをスキップします。")
        return {
            "rows_before": rows_before,
            "rows_after":  len(df_merged),
            "matched":     int(matched),
            "new_cols":    new_cols,
            "dry_run":     True,
        }

    # CSV 上書き保存
    df_merged.to_csv(FEAT_CSV, index=False, encoding="utf-8-sig")
    log.info("  保存完了: %s", FEAT_CSV)

    return {
        "rows_before": rows_before,
        "rows_after":  len(df_merged),
        "matched":     int(matched),
        "new_cols":    new_cols,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="血統指標を特徴量 CSV にマージ")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()

    result = merge_pedigree_to_features(dry_run=args.dry_run)
    print(result)
    sys.exit(0 if "error" not in result else 1)
