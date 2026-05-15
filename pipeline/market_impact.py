"""
market_impact.py — 市場インパクト（スリッパージ）推定ユーティリティ
=================================================================================

現状のバックテスト（最終確定オッズ使用）は、本番で「もし 1万円張ったら 30倍 → 28倍 に下がる」
というプール縮小効果を無視している。これは ROI の過大評価の主要システム要因の一つ。

このモジュールでは「パリミチュエル・コンセンサス」モデルに基づいて、
べットを打った後のオッズを推定し、ev_engine に「現実的な EV」を提供する。

モデル (単勝):
    単勝は「その馬への購入額 / 全体単勝プール」に反比例してオッズが決まる。
    pool に「自分の bet × (1 - takeout)」を足すと、その馬へのプールも、その馬のん購入額
    も同じだけ増える。そのためオッズは以下のように推定できる:

        old_share  = 1 / old_odds              # その馬のシェア（控除考慮前の近似）
        old_horse_pool = pool × old_share
        new_horse_pool = old_horse_pool + bet
        new_pool       = pool + bet
        new_share  = new_horse_pool / new_pool
        new_odds   = (1 - takeout) / new_share

    これを整理すると:
        new_odds = old_odds × pool / (pool + bet × old_odds)
    （takeout 効果を含めた近似。厳密には控除処理を別途とった方が良いが、
     pool の単位を「控除後プール」として掱えればこれが成り立つ）

使い方:
    from pipeline.market_impact import estimate_post_bet_odds, expected_payout_with_impact
    new_odds = estimate_post_bet_odds(old_odds=30.0, bet=10000, pool=5_000_000)
    # => 例えば 28.04
"""

from __future__ import annotations

from typing import Optional


# デフォルトの推定プールサイズ（単勝、円）。本場とローカルで大きく異なる。
#   GIグレードレース: 1〜10億円
#   平日中央: 5,000万〜1億円
#   地方・ローカル: 100万〜500万円
DEFAULT_TANSHO_POOL_JPY = 50_000_000  # 5千万円 (中央現実的値)
MIN_POOL_JPY = 100_000  # この下限を下回るとスリッパージ計算が不安定になる


def estimate_post_bet_odds(
    old_odds: float,
    bet: float,
    pool: Optional[float] = None,
) -> float:
    """べットを打った後の推定オッズを返す。

    Args:
        old_odds: べット前の掲示オッズ（倍）
        bet:      購入額（円）
        pool:     その馬券種の総プール（円）。None ならデフォルトを使う。

    Returns:
        スリップ項を加味した推定オッズ。bet=0 なら old_odds と一致。
        オッズは下げる方向に動くため new_odds <= old_odds。
    """
    if bet <= 0:
        return old_odds
    if pool is None or pool < MIN_POOL_JPY:
        pool = DEFAULT_TANSHO_POOL_JPY
    # new_odds = old_odds * pool / (pool + bet * old_odds)
    return old_odds * pool / (pool + bet * old_odds)


def expected_payout_with_impact(
    win_prob: float,
    old_odds: float,
    bet: float,
    takeout_rate: float = 0.20,
    pool: Optional[float] = None,
) -> float:
    """スリップージと控除率を考慮した期待収益を返す。

    Args:
        win_prob:    勝率（0〜1）
        old_odds:    掲示オッズ（倍）
        bet:         購入額（円）
        takeout_rate: 控除率（0〜1）
        pool:        プールサイズ（円）

    Returns:
        期待収益（円） = win_prob × (new_odds × bet) - bet
        ここで new_odds は控除を反映済みオッズ。old_odds が控除後の公表オッズなら
        追加控除は不要。控除前を渡された場合は estimate_post_bet_odds の後に
        (1 - takeout_rate) を乗じるとよいが、現在のパイプラインは控除後オッズを使うため
        ここでは二重に控除をとらない。takeout_rate は「控除前オッズ」を渡された場合のための
        予備パラメータとして保持。
    """
    if bet <= 0:
        return 0.0
    new_odds = estimate_post_bet_odds(old_odds, bet, pool)
    return win_prob * new_odds * bet - bet


def expected_value_with_impact(
    win_prob: float,
    old_odds: float,
    bet: float,
    takeout_rate: float = 0.20,
    pool: Optional[float] = None,
) -> float:
    """EV を bet で規格化した値を返す。bet=10000 をデフォルトとして
    estimate を返してもよいが、ここでは追加パラメータとして bet を渡す。　

    追加のポイント: bet が pool に対して十分小さい限り EV の低下はわずかだが、
    bet が pool / old_odds の水準に近づくと多くの EV が失われる。
    """
    if bet <= 0:
        return win_prob * old_odds - 1.0
    new_odds = estimate_post_bet_odds(old_odds, bet, pool)
    return win_prob * new_odds - 1.0


# 単体テスト用
if __name__ == "__main__":
    # ケース 1: 小口の購入、オッズはほぼ変わらない
    o1 = estimate_post_bet_odds(30.0, 1000, 50_000_000)
    print(f"30倍に1000円 → {o1:.4f}倍 (スリップれ上頼り)")

    # ケース 2: 中口の購入、複達に下げる
    o2 = estimate_post_bet_odds(30.0, 10000, 50_000_000)
    print(f"30倍に1万円 → {o2:.4f}倍 (低めのスリップ)")

    # ケース 3: 大口の購入、明らかに下げる
    o3 = estimate_post_bet_odds(30.0, 100000, 50_000_000)
    print(f"30倍に10万円 → {o3:.4f}倍 (大きなスリップ)")

    # ケース 4: プールが少ないレース、同じベットでのインパクトが大きい
    o4 = estimate_post_bet_odds(30.0, 10000, 1_000_000)
    print(f"30倍に1万円（小プール 100万円）→ {o4:.4f}倍 (大きなスリップ)")

    # EV テスト
    ev_naive = 0.05 * 30.0 - 1.0  # win_prob=5%, odds=30 → +0.50
    ev_real  = expected_value_with_impact(0.05, 30.0, 10000, pool=5_000_000)
    print(f"\nEV (限界スリップ無視): {ev_naive:.4f}")
    print(f"EV (スリップ反映, pool=500万): {ev_real:.4f}")
