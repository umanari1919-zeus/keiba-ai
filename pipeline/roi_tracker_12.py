"""
リアルタイム回収率トラッキング
日次・週次・月次の損益を自動集計し、目標回収率との乖離をアラートする。
"""
import logging
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

TRACKER_FILE = "D:\\keiba_ai\\data\\roi_tracker.csv"
TARGET_ROI = 1.15       # 目標回収率 115%
ALERT_ROI_WARN = 0.90   # 警告ライン 90%
ALERT_ROI_CRIT = 0.75   # 危機ライン 75%
MIN_BETS_FOR_ALERT = 5  # アラートを出す最低ベット数

COLS = [
    'date', 'race_code', 'bamei', 'bet_type',
    'bet_amount', 'odds', 'hit', 'return_amount', 'profit', 'race_type'
]


def _load():
    if os.path.exists(TRACKER_FILE):
        df = pd.read_csv(TRACKER_FILE, encoding="utf-8-sig",
                         dtype={'race_code': str})
        if 'race_type' not in df.columns:
            df['race_type'] = 'default'
        return df
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    return pd.DataFrame(columns=COLS)


def _save(df):
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    df.to_csv(TRACKER_FILE, index=False, encoding="utf-8-sig")


def record_bet(race_code, bamei, bet_type, bet_amount, odds, hit, race_type='default'):
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
        'profit':        profit,
        'race_type':     race_type,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    result_label = "的中" if hit else "外れ"
    log.info("記録：%s %s %s円 → %s (%+,.0f円)", bamei, bet_type, f"{bet_amount:,}", result_label, profit)
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


    # race_type breakdown
    if 'race_type' in df.columns and len(df) >= 5:
        valid_rt = df[df['hit'] != -1]
        if len(valid_rt) > 0 and valid_rt['race_type'].nunique() > 0:
            print(f"\n[\u30ec\u30fc\u30b9\u7a2e\u5225\u6210\u7e3e\uff08\u7d2f\u8a08\uff09]")
            _type_labels = {
                'debut':    '\u65b0\u99ac\u6226',
                'shogai':   '\u969c\u5bb3\u6226',
                'handicap': '\u30cf\u30f3\u30c7\u6226',
                'default':  '\u901a\u5e38\u6226',
            }
            for _rt, _g in valid_rt.groupby('race_type'):
                _lbl  = _type_labels.get(_rt, _rt)
                _bet  = _g['bet_amount'].sum()
                _ret  = _g['return_amount'].sum()
                _hits = (_g['hit'] == 1).sum()
                _roi  = _ret / _bet * 100 if _bet > 0 else 0
                print(f"   {_lbl:<6}: {len(_g):>4}R  "
                      f"\u7684\u4e2d\u7387{_hits/len(_g)*100:>5.1f}%  "
                      f"\u56de\u53ce\u7387{_roi:>6.1f}%  "
                      f"\u640d\u76ca{_ret-_bet:>+9,.0f}\u5186")

    # bankroll.json を roi_tracker の実績で自動更新
    _sync_bankroll(df)


def _sync_bankroll(df=None):
    """
    roi_tracker.csv の実績から bankroll.json を自動更新する。
    run_all.py の print_roi_report 呼び出し後に自動実行される。
    """
    import json as _json
    from datetime import datetime as _dt

    if df is None:
        df = _load()
    if len(df) == 0:
        return

    INITIAL = 10000
    total_profit = float(df['profit'].sum())
    current = INITIAL + total_profit

    # 月次履歴
    df2 = df.copy()
    df2['_date'] = pd.to_datetime(df2['date'], errors='coerce')
    df2['_month'] = df2['_date'].dt.strftime('%Y-%m')
    monthly = df2.groupby('_month').agg(
        profit=('profit', 'sum'),
        bets=('bet_amount', 'count'),
        hits=('hit', 'sum'),
        invested=('bet_amount', 'sum'),
        returned=('return_amount', 'sum')
    ).reset_index()

    history = []
    running = INITIAL
    for _, row in monthly.iterrows():
        running += float(row['profit'])
        bets = int(row['bets'])
        history.append({
            'month':    row['_month'],
            'profit':   round(float(row['profit']), 0),
            'balance':  round(running, 0),
            'hit_rate': round(float(row['hits']) / bets * 100, 1) if bets else 0,
            'roi':      round(float(row['returned']) / float(row['invested']) * 100, 1)
                        if float(row['invested']) > 0 else 0,
            'bets':     bets,
        })

    total_invested = float(df['bet_amount'].sum())
    total_returned = float(df['return_amount'].sum())
    result = {
        'initial':      INITIAL,
        'current':      round(current, 0),
        'total_profit': round(total_profit, 0),
        'total_roi':    round(total_returned / total_invested * 100, 1)
                        if total_invested > 0 else 0,
        'total_bets':   len(df),
        'hit_rate':     round(float(df['hit'].mean()) * 100, 1),
        'history':      history,
        'updated':      _dt.now().isoformat(),
    }
    bk_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'bankroll.json')
    bk_path = os.path.normpath(bk_path)
    with open(bk_path, 'w', encoding='utf-8') as f:
        _json.dump(result, f, ensure_ascii=False, indent=2)


def import_from_simulation(simulation_csv, year=2025):
    """
    既存の simulation_2025.csv から過去データを一括インポートする。
    初回セットアップ用。
    """
    df = pd.read_csv(simulation_csv, encoding="utf-8-sig", on_bad_lines="skip")
    log.info("%d件のシミュレーション結果をインポート中...", len(df))

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

    log.info("%d件をインポートしました", imported)


if __name__ == "__main__":
    print_roi_report()
