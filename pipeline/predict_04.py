import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime

BASE_DIR  = "D:\\keiba_ai"
DATA_DIR  = os.path.join(BASE_DIR, "data")
MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE  = os.path.join(BASE_DIR, "keiba_data_features.csv")

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
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


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
        print(f"[predict_04] 当日出馬表なし: {today_file}")
        print(f"[predict_04] pipeline/shutsuba_fetch.py を先に実行してください")
        return []

    saved    = _load_model()
    lgb_model = saved["lgb_model"]
    xgb_model = saved["xgb_model"]
    cb_model  = saved["cb_model"]
    le        = saved["le"]
    features  = saved["features"]
    weights   = saved.get("ensemble_weights", [0.5, 0.3, 0.2])

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
    cb_p  = cb_model.predict_proba(X)
    ensemble_p = weights[0] * lgb_p + weights[1] * xgb_p + weights[2] * cb_p

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
            results.append({
                "race_code":     str(rc),
                "race_label":    _fmt_race(str(rc)),
                "umaban":        int(row.get("umaban", 0) or 0),
                "bamei":         str(row.get("bamei", "")),
                "kishumei_ryakusho": str(row.get("kishumei_ryakusho", "")),
                "pred_chakujun": int(row["pred_chakujun"]),
                "win_prob":      round(float(row["win_prob"]) * 100, 2),
                "odds":          round(odds_raw / 10, 1),
                "barei":         int(row.get("barei", 0) or 0),
                "bataiju":       int(row.get("bataiju", 0) or 0),
                "chichi":        str(row.get("chichi", "")),
            })

    # CSV 保存
    out_path = os.path.join(DATA_DIR, f"predictions_{date_str}.csv")
    pd.DataFrame(results).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[predict_04] 予測完了: {df['race_code'].nunique()}R {len(results)}頭")
    print(f"[predict_04] 保存: {out_path}")

    # 上位予測を表示
    honmei = df[df["pred_chakujun"] == 1].sort_values("win_prob", ascending=False)
    print(f"\n{'─'*50}")
    print(f"  本日の本命予測（pred=1着 上位）")
    print(f"{'─'*50}")
    for _, r in honmei.head(10).iterrows():
        print(f"  {_fmt_race(str(r['race_code']))} "
              f"{int(r.get('umaban',0))}番 {r['bamei']} "
              f"勝率{r['win_prob']:.1f}%")
    print(f"{'─'*50}\n")

    return results

def simulate_recovery(year):
    with open("D:\\keiba_ai\\model_v8.pkl", "rb") as f:
        saved = pickle.load(f)
    
    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model = saved['cb_model']
    le = saved['le']
    features = saved['features']
    
    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False, on_bad_lines='skip')
    df = df.fillna(0)
    
    test_df = df[df['kaisai_nen'] == year].copy()
    if len(test_df) == 0:
        return None
    
    X_test = test_df[features]
    
    # 加重アンサンブル予測
    lgb_proba = lgb_model.predict_proba(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    cb_proba = cb_model.predict_proba(X_test)
    
    ensemble_proba = (
        0.5 * lgb_proba +
        0.3 * xgb_proba +
        0.2 * cb_proba
    )
    test_df['pred_chakujun'] = le.inverse_transform(
        ensemble_proba.argmax(axis=1)
    )
    
    results = []
    for race_code, race_df in test_df.groupby('race_code'):
        if len(race_df) < 3:
            continue
        
        # オッズ3倍以上の穴馬狙い
        race_df_filtered = race_df[race_df['tansho_odds'] >= 30]
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
        results_df.to_csv("D:\\keiba_ai\\simulation_2025.csv",
                          index=False, encoding="utf-8-sig")
        print(f"💾 simulation_2025.csv に保存しました！")
    
    return {
        'year': year,
        'races': total_races,
        'hit_rate': hit_rate,
        'recovery_rate': recovery_rate,
        'profit': total_return - total_bet
    }

if __name__ == "__main__":
    print("📊 年別回収率シミュレーション（データリーケージ修正版）")
    print("="*50)
    
    total_profit = 0
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        result = simulate_recovery(year)
        if result:
            emoji = "🎉" if result['recovery_rate'] >= 100 else "📉"
            print(f"{emoji} {result['year']}年")
            print(f"   レース数：{result['races']:,}")
            print(f"   的中率　：{result['hit_rate']:.1f}%")
            print(f"   回収率　：{result['recovery_rate']:.1f}%")
            print(f"   損　益　：{result['profit']:+,.0f}円")
            print(f"   {'─'*30}")
            total_profit += result['profit']
    
    print(f"\n💰 6年間の総損益：{total_profit:+,.0f}円")
    print("="*50)