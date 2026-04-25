"""
新馬戦強化分析 (debut_analysis_39)
────────────────────────────────────
新馬戦は過去成績ゼロ → 調教・血統・騎手/調教師の新馬戦実績が唯一の情報源

出力特徴量 (keiba_data_features.csv に追記):
  is_debut               1=新馬戦 0=それ以外
  jockey_debut_win_rate  騎手の新馬戦通算勝率
  trainer_debut_win_rate 調教師の新馬戦通算勝率
  sire_debut_win_rate    父馬の新馬戦勝率
  debut_weight_bonus     馬体重ボーナス (適正±20kgで+0, 大きく外れると減点)
  debut_score            新馬戦総合スコア (0〜1)

新馬戦確信度フォーミュラ (EVAgentで is_debut=1 のとき上書き):
  0.35 × training_score_v2   調教（最重要）
  0.25 × blood / sire_debut  血統・父系新馬実績
  0.20 × trainer_debut_rate  調教師の新馬戦得意度
  0.15 × jockey_debut_rate   騎手の新馬戦得意度
  0.05 × odds_signal_boost   オッズシグナル

依存: race_shosai, umagoto_race_joho, keiba_data_features.csv
"""

import os
import json
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime

BASE_DIR = "D:\\keiba_ai"
DB_URL   = "postgresql://postgres:trust@localhost:5433/mykeibadb"
CACHE_PATH = f"{BASE_DIR}\\data\\debut_race_codes.json"

MIN_DEBUT_RACES = 5   # 統計の信頼性確保のための最低出走数


# ─────────────────────────────────────────────────────────────
# 新馬戦race_code取得（キャッシュあり）
# ─────────────────────────────────────────────────────────────

def _load_debut_race_codes(engine, use_cache: bool = True) -> set:
    """race_shosai から新馬戦 race_code の集合を取得する。"""
    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)

    if use_cache and os.path.exists(CACHE_PATH):
        age_h = (datetime.now().timestamp() - os.path.getmtime(CACHE_PATH)) / 3600
        if age_h < 24 * 7:  # 1週間キャッシュ
            with open(CACHE_PATH, encoding='utf-8') as f:
                codes = set(json.load(f))
            print(f"    📂 キャッシュ使用: {len(codes):,}件の新馬戦race_code")
            return codes

    q = text("""
        SELECT DISTINCT race_code
        FROM race_shosai
        WHERE kyoso_joken_code_2sai = '701'
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn)
        codes = set(df['race_code'].astype(str).tolist())
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(list(codes), f)
        print(f"    🔍 新馬戦レース取得: {len(codes):,}件")
        return codes
    except Exception as e:
        print(f"  ⚠️ 新馬戦race_code取得エラー: {e}")
        return set()


# ─────────────────────────────────────────────────────────────
# 新馬戦出走データ取得
# ─────────────────────────────────────────────────────────────

def _load_debut_results(engine, debut_codes: set,
                        year_from: int = 2010) -> pd.DataFrame:
    """新馬戦の全出走結果を取得する（年フィルタあり）。"""
    q = text("""
        SELECT
            race_code,
            ketto_toroku_bango,
            bamei,
            kishu_code,
            chokyoshi_code,
            kakutei_chakujun,
            bataiju,
            barei,
            tansho_odds,
            kaisai_nen
        FROM umagoto_race_joho
        WHERE kaisai_nen >= :year_from
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn, params={'year_from': str(year_from)})
        # 新馬戦のみにフィルタ
        df = df[df['race_code'].astype(str).isin(debut_codes)].copy()
        df['kakutei_chakujun'] = pd.to_numeric(df['kakutei_chakujun'], errors='coerce')
        df['is_winner'] = (df['kakutei_chakujun'] == 1).astype(int)
        print(f"    → 新馬戦出走: {len(df):,}頭 / {df['race_code'].nunique():,}レース ({year_from}年〜)")
        return df
    except Exception as e:
        print(f"  ⚠️ 新馬戦出走データ取得エラー: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# 騎手の新馬戦勝率
# ─────────────────────────────────────────────────────────────

def _compute_jockey_debut_rates(df_debut: pd.DataFrame) -> pd.Series:
    """騎手コード → 新馬戦勝率 (最低5頭以上)"""
    g = df_debut.groupby('kishu_code').agg(
        races=('is_winner', 'count'),
        wins=('is_winner', 'sum')
    )
    g = g[g['races'] >= MIN_DEBUT_RACES]
    return (g['wins'] / g['races']).rename('jockey_debut_win_rate')


# ─────────────────────────────────────────────────────────────
# 調教師の新馬戦勝率
# ─────────────────────────────────────────────────────────────

def _compute_trainer_debut_rates(df_debut: pd.DataFrame) -> pd.Series:
    """調教師コード → 新馬戦勝率 (最低5頭以上)"""
    g = df_debut.groupby('chokyoshi_code').agg(
        races=('is_winner', 'count'),
        wins=('is_winner', 'sum')
    )
    g = g[g['races'] >= MIN_DEBUT_RACES]
    return (g['wins'] / g['races']).rename('trainer_debut_win_rate')


# ─────────────────────────────────────────────────────────────
# 父馬の新馬戦勝率（特徴量CSVの chichi 列を利用）
# ─────────────────────────────────────────────────────────────

def _compute_sire_debut_rates(df_debut: pd.DataFrame,
                               df_feat: pd.DataFrame) -> pd.Series:
    """父馬名 → 新馬戦勝率 (最低5頭以上)。bamei 経由でマッピング。"""
    if 'chichi' not in df_feat.columns or 'bamei' not in df_feat.columns:
        return pd.Series(dtype=float, name='sire_debut_win_rate')

    # features CSV: bamei → chichi のマップ（chichi が '0' でない行のみ）
    feat_valid = df_feat[
        df_feat['chichi'].astype(str).str.strip().ne('0') &
        df_feat['chichi'].notna()
    ]
    sire_map = (
        feat_valid[['bamei', 'chichi']]
        .dropna()
        .drop_duplicates('bamei')
        .set_index('bamei')['chichi']
        .astype(str)
    )

    df2 = df_debut.copy()
    df2['chichi'] = df2['bamei'].astype(str).map(sire_map)

    g = df2.dropna(subset=['chichi']).groupby('chichi').agg(
        races=('is_winner', 'count'),
        wins=('is_winner', 'sum')
    )
    g = g[g['races'] >= MIN_DEBUT_RACES]
    return (g['wins'] / g['races']).rename('sire_debut_win_rate')


# ─────────────────────────────────────────────────────────────
# 馬体重ボーナス（新馬戦は体の発達度が重要）
# ─────────────────────────────────────────────────────────────

def _weight_bonus(bataiju_raw) -> float:
    """
    新馬戦での適正体重ボーナス。
    - 牡馬: 460〜500kgが理想
    - 牝馬: 440〜480kgが理想
    体重が多いほど発育が進んでいる（新馬戦では有利）
    """
    try:
        w = float(bataiju_raw)
    except (ValueError, TypeError):
        return 0.0
    if w <= 0:
        return 0.0
    # 460〜500が最良 → +1.0、極端に軽い(<420)か重い(>540)でペナルティ
    if 460 <= w <= 500:
        return 1.0
    elif 440 <= w < 460 or 500 < w <= 520:
        return 0.7
    elif 420 <= w < 440 or 520 < w <= 540:
        return 0.4
    else:
        return 0.1


# ─────────────────────────────────────────────────────────────
# 特徴量計算・CSV結合
# ─────────────────────────────────────────────────────────────

def compute_debut_features(df_feat: pd.DataFrame,
                            debut_codes: set,
                            j_rates: pd.Series,
                            t_rates: pd.Series,
                            s_rates: pd.Series) -> pd.DataFrame:
    """
    keiba_data_features.csv に新馬戦特化特徴量を追加する。
    """
    df = df_feat.copy()
    rc = df['race_code'].astype(str)

    # ── is_debut フラグ ────────────────────────────────────
    df['is_debut'] = rc.isin(debut_codes).astype(int)

    # ── 騎手の新馬戦勝率 ──────────────────────────────────
    j_map = j_rates.to_dict()
    mean_j = j_rates.mean() if len(j_rates) > 0 else 0.10
    df['jockey_debut_win_rate'] = (
        df['kishu_code'].astype(str).map(j_map).fillna(mean_j)
    )

    # ── 調教師の新馬戦勝率 ────────────────────────────────
    t_map = t_rates.to_dict()
    mean_t = t_rates.mean() if len(t_rates) > 0 else 0.10
    df['trainer_debut_win_rate'] = (
        df['chokyoshi_code'].astype(str).map(t_map).fillna(mean_t)
    )

    # ── 父馬の新馬戦勝率 ──────────────────────────────────
    if 'chichi' in df.columns and len(s_rates) > 0:
        s_map = s_rates.to_dict()
        mean_s = s_rates.mean()
        df['sire_debut_win_rate'] = (
            df['chichi'].astype(str).map(s_map).fillna(mean_s)
        )
    else:
        df['sire_debut_win_rate'] = 0.10

    # ── 馬体重ボーナス ────────────────────────────────────
    df['debut_weight_bonus'] = df['bataiju'].apply(_weight_bonus)

    # ── 新馬戦総合スコア (is_debut=1 の行のみ意味あり) ──────
    # 調教(30%) + 血統(25%) + 調教師新馬(20%) + 騎手新馬(15%) + 体重(10%)
    tv2 = df.get('training_score_v2', pd.Series(0.0, index=df.index)).fillna(0)
    sire = df['sire_debut_win_rate'].fillna(0.10)
    tr   = df['trainer_debut_win_rate'].fillna(mean_t if 'mean_t' in dir() else 0.10)
    jo   = df['jockey_debut_win_rate'].fillna(mean_j if 'mean_j' in dir() else 0.10)
    wt   = df['debut_weight_bonus'].fillna(0.5)

    df['debut_score'] = (
        0.30 * tv2.clip(0, 1)
      + 0.25 * (sire / sire.clip(lower=0.01).max()).clip(0, 1)
      + 0.20 * (tr  / tr.clip(lower=0.01).max()).clip(0, 1)
      + 0.15 * (jo  / jo.clip(lower=0.01).max()).clip(0, 1)
      + 0.10 * wt
    ).clip(0, 1)

    # 非新馬戦は debut_score を 0 に
    df.loc[df['is_debut'] == 0, 'debut_score'] = 0.0

    return df


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

DEBUT_FEATURE_COLS = [
    'is_debut', 'jockey_debut_win_rate', 'trainer_debut_win_rate',
    'sire_debut_win_rate', 'debut_weight_bonus', 'debut_score',
]


def run_debut_analysis(year_from: int = 2010, save: bool = True) -> pd.DataFrame:
    print("\n" + "="*55)
    print("🐴 新馬戦強化分析 (debut_analysis_39)")
    print("="*55)

    feat_path = f"{BASE_DIR}\\keiba_data_features.csv"
    if not os.path.exists(feat_path):
        print("  ⚠️ keiba_data_features.csv なし")
        return pd.DataFrame()

    engine = create_engine(DB_URL)

    # ─ STEP 1: 新馬戦race_code取得 ─
    print("  📋 STEP 1: 新馬戦race_code取得...")
    debut_codes = _load_debut_race_codes(engine)
    if not debut_codes:
        print("  ⚠️ 新馬戦データなし（特徴量CSVにフォールバック）")
        # フォールバック: barei<=2 かつ prev_chakujun欠損 で代用
        df_feat = pd.read_csv(feat_path, encoding='utf-8-sig',
                              low_memory=False, on_bad_lines='skip')
        debut_codes = set(
            df_feat[
                (pd.to_numeric(df_feat['barei'], errors='coerce') <= 2) &
                (df_feat.get('prev_chakujun', pd.Series()).isna() |
                 (df_feat.get('prev_chakujun', pd.Series()) == 0))
            ]['race_code'].astype(str).unique()
        )
        print(f"    フォールバック: {len(debut_codes):,}件の新馬戦race_code（推定）")

    # ─ STEP 2: 新馬戦出走データ取得 ─
    print("  📊 STEP 2: 新馬戦出走データ取得...")
    df_debut = _load_debut_results(engine, debut_codes, year_from)

    # ─ STEP 3: 特徴量CSV読み込み ─
    print("  📂 STEP 3: 特徴量CSV読み込み...")
    df_feat = pd.read_csv(feat_path, encoding='utf-8-sig',
                          low_memory=False, on_bad_lines='skip')
    print(f"    → {len(df_feat):,}行 × {len(df_feat.columns)}列")

    # ─ STEP 4: 統計計算 ─
    if not df_debut.empty:
        print("  🔧 STEP 4: 騎手・調教師・父馬の新馬戦勝率計算...")
        j_rates = _compute_jockey_debut_rates(df_debut)
        t_rates = _compute_trainer_debut_rates(df_debut)
        s_rates = _compute_sire_debut_rates(df_debut, df_feat)

        print(f"    騎手: {len(j_rates)}名  調教師: {len(t_rates)}名  "
              f"父馬: {len(s_rates)}頭")

        # TOP調教師（新馬戦得意）
        top_t = t_rates.nlargest(5)
        print("\n  🏆 新馬戦TOP5調教師:")
        for code, wr in top_t.items():
            print(f"    {code}: {wr:.1%}")

        top_s = s_rates.nlargest(5)
        print("\n  🐎 新馬戦TOP5父馬:")
        for name, wr in top_s.items():
            print(f"    {name}: {wr:.1%}")
    else:
        print("  ⚠️ 新馬戦出走データなし（デフォルト値を使用）")
        j_rates = pd.Series(dtype=float, name='jockey_debut_win_rate')
        t_rates = pd.Series(dtype=float, name='trainer_debut_win_rate')
        s_rates = pd.Series(dtype=float, name='sire_debut_win_rate')

    # ─ STEP 5: 特徴量計算 ─
    print("\n  ⚙️ STEP 5: 新馬戦特徴量計算...")
    df_out = compute_debut_features(df_feat, debut_codes, j_rates, t_rates, s_rates)

    debut_rows = df_out[df_out['is_debut'] == 1]
    print(f"    is_debut=1: {len(debut_rows):,}行  "
          f"debut_score≥0.5: {(debut_rows['debut_score']>=0.5).sum()}頭")
    if len(debut_rows) > 0:
        sc = debut_rows['debut_score']
        print(f"    debut_score: 平均={sc.mean():.3f} 最高={sc.max():.3f} "
              f"中央値={sc.median():.3f}")

    # ─ STEP 6: CSV保存 ─
    if save:
        print(f"\n  💾 STEP 6: keiba_data_features.csv に追記中...")
        for col in DEBUT_FEATURE_COLS:
            if col in df_out.columns:
                df_feat[col] = df_out[col].values

        df_feat.to_csv(feat_path, index=False, encoding='utf-8-sig')
        print(f"  ✅ 保存完了: {len(df_feat):,}件 × {len(df_feat.columns)}列")

    return df_out[['race_code', 'ketto_toroku_bango'] + DEBUT_FEATURE_COLS
                  if 'ketto_toroku_bango' in df_out.columns else DEBUT_FEATURE_COLS]


if __name__ == "__main__":
    run_debut_analysis()
