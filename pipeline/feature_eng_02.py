import pandas as pd
import numpy as np
from datetime import datetime

def feature_engineering():
    print(f"⚙️ [{datetime.now()}] 特徴量計算開始...")
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data.csv",
                     encoding="utf-8-sig", low_memory=False)
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

    # 騎手の勝率
    print("🏇 騎手の勝率を計算中...")
    kishu_wins = df[df['kakutei_chakujun'] == 1].groupby('kishu_code').size()
    kishu_total = df.groupby('kishu_code').size()
    df['kishu_win_rate'] = df['kishu_code'].map((kishu_wins / kishu_total).fillna(0))

    # 調教師の勝率
    print("👨‍🏫 調教師の勝率を計算中...")
    cho_wins = df[df['kakutei_chakujun'] == 1].groupby('chokyoshi_code').size()
    cho_total = df.groupby('chokyoshi_code').size()
    df['chokyoshi_win_rate'] = df['chokyoshi_code'].map((cho_wins / cho_total).fillna(0))

    # 騎手×競馬場の相性
    print("🏟️ 騎手×競馬場の相性を計算中...")
    kishu_keibajo_wins = (
        df[df['kakutei_chakujun'] == 1]
        .groupby(['kishu_code', 'keibajo_code']).size()
    )
    kishu_keibajo_total = df.groupby(['kishu_code', 'keibajo_code']).size()
    kishu_keibajo_rate = (kishu_keibajo_wins / kishu_keibajo_total).fillna(0)
    df['kishu_keibajo_win_rate'] = df.set_index(
        ['kishu_code', 'keibajo_code']
    ).index.map(kishu_keibajo_rate.to_dict().get).fillna(0).values

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

    # ニックス指数を結合
    print("🐴 ニックス指数を結合中...")
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
        print(f"  ✅ ニックス結合完了（nick_index>1.0：{hits:,}件）")
    except FileNotFoundError:
        print(f"  ⚠️ {nicks_path} が見つかりません。ニックス特徴量をゼロで埋めます")
        for col in ['nick_index', 'nick_roi', 'nick_win_rate', 'nick_place_rate']:
            df[col] = 0.0

    # 保存
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")

    print(f"✅ 特徴量計算完了！件数：{len(df):,}件")
    print(f"📋 列数：{len(df.columns)}列")
    return df

if __name__ == "__main__":
    feature_engineering()