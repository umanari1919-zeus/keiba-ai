"""
時系列ウォークフォワード・バックテスト
- 訓練期間でモデル学習 → テスト期間で評価 → 1年ずつロール
- パージングウィンドウ（2週間）でリーク防止
- 各折のROI/的中率/最大DDを集計して汎化性能を評価
"""
import numpy as np
import pandas as pd
import pickle, json, os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

from pipeline.config import BASE_DIR, CSV_FEATURES, DATA_DIR
from pipeline.native_runtime import ensure_native_runtime

FEAT_FILE  = CSV_FEATURES
MODEL_FILE = os.path.join(BASE_DIR, "model_v8.pkl")

PURGE_WEEKS   = 2     # 訓練/テスト境界のパージ幅（週）
MIN_TRAIN_YRS = 2     # 最低訓練年数
EV_THRESHOLD  = 0.05
KELLY_FRAC    = 0.10  # 1/10ケリー（WF検証DD64%→安全係数に引き下げ）
MIN_ODDS      = 5.0


# ─────────────────────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────────────────────

def _parse_race_date(race_code: str) -> Optional[datetime]:
    """race_code (16桁) から開催日を抽出: 先頭8桁=YYYYMMDD"""
    try:
        return datetime.strptime(str(race_code)[:8], "%Y%m%d")
    except Exception:
        return None


def add_race_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'race_date' not in df.columns:
        if 'race_code' in df.columns:
            df['race_date'] = df['race_code'].astype(str).map(_parse_race_date)
        elif all(c in df.columns for c in ['kaisai_nen', 'kaisai_tsuki', 'kaisai_nichime']):
            df['race_date'] = pd.to_datetime(
                df['kaisai_nen'].astype(str) + '-' +
                df['kaisai_tsuki'].astype(str).str.zfill(2) + '-' +
                df['kaisai_nichime'].astype(str).str.zfill(2),
                errors='coerce'
            )
    return df


# ─────────────────────────────────────────────────────────────
# 折ごとのモデル学習
# ─────────────────────────────────────────────────────────────

def train_fold_model(train_df: pd.DataFrame, saved_template: dict) -> dict:
    """
    訓練データでアンサンブルを再学習して返す。
    saved_template は model_v8.pkl の構造を踏襲。
    """
    ensure_native_runtime()
    import lightgbm as lgb
    import xgboost as xgb
    import catboost as cb
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import train_test_split

    features = saved_template['features']
    feats    = [f for f in features if f in train_df.columns]
    X        = train_df[feats].fillna(0)
    y        = train_df['kakutei_chakujun'].fillna(99)

    # 全データのクラス範囲でLabelEncoderを初期化（テスト時のクラスミスマッチ防止）
    all_classes = sorted(y.unique())
    le = LabelEncoder()
    le.fit(all_classes)
    y_enc = le.transform(y)

    X_tr, X_vl, y_tr, y_vl = train_test_split(X, y,     test_size=0.15, random_state=42)
    _, _,  ye_tr, ye_vl    = train_test_split(X, y_enc, test_size=0.15, random_state=42)

    lgb_m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05,
                                 num_leaves=63, random_state=42,
                                 n_jobs=-1, verbose=-1)
    lgb_m.fit(X_tr, y_tr)

    xgb_m = xgb.XGBClassifier(n_estimators=150, learning_rate=0.05,
                                max_depth=5, random_state=42,
                                n_jobs=-1, verbosity=0, eval_metric='mlogloss')
    xgb_m.fit(X_tr, ye_tr)

    cb_m = cb.CatBoostClassifier(iterations=150, learning_rate=0.05,
                                  depth=5, random_seed=42, verbose=0)
    cb_m.fit(X_tr, y_tr)

    return {
        'lgb_model': lgb_m, 'xgb_model': xgb_m, 'cb_model': cb_m,
        'le': le, 'features': feats,
        'ensemble_weights': [0.5, 0.3, 0.2],
    }


def predict_proba_win(model_dict: dict, df: pd.DataFrame) -> np.ndarray:
    """アンサンブル勝率を返す"""
    feats   = [f for f in model_dict['features'] if f in df.columns]
    X       = df[feats].fillna(0)
    w       = model_dict.get('ensemble_weights', [0.5, 0.3, 0.2])
    le      = model_dict['le']
    p_ens   = (w[0] * model_dict['lgb_model'].predict_proba(X) +
               w[1] * model_dict['xgb_model'].predict_proba(X) +
               w[2] * model_dict['cb_model'].predict_proba(X))
    classes = list(le.classes_)
    win_idx = classes.index(1) if 1 in classes else 0
    return p_ens[:, win_idx]


# ─────────────────────────────────────────────────────────────
# 折ごとのバックテスト
# ─────────────────────────────────────────────────────────────

def _kelly_bet(bankroll: float, p: float, odds: float) -> int:
    b = odds - 1
    if b <= 0 or p <= 0 or not np.isfinite(p) or not np.isfinite(odds):
        return 0
    k = max(0.0, (p * b - (1 - p)) / b) * KELLY_FRAC
    k = min(k, 0.40)
    raw = bankroll * k / 100
    return 0 if not np.isfinite(raw) else max(100, round(raw) * 100)


def backtest_fold(test_df: pd.DataFrame, win_probs: np.ndarray,
                  initial_bankroll: float = 100_000) -> Dict:
    """1折のバックテスト実行"""
    test_df = test_df.copy()
    test_df['win_probability'] = win_probs
    test_df['odds_dec'] = pd.to_numeric(
        test_df.get('tansho_odds', pd.Series([0]*len(test_df))),
        errors='coerce').fillna(0) / 10
    test_df['ev'] = test_df['win_probability'] * test_df['odds_dec'] - 1.0
    test_df['rank'] = pd.to_numeric(
        test_df.get('kakutei_chakujun', pd.Series([99]*len(test_df))),
        errors='coerce').fillna(99)

    bankroll = initial_bankroll
    peak     = bankroll
    bets, dd_list = [], []

    for rc, race_df in test_df.groupby('race_code'):
        cands = race_df[
            (race_df['ev'] >= EV_THRESHOLD) &
            (race_df['odds_dec'] >= MIN_ODDS)
        ]
        race_pnl = 0
        for _, row in cands.iterrows():
            p    = float(row['win_probability'])
            odds = float(row['odds_dec'])
            bet  = _kelly_bet(bankroll, p, odds)
            if bet <= 0:
                continue
            won  = (int(row['rank']) == 1)
            pnl  = bet * (odds - 1) if won else -bet
            if not np.isfinite(pnl):
                continue
            race_pnl += pnl
            bets.append({'won': won, 'bet': bet, 'pnl': pnl, 'odds': odds})

        bankroll = float(np.clip(bankroll + race_pnl, 0, 1e10))
        peak     = max(peak, bankroll)
        dd       = (peak - bankroll) / peak if peak > 0 else 0
        dd_list.append(dd)

    if not bets:
        return {'roi': 0, 'hit_rate': 0, 'n_bets': 0,
                'max_dd': 0, 'final': initial_bankroll, 'growth': 0}

    total_bet = sum(b['bet'] for b in bets)
    total_pnl = sum(b['pnl'] for b in bets)
    wins      = sum(1 for b in bets if b['won'])
    roi       = total_pnl / total_bet * 100 if total_bet > 0 else 0

    return {
        'roi':      round(roi, 2),
        'hit_rate': round(wins / len(bets) * 100, 2),
        'n_bets':   len(bets),
        'max_dd':   round(max(dd_list) * 100, 2) if dd_list else 0,
        'final':    bankroll,
        'growth':   round((bankroll / initial_bankroll - 1) * 100, 2),
    }


# ─────────────────────────────────────────────────────────────
# ウォークフォワード本体
# ─────────────────────────────────────────────────────────────

def walk_forward_backtest(df: pd.DataFrame,
                           template: dict,
                           test_years: List[int] = None,
                           retrain: bool = True) -> List[Dict]:
    """
    ウォークフォワード検証。
    各テスト年に対して: 過去データで学習 → テスト年で評価。

    retrain=False の場合は既存モデル（template）をそのまま使用（高速）。
    """
    df = add_race_date(df)
    df['race_date'] = pd.to_datetime(df['race_date'], errors='coerce')
    df['_year'] = df['race_date'].dt.year

    all_years = sorted(df['_year'].dropna().unique().astype(int))
    if test_years is None:
        # 最後2年をテスト対象（それ以前を訓練）
        test_years = [int(y) for y in all_years if y >= all_years[-2]]

    results = []
    purge_delta = timedelta(weeks=PURGE_WEEKS)

    for test_yr in test_years:
        train_years = [y for y in all_years if y < test_yr]
        if len(train_years) < MIN_TRAIN_YRS:
            print(f"  [{test_yr}] 訓練データ不足（{len(train_years)}年分）→ スキップ")
            continue

        # パージング: テスト年開始の2週間前までを訓練に使う
        purge_end = pd.Timestamp(datetime(test_yr, 1, 1) - purge_delta)

        train_df = df[df['race_date'] < purge_end].copy()
        test_df  = df[df['_year'] == test_yr].copy()

        if len(train_df) == 0 or len(test_df) == 0:
            continue

        print(f"  [{test_yr}] 訓練: {len(train_df):,}件 → テスト: {len(test_df):,}件", end='')

        # 学習
        if retrain:
            try:
                fold_model = train_fold_model(train_df, template)
            except Exception as e:
                print(f" ⚠️ 学習失敗: {e}")
                fold_model = template
        else:
            fold_model = template

        # 予測
        win_probs = predict_proba_win(fold_model, test_df)

        # バックテスト
        fold_result = backtest_fold(test_df, win_probs)
        fold_result['test_year']    = test_yr
        fold_result['train_n']      = len(train_df)
        fold_result['test_n']       = len(test_df)
        fold_result['retrained']    = retrain

        print(f"  ROI={fold_result['roi']:+.1f}% "
              f"的中率={fold_result['hit_rate']:.1f}% "
              f"最大DD={fold_result['max_dd']:.1f}% "
              f"ベット={fold_result['n_bets']}")

        results.append(fold_result)

    return results


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_walkforward_backtest(retrain: bool = True) -> dict:
    print("\n" + "="*60)
    print("🔄 時系列ウォークフォワード・バックテスト")
    mode = "モデル再学習あり" if retrain else "既存モデル使用（高速）"
    print(f"   パージ幅: {PURGE_WEEKS}週 / EV閾値: {EV_THRESHOLD*100:.0f}% / {mode}")
    print("="*60)

    if not os.path.exists(FEAT_FILE):
        print("  ⚠️ 特徴量ファイルなし")
        return {}
    if not os.path.exists(MODEL_FILE):
        print("  ⚠️ model_v8.pkl なし → model_train_03 を先に実行")
        return {}

    df = pd.read_csv(FEAT_FILE, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
    print(f"  📊 全データ: {len(df):,}件")

    with open(MODEL_FILE, 'rb') as f:
        template = pickle.load(f)

    # 利用可能な全年度を確認
    df = add_race_date(df)
    df['_year'] = pd.to_datetime(df['race_date']).dt.year
    available = sorted(df['_year'].dropna().unique().astype(int))
    print(f"  📅 利用可能年度: {available}")

    # テスト対象年（最後2年）
    test_years = [y for y in available if y >= available[-2]]
    print(f"  🎯 テスト対象: {test_years}  訓練: {[y for y in available if y < test_years[0]]}\n")

    results = walk_forward_backtest(df, template,
                                     test_years=test_years,
                                     retrain=retrain)

    if not results:
        print("  ⚠️ 有効な折なし")
        return {}

    # サマリー
    result_df = pd.DataFrame(results)
    print("\n" + "─"*60)
    print("📊 ウォークフォワード集計")
    print("─"*60)
    print(result_df[['test_year', 'roi', 'hit_rate', 'max_dd',
                      'n_bets', 'growth']].to_string(index=False))

    avg_roi    = result_df['roi'].mean()
    avg_hit    = result_df['hit_rate'].mean()
    avg_dd     = result_df['max_dd'].mean()
    n_positive = (result_df['roi'] > 0).sum()

    print(f"\n  📈 平均ROI     : {avg_roi:+.1f}%")
    print(f"  🎯 平均的中率  : {avg_hit:.1f}%")
    print(f"  📉 平均最大DD  : {avg_dd:.1f}%")
    print(f"  ✅ プラス折    : {n_positive}/{len(results)}")

    # 汎化判定（ROI + DD両方考慮）
    if avg_roi > 5 and n_positive >= len(results) * 0.6 and avg_dd < 50:
        verdict = "✅ 汎化性能 良好 — 実運用可能レベル"
    elif avg_roi > 5 and avg_dd >= 50:
        verdict = "⚠️ ROIは良好だが最大DD過大 — Kelly係数を0.10以下に引き下げ推奨"
    elif avg_roi > 0:
        verdict = "⚠️ 汎化性能 普通 — パラメータ調整を推奨"
    else:
        verdict = "❌ 汎化性能 不足 — 過学習の可能性あり"
    print(f"\n  {verdict}")

    # DD警告: 60%超の場合はKelly推奨係数を自動算出
    if avg_dd >= 60:
        safe_kelly = round(KELLY_FRAC * 0.40, 2)  # 60%超→60%削減
        print(f"  ⚠️  最大DD {avg_dd:.1f}% — 安全なKelly係数: {safe_kelly} 推奨")
        print(f"     bankroll_advanced_24.py の KELLY_FRACTION を {safe_kelly} に変更してください")
    elif avg_dd >= 40:
        safe_kelly = round(KELLY_FRAC * 0.65, 2)
        print(f"  ⚠️  最大DD {avg_dd:.1f}% — 安全なKelly係数: {safe_kelly} 推奨")

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    out = {
        'mode':        mode,
        'purge_weeks': PURGE_WEEKS,
        'ev_threshold': EV_THRESHOLD,
        'kelly_frac':   KELLY_FRAC,
        'folds':        results,
        'avg_roi':      round(avg_roi, 2),
        'avg_hit_rate': round(avg_hit, 2),
        'avg_max_dd':   round(avg_dd, 2),
        'n_positive':   int(n_positive),
        'verdict':      verdict,
    }
    out_path = os.path.join(DATA_DIR, "walkforward_result.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    folds_path = os.path.join(DATA_DIR, "walkforward_folds.csv")
    result_df.to_csv(folds_path,
                     index=False, encoding='utf-8-sig')
    print(f"\n  💾 保存: data/walkforward_result.json")
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--fast', action='store_true',
                        help='既存モデルを再利用（再学習なし・高速）')
    args = parser.parse_args()
    run_walkforward_backtest(retrain=not args.fast)
