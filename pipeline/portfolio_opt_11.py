"""
馬券ポートフォリオ最適化
単勝・複勝・馬連・三連複の最適な組み合わせと配分をケリー基準で計算する。
"""
import pandas as pd
import numpy as np
import pickle
from datetime import datetime

from pipeline.kelly_bankroll_09 import load_bankroll, calculate_kelly_bet
from pipeline.ev_engine_10 import build_ev_dataframe, extract_win_probabilities
from pipeline.ensemble_utils import load_ensemble_weights

# 各馬券種の設定（推定的中確率補正・最低オッズ・ケリー分数）
BET_CONFIG = {
    'tansho':     {'min_odds':  8.0, 'kelly_frac': 0.25, 'min_ev': 0.05},
    'fukusho':    {'min_odds':  2.0, 'kelly_frac': 0.15, 'min_ev': 0.02},
    'umaren':     {'min_odds':  8.0, 'kelly_frac': 0.15, 'min_ev': 0.05},
    'sanrenpuku': {'min_odds': 15.0, 'kelly_frac': 0.10, 'min_ev': 0.05},
}

MAX_RACE_RATIO = 0.10  # 1レースへの最大投入比率（資金の10%）
BET_NAMES = {
    'tansho': '単勝', 'fukusho': '複勝',
    'umaren': '馬連', 'sanrenpuku': '三連複'
}


def _estimate_probs(p1, p2, p3):
    """
    1〜3番人気馬の勝利確率から各馬券種の的中確率を推定する。
    数値は経験的な近似値。
    """
    return {
        'tansho':     p1,
        'fukusho':    min(p1 * 3.2, 0.95),   # 複勝は3着以内
        'umaren':     p1 * p2 * 18,           # 2頭ボックス補正
        'sanrenpuku': p1 * p2 * p3 * 80,      # 3頭ボックス補正
    }


def _get_odds_map(race_df_raw, race_code):
    """レースコードに対応するオッズを馬番→オッズ辞書で返す（単勝のみ）。"""
    race = race_df_raw[race_df_raw['race_code'] == race_code]
    return dict(zip(race['umaban'].astype(str),
                    pd.to_numeric(race['tansho_odds'], errors='coerce').fillna(0) / 10))


def optimize_race_portfolio(p1, p2, p3,
                            tansho_odds, fukusho_odds,
                            umaren_odds, sanrenpuku_odds,
                            bankroll):
    """
    1レース分の最適馬券ポートフォリオを返す。

    Returns
    -------
    dict : {bet_type: bet_amount_yen}
    """
    probs    = _estimate_probs(p1, p2, p3)
    odds_map = {
        'tansho':     tansho_odds,
        'fukusho':    fukusho_odds,
        'umaren':     umaren_odds,
        'sanrenpuku': sanrenpuku_odds,
    }

    portfolio  = {}
    total_kelly = 0

    for bet_type, cfg in BET_CONFIG.items():
        p    = probs[bet_type]
        odds = odds_map[bet_type]

        if odds < cfg['min_odds'] or p <= 0:
            portfolio[bet_type] = 0
            continue

        ev = p * odds - 1.0
        if ev < cfg['min_ev']:
            portfolio[bet_type] = 0
            continue

        bet = calculate_kelly_bet(bankroll, p, odds,
                                  fraction=cfg['kelly_frac'])
        portfolio[bet_type] = bet
        total_kelly += bet

    # 1レース上限キャップ
    max_race = bankroll * MAX_RACE_RATIO
    if total_kelly > max_race and total_kelly > 0:
        ratio = max_race / total_kelly
        portfolio = {
            k: int(round(v * ratio / 100) * 100)
            for k, v in portfolio.items()
        }

    return portfolio


def run_portfolio_optimization(year=2025):
    print(f"📊 [{datetime.now()}] 馬券ポートフォリオ最適化開始...")

    with open("D:\\keiba_ai\\model_v8.pkl", "rb") as f:
        saved = pickle.load(f)

    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model  = saved['cb_model']
    le        = saved['le']
    features  = saved['features']
    weights   = load_ensemble_weights(saved)

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    test_df = df[df['kaisai_nen'] == year].copy()

    if len(test_df) == 0:
        print(f"⚠️ {year}年データなし")
        return pd.DataFrame()

    X_test = test_df[features]
    ensemble_proba = (
        weights[0] * lgb_model.predict_proba(X_test) +
        weights[1] * xgb_model.predict_proba(X_test) +
        weights[2] * (cb_model.predict_proba(X_test) if cb_model is not None else 0)
    )

    ev_df = build_ev_dataframe(test_df, ensemble_proba, le)
    win_probs = extract_win_probabilities(ensemble_proba, le)
    ev_df['win_probability'] = win_probs

    bk_data  = load_bankroll()
    bankroll = bk_data['current']

    results = []
    for race_code, race in ev_df.groupby('race_code'):
        if len(race) < 3:
            continue

        # 予測順位でソートして上位3頭を取得
        race = race.copy()
        race['pred_rank'] = race['win_probability'].rank(ascending=False)
        top3 = race.nsmallest(3, 'pred_rank')

        if len(top3) < 3:
            continue

        p1, p2, p3 = (top3.iloc[i]['win_probability'] for i in range(3))
        h1 = top3.iloc[0]

        # オッズ取得（三連複・馬連は単純化して単勝オッズから近似）
        tansho_odds     = h1['odds_decimal'] if 'odds_decimal' in h1 else h1['tansho_odds'] / 10
        fukusho_odds    = tansho_odds * 0.4   # 複勝は単勝の約40%
        umaren_odds     = (tansho_odds + top3.iloc[1]['tansho_odds'] / 10) * 0.7
        sanrenpuku_odds = tansho_odds * 1.5

        portfolio = optimize_race_portfolio(
            p1, p2, p3,
            tansho_odds, fukusho_odds, umaren_odds, sanrenpuku_odds,
            bankroll
        )
        total_bet = sum(portfolio.values())
        if total_bet == 0:
            continue

        results.append({
            'race_code':  race_code,
            'bamei':      h1.get('bamei', ''),
            'win_prob':   round(p1, 4),
            'tansho_odds': round(tansho_odds, 1),
            'ev':         round(p1 * tansho_odds - 1, 3),
            **portfolio,
            'total_bet':  total_bet
        })

    results_df = pd.DataFrame(results)

    print(f"\n{'='*60}")
    print(f"📊 {year}年 馬券ポートフォリオ最適化結果")
    print(f"💰 利用可能資金：{bankroll:,.0f}円")
    print(f"{'='*60}")

    if len(results_df) > 0:
        # サマリー表示
        bet_types = list(BET_CONFIG.keys())
        for bt in bet_types:
            col_total = results_df[bt].sum()
            cnt = (results_df[bt] > 0).sum()
            if col_total > 0:
                print(f"  {BET_NAMES[bt]}：{cnt}R  合計{col_total:,.0f}円")

        grand_total = results_df['total_bet'].sum()
        print(f"\n  総投資予定額：{grand_total:,.0f}円")
        print(f"  対象レース数：{len(results_df)}R")

        out = f"D:\\keiba_ai\\portfolio_{year}.csv"
        results_df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n💾 {out} に保存しました")
    else:
        print("本日は条件を満たすレースがありません")

    print(f"{'='*60}")
    return results_df


if __name__ == "__main__":
    run_portfolio_optimization(2025)
