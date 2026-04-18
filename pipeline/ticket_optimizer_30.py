"""
馬券種別自動選択システム
- 単勝/複勝/ワイド/馬連/三連複のEVを推定・比較
- 出走頭数・オッズ・勝率に応じて最適馬券種を自動選択
- Harville モデルによる複合馬券の確率推定
"""
import numpy as np
import pandas as pd
from collections import Counter
from typing import List, Dict, Optional
import json, os
from datetime import datetime

BASE_DIR = "D:\\keiba_ai"

# JRA公式控除率
TAKEOUT = {
    'tansho':     0.200,
    'fukusho':    0.200,
    'umaren':     0.225,
    'wide':       0.225,
    'sanrenfuku': 0.225,
}
PAYOUT = {k: 1 - v for k, v in TAKEOUT.items()}

KELLY_FRAC = 0.10  # 1/10ケリー（WF検証DD64%→安全係数に引き下げ）


# ─────────────────────────────────────────────────────────────
# 確率推定
# ─────────────────────────────────────────────────────────────

def estimate_place_prob(p_win: float, n: int) -> float:
    """単勝確率から複勝確率（3着以内）をHarville近似で推定"""
    if n <= 3:
        return min(0.99, p_win * n)
    if n >= 8:
        return min(0.92, p_win * 3.2)
    if n >= 5:
        return min(0.92, p_win * 2.6)
    return min(0.99, p_win * n)


def harville_p2(p1: float, p2: float) -> float:
    """馬1・馬2が1着2着に入る確率（Harville）"""
    q1, q2 = 1 - p1, 1 - p2
    if q1 <= 0 or q2 <= 0:
        return 0.0
    return p1 * p2 / q1 + p2 * p1 / q2


def harville_p3(p1: float, p2: float, p3: float) -> float:
    """3頭が3着以内に入る確率（Harville簡略版）"""
    q1, q2, q3 = 1 - p1, 1 - p2, 1 - p3
    eps = 1e-6
    # 全並び替えの和
    total = 0.0
    for pi, qi, pj, qj, pk in [
        (p1, q1, p2, q2, p3), (p1, q1, p3, q3, p2),
        (p2, q2, p1, q1, p3), (p2, q2, p3, q3, p1),
        (p3, q3, p1, q1, p2), (p3, q3, p2, q2, p1),
    ]:
        if qi > eps and (qi - pj) > eps:
            total += pi * pj / qi * pk / (qi - pj)
    return min(total, 0.99)


# ─────────────────────────────────────────────────────────────
# オッズ推定
# ─────────────────────────────────────────────────────────────

def est_fukusho_odds(p_win: float, tansho_odds: float, n: int) -> float:
    p_place = estimate_place_prob(p_win, n)
    theoretical = PAYOUT['fukusho'] / max(p_place, 0.01)
    # 実際の複勝オッズは 1.1〜tansho_odds*0.35 程度
    return round(min(max(theoretical, 1.1), max(tansho_odds * 0.35 + 0.5, 1.2)), 1)


def est_umaren_odds(p1: float, p2: float) -> float:
    p = harville_p2(p1, p2)
    return round(PAYOUT['umaren'] / max(p, 0.001), 1)


def est_wide_odds(p1: float, p2: float, n: int) -> float:
    pp1 = estimate_place_prob(p1, n)
    pp2 = estimate_place_prob(p2, n)
    # 両方3着以内: 粗い相関補正
    p = pp1 * pp2 * 0.55
    return round(PAYOUT['wide'] / max(p, 0.001), 1)


def est_sanrenfuku_odds(p1: float, p2: float, p3: float, n: int) -> float:
    p = harville_p3(p1, p2, p3)
    return round(PAYOUT['sanrenfuku'] / max(p, 0.0001), 1)


# ─────────────────────────────────────────────────────────────
# EV計算・最適馬券選択
# ─────────────────────────────────────────────────────────────

def calc_all_ticket_ev(candidates: List[Dict], n_horses: int) -> Dict[str, Dict]:
    """全馬券種の推定EV を計算して返す"""
    if not candidates:
        return {}

    c = sorted(candidates, key=lambda x: x.get('expected_value', 0), reverse=True)
    c1 = c[0]
    p1   = float(c1.get('win_probability', 0.1))
    od1  = float(c1.get('odds', 10.0))

    results: Dict[str, Dict] = {}

    # 単勝
    ev_t = p1 * od1 - 1.0
    results['tansho'] = {
        'ticket_type': '単勝', 'horses': [c1.get('bamei', '')],
        'p': p1, 'est_odds': od1, 'ev': ev_t,
        'note': f"EV={ev_t*100:+.1f}%"
    }

    # 複勝
    pp1   = estimate_place_prob(p1, n_horses)
    od_f  = est_fukusho_odds(p1, od1, n_horses)
    ev_f  = pp1 * od_f - 1.0
    results['fukusho'] = {
        'ticket_type': '複勝', 'horses': [c1.get('bamei', '')],
        'p': pp1, 'est_odds': od_f, 'ev': ev_f,
        'note': f"P(3着以内)={pp1*100:.1f}% EV={ev_f*100:+.1f}%"
    }

    if len(c) >= 2:
        c2  = c[1]
        p2  = float(c2.get('win_probability', 0.05))

        # 馬連
        od_u = est_umaren_odds(p1, p2)
        p_u  = PAYOUT['umaren'] / max(od_u, 1)
        ev_u = p_u * od_u - 1.0
        results['umaren'] = {
            'ticket_type': '馬連',
            'horses': [c1.get('bamei', ''), c2.get('bamei', '')],
            'p': p_u, 'est_odds': od_u, 'ev': ev_u,
            'note': f"推定{od_u:.1f}倍 EV={ev_u*100:+.1f}%"
        }

        # ワイド
        od_w = est_wide_odds(p1, p2, n_horses)
        p_w  = PAYOUT['wide'] / max(od_w, 1)
        ev_w = p_w * od_w - 1.0
        results['wide'] = {
            'ticket_type': 'ワイド',
            'horses': [c1.get('bamei', ''), c2.get('bamei', '')],
            'p': p_w, 'est_odds': od_w, 'ev': ev_w,
            'note': f"推定{od_w:.1f}倍 EV={ev_w*100:+.1f}%"
        }

        if len(c) >= 3:
            c3 = c[2]
            p3 = float(c3.get('win_probability', 0.03))
            od_3f = est_sanrenfuku_odds(p1, p2, p3, n_horses)
            p_3f  = PAYOUT['sanrenfuku'] / max(od_3f, 1)
            ev_3f = p_3f * od_3f - 1.0
            results['sanrenfuku'] = {
                'ticket_type': '三連複',
                'horses': [c1.get('bamei', ''), c2.get('bamei', ''), c3.get('bamei', '')],
                'p': p_3f, 'est_odds': od_3f, 'ev': ev_3f,
                'note': f"推定{od_3f:.1f}倍 EV={ev_3f*100:+.1f}%"
            }

    return results


# 単勝は直接確率精度が乗るので補正ボーナス
_TANSHO_BONUS = 0.02

# 馬券種ごとのケリー倍率（複勝はより安全に多く打てる）
_KELLY_MULT = {'tansho': 1.0, 'fukusho': 1.5, 'umaren': 0.8,
               'wide': 0.7, 'sanrenfuku': 0.5}


def select_optimal_ticket(candidates: List[Dict], bankroll: float,
                           race_code: str, n_horses: int = 12) -> Dict:
    """最高EVの馬券種を選択してベット額も算出する"""
    ev_map = calc_all_ticket_ev(candidates, n_horses)
    if not ev_map:
        return {}

    # EVスコア（単勝にボーナス）
    scores = {k: v['ev'] + (_TANSHO_BONUS if k == 'tansho' else 0)
              for k, v in ev_map.items()}
    best_key = max(scores, key=lambda k: scores[k])
    best = ev_map[best_key]

    # ケリー計算
    p, b = best['p'], best['est_odds'] - 1
    if p > 0 and b > 0:
        k_frac = max(0, (p * b - (1 - p)) / b) * KELLY_FRAC
        k_frac *= _KELLY_MULT.get(best_key, 1.0)
        bet = max(100, round(bankroll * k_frac / 100) * 100)
        bet = min(bet, int(bankroll * 0.05))
    else:
        bet = 100

    return {
        **best,
        'ticket_key':      best_key,
        'race_code':       race_code,
        'recommended_bet': bet,
        'all_ev': {k: round(v['ev'] * 100, 1) for k, v in ev_map.items()},
    }


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_ticket_optimizer(year: int = None, bankroll: float = None) -> dict:
    year = year or datetime.now().year
    print("\n" + "="*55)
    print("🎟️ 馬券種別自動選択システム")
    print("="*55)

    if bankroll is None:
        br_path = f"{BASE_DIR}\\data\\bankroll.json"
        if os.path.exists(br_path):
            with open(br_path, encoding='utf-8') as f:
                d = json.load(f)
            bankroll = float(d.get('bankroll', d.get('current', 100_000)))
        else:
            bankroll = 100_000
    print(f"  💰 現在資金: {bankroll:,.0f}円")

    feat_path = f"{BASE_DIR}\\keiba_data_features.csv"
    if not os.path.exists(feat_path):
        print("  ⚠️ 特徴量ファイルなし")
        return {}

    df = pd.read_csv(feat_path, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
    df = df[df['kaisai_nen'] == year].fillna(0)
    print(f"  📊 {year}年データ: {len(df):,}件")

    if 'race_code' not in df.columns:
        print("  ⚠️ race_code なし")
        return {}

    recommendations = []
    for rc, race_df in list(df.groupby('race_code'))[:30]:
        n_h = len(race_df)
        candidates = []
        for _, row in race_df.iterrows():
            odds = float(row.get('tansho_odds', 0)) / 10
            wp   = float(row.get('win_probability', 0))
            if odds < 5.0 or wp <= 0:
                continue
            candidates.append({
                'bamei':           str(row.get('bamei', '')),
                'odds':            odds,
                'win_probability': wp,
                'expected_value':  wp * odds - 1.0,
            })
        if not candidates:
            continue
        rec = select_optimal_ticket(candidates, bankroll, str(rc), n_h)
        if rec:
            recommendations.append(rec)

    dist = Counter(r.get('ticket_type', '?') for r in recommendations)
    if recommendations:
        n = len(recommendations)
        print(f"\n  🎟️ 推奨馬券種分布 ({n}R):")
        for t, cnt in dist.most_common():
            bar = '█' * (cnt * 20 // n)
            print(f"    {t:5s}: {cnt:3d}R ({cnt/n*100:4.0f}%) {bar}")

    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
    out_path = f"{BASE_DIR}\\data\\ticket_recommendations_{year}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(recommendations[:50], f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  💾 保存: {out_path}")

    return {'n_analyzed': len(recommendations), 'dist': dict(dist)}


if __name__ == "__main__":
    run_ticket_optimizer()
