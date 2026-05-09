"""
強化版 調教タイム分析
- 直近14日間の全セッションを集計（従来は最新1本のみ）
- コース別偏差値（同コース・同期間の相対評価）
- 前後半バランス（切れ型/先行型の判定）
- 調教本数・頻度スコア
- タイム改善トレンド（上昇/下降/安定）
- tracen区分（美浦/栗東）
- feature_eng_02 → model_train_03 の間に挿入して特徴量を強化

出力列（keiba_data_features.csv に追記）:
  wood_4f_best30      直近30日の最速4Fタイム
  wood_4f_last        直近調教の4Fタイム
  wood_4f_zscore      コース別偏差値（高い=速い）
  wood_trend          タイム改善率（+が改善、-が悪化）
  wood_sessions14d    直近14日の調教本数
  wood_pace_balance   前後半バランス（1F/(3F/3)、高い=切れ型）
  hanro_4f_best30     坂路 直近30日最速4F
  hanro_4f_last       坂路 直近4F
  hanro_4f_zscore     坂路コース別偏差値
  hanro_trend         坂路タイム改善率
  hanro_sessions14d   坂路直近14日本数
  training_score_v2   総合調教スコア v2（偏差値ベース）
  training_form       調教状態ラベル（A/B/C/D）
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import os

from pipeline.config import CSV_FEATURES, DB_URL

WOOD_COLUMNS = ['ketto_toroku_bango', 'date', 'tracen_kubun', 'course', 't4f', 'l4f', 't3f', 'l3f', 'l1f']
HANRO_COLUMNS = ['ketto_toroku_bango', 'date', 'tracen_kubun', 't4f', 'l4f', 't3f', 'l3f', 'l1f']


def _horse_count(df: pd.DataFrame) -> int:
    if 'ketto_toroku_bango' not in df.columns:
        return 0
    return int(df['ketto_toroku_bango'].nunique())


# タイム列の変換（整数文字列 → 秒）
def _parse_time(val, scale=10.0) -> float:
    """'0523' → 52.3, '000' → NaN"""
    try:
        v = int(str(val).strip())
        return v / scale if v > 0 else np.nan
    except Exception:
        return np.nan


# ─────────────────────────────────────────────────────────────
# DBから複数セッション取得
# ─────────────────────────────────────────────────────────────

def _load_wood(engine, days_back: int = 60) -> pd.DataFrame:
    """woodchip_chokyo から直近 days_back 日のセッションを全取得"""
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
    q = text("""
        SELECT
            ketto_toroku_bango,
            chokyo_nengappi,
            tracen_kubun,
            course,
            NULLIF(NULLIF(time_gokei_4furlong,'0000'),'')  AS t4f_raw,
            NULLIF(NULLIF(laptime_4furlong,'000'),'')       AS l4f_raw,
            NULLIF(NULLIF(time_gokei_3furlong,'0000'),'')  AS t3f_raw,
            NULLIF(NULLIF(laptime_3furlong,'000'),'')       AS l3f_raw,
            NULLIF(NULLIF(time_gokei_2furlong,'0000'),'')  AS t2f_raw,
            NULLIF(NULLIF(laptime_2furlong,'000'),'')       AS l2f_raw,
            NULLIF(NULLIF(laptime_1furlong,'000'),'')       AS l1f_raw
        FROM woodchip_chokyo
        WHERE chokyo_nengappi >= :cutoff
          AND NULLIF(time_gokei_4furlong,'0000') IS NOT NULL
        ORDER BY ketto_toroku_bango, chokyo_nengappi
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn, params={'cutoff': cutoff})
    except Exception as e:
        print(f"  ⚠️ woodchip取得エラー: {e}")
        return pd.DataFrame(columns=WOOD_COLUMNS)

    df['date']  = pd.to_datetime(df['chokyo_nengappi'], format='%Y%m%d', errors='coerce')
    df['t4f']   = df['t4f_raw'].apply(lambda x: _parse_time(x))
    df['l4f']   = df['l4f_raw'].apply(lambda x: _parse_time(x, 10.0))
    df['t3f']   = df['t3f_raw'].apply(lambda x: _parse_time(x))
    df['l3f']   = df['l3f_raw'].apply(lambda x: _parse_time(x, 10.0))
    df['l1f']   = df['l1f_raw'].apply(lambda x: _parse_time(x, 10.0))
    df['course'] = df['course'].astype(str)
    return df[WOOD_COLUMNS].dropna(subset=['t4f'])


def _load_hanro(engine, days_back: int = 60) -> pd.DataFrame:
    """hanro_chokyo から直近 days_back 日のセッションを全取得"""
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
    q = text("""
        SELECT
            ketto_toroku_bango,
            chokyo_nengappi,
            tracen_kubun,
            NULLIF(NULLIF(time_gokei_4furlong,'0000'),'')  AS t4f_raw,
            NULLIF(NULLIF(lap_time_4furlong,'000'),'')      AS l4f_raw,
            NULLIF(NULLIF(time_gokei_3furlong,'0000'),'')  AS t3f_raw,
            NULLIF(NULLIF(lap_time_3furlong,'000'),'')      AS l3f_raw,
            NULLIF(NULLIF(lap_time_1furlong,'000'),'')      AS l1f_raw
        FROM hanro_chokyo
        WHERE chokyo_nengappi >= :cutoff
          AND NULLIF(time_gokei_4furlong,'0000') IS NOT NULL
        ORDER BY ketto_toroku_bango, chokyo_nengappi
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn, params={'cutoff': cutoff})
    except Exception as e:
        print(f"  ⚠️ hanro取得エラー: {e}")
        return pd.DataFrame(columns=HANRO_COLUMNS)

    df['date'] = pd.to_datetime(df['chokyo_nengappi'], format='%Y%m%d', errors='coerce')
    df['t4f']  = df['t4f_raw'].apply(lambda x: _parse_time(x))
    df['l4f']  = df['l4f_raw'].apply(lambda x: _parse_time(x, 10.0))
    df['t3f']  = df['t3f_raw'].apply(lambda x: _parse_time(x))
    df['l3f']  = df['l3f_raw'].apply(lambda x: _parse_time(x, 10.0))
    df['l1f']  = df['l1f_raw'].apply(lambda x: _parse_time(x, 10.0))
    return df[HANRO_COLUMNS].dropna(subset=['t4f'])


# ─────────────────────────────────────────────────────────────
# セッション集計（馬ごとの特徴量計算）
# ─────────────────────────────────────────────────────────────

def _aggregate_sessions(df: pd.DataFrame, prefix: str,
                        ref_date: pd.Timestamp = None) -> pd.DataFrame:
    """
    馬ごとに複数セッションを集計して特徴量を生成する。
    prefix: 'wood' or 'hanro'
    """
    if df.empty:
        return pd.DataFrame()

    if ref_date is None:
        ref_date = pd.Timestamp.now()

    D14 = ref_date - timedelta(days=14)
    D30 = ref_date - timedelta(days=30)

    results = []
    for horse_id, g in df.groupby('ketto_toroku_bango'):
        g = g.sort_values('date')
        last = g.iloc[-1]

        # 直近30日の最速
        g30 = g[g['date'] >= D30]
        best30 = g30['t4f'].min() if len(g30) > 0 else np.nan

        # 直近14日の本数
        g14 = g[g['date'] >= D14]
        sessions14 = len(g14)

        # タイム改善トレンド（直近2本の差分、負=改善）
        if len(g) >= 2:
            trend = (g.iloc[-1]['t4f'] - g.iloc[-2]['t4f'])
        else:
            trend = 0.0

        # 最終セッションの前後半バランス
        # l1f / (t3f/3) → 1.0 = 均等, >1.0 = 後半が遅い（バテ型), <1.0 = 切れ型
        t3f_avg = last['t3f'] / 3 if pd.notna(last['t3f']) and last['t3f'] > 0 else np.nan
        if pd.notna(last['l1f']) and pd.notna(t3f_avg) and t3f_avg > 0:
            balance = last['l1f'] / t3f_avg
        else:
            balance = np.nan

        # tracen（最終セッションのもの）
        tracen = str(last.get('tracen_kubun', '0'))

        # コース（woodのみ）
        course = str(last.get('course', '0')) if prefix == 'wood' else '0'

        results.append({
            'ketto_toroku_bango':           horse_id,
            f'{prefix}_4f_last':            last['t4f'],
            f'{prefix}_4f_best30':          best30,
            f'{prefix}_trend':              trend,
            f'{prefix}_sessions14d':        sessions14,
            f'{prefix}_pace_balance':       balance,
            f'{prefix}_course':             course,
            f'{prefix}_tracen':             tracen,
        })

    return pd.DataFrame(results)


def _add_zscore(df: pd.DataFrame, col: str, group_col: str) -> pd.Series:
    """
    group_col ごとに col の偏差値（z-score）を計算。
    値が小さい（速い）ほど高いスコアになるよう符号を反転。
    """
    def _zscore(x):
        mu, sigma = x.mean(), x.std()
        if sigma < 1e-6:
            return pd.Series(0.0, index=x.index)
        return -(x - mu) / sigma   # 符号反転: 速い=高スコア

    return df.groupby(group_col)[col].transform(_zscore)


# ─────────────────────────────────────────────────────────────
# 総合スコア計算
# ─────────────────────────────────────────────────────────────

def _compute_overall_score(feat: pd.DataFrame) -> pd.DataFrame:
    """
    wood / hanro の各偏差値・トレンドを統合して
    training_score_v2 と training_form (A/B/C/D) を生成。
    """
    # 偏差値（z-score換算: 平均0, std1 → 0〜1にクリップ）
    def norm(s):
        return s.clip(-3, 3).fillna(0) / 3 * 0.5 + 0.5  # 0〜1

    w_z = norm(feat.get('wood_4f_zscore',  pd.Series(0, index=feat.index)))
    h_z = norm(feat.get('hanro_4f_zscore', pd.Series(0, index=feat.index)))
    w_t = feat.get('wood_trend',  pd.Series(0, index=feat.index)).fillna(0)
    h_t = feat.get('hanro_trend', pd.Series(0, index=feat.index)).fillna(0)
    w_s = feat.get('wood_sessions14d',  pd.Series(0, index=feat.index)).fillna(0).clip(0, 6) / 6
    h_s = feat.get('hanro_sessions14d', pd.Series(0, index=feat.index)).fillna(0).clip(0, 6) / 6

    # トレンドスコア（改善=高）: 負のtrendが良い（タイム短縮）
    trend_score = norm(-w_t * 0.5 + -h_t * 0.5)

    feat['training_score_v2'] = (
        0.35 * (w_z + h_z) / 2 +   # スピード偏差値
        0.30 * trend_score +          # 改善トレンド
        0.20 * (w_s + h_s) / 2 +    # 本数（活発さ）
        0.15 * 0.5                    # ベースライン
    ).clip(0, 1)

    # 調教状態ラベル
    s = feat['training_score_v2']
    feat['training_form'] = pd.cut(
        s, bins=[-np.inf, 0.35, 0.50, 0.65, np.inf],
        labels=['D', 'C', 'B', 'A']
    ).astype(str)

    return feat


# ─────────────────────────────────────────────────────────────
# メイン特徴量生成
# ─────────────────────────────────────────────────────────────

def build_training_features_v2(ref_date: pd.Timestamp = None) -> pd.DataFrame:
    """
    woodchip + hanro の強化版特徴量を馬ID単位で返す。
    """
    engine = create_engine(DB_URL)
    print("    📥 woodchip_chokyo 読み込み中...")
    wood_raw  = _load_wood(engine)
    print(f"    → {len(wood_raw):,}セッション ({_horse_count(wood_raw):,}頭)")

    print("    📥 hanro_chokyo 読み込み中...")
    hanro_raw = _load_hanro(engine)
    print(f"    → {len(hanro_raw):,}セッション ({_horse_count(hanro_raw):,}頭)")

    wood_feat  = _aggregate_sessions(wood_raw,  'wood',  ref_date)
    hanro_feat = _aggregate_sessions(hanro_raw, 'hanro', ref_date)

    # コース別偏差値（wood のみ: course が有意）
    if not wood_feat.empty and 'wood_4f_last' in wood_feat.columns:
        wood_feat['wood_4f_zscore'] = _add_zscore(wood_feat, 'wood_4f_last', 'wood_course')
    if not hanro_feat.empty and 'hanro_4f_last' in hanro_feat.columns:
        hanro_feat['hanro_4f_zscore'] = _add_zscore(
            hanro_feat.assign(dummy='all'), 'hanro_4f_last', 'dummy'
        )

    # 結合
    if wood_feat.empty and hanro_feat.empty:
        return pd.DataFrame()
    elif wood_feat.empty:
        feat = hanro_feat
    elif hanro_feat.empty:
        feat = wood_feat
    else:
        feat = wood_feat.merge(hanro_feat, on='ketto_toroku_bango', how='outer')

    feat = _compute_overall_score(feat)

    keep = ['ketto_toroku_bango',
            'wood_4f_last', 'wood_4f_best30', 'wood_4f_zscore',
            'wood_trend', 'wood_sessions14d', 'wood_pace_balance',
            'hanro_4f_last', 'hanro_4f_best30', 'hanro_4f_zscore',
            'hanro_trend', 'hanro_sessions14d',
            'training_score_v2', 'training_form']
    return feat[[c for c in keep if c in feat.columns]]


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_training_analysis(save: bool = True) -> pd.DataFrame:
    print("\n" + "="*55)
    print("🏋️ 強化版 調教タイム分析 v2")
    print("="*55)

    feat_path = CSV_FEATURES
    if not os.path.exists(feat_path):
        print("  ⚠️ keiba_data_features.csv なし — feature_eng_02 を先に実行")
        return pd.DataFrame()

    print("  📊 調教特徴量を構築中...")
    training_feat = build_training_features_v2()

    if training_feat.empty:
        print("  ⚠️ 調教データなし（DBに woodchip/hanro テーブルがあるか確認）")
        return pd.DataFrame()

    n_horses = len(training_feat)
    form_dist = training_feat['training_form'].value_counts().to_dict() if 'training_form' in training_feat.columns else {}
    print(f"  ✅ {n_horses:,}頭の調教特徴量を生成")
    for g in ['A', 'B', 'C', 'D']:
        cnt = form_dist.get(g, 0)
        bar = '█' * min(cnt * 20 // max(n_horses, 1), 20)
        print(f"    Form {g}: {cnt:5d}頭 {bar}")

    # 上位馬サンプル
    if 'training_score_v2' in training_feat.columns:
        top = training_feat.nlargest(5, 'training_score_v2')
        print("\n  🔥 調教スコア TOP5:")
        for _, r in top.iterrows():
            w4f = f"{r['wood_4f_last']:.1f}s" if pd.notna(r.get('wood_4f_last')) else '-'
            h4f = f"{r['hanro_4f_last']:.1f}s" if pd.notna(r.get('hanro_4f_last')) else '-'
            trnd_w = r.get('wood_trend', 0)
            trnd_h = r.get('hanro_trend', 0)
            trend_str = f"{trnd_w:+.1f}s" if pd.notna(trnd_w) else '-'
            print(f"    [{r.get('training_form','?')}] {r['ketto_toroku_bango']} "
                  f"Wood4F={w4f} Hanro4F={h4f} "
                  f"Trend={trend_str} "
                  f"Score={r['training_score_v2']:.3f}")

    if save:
        # keiba_data_features.csv に結合して上書き
        print("\n  💾 keiba_data_features.csv に追記中...")
        df = pd.read_csv(feat_path, encoding='utf-8-sig',
                         low_memory=False, on_bad_lines='skip')

        # 旧調教列を削除（上書き）
        old_cols = [c for c in df.columns if c in training_feat.columns and c != 'ketto_toroku_bango']
        df = df.drop(columns=old_cols, errors='ignore')

        df['ketto_toroku_bango'] = df['ketto_toroku_bango'].astype(str)
        training_feat['ketto_toroku_bango'] = training_feat['ketto_toroku_bango'].astype(str)
        df = df.merge(training_feat, on='ketto_toroku_bango', how='left')
        df['training_score_v2'] = df.get('training_score_v2', pd.Series(0, index=df.index)).fillna(0)
        df['training_form']     = df.get('training_form', pd.Series('C', index=df.index)).fillna('C')

        df.to_csv(feat_path, index=False, encoding='utf-8-sig')
        print(f"  ✅ 保存完了: {len(df):,}件 × {len(df.columns)}列")

    # 統計サマリー
    if 'wood_4f_last' in training_feat.columns:
        desc = training_feat['wood_4f_last'].dropna().describe()
        print(f"\n  📈 Wood4Fタイム分布: "
              f"中央値={desc['50%']:.1f}s "
              f"最速={desc['min']:.1f}s "
              f"最遅={desc['max']:.1f}s")

    if 'training_score_v2' in training_feat.columns:
        s_desc = training_feat['training_score_v2'].describe()
        print(f"  📈 総合スコア: "
              f"平均={s_desc['mean']:.3f} "
              f"標準偏差={s_desc['std']:.3f}")

    return training_feat


# 後方互換: 旧 build_training_features() の代替
def build_training_features(year_from=2020) -> pd.DataFrame:
    """pace_training_analysis_20.py からの呼び出し互換"""
    return build_training_features_v2()


if __name__ == "__main__":
    run_training_analysis()
