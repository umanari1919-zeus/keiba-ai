"""
条件別ベット係数自動調整システム
- 競馬場×距離×芝ダート×季節の組み合わせで過去ROIを集計
- 得意条件(ROI>120%)は係数UP、不得意条件は係数DOWN
- ev_agent・risk_agentのベット額にリアルタイム適用
"""
import numpy as np
import pandas as pd
import json, os
import pickle
from datetime import datetime
from typing import Dict, Optional, Tuple

BASE_DIR = "D:\\keiba_ai"
MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")

# 係数クリップ（安全範囲）
COEFF_MIN = 0.20
COEFF_MAX = 2.00
MIN_SAMPLES = 30   # 係数計算に必要な最低サンプル数


def _prepare_model_frame(df: pd.DataFrame, feature_names) -> pd.DataFrame:
    X = df.copy()
    for feat in feature_names:
        if feat not in X.columns:
            X[feat] = 0
    X = X[list(feature_names)].copy()
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]):
            converted = pd.to_numeric(X[col], errors='coerce')
            if converted.notna().sum() > 0:
                X[col] = converted
            else:
                X[col] = pd.factorize(X[col].astype(str).fillna(""))[0]
    return X.fillna(0)


def ensure_win_probability(df: pd.DataFrame) -> pd.DataFrame:
    if 'win_probability' in df.columns and pd.to_numeric(df['win_probability'], errors='coerce').fillna(0).sum() > 0:
        return df
    if not os.path.exists(MODEL_PATH):
        return df

    print("  🔧 既存モデルから win_probability を生成中...")
    with open(MODEL_PATH, 'rb') as f:
        saved = pickle.load(f)

    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model = saved.get('cb_model')
    le = saved['le']
    features = saved['features']
    weights = saved.get('ensemble_weights', [0.5, 0.3, 0.2])
    if len(weights) < 3:
        weights = list(weights) + [0.0] * (3 - len(weights))

    X = _prepare_model_frame(df, features)
    lgb_p = lgb_model.predict_proba(X)
    xgb_p = xgb_model.predict_proba(X)
    if cb_model is not None:
        cb_p = (cb_model.predict_proba(X) if cb_model is not None else 0)
        ensemble_p = weights[0] * lgb_p + weights[1] * xgb_p + weights[2] * cb_p
    else:
        ensemble_p = weights[0] * lgb_p + weights[1] * xgb_p

    classes = list(le.classes_)
    win_idx = classes.index(1) if 1 in classes else 0
    out = df.copy()
    out['win_probability'] = ensemble_p[:, win_idx]
    return out


# ─────────────────────────────────────────────────────────────
# 条件キー生成
# ─────────────────────────────────────────────────────────────

def _season(month: int) -> str:
    if month in (3, 4, 5):  return '春'
    if month in (6, 7, 8):  return '夏'
    if month in (9, 10, 11): return '秋'
    return '冬'


def _dist_bucket(kyori: int) -> str:
    if kyori <= 1400:  return '短距離'
    if kyori <= 2000:  return 'マイル中距離'
    return '長距離'


def _surface(track_code) -> str:
    tc = int(track_code) if str(track_code).isdigit() else 0
    return '芝' if tc == 1 else 'ダート' if tc == 2 else '障害'


def make_condition_key(keibajo: str, kyori: int, track_code, month: int) -> str:
    return f"{keibajo}_{_surface(track_code)}_{_dist_bucket(kyori)}_{_season(month)}"


# ─────────────────────────────────────────────────────────────
# ROI テーブル構築
# ─────────────────────────────────────────────────────────────

def build_roi_table(df: pd.DataFrame,
                    win_prob_col: str = 'win_probability') -> pd.DataFrame:
    """
    過去データから条件別ROIテーブルを構築。
    win_probability が必要（model_train_03 実行後）。
    """
    df = df.copy()

    # 必要列の確認・型変換
    for col, default in [('tansho_odds', 0), ('kakutei_chakujun', 99),
                          ('kyori', 1600), ('track_code', 0),
                          ('race_month', 6), ('keibajo_code', '00')]:
        if col not in df.columns:
            df[col] = default

    df['odds_dec']  = pd.to_numeric(df['tansho_odds'],       errors='coerce').fillna(0) / 10
    df['rank']      = pd.to_numeric(df['kakutei_chakujun'],   errors='coerce').fillna(99)
    df['kyori']     = pd.to_numeric(df['kyori'],              errors='coerce').fillna(1600)
    df['month']     = pd.to_numeric(df['race_month'],         errors='coerce').fillna(6)
    df['keibajo']   = df['keibajo_code'].astype(str)

    # win_probability がなければスキップ
    if win_prob_col not in df.columns or df[win_prob_col].sum() == 0:
        return pd.DataFrame()

    df['win_p'] = pd.to_numeric(df[win_prob_col], errors='coerce').fillna(0)
    df['ev']    = df['win_p'] * df['odds_dec'] - 1.0

    # EVフィルタ（バックテストと同条件）
    df_bet = df[(df['ev'] >= 0.15) & (df['odds_dec'] >= 5.0)].copy()
    if len(df_bet) == 0:
        return pd.DataFrame()

    df_bet['won']   = (df_bet['rank'] == 1)
    df_bet['pnl']   = df_bet.apply(
        lambda r: r['odds_dec'] - 1 if r['won'] else -1.0, axis=1
    )
    df_bet['cond_key'] = df_bet.apply(
        lambda r: make_condition_key(
            r['keibajo'], int(r['kyori']), r['track_code'], int(r['month'])
        ), axis=1
    )

    rows = []
    for key, sub in df_bet.groupby('cond_key'):
        if len(sub) < MIN_SAMPLES:
            continue
        n         = len(sub)
        n_win     = sub['won'].sum()
        hit_rate  = n_win / n
        total_bet = n  # 1単位ずつ
        total_ret = sub[sub['won']]['odds_dec'].sum()
        roi       = total_ret / total_bet  # 1.0 = 100% = トントン

        # 係数計算（ROI=1.0→係数1.0, ROI=1.5→係数1.5, ROI=0.7→係数0.7）
        coeff = float(np.clip(roi, COEFF_MIN, COEFF_MAX))

        parts = key.split('_')
        rows.append({
            'cond_key':  key,
            'keibajo':   parts[0] if len(parts) > 0 else '',
            'surface':   parts[1] if len(parts) > 1 else '',
            'dist':      parts[2] if len(parts) > 2 else '',
            'season':    parts[3] if len(parts) > 3 else '',
            'n':         n,
            'hit_rate':  round(hit_rate * 100, 1),
            'roi':       round(roi * 100, 1),
            'coeff':     round(coeff, 3),
            'grade':     ('S' if coeff >= 1.40 else 'A' if coeff >= 1.15 else
                          'B' if coeff >= 0.90 else 'C'),
        })

    result = pd.DataFrame(rows).sort_values('roi', ascending=False)
    return result.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# 係数テーブル読み込み・適用
# ─────────────────────────────────────────────────────────────

_COEFF_TABLE: Optional[Dict[str, float]] = None

def load_coeff_table(year: int = None) -> Dict[str, float]:
    """係数テーブルを JSON から読み込む（キャッシュあり）"""
    global _COEFF_TABLE
    if _COEFF_TABLE is not None:
        return _COEFF_TABLE

    year = year or datetime.now().year
    path = f"{BASE_DIR}\\data\\condition_coeffs_{year}.json"
    if not os.path.exists(path):
        # 前年のファイルも試みる
        path = f"{BASE_DIR}\\data\\condition_coeffs_{year-1}.json"

    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            _COEFF_TABLE = json.load(f)
    else:
        _COEFF_TABLE = {}

    return _COEFF_TABLE


def get_bet_coefficient(keibajo: str, kyori: int,
                         track_code, month: int,
                         year: int = None) -> Tuple[float, str]:
    """
    特定レース条件に対するベット係数を返す。
    Returns: (coefficient, grade)
    """
    table = load_coeff_table(year)
    key = make_condition_key(keibajo, kyori, track_code, month)

    if key in table:
        entry = table[key]
        return float(entry.get('coeff', 1.0)), entry.get('grade', 'B')

    # 部分キーで段階的にフォールバック
    parts = key.split('_')
    for n_parts in [3, 2, 1]:
        partial = '_'.join(parts[:n_parts])
        for k, v in table.items():
            if k.startswith(partial):
                return float(v.get('coeff', 1.0)), v.get('grade', 'B')

    return 1.0, 'B'  # デフォルト


def apply_condition_coefficient(bet_amount: int,
                                  keibajo: str, kyori: int,
                                  track_code, month: int,
                                  year: int = None) -> Tuple[int, float, str]:
    """
    ベット額に条件係数を適用して調整額を返す。
    Returns: (adjusted_bet, coeff, grade)
    """
    coeff, grade = get_bet_coefficient(keibajo, kyori, track_code, month, year)
    adjusted = max(100, round(bet_amount * coeff / 100) * 100)
    return adjusted, coeff, grade


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_condition_adjuster(year: int = None) -> dict:
    year = year or datetime.now().year
    print("\n" + "="*55)
    print("⚙️ 条件別ベット係数自動調整")
    print("="*55)

    feat_path = f"{BASE_DIR}\\keiba_data_features.csv"
    if not os.path.exists(feat_path):
        print("  ⚠️ 特徴量ファイルなし")
        return {}

    df = pd.read_csv(feat_path, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
    print(f"  📊 全データ: {len(df):,}件")
    df = ensure_win_probability(df)
    if 'win_probability' in df.columns:
        df.to_csv(feat_path, index=False, encoding='utf-8-sig')

    roi_table = build_roi_table(df)

    if roi_table.empty:
        print("  ⚠️ win_probability なし → モデル学習後に再実行してください")
        # ダミーの係数テーブルを保存（全条件=1.0）
        dummy = {}
        path = f"{BASE_DIR}\\data\\condition_coeffs_{year}.json"
        os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dummy, f, ensure_ascii=False, indent=2)
        return {}

    # 係数テーブルを JSON に保存
    coeff_dict = {
        row['cond_key']: {'coeff': row['coeff'], 'grade': row['grade'],
                           'roi': row['roi'], 'n': row['n']}
        for _, row in roi_table.iterrows()
    }

    os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
    coeff_path = f"{BASE_DIR}\\data\\condition_coeffs_{year}.json"
    with open(coeff_path, 'w', encoding='utf-8') as f:
        json.dump(coeff_dict, f, ensure_ascii=False, indent=2)

    roi_csv = f"{BASE_DIR}\\data\\condition_roi_{year}.csv"
    roi_table.to_csv(roi_csv, index=False, encoding='utf-8-sig')

    # 結果表示
    print(f"\n  📋 条件数: {len(roi_table)}件（{MIN_SAMPLES}件以上のみ）")

    grade_dist = roi_table['grade'].value_counts()
    for g in ['S', 'A', 'B', 'C']:
        cnt = int(grade_dist.get(g, 0))
        print(f"  Grade {g}: {cnt:3d}条件")

    top = roi_table[roi_table['grade'] == 'S'].head(10)
    if not top.empty:
        print(f"\n  🏆 得意条件 TOP (Grade S):")
        for _, r in top.iterrows():
            print(f"    {r['cond_key']:40s} "
                  f"ROI={r['roi']:6.1f}% 係数={r['coeff']:.2f}x n={r['n']}")

    worst = roi_table.tail(5)
    if not worst.empty:
        print(f"\n  ⚠️ 不得意条件 (係数引き下げ):")
        for _, r in worst.iterrows():
            print(f"    {r['cond_key']:40s} "
                  f"ROI={r['roi']:6.1f}% 係数={r['coeff']:.2f}x n={r['n']}")

    print(f"\n  💾 保存: {coeff_path}")

    # キャッシュリセット
    global _COEFF_TABLE
    _COEFF_TABLE = None

    return {'n_conditions': len(roi_table), 'coeff_path': coeff_path}


if __name__ == "__main__":
    run_condition_adjuster()
