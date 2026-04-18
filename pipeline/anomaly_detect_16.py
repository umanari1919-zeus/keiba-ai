"""
異常検知システム
① モデル精度の劣化を統計的に検知
② オッズの異常変動を検知（インサイダー・八百長の可能性）
③ レースパターンの不正兆候を検知
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text

PERF_FILE    = "D:\\keiba_ai\\data\\model_performance.json"
ALERT_OUT    = "D:\\keiba_ai\\data\\anomaly_alerts.json"
DB_URL       = "postgresql://postgres:trust@localhost:5433/mykeibadb"

# ──────────────────────────────────────────────────────────────
# 共通ユーティリティ
# ──────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _save_alerts(alerts: List[Dict]):
    os.makedirs(os.path.dirname(ALERT_OUT), exist_ok=True)
    history = _load_json(ALERT_OUT, [])
    history.extend(alerts)
    history = history[-200:]   # 最大200件保持
    with open(ALERT_OUT, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _make_alert(level: str, category: str, message: str,
                detail: Optional[Dict] = None) -> Dict:
    return {
        'detected_at': datetime.now().isoformat(),
        'level':       level,      # INFO / WARNING / CRITICAL
        'category':    category,
        'message':     message,
        'detail':      detail or {},
    }


# ──────────────────────────────────────────────────────────────
# ① モデル精度劣化検知
# ──────────────────────────────────────────────────────────────

def detect_model_degradation(window: int = 5,
                              zscore_thr: float = 2.0) -> List[Dict]:
    """
    過去のパフォーマンス履歴から精度劣化を統計的に検知する。

    手法: 直近 window 回の回収率が、全履歴の平均 ± zscore_thr×σ を外れた場合に警告。
    """
    alerts = []
    history = _load_json(PERF_FILE, [])

    if len(history) < window + 3:
        return alerts   # データ不足

    rois = np.array([h['recovery_rate'] for h in history])

    # ベースライン（直近 window 回を除いた全履歴）
    baseline = rois[:-window]
    recent   = rois[-window:]

    mean_b = baseline.mean()
    std_b  = baseline.std() if baseline.std() > 0 else 1e-6

    avg_recent = recent.mean()
    z = (avg_recent - mean_b) / std_b

    if z < -zscore_thr:
        level = 'CRITICAL' if z < -3.0 else 'WARNING'
        alerts.append(_make_alert(
            level, 'MODEL_DEGRADATION',
            f"モデル精度劣化検知: 直近{window}回平均回収率 "
            f"{avg_recent*100:.1f}% (ベースライン {mean_b*100:.1f}% | z={z:.2f})",
            {
                'avg_recent_roi': float(avg_recent),
                'baseline_mean':  float(mean_b),
                'baseline_std':   float(std_b),
                'z_score':        float(z),
                'window':         window,
            }
        ))

    # トレンド検知（単純線形回帰の傾き）
    if len(rois) >= 6:
        x = np.arange(len(rois[-6:]))
        y = rois[-6:]
        slope = np.polyfit(x, y, 1)[0]
        if slope < -0.02:   # 1ステップあたり回収率2%超下落
            alerts.append(_make_alert(
                'WARNING', 'MODEL_TREND_DECLINE',
                f"回収率が下降トレンド: 直近6回の傾き {slope*100:.2f}%/回",
                {'slope': float(slope), 'recent_rois': [float(r) for r in rois[-6:]]}
            ))

    return alerts


# ──────────────────────────────────────────────────────────────
# ② オッズ異常変動検知
# ──────────────────────────────────────────────────────────────

def _fetch_todays_odds(year: int) -> pd.DataFrame:
    engine = create_engine(DB_URL)
    query  = text("""
        SELECT race_code, umaban, tansho_odds, tansho_ninkijun
        FROM umagoto_race_joho
        WHERE kaisai_nen = :year
          AND tansho_odds IS NOT NULL
        ORDER BY race_code, umaban
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={'year': str(year)})
    df['tansho_odds'] = pd.to_numeric(df['tansho_odds'], errors='coerce')
    return df.dropna(subset=['tansho_odds'])


def detect_odds_anomaly(year: Optional[int] = None,
                        zscore_thr: float = 3.0) -> List[Dict]:
    """
    オッズの分布からの外れ値を検出する。
    同一条件（同距離・同馬場）のオッズ分布から逸脱している場合に警告。
    """
    alerts = []
    year   = year or datetime.now().year

    try:
        df = _fetch_todays_odds(year)
    except Exception as e:
        return [_make_alert('INFO', 'ODDS_FETCH_ERROR',
                            f"オッズ取得エラー（スキップ）: {e}")]

    if len(df) < 50:
        return alerts

    df['odds_decimal'] = df['tansho_odds'] / 10

    # レースごとの1番人気オッズを抽出
    fav_odds = (df[df['tansho_ninkijun'].astype(str) == '1']
                .groupby('race_code')['odds_decimal'].first())

    # 極端に低い1番人気オッズ（≦ 1.2倍）= 接待レース可能性
    very_low_fav = fav_odds[fav_odds <= 1.2]
    for race_code, odds in very_low_fav.items():
        alerts.append(_make_alert(
            'WARNING', 'SUSPICIOUS_FAVORITE_ODDS',
            f"異常に低い1番人気オッズ: race {race_code} → {odds:.1f}倍",
            {'race_code': str(race_code), 'fav_odds': float(odds)}
        ))

    # オッズ分布の外れ値（Z スコア）
    log_odds    = np.log1p(df['odds_decimal'])
    z_scores    = (log_odds - log_odds.mean()) / log_odds.std()
    df['z_odds'] = z_scores

    extreme = df[z_scores.abs() > zscore_thr]
    if len(extreme) > 0:
        top = extreme.nlargest(5, 'z_odds')
        for _, row in top.iterrows():
            alerts.append(_make_alert(
                'INFO', 'EXTREME_ODDS',
                f"極端なオッズ検出: {row['race_code']} 馬番{row['umaban']} "
                f"→ {row['odds_decimal']:.1f}倍 (z={row['z_odds']:.1f})",
                {
                    'race_code': str(row['race_code']),
                    'umaban':    str(row['umaban']),
                    'odds':      float(row['odds_decimal']),
                    'z_score':   float(row['z_odds']),
                }
            ))

    return alerts


# ──────────────────────────────────────────────────────────────
# ③ レースパターン不正兆候検知
# ──────────────────────────────────────────────────────────────

def _fetch_race_results(year: int, recent_n_races: int = 200) -> pd.DataFrame:
    engine = create_engine(DB_URL)
    query  = text("""
        SELECT
            race_code,
            umaban,
            tansho_ninkijun,
            tansho_odds,
            kakutei_chakujun
        FROM umagoto_race_joho
        WHERE kaisai_nen = :year
          AND kakutei_chakujun IS NOT NULL
          AND kakutei_chakujun != ''
        ORDER BY race_code DESC
        LIMIT :n
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn,
                         params={'year': str(year), 'n': recent_n_races * 20})
    df['kakutei_chakujun'] = pd.to_numeric(
        df['kakutei_chakujun'], errors='coerce')
    df['tansho_odds']      = pd.to_numeric(
        df['tansho_odds'],      errors='coerce')
    df['tansho_ninkijun']  = pd.to_numeric(
        df['tansho_ninkijun'],  errors='coerce')
    return df.dropna(subset=['kakutei_chakujun'])


def detect_race_irregularities(year: Optional[int] = None) -> List[Dict]:
    """
    レース結果パターンから不正の兆候を検知する。

    検知項目:
    1. 1番人気の連敗が統計的に異常な連続数
    2. 高オッズ馬が1着になる頻度の異常な増加
    3. 特定騎手の極端な成績低下
    """
    alerts = []
    year   = year or datetime.now().year

    try:
        df = _fetch_race_results(year)
    except Exception as e:
        return [_make_alert('INFO', 'RESULT_FETCH_ERROR',
                            f"結果取得エラー（スキップ）: {e}")]

    if len(df) < 100:
        return alerts

    # レースごとに1着馬の人気を取得
    winners = df[df['kakutei_chakujun'] == 1].copy()
    if len(winners) == 0:
        return alerts

    # ── 検知1: 1番人気連敗ストリーク ──
    fav_wins = []
    for _, race in df.groupby('race_code'):
        fav = race[race['tansho_ninkijun'] == 1]
        if len(fav) == 0:
            continue
        won = int((fav.iloc[0]['kakutei_chakujun'] == 1))
        fav_wins.append(won)

    if fav_wins:
        # 直近50レースの1番人気勝率
        recent_fav_rate = np.mean(fav_wins[-50:]) if len(fav_wins) >= 50 \
                          else np.mean(fav_wins)
        historical_rate = np.mean(fav_wins)   # 全体平均（約33%が標準）

        if recent_fav_rate < 0.15 and len(fav_wins) >= 30:
            alerts.append(_make_alert(
                'WARNING', 'FAV_WIN_ANOMALY',
                f"1番人気の勝率が異常低下: "
                f"直近{min(50,len(fav_wins))}R → {recent_fav_rate*100:.1f}% "
                f"(全体平均 {historical_rate*100:.1f}%)",
                {
                    'recent_fav_rate': float(recent_fav_rate),
                    'historical_rate': float(historical_rate),
                }
            ))

        # 連敗ストリーク（期待値ベース：5連敗以上で要注意、10連敗以上で警告）
        streak = 0
        max_streak = 0
        for w in reversed(fav_wins):
            if w == 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                break

        if streak >= 10:
            level = 'CRITICAL' if streak >= 15 else 'WARNING'
            alerts.append(_make_alert(
                level, 'FAV_LOSING_STREAK',
                f"1番人気 {streak}連敗中（統計的に稀な事象）",
                {'streak': streak}
            ))

    # ── 検知2: 超高配当頻発 ──
    winners_copy = winners.copy()
    winners_copy['odds_decimal'] = winners_copy['tansho_odds'] / 10
    very_high = (winners_copy['odds_decimal'] >= 50).mean()
    if very_high > 0.15:   # 15%超の高配当勝利は稀
        alerts.append(_make_alert(
            'WARNING', 'HIGH_ODDS_WIN_FREQ',
            f"50倍以上の超高配当馬が勝率 {very_high*100:.1f}% "
            f"（過去データから見て異常に高い）",
            {'rate': float(very_high)}
        ))

    # ── 検知3: 人気馬の着外率急上昇（直近30R vs 全体）──
    top3_fav = df[df['tansho_ninkijun'] <= 3].copy()
    if len(top3_fav) > 60:
        top3_recent  = top3_fav.iloc[-60:]
        top3_out_r   = (top3_recent['kakutei_chakujun'] > 3).mean()
        top3_out_all = (top3_fav['kakutei_chakujun'] > 3).mean()
        if top3_out_r > top3_out_all * 1.5 and top3_out_r > 0.7:
            alerts.append(_make_alert(
                'WARNING', 'POPULAR_HORSE_OUTRATE',
                f"人気上位3頭の着外率急上昇: "
                f"直近{len(top3_recent)}頭 {top3_out_r*100:.1f}% vs "
                f"全体 {top3_out_all*100:.1f}%",
                {
                    'recent_out_rate':  float(top3_out_r),
                    'overall_out_rate': float(top3_out_all),
                }
            ))

    return alerts


# ──────────────────────────────────────────────────────────────
# 統合実行
# ──────────────────────────────────────────────────────────────

def run_anomaly_detection(year: Optional[int] = None,
                          use_db: bool = True) -> List[Dict]:
    """
    3種の異常検知を実行してアラートを返す。

    use_db=False にすると DB アクセスをスキップ（モデル劣化検知のみ）。
    """
    year = year or datetime.now().year
    all_alerts: List[Dict] = []

    print(f"\n{'='*55}")
    print(f"🔍 異常検知システム起動 ({datetime.now().strftime('%H:%M:%S')})")
    print(f"{'='*55}")

    # ① モデル精度劣化
    print("\n【① モデル精度劣化検知】")
    alerts_model = detect_model_degradation()
    all_alerts.extend(alerts_model)
    if alerts_model:
        for a in alerts_model:
            _print_alert(a)
    else:
        print("  ✅ 異常なし")

    if use_db:
        # ② オッズ異常変動
        print("\n【② オッズ異常変動検知】")
        try:
            alerts_odds = detect_odds_anomaly(year)
            all_alerts.extend(alerts_odds)
            if alerts_odds:
                for a in alerts_odds:
                    _print_alert(a)
            else:
                print("  ✅ 異常なし")
        except Exception as e:
            print(f"  ⚠️ DBアクセス不可（スキップ）: {e}")

        # ③ レースパターン不正兆候
        print("\n【③ レースパターン不正兆候検知】")
        try:
            alerts_race = detect_race_irregularities(year)
            all_alerts.extend(alerts_race)
            if alerts_race:
                for a in alerts_race:
                    _print_alert(a)
            else:
                print("  ✅ 異常なし")
        except Exception as e:
            print(f"  ⚠️ DBアクセス不可（スキップ）: {e}")
    else:
        print("\n  （DB検知はスキップ: use_db=False）")

    # 結果サマリー
    print(f"\n{'='*55}")
    counts = {'CRITICAL': 0, 'WARNING': 0, 'INFO': 0}
    for a in all_alerts:
        counts[a.get('level', 'INFO')] = counts.get(a.get('level', 'INFO'), 0) + 1

    if counts['CRITICAL'] > 0:
        print(f"🚨 CRITICAL: {counts['CRITICAL']}件 — ベット停止を強く推奨")
    if counts['WARNING'] > 0:
        print(f"⚠️  WARNING:  {counts['WARNING']}件 — 投資額縮小を推奨")
    if counts['INFO'] > 0:
        print(f"ℹ️  INFO:     {counts['INFO']}件")
    if sum(counts.values()) == 0:
        print("✅ 全検知項目 異常なし")

    print(f"{'='*55}")

    # 保存
    if all_alerts:
        _save_alerts(all_alerts)

    return all_alerts


def _print_alert(alert: Dict):
    icons = {'CRITICAL': '🚨', 'WARNING': '⚠️', 'INFO': 'ℹ️'}
    icon = icons.get(alert['level'], 'ℹ️')
    print(f"  {icon} [{alert['level']}] {alert['message']}")


def load_alert_history(n: int = 50) -> List[Dict]:
    """保存済みアラート履歴を返す。"""
    return _load_json(ALERT_OUT, [])[-n:]


def get_alert_summary() -> Dict:
    """直近24時間のアラートをカテゴリ別に集計する。"""
    history = load_alert_history(200)
    cutoff  = (datetime.now() - timedelta(hours=24)).isoformat()
    recent  = [a for a in history if a.get('detected_at', '') >= cutoff]

    summary: Dict[str, List] = {}
    for a in recent:
        cat = a.get('category', 'OTHER')
        summary.setdefault(cat, []).append(a)

    return summary


if __name__ == "__main__":
    alerts = run_anomaly_detection()

    if alerts:
        print(f"\n📋 アラート詳細（{len(alerts)}件）")
        for a in alerts:
            print(f"\n  [{a['level']}] {a['category']}")
            print(f"  {a['message']}")
            if a.get('detail'):
                for k, v in a['detail'].items():
                    if not isinstance(v, list):
                        print(f"    {k}: {v}")
