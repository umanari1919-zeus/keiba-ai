"""
リアルタイム回収率トラッキング
日次・週次・月次の損益を自動集計し、目標回収率との乖離をアラートする。
"""
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

TRACKER_FILE = "D:\\keiba_ai\\data\\roi_tracker.csv"
TARGET_ROI = 1.15       # 目標回収率 115%
ALERT_ROI_WARN = 0.90   # 警告ライン 90%
ALERT_ROI_CRIT = 0.75   # 危機ライン 75%
MIN_BETS_FOR_ALERT = 5  # アラートを出す最低ベット数

COLS = [
    'date', 'race_code', 'bamei', 'bet_type',
    'bet_amount', 'odds', 'hit', 'return_amount', 'profit'
]


def _load():
    if os.path.exists(TRACKER_FILE):
        return pd.read_csv(TRACKER_FILE, encoding="utf-8-sig",
                           dtype={'race_code': str})
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    return pd.DataFrame(columns=COLS)


def _save(df):
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    df.to_csv(TRACKER_FILE, index=False, encoding="utf-8-sig")


def record_bet(race_code, bamei, bet_type, bet_amount, odds, hit):
    """
    賭け結果を1件記録する。

    Parameters
    ----------
    race_code  : str   レースコード
    bamei      : str   馬名
    bet_type   : str   馬券種 (tansho / fukusho / umaren / sanrenpuku)
    bet_amount : int   賭け金（円）
    odds       : float オッズ（10倍 → 10.0）
    hit        : bool  的中したか
    """
    df = _load()
    return_amount = bet_amount * odds if hit else 0.0
    profit = return_amount - bet_amount

    row = {
        'date':          datetime.now().strftime('%Y-%m-%d'),
        'race_code':     str(race_code),
        'bamei':         bamei,
        'bet_type':      bet_type,
        'bet_amount':    bet_amount,
        'odds':          odds,
        'hit':           int(hit),
        'return_amount': return_amount,
        'profit':        profit
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    emoji = "🎉" if hit else "💸"
    print(f"  {emoji} 記録：{bamei} {bet_type} {bet_amount:,}円 "
          f"→ {'的中' if hit else '外れ'} ({profit:+,.0f}円)")
    return df


def _period_filter(df, period):
    """期間ラベルとフィルタ済みDataFrameを返す。"""
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    now = datetime.now()

    if period == 'daily':
        mask  = df['date'].dt.date == now.date()
        label = f"日次 ({now.strftime('%Y-%m-%d')})"
    elif period == 'weekly':
        week_start = now - timedelta(days=now.weekday())
        mask  = df['date'].dt.date >= week_start.date()
        label = f"週次 ({week_start.strftime('%m/%d')}〜)"
    elif period == 'monthly':
        mask  = (df['date'].dt.year == now.year) & \
                (df['date'].dt.month == now.month)
        label = f"月次 ({now.strftime('%Y年%m月')})"
    else:
        mask  = pd.Series([True] * len(df), index=df.index)
        label = "累計"

    return df[mask], label


def get_summary(period='monthly'):
    """期間別の損益サマリーを返す。"""
    df = _load()
    if len(df) == 0:
        return None

    target, label = _period_filter(df, period)
    if len(target) == 0:
        return None

    total_bet    = target['bet_amount'].sum()
    total_return = target['return_amount'].sum()
    roi          = total_return / total_bet if total_bet > 0 else 0

    return {
        'label':        label,
        'bets':         len(target),
        'hits':         int(target['hit'].sum()),
        'total_bet':    int(total_bet),
        'total_return': float(total_return),
        'profit':       float(total_return - total_bet),
        'roi':          roi,
        'hit_rate':     float(target['hit'].mean()),
    }


def _roi_emoji(roi):
    if roi >= TARGET_ROI:
        return "🎉"
    if roi >= ALERT_ROI_WARN:
        return "📊"
    if roi >= ALERT_ROI_CRIT:
        return "⚠️"
    return "🚨"


def check_alerts():
    """目標回収率との乖離を検出してアラートリストを返す。"""
    alerts = []
    df = _load()
    if len(df) == 0:
        return alerts

    for period in ['daily', 'weekly', 'monthly']:
        s = get_summary(period)
        if s is None or s['bets'] < MIN_BETS_FOR_ALERT:
            continue

        roi     = s['roi']
        gap     = roi - TARGET_ROI
        gap_pct = gap * 100

        if roi < ALERT_ROI_CRIT:
            level = 'CRITICAL'
            msg   = (f"🚨 【緊急】{s['label']} 回収率{roi*100:.1f}% "
                     f"(目標比 {gap_pct:+.1f}%) — ベット停止を推奨")
        elif roi < ALERT_ROI_WARN:
            level = 'WARNING'
            msg   = (f"⚠️ {s['label']} 回収率{roi*100:.1f}% "
                     f"(目標比 {gap_pct:+.1f}%) — 戦略見直しを検討")
        else:
            continue

        alerts.append({'level': level, 'period': period,
                       'roi': roi, 'gap': gap, 'message': msg})
    return alerts


def print_roi_report():
    """全期間の回収率レポートをコンソールに表示する。"""
    df = _load()
    if len(df) == 0:
        print("まだ記録がありません")
        return

    print(f"\n{'='*60}")
    print(f"📊 リアルタイム回収率トラッキングレポート")
    print(f"   目標回収率：{TARGET_ROI*100:.0f}%")
    print(f"{'='*60}")

    for period in ['daily', 'weekly', 'monthly', 'all']:
        s = get_summary(period)
        if not s:
            continue
        roi  = s['roi']
        emoji = _roi_emoji(roi)
        gap  = (roi - TARGET_ROI) * 100

        print(f"\n{emoji} 【{s['label']}】")
        print(f"   ベット：{s['bets']}回  的中：{s['hits']}回 "
              f"({s['hit_rate']*100:.1f}%)")
        print(f"   投資額：{s['total_bet']:,}円  "
              f"回収額：{s['total_return']:,.0f}円")
        print(f"   回収率：{roi*100:.1f}%（目標比 {gap:+.1f}%）")
        print(f"   損　益：{s['profit']:+,.0f}円")

    # 馬券種別サマリー
    if len(df) > 0:
        print(f"\n【馬券種別成績（累計）】")
        for bt, g in df.groupby('bet_type'):
            bet = g['bet_amount'].sum()
            ret = g['return_amount'].sum()
            if bet > 0:
                roi_bt = ret / bet * 100
                print(f"   {bt:<12}：{len(g):>4}回  回収率{roi_bt:>6.1f}%  "
                      f"損益{ret-bet:>+9,.0f}円")

    # アラート
    alerts = check_alerts()
    if alerts:
        print(f"\n{'='*60}")
        print("🔔 アラート")
        for a in alerts:
            print(f"  {a['message']}")

    print(f"{'='*60}")


def import_from_simulation(simulation_csv, year=2025):
    """
    既存の simulation_2025.csv から過去データを一括インポートする。
    初回セットアップ用。
    """
    df = pd.read_csv(simulation_csv, encoding="utf-8-sig")
    print(f"📥 {len(df)}件のシミュレーション結果をインポート中...")

    imported = 0
    for _, row in df.iterrows():
        race_code = row['race_code']
        bamei     = row.get('bamei', '')
        odds      = float(row['odds'])
        hit       = int(row['hit']) == 1

        # 日付をrace_codeから推定 (YYYYMMDD形式前提)
        rc_str = str(race_code)
        try:
            date_str = f"{rc_str[:4]}-{rc_str[4:6]}-{rc_str[6:8]}"
        except Exception:
            date_str = f"{year}-01-01"

        tracker_df = _load()
        row_data = {
            'date':          date_str,
            'race_code':     str(race_code),
            'bamei':         bamei,
            'bet_type':      'tansho',
            'bet_amount':    100,
            'odds':          odds,
            'hit':           int(hit),
            'return_amount': odds * 100 if hit else 0.0,
            'profit':        (odds * 100 - 100) if hit else -100.0
        }
        tracker_df = pd.concat(
            [tracker_df, pd.DataFrame([row_data])], ignore_index=True
        )
        _save(tracker_df)
        imported += 1

    print(f"✅ {imported}件をインポートしました")


if __name__ == "__main__":
    print_roi_report()
