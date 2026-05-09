"""
多点買いポートフォリオ最適化
- 同一レース内複数馬への最適配分（期待対数成長率最大化）
- 相関調整ケリー基準
- 1日総投入上限・1レース上限管理
"""
import logging
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import List, Dict, Tuple
import json, os
from datetime import datetime

log = logging.getLogger(__name__)

BASE_DIR = "D:\\keiba_ai"

MAX_HORSES_PER_RACE  = 3     # 1レース最大買い点数
MAX_PORTFOLIO_RATIO  = 0.20  # 1日総投入上限（資金の20%）
MAX_RACE_RATIO       = 0.10  # 1レース上限（資金の10%）
KELLY_FRACTION       = 0.10  # 1/10ケリー（WF検証DD64%→安全係数に引き下げ）


def kelly_single(p: float, b: float) -> float:
    """単一ベットのフラクショナルケリー比率 (b = net odds = odds-1)"""
    if b <= 0 or p <= 0 or p >= 1:
        return 0.0
    k = (p * b - (1 - p)) / b
    return max(0.0, k * KELLY_FRACTION)


def expected_log_growth(fractions: np.ndarray, probs: np.ndarray,
                         net_odds: np.ndarray) -> float:
    """
    同一レース内で複数馬に同時ベットする期待対数成長率。
    各馬は互いに排他（同一レース）なので1頭しか勝てない。
    """
    total_bet = fractions.sum()
    if total_bet >= 1.0:
        return -1e9

    growth = 0.0
    p_all_lose = 1.0

    for i in range(len(fractions)):
        p_i = probs[i]
        p_all_lose -= p_i
        # 馬iが勝つシナリオ: 他の馬の掛け金は没収、馬iは net_odds[i] 倍
        bal = 1.0 - total_bet + fractions[i] * net_odds[i]
        if bal <= 0:
            return -1e9
        growth += p_i * np.log(max(bal, 1e-9))

    # 全馬外れ
    p_all_lose = max(0.0, p_all_lose)
    bal_lose = 1.0 - total_bet
    if bal_lose > 0:
        growth += p_all_lose * np.log(max(bal_lose, 1e-9))

    return growth


def optimize_race_bets(candidates: List[Dict], bankroll: float) -> List[Dict]:
    """
    1レース内の複数候補に対する最適投入額を計算。
    EV上位 MAX_HORSES_PER_RACE 頭に絞って最適化。
    """
    if not candidates:
        return []

    top = sorted(candidates, key=lambda x: x.get('expected_value', 0), reverse=True)
    top = top[:MAX_HORSES_PER_RACE]

    # 単独ベットは通常ケリーで処理
    if len(top) == 1:
        c = top[0]
        p, b = c['win_probability'], c['odds'] - 1
        frac = kelly_single(p, b)
        bet  = max(100, round(bankroll * frac / 100) * 100)
        bet  = min(bet, int(bankroll * MAX_RACE_RATIO))
        return [{**c, 'portfolio_bet': bet, 'portfolio_fraction': round(frac, 4)}]

    probs    = np.array([c['win_probability'] for c in top])
    net_odds = np.array([c['odds'] - 1        for c in top])
    n        = len(top)

    x0 = np.array([kelly_single(p, b) for p, b in zip(probs, net_odds)])
    # 初期値が MAX_RACE_RATIO を超えないよう正規化
    if x0.sum() > MAX_RACE_RATIO * 0.8:
        x0 = x0 / x0.sum() * (MAX_RACE_RATIO * 0.6)

    constraints = [{'type': 'ineq', 'fun': lambda x: MAX_RACE_RATIO - x.sum()}]
    bounds = [(0.0, MAX_RACE_RATIO)] * n

    res = minimize(
        lambda x: -expected_log_growth(x, probs, net_odds),
        x0,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints,
        options={'maxiter': 300, 'ftol': 1e-10}
    )

    fracs = np.clip(res.x, 0.0, MAX_RACE_RATIO)

    output = []
    for i, c in enumerate(top):
        frac = float(fracs[i])
        if frac < 0.001:
            continue
        bet = max(100, round(bankroll * frac / 100) * 100)
        output.append({**c, 'portfolio_bet': bet, 'portfolio_fraction': round(frac, 4)})

    return output


def portfolio_optimize_all(picks: List[Dict], bankroll: float) -> Tuple[List[Dict], Dict]:
    """
    全候補レースの多点買いポートフォリオを一括最適化。
    Returns: (optimized_picks, summary_dict)
    """
    races: Dict[str, List[Dict]] = {}
    for p in picks:
        rc = p.get('race_code', 'unknown')
        races.setdefault(rc, []).append(p)

    optimized  = []
    total_bet  = 0

    for rc, cands in races.items():
        race_picks  = optimize_race_bets(cands, bankroll)
        race_total  = sum(p.get('portfolio_bet', 0) for p in race_picks)

        # 1日総投入上限チェック
        remaining = bankroll * MAX_PORTFOLIO_RATIO - total_bet
        if race_total > remaining:
            if remaining < 100:
                continue
            scale = remaining / race_total
            race_picks = [
                {**p, 'portfolio_bet': max(100, round(p['portfolio_bet'] * scale / 100) * 100)}
                for p in race_picks
            ]
            race_total = sum(p.get('portfolio_bet', 0) for p in race_picks)

        optimized.extend(race_picks)
        total_bet += race_total

    summary = {
        'total_races':     len(races),
        'total_bets':      len(optimized),
        'total_amount':    int(total_bet),
        'portfolio_ratio': round(total_bet / max(bankroll, 1), 4),
        'avg_per_bet':     round(total_bet / max(len(optimized), 1)),
    }
    return optimized, summary


def run_bet_portfolio(year: int = None, bankroll: float = None) -> dict:
    """メイン実行"""
    year = year or datetime.now().year
    log.info("多点買いポートフォリオ最適化 開始")

    if bankroll is None:
        br_path = f"{BASE_DIR}\\data\\bankroll.json"
        if os.path.exists(br_path):
            with open(br_path, encoding='utf-8') as f:
                d = json.load(f)
            bankroll = float(d.get('bankroll', d.get('current', 100_000)))
        else:
            bankroll = 100_000
    log.info("現在資金: %s円", f"{bankroll:,.0f}")

    # simulation CSV から候補取得
    sim_path = f"{BASE_DIR}\\simulation_{year}.csv"
    if not os.path.exists(sim_path):
        log.warning("simulation CSV なし: %s", sim_path)
        return {}

    df = pd.read_csv(sim_path, encoding='utf-8-sig')
    if 'expected_value' in df.columns:
        df = df[df['expected_value'] >= 0.05]
    if 'tansho_odds' in df.columns:
        df['odds'] = pd.to_numeric(df['tansho_odds'], errors='coerce').fillna(0) / 10
        df = df[df['odds'] >= 5.0]
    if 'win_probability' not in df.columns:
        df['win_probability'] = 0.1

    picks = df.to_dict('records')
    optimized, summary = portfolio_optimize_all(picks, bankroll)

    log.info("対象レース: %dR", summary['total_races'])
    log.info("最適ベット数: %d点", summary['total_bets'])
    log.info("総投入額: %s円 (%.1f%%)", f"{summary['total_amount']:,}", summary['portfolio_ratio'] * 100)
    log.info("平均ベット: %s円", f"{summary['avg_per_bet']:,}")

    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
    out = {'year': year, 'bankroll': bankroll, 'summary': summary,
           'optimized_picks': optimized[:50]}
    with open(f"{BASE_DIR}\\data\\portfolio_v2_{year}.json", 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    log.info("保存: data/portfolio_v2_%d.json", year)

    return summary


if __name__ == "__main__":
    run_bet_portfolio()
