import pandas as pd
import numpy as np
from datetime import datetime

from pipeline.db_sync_42 import add_ingest_meta, write_snapshot

def feature_engineering():
    print(f"⚙️ [{datetime.now()}] 特徴量計算開始...")
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    
    # 日付でソート
    df = df.sort_values(['ketto_toroku_bango', 'kaisai_nen', 'race_code'])
    df = df.reset_index(drop=True)

    # 前走間隔
    print("📅 前走間隔を計算中...")
    df['kaisai_gappi'] = df['kaisai_gappi'].astype(str)
    df['race_date'] = pd.to_datetime(
        df['kaisai_nen'].astype(str) + df['kaisai_gappi'].str.zfill(4),
        format='%Y%m%d', errors='coerce'
    )
    df['prev_race_date'] = df.groupby('ketto_toroku_bango')['race_date'].shift(1)
    df['weeks_since_last_race'] = (
        (df['race_date'] - df['prev_race_date']).dt.days / 7
    ).fillna(0)

    # 斤量変化
    df['prev_futan_juryo'] = df.groupby('ketto_toroku_bango')['futan_juryo'].shift(1)
    df['futan_henka'] = df['futan_juryo'] - df['prev_futan_juryo'].fillna(0)

    # 過去成績
    df['past3_avg_chakujun'] = (
        df.groupby('ketto_toroku_bango')['kakutei_chakujun']
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )
    df['past3_avg_odds'] = (
        df.groupby('ketto_toroku_bango')['tansho_odds']
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )
    df['total_races'] = df.groupby('ketto_toroku_bango').cumcount()
    df['win_count'] = (
        df.groupby('ketto_toroku_bango')['kakutei_chakujun']
        .transform(lambda x: (x.shift(1) == 1).cumsum())
    )
    df['win_rate'] = df['win_count'] / (df['total_races'] + 1)
    df['prev_chakujun'] = df.groupby('ketto_toroku_bango')['kakutei_chakujun'].shift(1).fillna(0)
    df['prev_odds'] = df.groupby('ketto_toroku_bango')['tansho_odds'].shift(1).fillna(0)

    # 通算勝率
    df['sogo_total'] = df['sogo_1chaku'] + df['sogo_2chaku'] + df['sogo_3chaku']
    df['sogo_win_rate'] = df['sogo_1chaku'] / (df['sogo_total'] + 1)

    # 馬場適性
    df['shiba_win_rate'] = (
        df['shiba_ryo_1chaku'] /
        (df['shiba_ryo_1chaku'] + df['shiba_ryo_2chaku'] + df['shiba_ryo_3chaku'] + 1)
    )
    df['dirt_win_rate'] = (
        df['dirt_ryo_1chaku'] /
        (df['dirt_ryo_1chaku'] + df['dirt_ryo_2chaku'] + df['dirt_ryo_3chaku'] + 1)
    )

    # 距離適性
    df['short_win_rate'] = df['shiba_short_1chaku'] + df['dirt_short_1chaku']
    df['middle_win_rate'] = df['shiba_middle_1chaku'] + df['dirt_middle_1chaku']
    df['long_win_rate'] = df['shiba_long_1chaku'] + df['dirt_long_1chaku']

    # 騎手の勝率（expanding window でデータリーク防止: 当該レース以前のデータのみ使用）
    print("🏇 騎手の勝率を計算中...")
    df = df.sort_values('race_code').reset_index(drop=True)
    df['_w'] = (df['kakutei_chakujun'] == 1).astype(float)
    df['kishu_win_rate'] = (
        df.groupby('kishu_code')['_w']
        .transform(lambda x: x.shift(1).expanding().mean())
        .fillna(0)
    )

    # 調教師の勝率（expanding window）
    print("👨‍🏫 調教師の勝率を計算中...")
    df['chokyoshi_win_rate'] = (
        df.groupby('chokyoshi_code')['_w']
        .transform(lambda x: x.shift(1).expanding().mean())
        .fillna(0)
    )

    # 騎手×競馬場の相性（expanding window）
    print("🏟️ 騎手×競馬場の相性を計算中...")
    df['kishu_keibajo_win_rate'] = (
        df.groupby(['kishu_code', 'keibajo_code'])['_w']
        .transform(lambda x: x.shift(1).expanding().mean())
        .fillna(0)
    )
    df.drop(columns=['_w'], inplace=True)

    # ── data_fetch_01 新列をパススルー & 派生特徴量 ────────────────
    print("🆕 新列クロス特徴量を計算中...")

    # 存在しない場合は 0 で初期化（古い keiba_data.csv との互換性）
    _new_cols_defaults = {
        'grade_score': 1, 'prev_grade_score': 1, 'grade_up': 0,
        'kishu_change': 0, 'prev_keibajo': 0, 'prev_kyori': 0,
        'chokyo_3f_avg3': 0, 'chokyo_3f_best': 0,
        'chokyo_3f_std': 0, 'chokyo_trend': 0,
        'chokyo_improving': 0, 'fresh_improving': 0,
        'chokyo_lap_3f': 0, 'chokyo_lap_1f': 0, 'chokyo_4f': 0,
        'kishu_keibajo_win_rate': 0, 'chokyoshi_place_win_rate': 0,
    }
    for col, default in _new_cols_defaults.items():
        if col not in df.columns:
            df[col] = default
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default)

    # グレード×休み明け: 格上げ+休養+調教好調 の三拍子フラグ
    df['grade_up_fresh'] = (
        (df['grade_up'] == 1) & (df['fresh_improving'] == 1)
    ).astype(int)

    # 調教質スコア: 速さ×安定性（低std=安定）
    df['chokyo_quality'] = (
        df['chokyo_3f_best'] * (1.0 / (df['chokyo_3f_std'] + 1.0))
    )

    # 騎手変更×グレード: 格上げ+乗り替わりは荒れやすい
    df['kishu_change_grade_up'] = df['kishu_change'] * df['grade_up']

    # 調教師スキル×競馬場適性
    df['chokyoshi_rate_x_grade'] = (
        df['chokyoshi_place_win_rate'] * df['grade_score']
    )

    # 前走着順×前走グレード: 前走の質を補正した着順
    df['prev_quality_chakujun'] = (
        df['prev_chakujun'] / (df['prev_grade_score'] + 1e-6)
    )

    # 馬場変化フラグ: 前走と今走で競馬場が変わったか
    df['keibajo_change'] = (
        df['prev_keibajo'].astype(str) != df['keibajo_code'].astype(str)
    ).astype(int)

    # 距離変化: 今走距離 - 前走距離
    df['kyori_change'] = (
        pd.to_numeric(df['kyori'], errors='coerce').fillna(0) -
        pd.to_numeric(df['prev_kyori'], errors='coerce').fillna(0)
    )
    df['kyori_up']   = (df['kyori_change'] > 0).astype(int)
    df['kyori_down'] = (df['kyori_change'] < 0).astype(int)

    # クロス特徴量
    print("🔀 クロス特徴量を計算中...")
    df['chichi_kyori'] = df['chichi_code'] * df['kyori']
    df['haha_kyori'] = df['haha_code'] * df['kyori']
    df['chichi_track'] = df['chichi_code'] * df['track_code']
    df['haha_track'] = df['haha_code'] * df['track_code']
    df['kishu_kyori'] = df['kishu_code'] * df['kyori']
    df['kishu_track'] = df['kishu_code'] * df['track_code']
    df['barei_kyori'] = df['barei'] * df['kyori']
    df['bataiju_kyori'] = df['bataiju'] * df['kyori']
    df['weeks_barei'] = df['weeks_since_last_race'] * df['barei']
    df['kaishi_nige'] = df['kaisai_nichime'] * df['kyakushitsu_keiko_nige']
    df['kaishi_senko'] = df['kaisai_nichime'] * df['kyakushitsu_keiko_senko']
    df['futan_barei'] = df['futan_juryo'] * df['barei']

    df = df.fillna(0)

    # nicks join
    print("nicks join...")
    nicks_path = "D:\\keiba_ai\\pedigree_output\\nicks_feature.csv"
    try:
        nicks_df = pd.read_csv(nicks_path, encoding="utf-8-sig")
        nick_cols = ['chichi', 'haha_chichi',
                     'nick_index', 'nick_roi', 'nick_win_rate', 'nick_place_rate']
        nicks_df = nicks_df[nick_cols].drop_duplicates(subset=['chichi', 'haha_chichi'])
        if 'haha_chichi' in df.columns:
            df = df.merge(nicks_df, on=['chichi', 'haha_chichi'], how='left')
        else:
            for col in ['nick_index', 'nick_roi', 'nick_win_rate', 'nick_place_rate']:
                df[col] = 0.0
        df['nick_index']      = df['nick_index'].fillna(1.0)
        df['nick_roi']        = df['nick_roi'].fillna(1.0)
        df['nick_win_rate']   = df['nick_win_rate'].fillna(0.0)
        df['nick_place_rate'] = df['nick_place_rate'].fillna(0.0)
        hits = df['nick_index'].gt(1.0).sum()
        print(f"  nicks ok: {hits:,}")
    except FileNotFoundError:
        for col in ['nick_index', 'nick_roi', 'nick_win_rate', 'nick_place_rate']:
            df[col] = 0.0

    # save
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")
    try:
        from pipeline.db_sync_42 import add_ingest_meta, write_snapshot
        snapshot = add_ingest_meta(df, source_name="feature_eng_02")
        ok = write_snapshot(
            snapshot,
            "keiba_data_features_snapshot",
            if_exists="replace",
            source_name="feature_eng_02",
        )
        if ok:
            print("DB sync: keiba_data_features_snapshot")
    except Exception as e:
        print(f"DB sync skip: {e}")

    print(f"done: {len(df):,} rows, {len(df.columns)} cols")
    return df

if __name__ == "__main__":
    feature_engineering()
