import json
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
from pipeline.ensemble_utils import load_ensemble_weights

EV_THRESHOLD = 0.15
MIN_ODDS     = 10.0

# レース種別ごとのEV閾値（新馬・障害は低め、ハンデ戦は高め）
EV_THRESHOLDS_BY_TYPE = {
    "debut":   0.10,   # 新馬戦: 実績なし → 低い閾値で広く拾う
    "shogai":  0.10,   # 障害戦: 専門性 → 低め
    "handicap": 0.20,  # ハンデ戦: 混戦 → 高め
    "default": EV_THRESHOLD,
}

BASE_DIR   = "D:\\keiba_ai"
MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE  = os.path.join(BASE_DIR, "keiba_data_features.csv")
KB_DIR     = os.path.join(BASE_DIR, "data", "knowledge_base")


# ─────────────────────────────────────────────────────────────
# knowledge_base EV boost
# ─────────────────────────────────────────────────────────────

_ev_boost_cache: dict = {}

def _load_ev_boost_map() -> dict:
    """knowledge_curator が生成した EV boost map を読み込む（キャッシュあり）。"""
    global _ev_boost_cache
    if _ev_boost_cache:
        return _ev_boost_cache
    path = os.path.join(KB_DIR, "ev_boost_map.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            _ev_boost_cache = json.load(f)
    except Exception:
        _ev_boost_cache = {}
    return _ev_boost_cache


def _apply_ev_boost(row: pd.Series, ev: float) -> float:
    """
    knowledge_base の EV boost を適用。
    race_code または (chichi, keibajo) をキーに boost 係数を乗算。
    """
    boost_map = _load_ev_boost_map()
    if not boost_map:
        return ev

    # race_code キー
    rc = str(row.get("race_code", ""))
    if rc in boost_map:
        return ev * float(boost_map[rc])

    # (父馬, 競馬場) キー
    chichi = str(row.get("chichi", ""))
    jyo = rc[8:10] if len(rc) >= 10 else ""
    combo_key = f"{chichi}_{jyo}"
    if combo_key in boost_map:
        return ev * float(boost_map[combo_key])

    return ev


def _get_race_type(row: pd.Series) -> str:
    """レース種別を判定してEV閾値キーを返す。"""
    # 新馬戦: joken_cd == '005' or race_name に "新馬" を含む
    joken = str(row.get("joken_cd", "")).strip()
    race_name = str(row.get("race_name", "")).lower()
    kyoso_joken = str(row.get("kyoso_joken_cd", "")).strip()

    if joken == "005" or "新馬" in race_name:
        return "debut"
    if "障害" in race_name or "hs" in race_name or kyoso_joken in ("210", "220"):
        return "shogai"
    if "ハンデ" in race_name or "handicap" in race_name:
        return "handicap"
    return "default"


def _get_ev_threshold(row: pd.Series) -> float:
    """行のレース種別に対応するEV閾値を返す。"""
    return EV_THRESHOLDS_BY_TYPE.get(_get_race_type(row), EV_THRESHOLD)


# ─────────────────────────────────────────────────────────────
# Core functions
# ─────────────────────────────────────────────────────────────

def _get_win_prob_index(le):
    classes = list(le.classes_)
    if 1 in classes:
        return classes.index(1)
    if '1' in classes:
        return classes.index('1')
    return 0


def extract_win_probabilities(ensemble_proba, le):
    idx = _get_win_prob_index(le)
    return ensemble_proba[:, idx]


def calculate_ev(p_win, odds):
    return p_win * odds - 1.0


def build_ev_dataframe(test_df, ensemble_proba, le):
    win_probs = extract_win_probabilities(ensemble_proba, le)
    result = test_df.copy()
    result['win_probability'] = win_probs
    result['odds_decimal'] = pd.to_numeric(
        result['tansho_odds'], errors='coerce').fillna(0) / 10
    # 基本EV
    result['expected_value'] = (
        result['win_probability'] * result['odds_decimal'] - 1.0
    )
    # knowledge_base boost 適用
    boost_map = _load_ev_boost_map()
    if boost_map:
        result['expected_value'] = result.apply(
            lambda r: _apply_ev_boost(r, r['expected_value']), axis=1
        )
        print(f"  [EV] knowledge_base boost 適用 ({len(boost_map)}件)")
    # レース種別EV閾値カラム（filter で使用）
    result['ev_threshold'] = result.apply(_get_ev_threshold, axis=1)
    # レース種別フラグ
    result['race_type'] = result.apply(_get_race_type, axis=1)
    return result


def filter_positive_ev(df, threshold=EV_THRESHOLD, min_odds=MIN_ODDS):
    """
    レース種別ごとの閾値 (ev_threshold) を使って正のEV馬を抽出。
    ev_threshold カラムがない場合は固定 threshold を使用。
    """
    if 'ev_threshold' in df.columns:
        # 行ごとに閾値を適用
        mask = (
            (df['expected_value'] >= df['ev_threshold']) &
            (df['odds_decimal']   >= min_odds)
        )
    else:
        mask = (
            (df['expected_value'] >= threshold) &
            (df['odds_decimal']   >= min_odds)
        )
    filtered = df[mask].copy()
    best = (filtered
            .sort_values('expected_value', ascending=False)
            .groupby('race_code', as_index=False)
            .first())
    return best.sort_values('expected_value', ascending=False)


def run_ev_analysis(year=2025, threshold=EV_THRESHOLD):
    print(f"[EV] {datetime.now()} 期待値計算エンジン起動...")

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {MODEL_PATH}\n"
            "先に pipeline/model_train_03.py を実行してください"
        )
    try:
        with open(MODEL_PATH, "rb") as fh:
            saved = pickle.load(fh)
    except Exception as exc:
        raise RuntimeError(f"モデル読み込みエラー: {exc}") from exc

    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model  = saved['cb_model']
    le        = saved['le']
    features  = saved['features']
    weights   = load_ensemble_weights(saved)

    if not os.path.exists(FEAT_FILE):
        raise FileNotFoundError(
            f"特徴量CSVが見つかりません: {FEAT_FILE}\n"
            "先に pipeline/feature_eng_02.py を実行してください"
        )
    try:
        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig",
                         low_memory=False, on_bad_lines='skip')
    except Exception as exc:
        raise RuntimeError(f"特徴量CSV読み込みエラー: {exc}") from exc

    df = df.fillna(0)
    test_df = df[df['kaisai_nen'] == year].copy()

    if len(test_df) == 0:
        print(f"[EV] {year}年のデータがありません")
        return pd.DataFrame()

    missing_feats = [feat for feat in features if feat not in test_df.columns]
    if missing_feats:
        print(f"[EV] 不足特徴量 {len(missing_feats)}件 -> 0埋め")
        for feat in missing_feats:
            test_df[feat] = 0

    X_test = test_df[features].copy()
    for col in X_test.select_dtypes(include="object").columns:
        X_test[col] = pd.to_numeric(X_test[col], errors="coerce").fillna(0)

    try:
        ensemble_proba = (
            weights[0] * lgb_model.predict_proba(X_test) +
            weights[1] * xgb_model.predict_proba(X_test) +
            weights[2] * cb_model.predict_proba(X_test)
        )
    except Exception as exc:
        raise RuntimeError(f"アンサンブル予測エラー: {exc}") from exc

    ev_df = build_ev_dataframe(test_df, ensemble_proba, le)
    positive_ev = filter_positive_ev(ev_df, threshold)

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"[EV] {year}年 期待値分析結果")
    print(sep)
    print(f"全馬数                : {len(ev_df):,}頭")
    print(f"期待値{threshold*100:.0f}%以上・選抜レース: {len(positive_ev):,}R")

    bins   = [float('-inf'), -0.1, 0.0, 0.1, 0.3, float('inf')]
    labels = ['EV<-10%', '-10~0%', '0~10%', '10~30%', 'EV>30%']
    ev_df['ev_band'] = pd.cut(ev_df['expected_value'], bins=bins, labels=labels)

    print("\n『期待値帯別実績』")
    for band, g in ev_df.groupby('ev_band', observed=True):
        total = len(g)
        hits  = (g['kakutei_chakujun'] == 1).sum()
        ret   = (g[g['kakutei_chakujun'] == 1]['odds_decimal'] * 100).sum()
        bet   = total * 100
        roi   = ret / bet * 100 if bet > 0 else 0
        print(f"  {band:<12}: {total:>6,}頭  "
              f"的中率{hits/total*100:>5.1f}%  "
              f"回収率{roi:>6.1f}%")

    out_path = os.path.join(BASE_DIR, f"ev_analysis_{year}.csv")
    positive_ev.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n[EV] 保存完了: {out_path}")

    return positive_ev


if __name__ == "__main__":
    result = run_ev_analysis(2025)
    if len(result) > 0:
        print("\n『期待値TOP10』")
        cols = ['race_code', 'bamei', 'win_probability',
                'odds_decimal', 'expected_value']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head(10).to_string(index=False))
