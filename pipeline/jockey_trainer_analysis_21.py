"""
騎手×調教師×馬主の相性分析
3代ニックス（父×母父×母母父）分析
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from scipy import stats
from datetime import datetime

DB_URL = "postgresql://postgres:trust@localhost:5433/mykeibadb"


# ──────────────────────────────────────────────
# 騎手×調教師相性
# ──────────────────────────────────────────────

def build_jockey_trainer_combo(df: pd.DataFrame) -> pd.DataFrame:
    wins   = df[df['kakutei_chakujun'] == 1]
    places = df[df['kakutei_chakujun'] <= 3]

    key = ['kishu_code', 'chokyoshi_code']
    total_cnt = df.groupby(key).size().rename('jt_total')
    win_cnt   = wins.groupby(key).size().rename('jt_wins')
    place_cnt = places.groupby(key).size().rename('jt_places')

    combo = total_cnt.to_frame().join(win_cnt).join(place_cnt).fillna(0)
    combo['jt_win_rate']   = combo['jt_wins']   / (combo['jt_total'] + 1)
    combo['jt_place_rate'] = combo['jt_places'] / (combo['jt_total'] + 1)

    # オッズ期待値（的中時の平均オッズ）
    win_odds = (df[df['kakutei_chakujun'] == 1]
                .groupby(key)['tansho_odds'].mean() / 10).rename('jt_avg_odds')
    combo = combo.join(win_odds)
    combo['jt_roi'] = combo['jt_win_rate'] * combo['jt_avg_odds'].fillna(0)

    df = df.merge(combo[['jt_win_rate', 'jt_place_rate', 'jt_roi']].reset_index(),
                  on=key, how='left')
    df[['jt_win_rate', 'jt_place_rate', 'jt_roi']] = \
        df[['jt_win_rate', 'jt_place_rate', 'jt_roi']].fillna(0)
    return df


# ──────────────────────────────────────────────
# 騎手×競馬場×距離相性
# ──────────────────────────────────────────────

def build_jockey_course_distance(df: pd.DataFrame) -> pd.DataFrame:
    wins = df[df['kakutei_chakujun'] == 1]
    key  = ['kishu_code', 'keibajo_code', 'kyori']

    total = df.groupby(key).size()
    win_c = wins.groupby(key).size()
    rate  = (win_c / total).fillna(0).rename('jockey_course_dist_win_rate')

    df = df.join(rate, on=key)
    df['jockey_course_dist_win_rate'] = df['jockey_course_dist_win_rate'].fillna(0)
    return df


# ──────────────────────────────────────────────
# 調教師×競馬場相性
# ──────────────────────────────────────────────

def build_trainer_course_aptitude(df: pd.DataFrame) -> pd.DataFrame:
    wins = df[df['kakutei_chakujun'] == 1]
    key  = ['chokyoshi_code', 'keibajo_code']

    total = df.groupby(key).size()
    win_c = wins.groupby(key).size()
    rate  = (win_c / total).fillna(0).rename('trainer_course_win_rate')

    df = df.join(rate, on=key)
    df['trainer_course_win_rate'] = df['trainer_course_win_rate'].fillna(0)
    return df


# ──────────────────────────────────────────────
# 3代ニックス（父×母父×母母父）
# ──────────────────────────────────────────────

def build_3gen_nicks_features(year_from=2018):
    """
    nicks_analysis_18.py の3代ニックスCSVを読み込んで特徴量を追加する。
    """
    nicks3_path = "D:\\keiba_ai\\pedigree_output\\nicks_3gen.csv"
    try:
        nicks3 = pd.read_csv(nicks3_path, encoding="utf-8-sig")
        print(f"  📖 3代ニックス: {len(nicks3):,}組")

        # 3代ニックス指数の高い組み合わせを特徴量に
        nicks3 = nicks3.rename(columns={
            'nick_index':     'nick3_index',
            'nick_roi':       'nick3_roi',
            'win_rate':       'nick3_win_rate',
        })
        return nicks3[['chichi', 'haha_chichi', 'haha_haha_chichi',
                        'nick3_index', 'nick3_roi', 'nick3_win_rate']].drop_duplicates()
    except FileNotFoundError:
        print(f"  ⚠️ {nicks3_path} が見つかりません。先に nicks_analysis_18.py を実行してください。")
        return pd.DataFrame()


def enrich_3gen_nicks(df: pd.DataFrame) -> pd.DataFrame:
    """keiba_data_features.csv に3代ニックスを結合"""
    # ketto5_bamei=母父、ketto6=母母父が必要
    if 'haha_chichi' not in df.columns:
        print("  ⚠️ haha_chichi列がありません")
        for col in ['nick3_index', 'nick3_roi', 'nick3_win_rate']:
            df[col] = 0.0
        return df

    nicks3 = build_3gen_nicks_features()
    if len(nicks3) == 0:
        for col in ['nick3_index', 'nick3_roi', 'nick3_win_rate']:
            df[col] = 0.0
        return df

    # 母母父カラムが必要（data_fetch_01.pyで追加が必要）
    if 'haha_haha_chichi' not in df.columns:
        df['haha_haha_chichi'] = ''

    df = df.merge(nicks3, on=['chichi', 'haha_chichi', 'haha_haha_chichi'],
                  how='left')
    df['nick3_index']    = df['nick3_index'].fillna(1.0)
    df['nick3_roi']      = df['nick3_roi'].fillna(1.0)
    df['nick3_win_rate'] = df['nick3_win_rate'].fillna(0.0)
    return df


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_jockey_trainer_analysis():
    print("\n" + "="*55)
    print("👑 騎手・調教師・3代ニックス分析")
    print("="*55)

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    n_before = len(df.columns)

    print("  🏇 騎手×調教師コンボ...")
    df = build_jockey_trainer_combo(df)

    print("  🏟️ 騎手×コース×距離...")
    df = build_jockey_course_distance(df)

    print("  👨‍🏫 調教師×コース相性...")
    df = build_trainer_course_aptitude(df)

    print("  🧬 3代ニックス...")
    df = enrich_3gen_nicks(df)

    df = df.fillna(0)
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")

    n_after = len(df.columns)
    print(f"  ✅ 完了: {len(df):,}件 × {n_after}列 (+{n_after-n_before}列)")
    return df


JOCKEY_FEATURES = [
    'jt_win_rate', 'jt_place_rate', 'jt_roi',
    'jockey_course_dist_win_rate', 'trainer_course_win_rate',
    'nick3_index', 'nick3_roi', 'nick3_win_rate',
]


if __name__ == "__main__":
    run_jockey_trainer_analysis()
