"""
odds_model.py — 市場オッズ予測モデル
====================================
過去のレースデータから「市場がつけるオッズ」を予測する LightGBM 回帰モデル。
モデルの勝率予測との乖離から EV を算出し、前日夜でも穴馬判定を可能にする。

使い方:
    python pipeline/odds_model.py --train          # 学習 → odds_model.pkl 保存
    python pipeline/odds_model.py --predict 20260510  # 当日予測
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import pathlib
from datetime import datetime

import numpy as np

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR, DATA_DIR, CSV_FEATURES

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

MODEL_PATH = os.path.join(BASE_DIR, "odds_model.pkl")
WIN_MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")


def _load_features_list() -> list[str]:
    """model_v8.pkl から学習特徴量リストを取得する。"""
    with open(WIN_MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    return saved["features"]


def train_odds_model(
    test_year: int = 2025,
    n_estimators: int = 800,
    learning_rate: float = 0.05,
) -> dict:
    """市場オッズ予測モデルを学習する。

    target: log(tansho_odds) — 対数変換で長い裾を圧縮
    features: model_v8 と同じ161特徴量（オッズ非含有）
    """
    print(f"[odds_model] 学習開始...")
    features = _load_features_list()

    df = pd.read_csv(CSV_FEATURES, encoding="utf-8-sig",
                     low_memory=False, on_bad_lines="skip")
    df = df.fillna(0)

    # オッズが有効なデータのみ使用（x10形式、10=1.0倍以上）
    df = df[df["tansho_odds"] > 10].copy()
    print(f"[odds_model] 有効データ: {len(df):,} 行")

    # target: log(odds_decimal)
    df["log_odds"] = np.log(df["tansho_odds"] / 10.0)

    # 不足特徴量を0埋め
    for f in features:
        if f not in df.columns:
            df[f] = 0

    X = df[features].copy()
    for col in X.select_dtypes(include="object").columns:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)
    y = df["log_odds"]

    # train / test split by year
    train_mask = df["kaisai_nen"] < test_year
    test_mask = df["kaisai_nen"] == test_year

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"[odds_model] train: {len(X_train):,}  test({test_year}): {len(X_test):,}")

    model = lgb.LGBMRegressor(
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=8,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbose=-1,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.log_evaluation(100)],
    )

    # 評価
    from sklearn.metrics import mean_absolute_error, r2_score

    pred_log = model.predict(X_test)
    pred_odds = np.exp(pred_log)
    actual_odds = np.exp(y_test.values)

    mae = mean_absolute_error(actual_odds, pred_odds)
    r2 = r2_score(y_test, pred_log)

    # 人気順位の一致率（レース内順位）
    test_df = df[test_mask].copy()
    test_df["pred_log_odds"] = pred_log
    rank_corr_list = []
    for _, g in test_df.groupby("race_code"):
        if len(g) < 3:
            continue
        actual_rank = g["tansho_odds"].rank()
        pred_rank = g["pred_log_odds"].rank()
        corr = actual_rank.corr(pred_rank)
        if not np.isnan(corr):
            rank_corr_list.append(corr)
    rank_corr = np.mean(rank_corr_list)

    # オッズ帯別の精度
    print(f"\n{'='*55}")
    print(f"[odds_model] {test_year}年 検証結果")
    print(f"{'='*55}")
    print(f"  MAE (倍)      : {mae:.1f}")
    print(f"  R² (log)      : {r2:.4f}")
    print(f"  人気順位相関   : {rank_corr:.4f}")

    bins = [(1, 5), (5, 10), (10, 30), (30, 100), (100, 1000)]
    print(f"\n  オッズ帯別 MAE:")
    for lo, hi in bins:
        mask = (actual_odds >= lo) & (actual_odds < hi)
        if mask.sum() > 0:
            band_mae = mean_absolute_error(actual_odds[mask], pred_odds[mask])
            print(f"    {lo:>4}-{hi:<4}倍: MAE={band_mae:>6.1f}  ({mask.sum():>6,}頭)")

    # 特徴量重要度 TOP10
    importance = model.feature_importances_
    top_idx = np.argsort(importance)[::-1][:10]
    print(f"\n  特徴量重要度 TOP10:")
    for i in top_idx:
        print(f"    {features[i]:30s}  {importance[i]:>6}")

    # 保存
    result = {
        "model": model,
        "features": features,
        "metrics": {
            "mae": float(mae),
            "r2": float(r2),
            "rank_corr": float(rank_corr),
            "test_year": test_year,
        },
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(result, f)
    print(f"\n[odds_model] 保存: {MODEL_PATH}")

    return result


def predict_market_odds(date_str: str = None) -> pd.DataFrame:
    """当日出馬表から市場オッズを予測する。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    today_file = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    if not os.path.exists(today_file):
        print(f"[odds_model] 出馬表なし: {today_file}")
        return pd.DataFrame()

    if not os.path.exists(MODEL_PATH):
        print(f"[odds_model] モデルなし: {MODEL_PATH}")
        print(f"[odds_model] python pipeline/odds_model.py --train で学習してください")
        return pd.DataFrame()

    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    model = saved["model"]
    features = saved["features"]

    df = pd.read_csv(today_file, encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)

    for feat in features:
        if feat not in df.columns:
            df[feat] = 0

    X = df[features].copy()
    for col in X.select_dtypes(include="object").columns:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    pred_log = model.predict(X)
    df["market_odds"] = np.round(np.exp(pred_log), 1)
    df["market_ninki"] = df.groupby("race_code")["market_odds"].rank(method="first").astype(int)

    # tansho_odds を market_odds で上書き（x10形式で保存）
    out_path = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    real_odds = df["tansho_odds"].fillna(0).astype(float)
    n_filled = (real_odds == 0).sum()
    if n_filled > 0:
        df.loc[real_odds == 0, "tansho_odds"] = (df.loc[real_odds == 0, "market_odds"] * 10).astype(int)
        df.loc[real_odds == 0, "tansho_ninkijun"] = df.loc[real_odds == 0, "market_ninki"]
        print(f"[odds_model] {n_filled}頭の実オッズなし → 市場推定オッズで補完")

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[odds_model] 保存: {out_path}")

    # サマリー表示
    keibajo = {"04": "新潟", "05": "東京", "08": "小倉", "01": "札幌", "02": "函館",
               "03": "福島", "06": "中山", "07": "中京", "09": "阪神", "10": "小倉"}

    print(f"\n[odds_model] {date_str} 市場オッズ予測 ({len(df)}頭, {df['race_code'].nunique()}R)")
    print(f"{'─'*55}")

    anaba = df[df["market_odds"] >= 30.0].sort_values("market_odds")
    print(f"  穴馬候補(推定30倍以上): {len(anaba)}頭")
    for _, r in anaba.head(10).iterrows():
        rc = str(r["race_code"])
        jyo = keibajo.get(rc[8:10], rc[8:10])
        rno = rc[14:16].lstrip("0")
        print(f"    {jyo}{rno}R {int(r['umaban']):2d}番 {r['bamei']}  ≈{r['market_odds']:.1f}倍")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="市場オッズ予測モデル")
    parser.add_argument("--train", action="store_true", help="モデル学習")
    parser.add_argument("--predict", default=None, help="当日予測 YYYYMMDD")
    parser.add_argument("--test-year", type=int, default=2025, help="検証年")
    args, _ = parser.parse_known_args()

    if args.train:
        train_odds_model(test_year=args.test_year)
    elif args.predict:
        predict_market_odds(args.predict)
    else:
        parser.print_help()
