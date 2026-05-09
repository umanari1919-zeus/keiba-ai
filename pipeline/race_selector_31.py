"""
レース価値スコアリングシステム
- 荒れやすいレースを自動検出（オッズエントロピー・頭数・クラス）
- 参戦価値スコアで全レースをランキング
- Grade S/A/B/C で参戦優先度を可視化
"""
import logging
import numpy as np
import pandas as pd
from scipy.stats import entropy as scipy_entropy
from typing import List, Dict
import json, os
from datetime import datetime

log = logging.getLogger(__name__)

BASE_DIR = "D:\\keiba_ai"

# 荒れやすさ指標の重み
UPSET_W = {
    'odds_entropy':   0.30,
    'n_horses':       0.15,
    'race_class':     0.20,
    'surface':        0.10,
    'distance':       0.10,
    'season':         0.15,
}


# ─────────────────────────────────────────────────────────────
# 荒れやすさ指標
# ─────────────────────────────────────────────────────────────

def calc_odds_entropy(odds_list: List[float]) -> float:
    """
    オッズ分布のエントロピー（均等分布=荒れやすい、一強=荒れにくい）
    """
    if len(odds_list) < 2:
        return 0.0
    probs = np.array([1.0 / max(o, 1.0) for o in odds_list], dtype=float)
    probs /= probs.sum()
    return float(scipy_entropy(probs, base=2))


def race_class_upset(class_code) -> float:
    """grade_code → 荒れやすさスコア (0=荒れにくい, 1=荒れやすい)"""
    c = str(class_code).strip()
    mapping = {'A': 0.20, 'B': 0.28, 'C': 0.35, 'L': 0.38,
               ' ': 0.72, '': 0.72, '0': 0.85}
    return mapping.get(c, 0.60)


_MAIN_DISTANCES = {1200, 1400, 1600, 1800, 2000, 2400}

_SEASON_UPSET = {
    1: 0.45, 2: 0.40, 3: 0.58, 4: 0.52,
    5: 0.62, 6: 0.80, 7: 0.72, 8: 0.72,
    9: 0.80, 10: 0.62, 11: 0.50, 12: 0.42
}


def score_upset(race_df: pd.DataFrame) -> float:
    """1レースの荒れやすさスコア 0〜1"""
    s = 0.0
    n = len(race_df)

    # オッズエントロピー
    if 'tansho_odds' in race_df.columns:
        odds = pd.to_numeric(race_df['tansho_odds'], errors='coerce').dropna() / 10
        ent  = calc_odds_entropy(odds.tolist())
        max_ent = np.log2(max(n, 2))
        s += UPSET_W['odds_entropy'] * (ent / max_ent if max_ent > 0 else 0)

    # 頭数（4頭=0, 18頭=1）
    n_score = np.clip((n - 4) / 14, 0, 1)
    s += UPSET_W['n_horses'] * n_score

    # レースクラス（grade_code）
    gc = str(race_df.get('grade_code', pd.Series([''])).iloc[0]).strip() if n > 0 else ''
    s += UPSET_W['race_class'] * race_class_upset(gc)

    # 芝/ダート（track_code の多様性）
    if 'track_code' in race_df.columns:
        tc_variety = min(1.0, race_df['track_code'].nunique() / 2)
        s += UPSET_W['surface'] * tc_variety
    else:
        s += UPSET_W['surface'] * 0.5

    # 距離（非主流距離ほど荒れやすい）
    if 'kyori' in race_df.columns:
        kyori = int(race_df['kyori'].iloc[0]) if n > 0 else 1600
        s += UPSET_W['distance'] * (0.30 if kyori in _MAIN_DISTANCES else 0.75)
    else:
        s += UPSET_W['distance'] * 0.50

    # 季節
    if 'race_month' in race_df.columns:
        month = int(race_df['race_month'].iloc[0]) if n > 0 else datetime.now().month
    else:
        month = datetime.now().month
    s += UPSET_W['season'] * _SEASON_UPSET.get(month, 0.55)

    return round(min(1.0, s), 4)


def score_value(race_df: pd.DataFrame, upset: float) -> float:
    """
    参戦価値スコア = EV 50% + 荒れやすさ 30% + 予測可能性 20%
    EV データがない場合は荒れやすさ単独スコアにフォールバック。
    """
    ev_score = 0.0
    has_ev = False

    if 'expected_value' in race_df.columns:
        max_ev = race_df['expected_value'].max()
        if max_ev > 0:
            ev_score = np.clip(max_ev / 0.5, 0, 1)
            has_ev = True
    elif 'win_probability' in race_df.columns and 'tansho_odds' in race_df.columns:
        p  = pd.to_numeric(race_df['win_probability'], errors='coerce').fillna(0)
        od = pd.to_numeric(race_df['tansho_odds'],     errors='coerce').fillna(0) / 10
        max_ev = (p * od - 1.0).max()
        if max_ev > 0:
            ev_score = np.clip(max_ev / 0.5, 0, 1)
            has_ev = True

    if not has_ev:
        # EV なし: オッズ分散スコアだけで評価
        # upset=0.8 → value=0.80, upset=0.3 → value=0.30
        return round(upset, 4)

    predictability = 1.0 - upset
    value = 0.50 * ev_score + 0.30 * upset + 0.20 * predictability
    return round(value, 4)


# ─────────────────────────────────────────────────────────────
# レースランキング
# ─────────────────────────────────────────────────────────────

def rank_races(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """全レースをスコアリングしてランキング DataFrame を返す"""
    df = df[df['kaisai_nen'] == year].fillna(0)
    if 'race_code' not in df.columns or len(df) == 0:
        return pd.DataFrame()

    rows = []
    for rc, rdf in df.groupby('race_code'):
        n   = len(rdf)
        ups = score_upset(rdf)
        val = score_value(rdf, ups)

        odds_col = pd.to_numeric(rdf.get('tansho_odds', pd.Series([])), errors='coerce').dropna() / 10
        fav_odds = round(float(odds_col.min()), 1) if len(odds_col) > 0 else 0.0
        max_odds = round(float(odds_col.max()), 1) if len(odds_col) > 0 else 0.0

        rows.append({
            'race_code':   str(rc),
            'n_horses':    n,
            'fav_odds':    fav_odds,
            'max_odds':    max_odds,
            'upset_score': ups,
            'value_score': val,
            'grade':       'S' if val >= 0.70 else 'A' if val >= 0.55 else
                           'B' if val >= 0.40 else 'C',
        })

    result = pd.DataFrame(rows).sort_values('value_score', ascending=False)
    return result.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_race_selector(year: int = None) -> dict:
    year = year or datetime.now().year
    log.info("レース価値スコアリングシステム 開始")

    feat_path = f"{BASE_DIR}\\keiba_data_features.csv"
    if not os.path.exists(feat_path):
        log.warning("特徴量ファイルなし: %s", feat_path)
        return {}

    df = pd.read_csv(feat_path, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
    ranked = rank_races(df, year)

    if ranked.empty:
        log.warning("ランキング生成失敗")
        return {}

    log.info("分析レース数: %d R", len(ranked))

    grade_dist = ranked['grade'].value_counts()
    for g in ['S', 'A', 'B', 'C']:
        cnt = int(grade_dist.get(g, 0))
        log.info("Grade %s: %4d R", g, cnt)

    top = ranked[ranked['grade'].isin(['S', 'A'])].head(10)
    if not top.empty:
        log.info("参戦推奨レース TOP%d:", len(top))
        for _, r in top.iterrows():
            log.info("  [%s] %s (%d頭) 荒れ=%.2f 価値=%.3f オッズ%.1f〜%.1f倍",
                     r['grade'], r['race_code'], r['n_horses'],
                     r['upset_score'], r['value_score'], r['fav_odds'], r['max_odds'])

    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
    ranked.to_csv(f"{BASE_DIR}\\data\\race_ranking_{year}.csv",
                  index=False, encoding='utf-8-sig')
    with open(f"{BASE_DIR}\\data\\race_selector_{year}.json", 'w', encoding='utf-8') as f:
        json.dump(ranked.head(50).to_dict('records'), f,
                  ensure_ascii=False, indent=2, default=str)
    log.info("保存: data/race_ranking_%d.csv", year)

    return {
        'total_races': len(ranked),
        'grade_s':  int(grade_dist.get('S', 0)),
        'grade_a':  int(grade_dist.get('A', 0)),
        'top_races': top.head(5).to_dict('records'),
    }


if __name__ == "__main__":
    run_race_selector()
