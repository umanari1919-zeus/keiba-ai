"""
ペース分析・調教タイム分析
- 前半3F・後半3F・ラップ推移
- 調教タイム強度スコア
- 調教コース・ペース変化
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime

DB_URL = "postgresql://postgres:trust@localhost:5433/mykeibadb"


# ──────────────────────────────────────────────
# 調教タイム分析（woodchip_chokyo / hanro_chokyo）
# ──────────────────────────────────────────────

def build_training_features(year_from=2020):
    engine = create_engine(DB_URL)

    # ウッドチップ調教
    q_wood = text("""
        SELECT
            ketto_toroku_bango,
            chokyo_nengappi,
            course,
            COALESCE(NULLIF(time_gokei_4furlong,''),NULL)::float   as wood_4f,
            COALESCE(NULLIF(laptime_4furlong,''),NULL)::float       as wood_lap4f,
            COALESCE(NULLIF(time_gokei_3furlong,''),NULL)::float   as wood_3f,
            COALESCE(NULLIF(laptime_3furlong,''),NULL)::float       as wood_lap3f,
            COALESCE(NULLIF(time_gokei_2furlong,''),NULL)::float   as wood_2f,
            COALESCE(NULLIF(laptime_2furlong,''),NULL)::float       as wood_lap2f,
            COALESCE(NULLIF(laptime_1furlong,''),NULL)::float       as wood_1f
        FROM woodchip_chokyo
        WHERE chokyo_nengappi >= :year
    """)

    # 坂路・ハロン路調教
    q_hanro = text("""
        SELECT
            ketto_toroku_bango,
            chokyo_nengappi,
            COALESCE(NULLIF(time_gokei_4furlong,''),NULL)::float   as hanro_4f,
            COALESCE(NULLIF(lap_time_4furlong,''),NULL)::float      as hanro_lap4f,
            COALESCE(NULLIF(time_gokei_3furlong,''),NULL)::float   as hanro_3f,
            COALESCE(NULLIF(lap_time_3furlong,''),NULL)::float      as hanro_lap3f,
            COALESCE(NULLIF(lap_time_1furlong,''),NULL)::float      as hanro_lap1f
        FROM hanro_chokyo
        WHERE chokyo_nengappi >= :year
    """)

    try:
        with engine.connect() as conn:
            wood_df  = pd.read_sql(q_wood,  conn, params={'year': str(year_from)})
            hanro_df = pd.read_sql(q_hanro, conn, params={'year': str(year_from)})
    except Exception as e:
        print(f"  ⚠️ 調教データ取得エラー: {e}")
        return pd.DataFrame()

    # 最新調教を1本だけ取得
    def latest_one(df, key='ketto_toroku_bango'):
        df['chokyo_nengappi'] = pd.to_datetime(df['chokyo_nengappi'], errors='coerce')
        return df.sort_values('chokyo_nengappi').groupby(key).last().reset_index()

    wood_latest  = latest_one(wood_df)
    hanro_latest = latest_one(hanro_df)

    merged = wood_latest.merge(hanro_latest, on='ketto_toroku_bango', how='outer',
                                suffixes=('_wood', '_hanro'))

    # 調教強度スコア（タイムが速いほど高い、基準値との比較）
    # ウッドチップ4F基準: 52秒、坂路4F基準: 54秒
    WOOD_BASE  = 52.0
    HANRO_BASE = 54.0

    merged['wood_intensity']  = (WOOD_BASE  - merged['wood_4f'].fillna(WOOD_BASE)) / WOOD_BASE
    merged['hanro_intensity'] = (HANRO_BASE - merged['hanro_4f'].fillna(HANRO_BASE)) / HANRO_BASE

    # 最終1F（切れ）スコア
    merged['wood_kick']  = (12.5 - merged['wood_1f'].fillna(12.5)) / 12.5
    merged['hanro_kick'] = (13.5 - merged['hanro_lap1f'].fillna(13.5)) / 13.5

    # 総合調教スコア
    merged['training_score'] = (
        0.4 * merged['wood_intensity'].fillna(0) +
        0.4 * merged['hanro_intensity'].fillna(0) +
        0.2 * (merged['wood_kick'].fillna(0) + merged['hanro_kick'].fillna(0)) / 2
    )

    cols = ['ketto_toroku_bango', 'wood_4f', 'wood_3f', 'wood_lap3f', 'wood_1f',
            'hanro_4f', 'hanro_3f', 'hanro_lap1f',
            'wood_intensity', 'hanro_intensity', 'wood_kick', 'hanro_kick',
            'training_score']
    return merged[[c for c in cols if c in merged.columns]]


# ──────────────────────────────────────────────
# ペース分析（レース内スプリット推定）
# ──────────────────────────────────────────────

def add_pace_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    既存データから前後半ペース指標を推定する。
    本来はラップタイムDBが必要だが、既存データから近似値を計算。
    """
    # 調教4Fタイムからペース適性を推定
    df['chokyo_pace_est'] = df['chokyo_3f'] / (df['kyori'] / 200 + 1e-6)

    # 距離カテゴリ（短距離・中距離・長距離）
    df['dist_category'] = pd.cut(
        df['kyori'],
        bins=[0, 1400, 1800, 2200, 9999],
        labels=[0, 1, 2, 3]  # 短距離, マイル, 中距離, 長距離
    ).astype(int)

    # 脚質×距離の相性スコア
    df['nige_dist_score'] = df['kyakushitsu_keiko_nige'] * (1 - df['dist_category'] / 4)
    df['oikomi_dist_score'] = df['kyakushitsu_keiko_oikomi'] * (df['dist_category'] / 4)

    # 前走ペース適性（脚質安定性）
    df['pace_consistency'] = (
        df.groupby('ketto_toroku_bango')['kyakushitsu_hantei']
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).std())
        .fillna(0)
    )

    # 芝vs.ダートのペース変化適応力
    df['prev_track'] = df.groupby('ketto_toroku_bango')['track_code'].shift(1).fillna(0)
    df['track_change'] = (df['track_code'] != df['prev_track']).astype(int)

    return df


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_pace_training_analysis():
    print("\n" + "="*55)
    print("🏋️ ペース・調教タイム分析")
    print("="*55)

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')

    print("  📋 調教タイム特徴量を構築中...")
    training_df = build_training_features()
    if len(training_df) > 0:
        df = df.merge(training_df, on='ketto_toroku_bango', how='left', suffixes=('', '_new'))
        for col in ['wood_intensity', 'hanro_intensity', 'wood_kick', 'hanro_kick', 'training_score']:
            if col in df.columns:
                df[col] = df[col].fillna(0)
        print(f"  ✅ 調教特徴量追加: {len(training_df):,}頭分")

    print("  📊 ペース特徴量を計算中...")
    df = add_pace_features(df)

    df = df.fillna(0)
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")
    print(f"  ✅ 完了: {len(df):,}件 × {len(df.columns)}列")
    return df


PACE_FEATURES = [
    'training_score', 'wood_intensity', 'hanro_intensity', 'wood_kick', 'hanro_kick',
    'dist_category', 'nige_dist_score', 'oikomi_dist_score',
    'pace_consistency', 'track_change',
]


if __name__ == "__main__":
    run_pace_training_analysis()
