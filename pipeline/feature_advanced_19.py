"""
高度特徴量エンジニアリング
- コース適性スコア（競馬場×距離×馬場×季節）
- 馬体重トレンド分析（増減パターン）
- 枠番有利不利（競馬場別）
- 開催週馬場バイアス
- 天候・馬場状態の影響
- 指数移動平均（EMA）
- 斤量補正
- レース間隔最適化
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime

DB_URL = "postgresql://postgres:trust@localhost:5433/mykeibadb"

KEIBAJO_MAP = {
    '01': 'sapporo', '02': 'hakodate', '03': 'fukushima', '04': 'niigata',
    '05': 'tokyo',   '06': 'nakayama', '07': 'chukyo',    '08': 'kyoto',
    '09': 'hanshin', '10': 'kokura'
}

# ──────────────────────────────────────────────
# コース適性スコア（shussobetsu_keibajoから）
# ──────────────────────────────────────────────

def build_course_aptitude_features(year_from=2020):
    engine = create_engine(DB_URL)
    query = text("""
        SELECT
            sk.ketto_toroku_bango,
            sk.race_code,
            sk.keibajo_code,
            sk.kaisai_nen,
            -- 東京
            COALESCE(sk.tokyo_shiba_1chaku,0)  as tk_shiba_1,
            COALESCE(NULLIF(sk.tokyo_shiba_1chaku,0)+NULLIF(sk.tokyo_shiba_2chaku,0)+
                     NULLIF(sk.tokyo_shiba_3chaku,0)+NULLIF(sk.tokyo_shiba_4chaku,0)+
                     NULLIF(sk.tokyo_shiba_5chaku,0)+NULLIF(sk.tokyo_shiba_chakugai,0),0) as tk_shiba_total,
            COALESCE(sk.tokyo_dirt_1chaku,0)   as tk_dirt_1,
            COALESCE(NULLIF(sk.tokyo_dirt_1chaku,0)+NULLIF(sk.tokyo_dirt_2chaku,0)+
                     NULLIF(sk.tokyo_dirt_3chaku,0)+NULLIF(sk.tokyo_dirt_4chaku,0)+
                     NULLIF(sk.tokyo_dirt_5chaku,0)+NULLIF(sk.tokyo_dirt_chakugai,0),0) as tk_dirt_total,
            -- 中山
            COALESCE(sk.nakayama_shiba_1chaku,0) as ny_shiba_1,
            COALESCE(NULLIF(sk.nakayama_shiba_1chaku,0)+NULLIF(sk.nakayama_shiba_2chaku,0)+
                     NULLIF(sk.nakayama_shiba_3chaku,0)+NULLIF(sk.nakayama_shiba_4chaku,0)+
                     NULLIF(sk.nakayama_shiba_5chaku,0)+NULLIF(sk.nakayama_shiba_chakugai,0),0) as ny_shiba_total,
            -- 阪神
            COALESCE(sk.hanshin_shiba_1chaku,0) as hs_shiba_1,
            COALESCE(NULLIF(sk.hanshin_shiba_1chaku,0)+NULLIF(sk.hanshin_shiba_2chaku,0)+
                     NULLIF(sk.hanshin_shiba_3chaku,0)+NULLIF(sk.hanshin_shiba_4chaku,0)+
                     NULLIF(sk.hanshin_shiba_5chaku,0)+NULLIF(sk.hanshin_shiba_chakugai,0),0) as hs_shiba_total,
            -- 京都
            COALESCE(sk.kyoto_shiba_1chaku,0) as ky_shiba_1,
            COALESCE(NULLIF(sk.kyoto_shiba_1chaku,0)+NULLIF(sk.kyoto_shiba_2chaku,0)+
                     NULLIF(sk.kyoto_shiba_3chaku,0)+NULLIF(sk.kyoto_shiba_4chaku,0)+
                     NULLIF(sk.kyoto_shiba_5chaku,0)+NULLIF(sk.kyoto_shiba_chakugai,0),0) as ky_shiba_total,
            -- 中京
            COALESCE(sk.chukyo_shiba_1chaku,0) as ck_shiba_1,
            COALESCE(NULLIF(sk.chukyo_shiba_1chaku,0)+NULLIF(sk.chukyo_shiba_2chaku,0)+
                     NULLIF(sk.chukyo_shiba_3chaku,0)+NULLIF(sk.chukyo_shiba_4chaku,0)+
                     NULLIF(sk.chukyo_shiba_5chaku,0)+NULLIF(sk.chukyo_shiba_chakugai,0),0) as ck_shiba_total
        FROM shussobetsu_keibajo sk
        WHERE sk.kaisai_nen >= :year
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={'year': str(year_from)})

    # コード→名前マッピング
    course_map = {
        '05': ('tk_shiba', 'tk_dirt'), '06': ('ny_shiba', None),
        '09': ('hs_shiba', None),      '08': ('ky_shiba', None),
        '07': ('ck_shiba', None)
    }

    def _win_rate(w, t): return w / (t + 1)

    df['course_win_rate'] = 0.0
    for code, (shiba_pref, dirt_pref) in course_map.items():
        mask = df['keibajo_code'] == code
        if shiba_pref and f'{shiba_pref}_1' in df.columns:
            df.loc[mask, 'course_win_rate'] = _win_rate(
                df.loc[mask, f'{shiba_pref}_1'],
                df.loc[mask, f'{shiba_pref}_total']
            )

    return df[['ketto_toroku_bango', 'race_code', 'course_win_rate']].drop_duplicates()


# ──────────────────────────────────────────────
# 馬体重トレンド（増減パターン分析）
# ──────────────────────────────────────────────

def add_weight_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(['ketto_toroku_bango', 'race_code'])

    # 体重の符号付き変化
    df['bataiju_signed'] = df['zogen_fugo'] * df['zogen_sa']

    # 直近3走の体重変化EMA
    df['weight_ema3'] = (
        df.groupby('ketto_toroku_bango')['bataiju_signed']
        .transform(lambda x: x.shift(1).ewm(span=3, adjust=False).mean())
        .fillna(0)
    )

    # 増加トレンド・減少トレンドフラグ
    df['weight_up_trend']   = (df['weight_ema3'] > 2).astype(int)
    df['weight_down_trend'] = (df['weight_ema3'] < -2).astype(int)

    # 大幅増減フラグ（±10kg以上）
    df['weight_big_change'] = (df['zogen_sa'].abs() >= 10).astype(int)

    # 体重安定性（直近5走の標準偏差）
    df['weight_stability'] = (
        df.groupby('ketto_toroku_bango')['bataiju']
        .transform(lambda x: x.shift(1).rolling(5, min_periods=2).std())
        .fillna(0)
    )
    return df


# ──────────────────────────────────────────────
# 枠番有利不利（競馬場×距離×馬場別）
# ──────────────────────────────────────────────

def build_post_position_bias(df: pd.DataFrame) -> pd.DataFrame:
    wins = df[df['kakutei_chakujun'] == 1]
    total = df.groupby(['keibajo_code', 'kyori', 'track_code', 'wakuban']).size()
    win_c = wins.groupby(['keibajo_code', 'kyori', 'track_code', 'wakuban']).size()
    bias  = (win_c / total).fillna(0)

    bias_df = bias.reset_index()
    bias_df.columns = ['keibajo_code', 'kyori', 'track_code', 'wakuban', 'post_win_rate']

    # 全体の平均勝率と比較したバイアス
    avg_rate = wins.shape[0] / df.shape[0]
    bias_df['post_bias'] = bias_df['post_win_rate'] - avg_rate

    df = df.merge(bias_df, on=['keibajo_code', 'kyori', 'track_code', 'wakuban'], how='left')
    df['post_win_rate'] = df['post_win_rate'].fillna(avg_rate)
    df['post_bias']     = df['post_bias'].fillna(0)
    return df


# ──────────────────────────────────────────────
# 開催週馬場バイアス（開催が進むと内外どちらが有利か）
# ──────────────────────────────────────────────

def add_kaikai_week_bias(df: pd.DataFrame) -> pd.DataFrame:
    # 開催週×競馬場×track_code での内枠（wakuban<=4）勝率
    df['is_inner'] = (df['wakuban'] <= 4).astype(int)
    df['is_outer'] = (df['wakuban'] >= 5).astype(int)

    wins = df[df['kakutei_chakujun'] == 1]
    key  = ['keibajo_code', 'kaisai_kai', 'track_code']

    inner_wins  = wins[wins['is_inner'] == 1].groupby(key).size()
    inner_total = df[df['is_inner'] == 1].groupby(key).size()
    outer_wins  = wins[wins['is_outer'] == 1].groupby(key).size()
    outer_total = df[df['is_outer'] == 1].groupby(key).size()

    inner_rate = (inner_wins / inner_total).fillna(0).rename('kaikai_inner_rate')
    outer_rate = (outer_wins / outer_total).fillna(0).rename('kaikai_outer_rate')

    df = df.join(inner_rate, on=key)
    df = df.join(outer_rate, on=key)
    df['kaikai_inner_rate'] = df['kaikai_inner_rate'].fillna(0)
    df['kaikai_outer_rate'] = df['kaikai_outer_rate'].fillna(0)
    df['inner_advantage'] = df['kaikai_inner_rate'] - df['kaikai_outer_rate']
    return df


# ──────────────────────────────────────────────
# 天候・馬場状態の影響スコア
# ──────────────────────────────────────────────

def add_weather_aptitude(df: pd.DataFrame) -> pd.DataFrame:
    wins = df[df['kakutei_chakujun'] == 1]

    # 馬場状態別の個別勝率
    for col, suffix in [('tenko_code', 'tenko'), ('shiba_babajotai_code', 'shiba_baba'),
                         ('dirt_babajotai_code', 'dirt_baba')]:
        total = df.groupby(['ketto_toroku_bango', col]).size()
        win_c = wins.groupby(['ketto_toroku_bango', col]).size()
        rate  = (win_c / total).fillna(0).rename(f'{suffix}_apt')
        df = df.join(rate, on=['ketto_toroku_bango', col])
        df[f'{suffix}_apt'] = df[f'{suffix}_apt'].fillna(0)
    return df


# ──────────────────────────────────────────────
# 指数移動平均（EMA）による過去N走重み付き平均
# ──────────────────────────────────────────────

def add_ema_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(['ketto_toroku_bango', 'race_code'])

    for span in [3, 5, 10]:
        df[f'ema{span}_chakujun'] = (
            df.groupby('ketto_toroku_bango')['kakutei_chakujun']
            .transform(lambda x: x.shift(1).ewm(span=span, adjust=False).mean())
            .fillna(0)
        )
        df[f'ema{span}_odds'] = (
            df.groupby('ketto_toroku_bango')['tansho_odds']
            .transform(lambda x: x.shift(1).ewm(span=span, adjust=False).mean())
            .fillna(0)
        )
    return df


# ──────────────────────────────────────────────
# 斤量補正モデル
# ──────────────────────────────────────────────

def add_weight_correction(df: pd.DataFrame) -> pd.DataFrame:
    # 斤量が標準（55kg）からの偏差が成績に与える影響
    STANDARD_WEIGHT = 55.0
    df['futan_diff'] = df['futan_juryo'].astype(float) - STANDARD_WEIGHT

    # 馬齢×斤量の交互作用
    df['age_futan_interaction'] = df['barei'] * df['futan_diff']

    # 斤量が前走より増えた場合の影響
    df['prev_futan'] = df.groupby('ketto_toroku_bango')['futan_juryo'].shift(1).fillna(0)
    df['futan_increase'] = (df['futan_juryo'] - df['prev_futan']).clip(lower=0)
    return df


# ──────────────────────────────────────────────
# レース間隔最適化モデル
# ──────────────────────────────────────────────

def add_interval_features(df: pd.DataFrame) -> pd.DataFrame:
    # 最適間隔バケット（1-4週、5-8週、9-12週、13週以上）
    df['interval_bucket'] = pd.cut(
        df['weeks_since_last_race'],
        bins=[-1, 4, 8, 12, 999],
        labels=[0, 1, 2, 3]
    ).astype(int)

    # 間隔×年齢の交互作用
    df['interval_age'] = df['weeks_since_last_race'] * df['barei']

    # 長休養明け（13週以上）フラグ
    df['long_rest'] = (df['weeks_since_last_race'] >= 13).astype(int)

    # 詰め込みフラグ（1週以内）
    df['tight_schedule'] = (df['weeks_since_last_race'] <= 1).astype(int)
    return df


# ──────────────────────────────────────────────
# 季節特徴量
# ──────────────────────────────────────────────

def add_season_features(df: pd.DataFrame) -> pd.DataFrame:
    gappi = df['kaisai_gappi'].astype(str).str.zfill(4)
    month = gappi.str[:2].astype(int)
    df['race_month'] = month
    df['season'] = pd.cut(month, bins=[0,3,6,9,12], labels=[0,1,2,3]).astype(int)
    df['is_spring'] = (month.between(3, 5)).astype(int)
    df['is_summer'] = (month.between(6, 8)).astype(int)
    df['is_autumn'] = (month.between(9, 11)).astype(int)
    df['is_winter'] = ((month <= 2) | (month == 12)).astype(int)
    return df


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_advanced_feature_engineering():
    print("\n" + "="*55)
    print("🔬 高度特徴量エンジニアリング")
    print("="*55)

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    n_before = len(df.columns)

    print(f"  入力: {len(df):,}件 × {n_before}列")

    # 各特徴量を追加
    print("  ⚖️ 馬体重トレンド...")
    df = add_weight_trend_features(df)

    print("  🏇 枠番バイアス...")
    df = build_post_position_bias(df)

    print("  🌦️ 馬場・天候適性...")
    df = add_weather_aptitude(df)

    print("  📊 指数移動平均...")
    df = add_ema_features(df)

    print("  ⚖️ 斤量補正...")
    df = add_weight_correction(df)

    print("  📅 レース間隔・季節...")
    df = add_interval_features(df)
    df = add_season_features(df)

    print("  🏟️ 開催週バイアス...")
    df = add_kaikai_week_bias(df)

    df = df.fillna(0)
    df.to_csv("D:\\keiba_ai\\keiba_data_features.csv",
              index=False, encoding="utf-8-sig")

    n_after = len(df.columns)
    print(f"  ✅ 完了: {len(df):,}件 × {n_after}列 (+{n_after-n_before}列)")
    return df


# 追加する特徴量リスト（model_train_03.pyのFEATURESに追記）
ADVANCED_FEATURES = [
    'course_win_rate',                   # コース適性
    'post_win_rate', 'post_bias',        # 枠番バイアス
    'inner_advantage',                   # 内枠有利度
    'tenko_apt', 'shiba_baba_apt', 'dirt_baba_apt',  # 天候・馬場適性
    'ema3_chakujun', 'ema5_chakujun', 'ema10_chakujun',  # EMA着順
    'ema3_odds',                         # EMAオッズ
    'weight_ema3', 'weight_up_trend', 'weight_down_trend',
    'weight_big_change', 'weight_stability',  # 体重トレンド
    'futan_diff', 'age_futan_interaction', 'futan_increase',  # 斤量補正
    'interval_bucket', 'interval_age', 'long_rest', 'tight_schedule',  # 間隔
    'race_month', 'season', 'is_spring', 'is_summer', 'is_autumn', 'is_winter',  # 季節
    'kaikai_inner_rate', 'kaikai_outer_rate',  # 開催週バイアス
]


if __name__ == "__main__":
    run_advanced_feature_engineering()
    print(f"\n新規特徴量 ({len(ADVANCED_FEATURES)}個): {ADVANCED_FEATURES}")
