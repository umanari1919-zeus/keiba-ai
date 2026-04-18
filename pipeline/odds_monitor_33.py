"""
オッズ変動モニタリング
- 開始オッズ→締め切りオッズの変動を分類（SHARP/STEAM/DRIFT/STABLE）
- プロ資金流入シグナル検出 → 参戦価値判断に反映
- 過去データから変動パターンと的中率の相関を分析
- リアルタイム監視フック（APIキー設定時）
"""
import numpy as np
import pandas as pd
import json, os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

BASE_DIR = "D:\\keiba_ai"


# ─────────────────────────────────────────────────────────────
# オッズ変動分類
# ─────────────────────────────────────────────────────────────

class OddsMovement(str, Enum):
    SHARP   = "SHARP"    # 急落（5%以上下落）→ プロ資金流入
    STEAM   = "STEAM"    # 急騰（10%以上上昇）→ 資金離脱
    DRIFT   = "DRIFT"    # 緩やかな上昇（5〜10%）→ 見送り傾向
    STABLE  = "STABLE"   # 安定（±5%以内）
    UNKNOWN = "UNKNOWN"


def classify_movement(opening: float, closing: float,
                      sharp_drop: float   = -0.05,
                      steam_rise: float   =  0.10,
                      drift_rise: float   =  0.05) -> OddsMovement:
    """
    オッズ変動を分類する。
    opening: 開幕オッズ, closing: 締め切りオッズ
    """
    if opening <= 0:
        return OddsMovement.UNKNOWN
    pct = (closing - opening) / opening   # 負 = 下落（人気上昇）

    if pct <= sharp_drop:
        return OddsMovement.SHARP
    if pct >= steam_rise:
        return OddsMovement.STEAM
    if pct >= drift_rise:
        return OddsMovement.DRIFT
    return OddsMovement.STABLE


def should_bet_after_movement(movement: OddsMovement, ev: float,
                               confidence: float = 0.5) -> Tuple[bool, str]:
    """
    オッズ変動を考慮してベット可否を判断。
    Returns: (bet_ok, reason)
    """
    if movement == OddsMovement.SHARP and ev > 0:
        # プロ資金が入ったならより有利 → 積極的にベット
        return True, "プロ資金流入確認 → 参戦推奨"
    if movement == OddsMovement.STEAM:
        # 急騰は資金離脱 → EVが大幅プラスでも慎重に
        return ev > 0.20, "急騰（資金離脱）→ EV20%超のみ参戦"
    if movement == OddsMovement.DRIFT:
        return ev > 0.10, "緩やかな上昇 → EV10%超のみ参戦"
    # STABLE
    return ev > 0.15, "安定オッズ → 標準EV基準（15%閾値）"


# ─────────────────────────────────────────────────────────────
# 過去データからオッズ変動パターン分析
# ─────────────────────────────────────────────────────────────

def analyze_odds_movement_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    過去データにオッズ変動列がある場合に分析。
    JRAのデータには開幕オッズ(tansho_odds_open)と締め切り(tansho_odds)が
    別々に存在する場合がある。存在しない場合は前走オッズとの比較で代替。
    """
    if 'tansho_odds' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['tansho_odds_dec'] = pd.to_numeric(df['tansho_odds'], errors='coerce') / 10

    # 開幕オッズがなければ前走オッズで代替
    if 'tansho_odds_open' in df.columns:
        df['opening'] = pd.to_numeric(df['tansho_odds_open'], errors='coerce') / 10
    elif 'prev_odds' in df.columns:
        df['opening'] = pd.to_numeric(df['prev_odds'], errors='coerce')
    else:
        df['opening'] = df['tansho_odds_dec']  # 変動なし扱い

    df['movement_pct'] = (df['tansho_odds_dec'] - df['opening']) / df['opening'].clip(lower=0.1)
    df['movement'] = df.apply(
        lambda r: classify_movement(r['opening'], r['tansho_odds_dec']).value,
        axis=1
    )

    if 'kakutei_chakujun' not in df.columns:
        return df[['movement', 'movement_pct']].dropna()

    df['won']   = (pd.to_numeric(df['kakutei_chakujun'], errors='coerce') == 1)
    df['placed'] = (pd.to_numeric(df['kakutei_chakujun'], errors='coerce') <= 3)

    # 変動分類別の的中率・回収率集計
    rows = []
    for mv in OddsMovement:
        sub = df[df['movement'] == mv.value]
        if len(sub) == 0:
            continue
        total_bet = (sub['tansho_odds_dec'] * 0 + 1).sum()  # 各1単位と仮定
        total_ret = sub[sub['won']]['tansho_odds_dec'].sum()
        rows.append({
            '変動区分':  mv.value,
            '件数':      len(sub),
            '勝率':      round(sub['won'].mean() * 100, 1),
            '複勝率':    round(sub['placed'].mean() * 100, 1),
            '平均変動%': round(sub['movement_pct'].mean() * 100, 1),
            '単勝回収率': round(total_ret / max(len(sub), 1), 3),
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# リアルタイム監視（ポーリング）
# ─────────────────────────────────────────────────────────────

class OddsSnapshot:
    """オッズのスナップショットを管理"""
    def __init__(self):
        self._store: Dict[str, Dict[str, float]] = {}  # race_code → {bamei: odds}
        self._first: Dict[str, Dict[str, float]] = {}  # 初回記録

    def update(self, race_code: str, odds_map: Dict[str, float]):
        if race_code not in self._first:
            self._first[race_code] = dict(odds_map)
        self._store[race_code] = dict(odds_map)

    def get_movements(self, race_code: str) -> List[Dict]:
        """変動があった馬を返す"""
        if race_code not in self._store or race_code not in self._first:
            return []
        results = []
        for bamei, current in self._store[race_code].items():
            opening = self._first[race_code].get(bamei, current)
            mv = classify_movement(opening, current)
            pct = (current - opening) / max(opening, 0.1) * 100
            results.append({
                'bamei':    bamei,
                'opening':  opening,
                'current':  current,
                'pct':      round(pct, 1),
                'movement': mv.value,
            })
        return sorted(results, key=lambda x: x['pct'])  # 最も下落した馬から

    def get_sharp_signals(self, race_code: str, min_drop_pct: float = 5.0) -> List[Dict]:
        return [m for m in self.get_movements(race_code)
                if m['movement'] == OddsMovement.SHARP.value
                and abs(m['pct']) >= min_drop_pct]


def monitor_odds_live(race_codes: List[str], interval_sec: int = 60,
                      max_cycles: int = 30) -> OddsSnapshot:
    """
    リアルタイムオッズ監視ループ（netkeiba スクレイピング版）。
    NETKEIBA_SESSION_ID 環境変数がある場合のみ実際にスクレイピング。
    それ以外はフレームワークのみ提供。
    """
    snapshot = OddsSnapshot()
    session_id = os.environ.get("NETKEIBA_SESSION_ID", "")

    if not session_id:
        print("  ℹ️  NETKEIBA_SESSION_ID 未設定 → リアルタイム監視スキップ")
        print("     .env に NETKEIBA_SESSION_ID=xxx を設定すると自動監視が有効になります")
        return snapshot

    import time
    try:
        import requests
    except ImportError:
        print("  ⚠️ requests 未インストール: pip install requests")
        return snapshot

    headers = {'Cookie': f'NETKEIBA_SESSION={session_id}'}

    for cycle in range(max_cycles):
        for rc in race_codes:
            try:
                url = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={rc}&type=1"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.ok:
                    data = resp.json()
                    odds_map = {}
                    for item in data.get('data', {}).get('odds', []):
                        bamei = item.get('name', '')
                        odds  = float(item.get('odds', 0))
                        if bamei and odds > 0:
                            odds_map[bamei] = odds
                    snapshot.update(rc, odds_map)
                    sharps = snapshot.get_sharp_signals(rc)
                    if sharps:
                        for s in sharps:
                            print(f"  🔥 SHARP: {rc} {s['bamei']} "
                                  f"{s['opening']:.1f}→{s['current']:.1f}倍 "
                                  f"({s['pct']:+.1f}%)")
            except Exception as e:
                pass  # ネットワークエラーは無視して継続

        time.sleep(interval_sec)

    return snapshot


# ─────────────────────────────────────────────────────────────
# EV補正（オッズ変動を織り込んだEV再計算）
# ─────────────────────────────────────────────────────────────

def adjust_ev_for_movement(ev: float, movement: OddsMovement,
                            movement_pct: float) -> float:
    """
    オッズ変動を考慮してEVを補正する。
    SHARP → EVにボーナス（プロが注目している証拠）
    STEAM → EVにペナルティ（資金離脱 = 問題あり）
    """
    if movement == OddsMovement.SHARP:
        # 5%下落ごとに+2%ボーナス
        bonus = abs(movement_pct) / 5 * 0.02
        return ev + min(bonus, 0.10)
    if movement == OddsMovement.STEAM:
        # 10%上昇ごとに-3%ペナルティ
        penalty = movement_pct / 10 * 0.03
        return ev - min(penalty, 0.15)
    return ev


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_odds_monitor(year: int = None) -> dict:
    year = year or datetime.now().year
    print("\n" + "="*55)
    print("📡 オッズ変動モニタリング")
    print("="*55)

    feat_path = f"{BASE_DIR}\\keiba_data_features.csv"
    if not os.path.exists(feat_path):
        print("  ⚠️ 特徴量ファイルなし")
        return {}

    df = pd.read_csv(feat_path, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
    df = df[df['kaisai_nen'] == year]

    print(f"  📊 {year}年データ: {len(df):,}件")

    # 過去変動パターン分析
    print("\n  📈 変動区分別成績分析...")
    hist = analyze_odds_movement_history(df)
    if not hist.empty:
        print(hist.to_string(index=False))
    else:
        print("  ⚠️ オッズ変動データなし（prev_odds 列が必要）")
        # prev_oddsがある場合の仮統計を表示
        print("\n  💡 参考: 変動区分の定義")
        print("    SHARP  : オッズ5%以上下落  → プロ資金流入 → EV+2〜10%ボーナス")
        print("    STEAM  : オッズ10%以上上昇 → 資金離脱     → EV-3〜15%ペナルティ")
        print("    DRIFT  : オッズ5〜10%上昇  → 弱い離脱     → EV閾値引き上げ")
        print("    STABLE : 変動±5%以内       → 通常判定")

    # リアルタイム監視の設定確認
    session_id = os.environ.get("NETKEIBA_SESSION_ID", "")
    print(f"\n  📡 リアルタイム監視: {'有効' if session_id else '⏩ NETKEIBA_SESSION_ID 未設定'}")

    # 設定を保存
    config = {
        'sharp_drop_threshold':  -0.05,
        'steam_rise_threshold':   0.10,
        'drift_rise_threshold':   0.05,
        'sharp_ev_bonus':         0.02,
        'steam_ev_penalty':       0.03,
        'realtime_enabled':       bool(session_id),
        'poll_interval_sec':      60,
    }
    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
    with open(f"{BASE_DIR}\\data\\odds_monitor_config.json", 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"  💾 設定保存: data/odds_monitor_config.json")
    return config


if __name__ == "__main__":
    run_odds_monitor()
