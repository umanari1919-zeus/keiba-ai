"""
enrich_today.py — 当日出馬表に過去データの特徴量を補完
=====================================================
shutsuba_fetch.py が生成する today_entries CSV は多くの特徴量が 0 のまま。
keiba_data_features.csv から各馬の最新レース行を引き、不足特徴量を埋める。

使い方:
    python pipeline/enrich_today.py 20260510
    python pipeline/enrich_today.py              # 当日
"""
from __future__ import annotations

import argparse
import os
import sys
import pathlib
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, DATA_DIR, CSV_FEATURES

import pandas as pd
import numpy as np

CARRY_OVER_COLS = [
    "seibetsu_code",
    "chokyoshi_code",
    "kishu_win_rate",
    "chokyoshi_win_rate",
    "kishu_keibajo_win_rate",
    "kyakushitsu_keiko_nige",
    "kyakushitsu_keiko_senko",
    "kyakushitsu_keiko_sashi",
    "kyakushitsu_keiko_oikomi",
    "kaishi_nige",
    "kaishi_senko",
    "post_win_rate",
    "post_bias",
    "inner_advantage",
    "tenko_apt",
    "shiba_baba_apt",
    "dirt_baba_apt",
    "ema3_chakujun",
    "ema5_chakujun",
    "ema10_chakujun",
    "weight_ema3",
    "weight_up_trend",
    "weight_down_trend",
    "weight_big_change",
    "weight_stability",
    "futan_diff",
    "age_futan_interaction",
    "futan_increase",
    "interval_bucket",
    "interval_age",
    "long_rest",
    "tight_schedule",
    "kaikai_inner_rate",
    "kaikai_outer_rate",
    "dist_category",
    "nige_dist_score",
    "oikomi_dist_score",
    "pace_consistency",
    "track_change",
    "jt_win_rate",
    "jt_place_rate",
    "jt_roi",
    "jockey_course_dist_win_rate",
    "trainer_course_win_rate",
    "nick3_index",
    "nick3_roi",
    "nick3_win_rate",
    "chokyo_3f_avg3",
    "chokyo_3f_best",
    "chokyo_3f_std",
    "chokyo_improving",
    "chokyo_pace_est",
    "chokyo_quality",
    "chokyo_trend",
    "chokyoshi_place_win_rate",
    "chokyoshi_rate_x_grade",
    "chokyoshimei_ryakusho",
    "debut_score",
    "debut_weight_bonus",
    "fresh_improving",
    "grade_score",
    "grade_up",
    "grade_up_fresh",
    "haha_haha_chichi",
    "is_debut",
    "is_inner",
    "is_outer",
    "jockey_debut_win_rate",
    "keibajo_change",
    "kishu_change_grade_up",
    "kyori_change",
    "kyori_down",
    "kyori_up",
    "prev_futan",
    "prev_futan_juryo",
    "prev_grade",
    "prev_quality_chakujun",
    "prev_track",
    "race_grade",
    "sire_debut_win_rate",
    "trainer_debut_win_rate",
    "prev_chakujun",
    "bataiju",
    "zogen_sa",
    "zogen_fugo",
    "bataiju_kyori",
    "bataiju_signed",
    "race_month",
    "season",
    "is_spring",
    "is_summer",
    "is_autumn",
    "is_winter",
]

DATE_DERIVED_COLS = [
    "race_month", "season", "is_spring", "is_summer", "is_autumn", "is_winter",
]


def _compute_date_features(df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """日付ベースの特徴量を正確に計算する。"""
    month = int(date_str[4:6])
    df["race_month"] = month
    if month in (3, 4, 5):
        df["season"], df["is_spring"] = 1, 1
    elif month in (6, 7, 8):
        df["season"], df["is_summer"] = 2, 1
    elif month in (9, 10, 11):
        df["season"], df["is_autumn"] = 3, 1
    else:
        df["season"], df["is_winter"] = 4, 1
    for c in ["is_spring", "is_summer", "is_autumn", "is_winter"]:
        if c not in df.columns:
            df[c] = 0
    return df


def enrich_today_entries(date_str: str = None) -> pd.DataFrame:
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    today_file = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    if not os.path.exists(today_file):
        print(f"[enrich] 出馬表なし: {today_file}")
        return pd.DataFrame()

    if not os.path.exists(CSV_FEATURES):
        print(f"[enrich] 特徴量CSVなし: {CSV_FEATURES}")
        return pd.DataFrame()

    print(f"[enrich] 特徴量補完開始: {today_file}")
    today = pd.read_csv(today_file, encoding="utf-8-sig", low_memory=False)
    today = today.fillna(0)

    kettos = set(str(k) for k in today["ketto_toroku_bango"].unique())

    print(f"[enrich] keiba_data_features.csv 読み込み中...")
    hist = pd.read_csv(CSV_FEATURES, encoding="utf-8-sig",
                       low_memory=False, on_bad_lines="skip")
    hist = hist.fillna(0)
    hist["ketto_toroku_bango"] = hist["ketto_toroku_bango"].astype(str)

    hist_match = hist[hist["ketto_toroku_bango"].isin(kettos)].copy()
    latest = hist_match.sort_values("race_code").groupby("ketto_toroku_bango").last()
    print(f"[enrich] 過去データあり: {len(latest)} / {len(kettos)} 頭")

    today["ketto_toroku_bango"] = today["ketto_toroku_bango"].astype(str)

    filled_count = 0
    carry_cols = [c for c in CARRY_OVER_COLS if c in latest.columns and c not in DATE_DERIVED_COLS]

    for idx, row in today.iterrows():
        ketto = str(row["ketto_toroku_bango"])
        if ketto not in latest.index:
            continue

        hist_row = latest.loc[ketto]
        for col in carry_cols:
            current_val = row.get(col, 0)
            if pd.isna(current_val) or current_val == 0 or current_val == "0":
                hist_val = hist_row.get(col, 0)
                if hist_val != 0 and not pd.isna(hist_val):
                    today.at[idx, col] = hist_val
                    filled_count += 1

    today = _compute_date_features(today, date_str)

    today.to_csv(today_file, index=False, encoding="utf-8-sig")
    print(f"[enrich] 補完セル数: {filled_count:,}")
    print(f"[enrich] 保存: {today_file}")

    non_zero_check = []
    for col in CARRY_OVER_COLS[:10]:
        if col in today.columns:
            nz = (pd.to_numeric(today[col], errors="coerce").fillna(0) != 0).sum()
            non_zero_check.append(f"  {col}: {nz}/{len(today)}")
    print(f"[enrich] 補完後のサンプル:")
    for line in non_zero_check:
        print(line)

    return today


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="当日出馬表の特徴量補完")
    parser.add_argument("date", nargs="?", default=None, help="YYYYMMDD")
    args = parser.parse_args()
    enrich_today_entries(args.date)
