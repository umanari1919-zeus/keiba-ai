import logging
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
from pipeline.ensemble_utils import load_ensemble_weights

log = logging.getLogger(__name__)

BASE_DIR  = "D:\\keiba_ai"
DATA_DIR  = os.path.join(BASE_DIR, "data")
MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE  = os.path.join(BASE_DIR, "keiba_data_features.csv")

# tansho_odds は x10 格納（150 = 15.0倍）
# MIN_ODDS=10.0倍 → tansho_odds >= 100
# 穴馬 30.0倍以上 → tansho_odds >= 300
MIN_ODDS_RAW  = 100   # 10倍以上（EV分析の最低ライン）
ANABA_ODDS_RAW = 300  # 30倍以上（穴馬定義）

KEIBAJO = {
    "1":"札幌","2":"函館","3":"福島","4":"新潟","5":"東京",
    "6":"中山","7":"中京","8":"京都","9":"阪神","10":"小倉",
    "30":"門別","31":"盛岡","32":"水沢","39":"浦和",
    "40":"船橋","41":"大井","42":"川崎","43":"金沢",
    "44":"笠松","45":"名古屋","47":"園田","48":"姫路",
    "50":"高知","51":"佐賀","58":"帯広",
}

def _fmt_race(code: str) -> str:
    s = str(code).strip()
    if len(s) != 16: return s
    mm  = str(int(s[4:6]))
    dd  = str(int(s[6:8]))
    jyo = KEIBAJO.get(str(int(s[8:10])), s[8:10])
    rno = s[14:16].lstrip("0") or "1"
    return f"{mm}/{dd} {jyo}{rno}R"

def _load_model():
    """モデルファイルを安全に読み込む（存在確認・例外処理付き）。"""
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {MODEL_PATH}\n"
            f"先に pipeline/model_train_03.py を実行してください"
        )
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        raise RuntimeError(f"モデル読み込みエラー: {e}") from e


def predict_today(date_str: str = None) -> list:
    """
    当日出馬表 today_entries_YYYYMMDD.csv を使ってリアル予測を行う。
    kakutei_chakujun（確定着順）不要。
    Returns: 予測結果のリスト（race_code, bamei, pred_chakujun, win_prob, odds）
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    today_file = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    if not os.path.exists(today_file):
        log.warning("[predict_04] 当日出馬表なし: %s", today_file)
        log.warning("[predict_04] pipeline/shutsuba_fetch.py を先に実行してください")
        return []

    saved    = _load_model()
    lgb_model = saved["lgb_model"]
    xgb_model = saved["xgb_model"]
    cb_model  = saved["cb_model"]
    le        = saved["le"]
    features  = saved["features"]
    weights   = load_ensemble_weights(saved)

    df = pd.read_csv(today_file, encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    log.info("[predict_04] 当日出馬表: %d頭 %dR", len(df), df['race_code'].nunique())

    # モデルが必要とする特徴量のうち存在するものだけ使用
    feats = [f for f in features if f in df.columns]
    missing = [f for f in features if f not in df.columns]
    if missing:
        log.warning("[predict_04] 不足特徴量 %d件 → 0埋め", len(missing))
        for f in missing:
            df[f] = 0

    X = df[features].copy()
    # 文字列列を数値に強制変換（モデルは int/float のみ受付）
    for col in X.select_dtypes(include="object").columns:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    lgb_p = lgb_model.predict_proba(X)
    xgb_p = xgb_model.predict_proba(X)
    if cb_model is not None:
        cb_p  = cb_model.predict_proba(X)
        ensemble_p = weights[0] * lgb_p + weights[1] * xgb_p + weights[2] * cb_p
    else:
        # CatBoost未学習: LGB+XGB で再正規化
        w_sum = weights[0] + weights[1]
        ensemble_p = (weights[0] * lgb_p + weights[1] * xgb_p) / (w_sum or 1.0)

    df["pred_chakujun"] = le.inverse_transform(ensemble_p.argmax(axis=1))
    # 1着確率
    try:
        first_idx = list(le.classes_).index(1)
        df["win_prob"] = ensemble_p[:, first_idx]
    except (ValueError, IndexError):
        df["win_prob"] = ensemble_p.max(axis=1)

    results = []
    for rc, race_df in df.groupby("race_code"):
        race_df = race_df.sort_values("win_prob", ascending=False)
        for _, row in race_df.iterrows():
            odds_raw = float(row.get("tansho_odds", 0) or 0)
            odds_dec = round(odds_raw / 10, 1)
            results.append({
                "race_code":     str(rc),
                "race_label":    _fmt_race(str(rc)),
                "umaban":        int(row.get("umaban", 0) or 0),
                "bamei":         str(row.get("bamei", "")),
                "kishumei_ryakusho": str(row.get("kishumei_ryakusho", "")),
                "pred_chakujun": int(row["pred_chakujun"]),
                "win_prob":      round(float(row["win_prob"]) * 100, 2),
                "odds":          odds_dec,
                "is_anaba":      odds_raw >= ANABA_ODDS_RAW,   # 30倍以上フラグ
                "barei":         int(row.get("barei", 0) or 0),
                "bataiju":       int(row.get("bataiju", 0) or 0),
                "chichi":        str(row.get("chichi", "")),
            })

    # CSV 保存
    out_path = os.path.join(DATA_DIR, f"predictions_{date_str}.csv")
    pd.DataFrame(results).to_csv(out_path, index=False, encoding="utf-8-sig")
    log.info("[predict_04] 予測完了: %dR %d頭", df['race_code'].nunique(), len(results))
    log.info("[predict_04] 保存: %s", out_path)

    # 上位予測を表示（穴馬フラグ付き）
    honmei = df[df["pred_chakujun"] == 1].sort_values("win_prob", ascending=False)
    anaba_candidates = [r for r in results
                        if r["pred_chakujun"] == 1 and r["is_anaba"]]
    log.info("本日の本命予測（pred=1着 上位）")
    for _, r in honmei.head(10).iterrows():
        odds_raw_r = float(r.get("tansho_odds", 0) or 0)
        anaba_mark = " ★穴" if odds_raw_r >= ANABA_ODDS_RAW else ""
        log.info("  %s %d番 %s 勝率%.1f%% %.1f倍%s",
                 _fmt_race(str(r['race_code'])), int(r.get('umaban', 0)),
                 r['bamei'], r['win_prob'], odds_raw_r / 10, anaba_mark)
    log.info("穴馬候補(30倍以上): %d頭", len(anaba_candidates))

    return results

def simulate_recovery(year):
    # ── モデル読み込み（共通関数を使用） ──────────────────────
    saved = _load_model()

    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model = saved['cb_model']
    le = saved['le']
    features = saved['features']
    weights = load_ensemble_weights(saved)

    # ── 特徴量CSV読み込み（on_bad_lines='skip' 必須） ─────────
    if not os.path.exists(FEAT_FILE):
        raise FileNotFoundError(
            f"特徴量CSVが見つかりません: {FEAT_FILE}\n"
            f"先に pipeline/feature_eng_02.py を実行してください"
        )
    df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig",
                     low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    
    test_df = df[df['kaisai_nen'] == year].copy()
    if len(test_df) == 0:
        return None
    
    X_test = test_df[features]
    
    # 加重アンサンブル予測
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    if cb_model is not None:
        cb_proba = cb_model.predict_proba(X_test)
        ensemble_proba = (
            weights[0] * lgb_proba +
            weights[1] * xgb_proba +
            weights[2] * cb_proba
        )
    else:
        w_sum = weights[0] + weights[1]
        ensemble_proba = (weights[0] * lgb_proba + weights[1] * xgb_proba) / (w_sum or 1.0)
    test_df['pred_chakujun'] = le.inverse_transform(
        ensemble_proba.argmax(axis=1)
    )
    
    results = []
    for race_code, race_df in test_df.groupby('race_code'):
        if len(race_df) < 3:
            continue
        
        # 穴馬狙い: 10倍以上（tansho_odds x10格納 → >= 100）
        race_df_filtered = race_df[race_df['tansho_odds'] >= MIN_ODDS_RAW]
        if len(race_df_filtered) == 0:
            continue
        
        honmei = race_df_filtered.loc[
            race_df_filtered['pred_chakujun'].idxmin()
        ]
        
        actual_chakujun = honmei['kakutei_chakujun']
        odds = honmei['tansho_odds'] / 10
        
        results.append({
            'race_code': race_code,
            'bamei': honmei['bamei'],
            'barei': honmei['barei'],
            'bataiju': honmei['bataiju'],
            'zogen_sa': honmei['zogen_sa'],
            'zogen_fugo': honmei['zogen_fugo'],
            'kishumei_ryakusho': honmei['kishumei_ryakusho'],
            'pred_chakujun': honmei['pred_chakujun'],
            'actual_chakujun': actual_chakujun,
            'odds': odds,
            'hit': 1 if actual_chakujun == 1 else 0
        })
    
    results_df = pd.DataFrame(results)
    total_races = len(results_df)
    total_bet = total_races * 100
    wins = results_df[results_df['hit'] == 1]
    total_return = (wins['odds'] * 100).sum()
    hit_rate = len(wins) / total_races * 100
    recovery_rate = total_return / total_bet * 100
    
    if year == 2025:
        sim_path = os.path.join(BASE_DIR, "simulation_2025.csv")
        results_df.to_csv(sim_path, index=False, encoding="utf-8-sig")
        log.info("保存: %s", sim_path)
    
    return {
        'year': year,
        'races': total_races,
        'hit_rate': hit_rate,
        'recovery_rate': recovery_rate,
        'profit': total_return - total_bet
    }
