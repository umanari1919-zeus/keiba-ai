"""
高度資金管理システム
- ドローダウン管理・自動縮小
- バンクロール成長シミュレーション
- 複数馬券の相関リスク管理
- フラクショナルケリー最適化
"""
import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from scipy.optimize import minimize_scalar, minimize

DATA_DIR     = "D:\\keiba_ai\\data"
BANKROLL_FILE = f"{DATA_DIR}\\bankroll.json"
DD_LOG_FILE   = f"{DATA_DIR}\\drawdown_log.json"

# ドローダウン閾値
DD_THRESHOLDS = {
    'WARNING':  0.10,   # 10%でベット額を50%削減
    'DANGER':   0.20,   # 20%でベット額を75%削減
    'CRITICAL': 0.30,   # 30%でベット停止
}


# ──────────────────────────────────────────────
# ドローダウン管理
# ──────────────────────────────────────────────

def get_current_bankroll() -> dict:
    if not os.path.exists(BANKROLL_FILE):
        return {'bankroll': 100000, 'current': 100000, 'peak': 100000, 'history': []}
    with open(BANKROLL_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # current → bankroll へ正規化
    if 'bankroll' not in data:
        data['bankroll'] = data.get('current', 100000)
    if 'peak' not in data:
        data['peak'] = data['bankroll']
    return data


def update_peak(data: dict) -> dict:
    if data['bankroll'] > data.get('peak', data['bankroll']):
        data['peak'] = data['bankroll']
    return data


def calc_drawdown(data: dict) -> float:
    peak = data.get('peak', data['bankroll'])
    if peak <= 0:
        return 0.0
    return (peak - data['bankroll']) / peak


def get_bet_multiplier(drawdown: float) -> float:
    if drawdown >= DD_THRESHOLDS['CRITICAL']:
        return 0.0
    elif drawdown >= DD_THRESHOLDS['DANGER']:
        return 0.25
    elif drawdown >= DD_THRESHOLDS['WARNING']:
        return 0.50
    return 1.0


def log_drawdown_event(drawdown: float, bankroll: float, level: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    log = []
    if os.path.exists(DD_LOG_FILE):
        with open(DD_LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
    log.append({
        'timestamp': datetime.now().isoformat(),
        'drawdown':  round(drawdown, 4),
        'bankroll':  bankroll,
        'level':     level
    })
    log = log[-100:]
    with open(DD_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def manage_drawdown(verbose=True) -> dict:
    data = get_current_bankroll()
    data = update_peak(data)
    dd   = calc_drawdown(data)
    mult = get_bet_multiplier(dd)

    if dd >= DD_THRESHOLDS['WARNING'] and verbose:
        level = ('CRITICAL' if dd >= DD_THRESHOLDS['CRITICAL'] else
                 'DANGER'   if dd >= DD_THRESHOLDS['DANGER']   else 'WARNING')
        log_drawdown_event(dd, data['bankroll'], level)
        emojis = {'WARNING': '⚠️', 'DANGER': '🚨', 'CRITICAL': '🛑'}
        print(f"  {emojis[level]} ドローダウン {dd*100:.1f}% [{level}]")
        print(f"     現在資金: {data['bankroll']:,}円 | ピーク: {data['peak']:,}円")
        if mult == 0:
            print("     🛑 ベット停止。資金回復後に再開してください。")
        else:
            print(f"     ベット乗数: {mult:.2f}x（自動縮小）")

    return {
        'bankroll':  data['bankroll'],
        'peak':      data['peak'],
        'drawdown':  dd,
        'multiplier': mult
    }


# ──────────────────────────────────────────────
# フラクショナルケリー最適化
# ──────────────────────────────────────────────

def optimal_kelly_fraction(win_prob: float, odds: float,
                             max_fraction=0.5,
                             target_ruin_rate=0.05,
                             n_sim=2000) -> float:
    """
    指定した破産確率以下を維持しつつ、期待成長率を最大化するケリー分数を求める。
    """
    def ruin_rate(fraction):
        rng = np.random.default_rng(42)
        ruins = 0
        for _ in range(n_sim):
            bal = 1.0
            for _ in range(200):
                bet = bal * fraction
                if rng.random() < win_prob:
                    bal += bet * (odds - 1)
                else:
                    bal -= bet
                if bal <= 0.1:
                    ruins += 1
                    break
        return ruins / n_sim

    def neg_growth(fraction):
        if fraction <= 0:
            return 0
        # Kelly growth rate formula: E[log(1 + fraction*(odds-1)*win - fraction*(1-win))]
        return -(win_prob * np.log(1 + fraction * (odds - 1)) +
                 (1 - win_prob) * np.log(1 - fraction + 1e-9))

    # 破産確率制約を満たす最大フラクションを探索
    best_frac = 0.01
    for frac in np.linspace(0.01, max_fraction, 50):
        if ruin_rate(frac) <= target_ruin_rate:
            best_frac = frac
        else:
            break

    return best_frac


# ──────────────────────────────────────────────
# 複数馬券の相関リスク管理
# ──────────────────────────────────────────────

def portfolio_risk_management(bets: list, bankroll: float,
                               max_portfolio_fraction=0.15) -> list:
    """
    複数のベット候補の相関を考慮してリスクを管理する。

    bets: [{'race_code', 'bamei', 'win_prob', 'odds', 'kelly_bet'}, ...]
    """
    if not bets:
        return []

    # 同一レースのベットは相関1（その他は無相関と仮定）
    adjusted = []
    race_totals = {}
    for b in bets:
        rc = b['race_code']
        race_totals[rc] = race_totals.get(rc, 0) + b.get('kelly_bet', 0)

    for b in bets:
        rc  = b['race_code']
        bet = b.get('kelly_bet', 0)
        # 同一レース内の他ベットとの相関リスク調整
        total_in_race = race_totals[rc]
        max_bet = bankroll * max_portfolio_fraction
        if total_in_race > max_bet:
            scale = max_bet / total_in_race
            bet   = bet * scale
        adjusted.append({**b, 'adjusted_bet': max(100, round(bet / 100) * 100)})

    return adjusted


# ──────────────────────────────────────────────
# バンクロール成長シミュレーション
# ──────────────────────────────────────────────

def bankroll_growth_simulation(bankroll=100000, hit_rate=0.388,
                                avg_odds=4.78, n_races=500,
                                kelly_fraction=0.05) -> dict:
    """現在のパラメータでの長期成長をシミュレート"""
    rng = np.random.default_rng(123)
    history = [bankroll]
    peak    = bankroll
    dd_list = []

    for i in range(n_races):
        bal = history[-1]
        bet = bal * kelly_fraction
        if rng.random() < hit_rate:
            bal += bet * (avg_odds - 1)
        else:
            bal -= bet
        bal = max(0, bal)
        history.append(bal)

        if bal > peak:
            peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        dd_list.append(dd)
        if bal == 0:
            break

    result = {
        'initial':         bankroll,
        'final':           history[-1],
        'peak':            max(history),
        'total_races':     len(history) - 1,
        'growth_rate':     (history[-1] / bankroll - 1) * 100,
        'max_drawdown':    max(dd_list) if dd_list else 0,
        'avg_drawdown':    np.mean(dd_list) if dd_list else 0,
        'ruin':            history[-1] == 0,
        'history_sample':  history[::max(1, len(history)//50)]  # 50点サンプリング
    }
    return result


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_bankroll_advanced():
    print("\n" + "="*55)
    print("💰 高度資金管理システム")
    print("="*55)

    # ドローダウン確認
    print("\n📉 ドローダウン状態確認...")
    dd_status = manage_drawdown(verbose=True)
    if dd_status['drawdown'] < DD_THRESHOLDS['WARNING']:
        print(f"  ✅ 正常: ドローダウン {dd_status['drawdown']*100:.1f}%")

    # ケリー分数最適化デモ
    print("\n⚙️ フラクショナルケリー最適化...")
    for wp, od in [(0.388, 4.78), (0.15, 30.0), (0.05, 100.0)]:
        frac = optimal_kelly_fraction(wp, od, max_fraction=0.5)
        ev   = wp * od - 1
        print(f"  勝率{wp*100:.0f}% オッズ{od:.1f}x EV={ev:.3f}: "
              f"最適ケリー = {frac*100:.1f}%")

    # 成長シミュレーション
    print("\n📈 バンクロール成長シミュレーション (500レース)...")
    sim = bankroll_growth_simulation()
    emoji = "🎉" if sim['growth_rate'] > 0 else "📉"
    print(f"  {emoji} 最終資金: {sim['final']:,.0f}円 "
          f"({sim['growth_rate']:+.1f}%)")
    print(f"     最大ドローダウン: {sim['max_drawdown']*100:.1f}%")
    print(f"     ピーク資金: {sim['peak']:,.0f}円")

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/bankroll_simulation.json", 'w', encoding='utf-8') as f:
        json.dump(sim, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 保存: {DATA_DIR}/bankroll_simulation.json")

    return dd_status


if __name__ == "__main__":
    run_bankroll_advanced()
