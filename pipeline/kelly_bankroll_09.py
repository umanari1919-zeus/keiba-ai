import json
import os
from datetime import datetime

BANKROLL_FILE = "D:\\keiba_ai\\data\\bankroll.json"
KELLY_FRACTION = 0.10  # 1/10ケリー（WF検証DD64%→安全係数に引き下げ）
MAX_BET_RATIO = 0.05  # 1レース最大5%まで


def load_bankroll():
    if not os.path.exists(BANKROLL_FILE):
        os.makedirs(os.path.dirname(BANKROLL_FILE), exist_ok=True)
        initial = {
            'current': 100000,
            'initial': 100000,
            'history': [],
            'updated': datetime.now().isoformat()
        }
        _save_bankroll(initial)
        return initial
    with open(BANKROLL_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_bankroll(data):
    os.makedirs(os.path.dirname(BANKROLL_FILE), exist_ok=True)
    with open(BANKROLL_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calculate_kelly_bet(bankroll, p_win, odds,
                        fraction=KELLY_FRACTION, min_bet=100):
    """
    ケリー基準で最適賭け金を計算。

    p_win : AIの勝利確率 (0〜1)
    odds  : 単勝オッズ (例: 30.0)
    """
    b = odds - 1.0  # 純利益倍率
    if p_win <= 0 or b <= 0:
        return 0

    # ケリー公式 f* = (b*p - (1-p)) / b
    kelly_f = (b * p_win - (1.0 - p_win)) / b
    if kelly_f <= 0:
        return 0  # 期待値マイナスはベットしない

    kelly_f = min(kelly_f * fraction, MAX_BET_RATIO)
    bet = bankroll * kelly_f
    return int(max(min_bet, round(bet / 100) * 100))


def update_bankroll(race_code, bamei, bet_amount, odds, hit,
                    bet_type='tansho'):
    """レース結果で資金を更新して永続化する。"""
    data = load_bankroll()

    profit = bet_amount * odds - bet_amount if hit else -bet_amount
    data['current'] += profit
    data['history'].append({
        'date': datetime.now().isoformat(),
        'race_code': str(race_code),
        'bamei': bamei,
        'bet_type': bet_type,
        'bet_amount': bet_amount,
        'odds': odds,
        'hit': int(hit),
        'profit': profit,
        'bankroll_after': data['current']
    })
    data['updated'] = datetime.now().isoformat()
    _save_bankroll(data)

    roi = (data['current'] - data['initial']) / data['initial'] * 100
    result_str = f"的中 +{profit:,.0f}円" if hit else f"外れ {profit:,.0f}円"
    print(f"  💰 資金更新：{result_str}")
    print(f"  📊 現在資金：{data['current']:,.0f}円 (初期比 {roi:+.1f}%)")
    return data['current']


def get_bankroll_status():
    data = load_bankroll()
    current = data['current']
    initial = data['initial']
    roi = (current - initial) / initial * 100

    print(f"\n{'='*45}")
    print(f"💰 資金状況レポート")
    print(f"{'='*45}")
    print(f"初期資金：{initial:,.0f}円")
    print(f"現在資金：{current:,.0f}円")
    print(f"損　益　：{current - initial:+,.0f}円 ({roi:+.1f}%)")

    history = data.get('history', [])
    if history:
        wins = sum(1 for h in history if h['hit'])
        total = len(history)
        print(f"累計ベット：{total}回  的中率：{wins/total*100:.1f}% ({wins}/{total})")

        # 破産リスク警告
        if current < initial * 0.5:
            print("🚨 警告：資金が初期の50%を下回りました。賭け金を見直してください")

    print(f"{'='*45}")
    return data


if __name__ == "__main__":
    get_bankroll_status()

    # 動作確認
    bk = load_bankroll()
    bankroll = bk['current']
    print(f"\n【ケリー基準 賭け金計算例】")
    for p, odds in [(0.05, 30.0), (0.08, 20.0), (0.15, 10.0), (0.03, 50.0)]:
        bet = calculate_kelly_bet(bankroll, p, odds)
        ev = p * odds - 1
        print(f"  勝率{p*100:.0f}% オッズ{odds:.0f}倍 EV{ev:+.2f} → 推奨賭け金：{bet:,}円")
