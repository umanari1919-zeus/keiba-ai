import pickle
import os
import argparse
import sys
import pathlib
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, DATA_DIR, CSV_FEATURES
from pipeline.native_runtime import ensure_native_runtime

ensure_native_runtime()

try:
    from pipeline.ensemble_utils import load_ensemble_weights
except ImportError:
    load_ensemble_weights = None

try:
    import pandas as pd
except ImportError:
    pd = None

MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE  = CSV_FEATURES

# tansho_odds は x10 格納（150 = 15.0倍）
# MIN_ODDS=10.0倍 → tansho_odds >= 100
# 穴馬 30.0倍以上 → tansho_odds >= 300
MIN_ODDS_RAW  = 100   # 10倍以上（EV分析の最低ライン）
ANABA_ODDS_RAW = 300  # 30倍以上（穴馬定義）
JRA_TANSHO_TAKEOUT = 0.20  # JRA単勝控除率


def estimate_odds_for_race(race_df):
    """レース内の win_prob から推定オッズ・推定人気を算出する。

    推定オッズ = (1 - 控除率) / p_normalized
    p_normalized = win_prob_i / sum(win_prob_j)  (レース内正規化)
    """
    probs = race_df["win_prob"].clip(lower=1e-6).values
    p_norm = probs / probs.sum()
    est_odds_dec = (1 - JRA_TANSHO_TAKEOUT) / p_norm
    est_odds_dec = est_odds_dec.round(1)
    est_ninki = (-probs).argsort().argsort() + 1  # 1-indexed rank
    return est_odds_dec, est_ninki

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


def _check_runtime(date_str: str | None = None) -> list[str]:
    issues = []
    if pd is None:
        issues.append("pandas が未インストールです")
    if load_ensemble_weights is None:
        issues.append("numpy など推論依存が不足しています")
    if not os.path.exists(MODEL_PATH):
        issues.append(f"モデルファイルなし: {MODEL_PATH}")
    if not os.path.exists(FEAT_FILE):
        issues.append(f"特徴量CSVなし: {FEAT_FILE}")
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    today_file = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    if not os.path.exists(today_file):
        issues.append(f"当日出馬表なし: {today_file}")
    return issues


def predict_today(date_str: str = None) -> list:
    """
    当日出馬表 today_entries_YYYYMMDD.csv を使ってリアル予測を行う。
    kakutei_chakujun（確定着順）不要。
    Returns: 予測結果のリスト（race_code, bamei, pred_chakujun, win_prob, odds）
    """
    if pd is None:
        print("[predict_04] pandas が未インストールのため予測を実行できません")
        return []

    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    today_file = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    if not os.path.exists(today_file):
        print(f"[predict_04] 当日出馬表なし: {today_file}")
        print(f"[predict_04] pipeline/shutsuba_fetch.py を先に実行してください")
        return []

    saved    = _load_model()
    if load_ensemble_weights is None:
        print("[predict_04] numpy など推論依存が未導入のため予測を実行できません")
        return []
    lgb_model = saved["lgb_model"]
    xgb_model = saved["xgb_model"]
    cb_model  = saved["cb_model"]
    le        = saved["le"]
    features  = saved["features"]
    weights   = load_ensemble_weights(saved)

    df = pd.read_csv(today_file, encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    print(f"[predict_04] 当日出馬表: {len(df)}頭 {df['race_code'].nunique()}R")

    # モデルが必要とする特徴量のうち存在するものだけ使用
    feats = [f for f in features if f in df.columns]
    missing = [f for f in features if f not in df.columns]
    if missing:
        print(f"[predict_04] 不足特徴量 {len(missing)}件 → 0埋め")
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
    n_estimated = 0
    import numpy as np
    for rc, race_df in df.groupby("race_code"):
        race_df = race_df.sort_values("win_prob", ascending=False).copy()
        has_real_odds = (race_df["tansho_odds"].fillna(0).astype(float) > 0).any()

        raw_probs = race_df["win_prob"].clip(lower=1e-6).values
        log_probs = np.log(raw_probs)
        # 推定オッズ時はT=1.8で圧縮、実オッズ時はT=1.0（バックテスト最適値）
        uses_market_odds = "market_odds" in race_df.columns and (race_df["market_odds"].fillna(0) > 0).any()
        T = 1.8 if (not has_real_odds or uses_market_odds) else 1.0
        scaled = np.exp(log_probs / T)
        norm_probs = (scaled / scaled.sum() * 100).round(1)
        race_df["win_prob_norm"] = norm_probs

        if not has_real_odds:
            est_odds, est_ninki = estimate_odds_for_race(race_df)
            race_df["est_odds_dec"] = est_odds
            race_df["est_ninki"] = est_ninki
            n_estimated += 1

        for idx, (_, row) in enumerate(race_df.iterrows()):
            odds_raw = float(row.get("tansho_odds", 0) or 0)
            odds_dec = round(odds_raw / 10, 1)
            estimated = False
            if odds_dec == 0 and "est_odds_dec" in race_df.columns:
                odds_dec = float(row["est_odds_dec"])
                odds_raw = odds_dec * 10
                estimated = True
            ninki = int(row.get("tansho_ninkijun", 0) or 0)
            if ninki == 0 and "est_ninki" in race_df.columns:
                ninki = int(row["est_ninki"])
            results.append({
                "race_code":     str(rc),
                "race_label":    _fmt_race(str(rc)),
                "umaban":        int(row.get("umaban", 0) or 0),
                "bamei":         str(row.get("bamei", "")),
                "kishumei_ryakusho": str(row.get("kishumei_ryakusho", "")),
                "pred_chakujun": int(row["pred_chakujun"]),
                "win_prob":      float(row["win_prob_norm"]),
                "win_prob_raw":  round(float(row["win_prob"]) * 100, 4),
                "odds":          odds_dec,
                "odds_estimated": estimated,
                "ninki":         ninki,
                "is_anaba":      odds_raw >= ANABA_ODDS_RAW,
                "barei":         int(row.get("barei", 0) or 0),
                "bataiju":       int(row.get("bataiju", 0) or 0),
                "chichi":        str(row.get("chichi", "")),
            })
    if n_estimated > 0:
        print(f"[predict_04] 推定オッズ適用: {n_estimated}R (実オッズなし)")

    # CSV 保存
    out_path = os.path.join(DATA_DIR, f"predictions_{date_str}.csv")
    pd.DataFrame(results).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[predict_04] 予測完了: {df['race_code'].nunique()}R {len(results)}頭")
    print(f"[predict_04] 保存: {out_path}")

    # 上位予測を表示（穴馬フラグ付き）
    res_df = pd.DataFrame(results)
    honmei = res_df.sort_values("win_prob", ascending=False).drop_duplicates("race_code")
    anaba_candidates = res_df[res_df["is_anaba"]]
    print(f"\n{'─'*50}")
    print(f"  本日の本命予測（各レース win_prob 1位）")
    print(f"{'─'*50}")
    for _, r in honmei.head(10).iterrows():
        est_tag = "≈" if r.get("odds_estimated", False) else ""
        anaba_mark = " ★穴" if r["is_anaba"] else ""
        print(f"  {r['race_label']} "
              f"{int(r['umaban'])}番 {r['bamei']} "
              f"勝率{r['win_prob']:.2f}% "
              f"{est_tag}{r['odds']:.1f}倍 {int(r['ninki'])}人気{anaba_mark}")
    print(f"  穴馬候補(30倍以上): {len(anaba_candidates)}頭")
    print(f"{'─'*50}\n")

    return results

def simulate_recovery(year):
    if pd is None:
        raise RuntimeError("pandas が未インストールのため simulate_recovery を実行できません")
    if load_ensemble_weights is None:
        raise RuntimeError("numpy など推論依存が未導入のため simulate_recovery を実行できません")

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
        print(f"💾 {sim_path} に保存しました！")
    
    return {
        'year': year,
        'races': total_races,
        'hit_rate': hit_rate,
        'recovery_rate': recovery_rate,
        'profit': total_return - total_bet
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="当日予測 / 回収率シミュレーション")
    parser.add_argument("--date", default=None, help="対象日 YYYYMMDD")
    parser.add_argument("--year", type=int, default=None, help="simulate_recovery の対象年")
    parser.add_argument("--dry-run", action="store_true", help="依存関係と入力ファイルだけ確認する")
    parser.add_argument("--simulate-recovery", action="store_true", help="年次回収率シミュレーションを実行")
    args, _ = parser.parse_known_args()

    if args.dry_run:
        issues = _check_runtime(args.date)
        if issues:
            print("[predict_04] dry-run: 要確認")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("[predict_04] dry-run: 実行要件は概ね満たしています")
        return 0

    if args.simulate_recovery:
        year = args.year or datetime.now().year
        result = simulate_recovery(year)
        if result is None:
            print(f"[predict_04] {year}年データがありません")
            return 1
        print(result)
        return 0

    result = predict_today(args.date)
    if len(result) > 0:
        print("\n✅ 当日予測が完了しました")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
