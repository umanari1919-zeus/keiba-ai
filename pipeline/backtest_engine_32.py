"""
バックテストエンジン
- 馬券種別・レース選別・多点買い戦略を過去データで検証
- 条件別（競馬場/距離/芝ダート/頭数/季節）ROI計測
- EV閾値×ケリー係数の最適パラメータ自動探索
"""
import numpy as np
import pandas as pd
import pickle, json, os, itertools
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pipeline.ensemble_utils import load_ensemble_weights
from pipeline.config import BASE_DIR, CSV_FEATURES, DATA_DIR
from pipeline.native_runtime import ensure_native_runtime

ensure_native_runtime()

MODEL_FILE = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE  = CSV_FEATURES


# ─────────────────────────────────────────────────────────────
# シミュレーション単体
# ─────────────────────────────────────────────────────────────

def _kelly_bet(bankroll: float, p: float, odds: float,
               fraction: float = 0.25) -> int:
    b = odds - 1
    if b <= 0 or p <= 0 or not np.isfinite(p) or not np.isfinite(odds):
        return 0
    k = max(0.0, (p * b - (1 - p)) / b) * fraction
    if not np.isfinite(k) or k <= 0:
        return 0
    k = min(k, 0.5)  # 上限50%
    raw = bankroll * k / 100
    if not np.isfinite(raw):
        return 0
    return max(100, round(raw) * 100)


def simulate_one_race(race_df: pd.DataFrame, bankroll: float,
                      ev_threshold: float, kelly_fraction: float,
                      min_odds: float = 5.0) -> Tuple[float, List[Dict]]:
    """
    1レースのシミュレーション。
    Returns: (net_pnl, [bet_records])
    """
    bets = []
    if 'win_probability' not in race_df.columns:
        return 0.0, []

    for _, row in race_df.iterrows():
        p    = float(row.get('win_probability', 0))
        odds = float(row.get('tansho_odds', 0)) / 10
        rank = int(row.get('kakutei_chakujun', 99))
        ev   = p * odds - 1.0

        if odds < min_odds or ev < ev_threshold:
            continue

        bet_amt = _kelly_bet(bankroll, p, odds, kelly_fraction)
        if bet_amt <= 0:
            continue

        won   = (rank == 1)
        pnl   = bet_amt * (odds - 1) if won else -bet_amt
        if not np.isfinite(pnl):
            pnl = -bet_amt
        bets.append({
            'bamei':    str(row.get('bamei', '')),
            'odds':     odds,
            'ev':       round(ev, 4),
            'bet':      bet_amt,
            'won':      won,
            'rank':     rank,
            'pnl':      pnl,
        })

    total_pnl = sum(b['pnl'] for b in bets)
    return total_pnl, bets


# ─────────────────────────────────────────────────────────────
# バックテスト本体
# ─────────────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, ev_threshold: float = 0.05,
                 kelly_fraction: float = 0.25,
                 initial_bankroll: float = 100_000,
                 min_odds: float = 5.0) -> Dict:
    """
    全レースに対してバックテストを実行し、結果 dict を返す。
    """
    bankroll   = initial_bankroll
    peak       = bankroll
    equity     = [bankroll]
    all_bets   = []
    dd_list    = []

    race_groups = sorted(df.groupby('race_code'), key=lambda x: str(x[0]))

    for rc, race_df in race_groups:
        pnl, bets = simulate_one_race(
            race_df, bankroll, ev_threshold, kelly_fraction, min_odds
        )
        bankroll += pnl
        bankroll  = max(0, min(bankroll, 1e10))  # 上限100億円でキャップ
        if not np.isfinite(bankroll):
            bankroll = initial_bankroll
        peak      = max(peak, bankroll)
        dd        = (peak - bankroll) / peak if peak > 0 else 0
        dd_list.append(dd)
        equity.append(bankroll)

        for b in bets:
            b.update({'race_code': str(rc), 'bankroll_after': bankroll})
            all_bets.append(b)

    total_bet  = sum(b['bet'] for b in all_bets)
    total_pnl  = sum(b['pnl'] for b in all_bets)
    wins       = [b for b in all_bets if b['won']]
    roi        = (total_pnl / total_bet * 100) if total_bet > 0 else 0

    return {
        'ev_threshold':   ev_threshold,
        'kelly_fraction': kelly_fraction,
        'initial':        initial_bankroll,
        'final':          bankroll,
        'peak':           peak,
        'total_bet':      total_bet,
        'total_pnl':      total_pnl,
        'roi':            round(roi, 2),
        'n_bets':         len(all_bets),
        'n_wins':         len(wins),
        'hit_rate':       round(len(wins) / max(len(all_bets), 1) * 100, 2),
        'max_dd':         round(max(dd_list) * 100, 2) if dd_list else 0,
        'avg_dd':         round(np.mean(dd_list) * 100, 2) if dd_list else 0,
        'growth_rate':    round((bankroll / initial_bankroll - 1) * 100, 2),
        'equity_sample':  equity[::max(1, len(equity)//50)],
        'bets':           all_bets,
    }


# ─────────────────────────────────────────────────────────────
# 条件別ROI分析
# ─────────────────────────────────────────────────────────────

def analyze_by_condition(bets: List[Dict], df: pd.DataFrame) -> pd.DataFrame:
    """
    ベット結果を競馬場・距離・芝ダート・頭数・季節で集計。
    """
    if not bets:
        return pd.DataFrame()

    bet_df = pd.DataFrame(bets)
    # レースコードから race_code でマスタと結合
    meta_cols = ['race_code', 'track_code', 'kyori', 'shusso_tosu',
                 'race_month', 'grade_code']
    meta_cols = [c for c in meta_cols if c in df.columns]
    if meta_cols:
        meta = df[meta_cols].drop_duplicates('race_code') if 'race_code' in df.columns else pd.DataFrame()
        if not meta.empty:
            bet_df = bet_df.merge(meta, on='race_code', how='left')

    rows = []
    def _agg(subset, label):
        if len(subset) == 0:
            return
        total_bet = subset['bet'].sum()
        total_pnl = subset['pnl'].sum()
        safe_pnl = float(np.clip(total_pnl, -1e10, 1e10))
        safe_bet = float(np.clip(total_bet, 1, 1e10))
        rows.append({
            '条件':    label,
            '件数':    len(subset),
            '的中':    int(subset['won'].sum()),
            '的中率':  round(float(subset['won'].mean()) * 100, 1),
            '投入':    int(safe_bet),
            '損益':    int(safe_pnl),
            'ROI':     round(safe_pnl / safe_bet * 100, 1) if safe_bet > 0 else 0,
        })

    # 全体
    _agg(bet_df, '全体')

    # 芝/ダート
    if 'track_code' in bet_df.columns:
        for tc, label in [(1, '芝'), (2, 'ダート')]:
            _agg(bet_df[bet_df['track_code'] == tc], label)

    # 頭数
    if 'shusso_tosu' in bet_df.columns:
        bet_df['shusso_tosu'] = pd.to_numeric(bet_df['shusso_tosu'], errors='coerce')
        _agg(bet_df[bet_df['shusso_tosu'] <= 10], '少頭数(≤10)')
        _agg(bet_df[(bet_df['shusso_tosu'] >= 11) & (bet_df['shusso_tosu'] <= 14)], '中頭数(11-14)')
        _agg(bet_df[bet_df['shusso_tosu'] >= 15], '大頭数(≥15)')

    # 距離
    if 'kyori' in bet_df.columns:
        bet_df['kyori'] = pd.to_numeric(bet_df['kyori'], errors='coerce')
        _agg(bet_df[bet_df['kyori'] <= 1400], '短距離(≤1400m)')
        _agg(bet_df[(bet_df['kyori'] >= 1600) & (bet_df['kyori'] <= 2000)], 'マイル〜中距離(1600-2000m)')
        _agg(bet_df[bet_df['kyori'] >= 2200], '長距離(≥2200m)')

    # 季節
    if 'race_month' in bet_df.columns:
        bet_df['race_month'] = pd.to_numeric(bet_df['race_month'], errors='coerce')
        for months, label in [([3,4,5], '春'), ([6,7,8], '夏'), ([9,10,11], '秋'), ([12,1,2], '冬')]:
            _agg(bet_df[bet_df['race_month'].isin(months)], label)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# パラメータ最適化（グリッドサーチ）
# ─────────────────────────────────────────────────────────────

def optimize_params(df: pd.DataFrame,
                    ev_thresholds: List[float] = None,
                    kelly_fractions: List[float] = None) -> pd.DataFrame:
    """
    EV閾値×ケリー係数のグリッドサーチでROI最大の組み合わせを探索。
    """
    if ev_thresholds is None:
        ev_thresholds  = [0.02, 0.05, 0.10, 0.15, 0.20, 0.30]
    if kelly_fractions is None:
        kelly_fractions = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]

    results = []
    total = len(ev_thresholds) * len(kelly_fractions)
    done  = 0
    for ev_th, kf in itertools.product(ev_thresholds, kelly_fractions):
        res = run_backtest(df, ev_threshold=ev_th, kelly_fraction=kf)
        results.append({
            'ev_threshold':   ev_th,
            'kelly_fraction': kf,
            'roi':            res['roi'],
            'hit_rate':       res['hit_rate'],
            'n_bets':         res['n_bets'],
            'max_dd':         res['max_dd'],
            'growth_rate':    res['growth_rate'],
        })
        done += 1
        if done % 6 == 0:
            print(f"    グリッドサーチ {done}/{total}...", end='\r')

    return pd.DataFrame(results).sort_values('roi', ascending=False)


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_backtest_engine(year: int = None) -> dict:
    year = year or datetime.now().year
    print("\n" + "="*55)
    print("📈 バックテストエンジン")
    print("="*55)

    if not os.path.exists(FEAT_FILE):
        print("  ⚠️ 特徴量ファイルなし")
        return {}

    df = pd.read_csv(FEAT_FILE, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')

    # ML モデルで win_probability を付与
    if 'win_probability' not in df.columns and os.path.exists(MODEL_FILE):
        print("  🔧 ML予測を実行中...")
        with open(MODEL_FILE, 'rb') as f:
            saved = pickle.load(f)
        lgb_m = saved['lgb_model']
        xgb_m = saved['xgb_model']
        cb_m  = saved['cb_model']
        le    = saved['le']
        feats = [f for f in saved['features'] if f in df.columns]
        X     = df[feats].fillna(0)
        weights = load_ensemble_weights(saved)
        p_ens = (weights[0] * lgb_m.predict_proba(X) +
                 weights[1] * xgb_m.predict_proba(X) +
                 weights[2] * cb_m.predict_proba(X))
        classes = list(le.classes_)
        win_idx = classes.index(1) if 1 in classes else 0
        df['win_probability'] = p_ens[:, win_idx]

    if 'win_probability' not in df.columns:
        print("  ⚠️ win_probability なし（モデル未学習）")
        return {}

    # 過去データでバックテスト（全年度）
    print(f"  📊 データ: {len(df):,}件 / {df['race_code'].nunique():,}レース")

    # ベースライン（デフォルトパラメータ）
    print("\n  ① ベースラインバックテスト (EV≥5%, Kelly×0.25)...")
    base = run_backtest(df, ev_threshold=0.05, kelly_fraction=0.10)
    print(f"    ROI: {base['roi']:+.1f}%  的中率: {base['hit_rate']:.1f}%  "
          f"最大DD: {base['max_dd']:.1f}%  ベット数: {base['n_bets']:,}")
    print(f"    最終資金: {base['final']:,.0f}円 ({base['growth_rate']:+.1f}%)")

    # 条件別分析
    print("\n  ② 条件別ROI分析...")
    cond_df = analyze_by_condition(base['bets'], df)
    if not cond_df.empty:
        print(cond_df.to_string(index=False))

    # パラメータ最適化
    print("\n  ③ パラメータ最適化（グリッドサーチ）...")
    grid = optimize_params(df)
    best = grid.iloc[0]
    print(f"\n    🏆 最適パラメータ:")
    print(f"    EV閾値={best['ev_threshold']} ケリー={best['kelly_fraction']} "
          f"→ ROI={best['roi']:+.1f}% 的中率={best['hit_rate']:.1f}% "
          f"最大DD={best['max_dd']:.1f}%")

    # 最適パラメータで再バックテスト
    opt_res = run_backtest(df,
                           ev_threshold=best['ev_threshold'],
                           kelly_fraction=best['kelly_fraction'])
    print(f"    最終資金: {opt_res['final']:,.0f}円 ({opt_res['growth_rate']:+.1f}%)")

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)

    cond_path = os.path.join(DATA_DIR, f"backtest_conditions_{year}.csv")
    if not cond_df.empty:
        cond_df.to_csv(cond_path, index=False, encoding='utf-8-sig')

    grid_path = os.path.join(DATA_DIR, f"backtest_grid_{year}.csv")
    grid.to_csv(grid_path, index=False, encoding='utf-8-sig')

    summary = {
        'year':          year,
        'baseline':      {k: v for k, v in base.items() if k not in ('bets', 'equity_sample')},
        'best_params':   best.to_dict(),
        'optimized':     {k: v for k, v in opt_res.items() if k not in ('bets', 'equity_sample')},
        'equity_sample': opt_res['equity_sample'],
    }
    summary_path = os.path.join(DATA_DIR, f"backtest_summary_{year}.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  💾 保存: data/backtest_summary_{year}.json, backtest_grid_{year}.csv")
    return summary


if __name__ == "__main__":
    run_backtest_engine()
