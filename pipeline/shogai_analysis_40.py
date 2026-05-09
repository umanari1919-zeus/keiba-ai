"""
障害戦強化分析 (shogai_analysis_40)
- 障害レース検出: race_shosai.kyoso_shubetsu_code IN ('18','19')
- 騎手・調教師の障害成績から勝率計算
- 馬の障害経験数カウント
- 新特徴量: is_shogai, jockey_shogai_win_rate, trainer_shogai_win_rate,
             shogai_keiken, shogai_score
"""
import json
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from pipeline.config import BASE_DIR, DATA_DIR, DB_URL

FEAT_FILE = os.path.join(DATA_DIR, "keiba_data_features.csv")
CACHE_PATH = os.path.join(DATA_DIR, "shogai_race_codes.json")

CACHE_TTL_DAYS = 7
MIN_SHOGAI_RACES = 3  # 最小障害レース数（騎手・調教師の勝率計算用）


def _load_shogai_race_codes(engine, use_cache: bool = True) -> set:
    """障害レースコードをDBから取得（1週間キャッシュ）"""
    if use_cache and os.path.exists(CACHE_PATH):
        mtime = os.path.getmtime(CACHE_PATH)
        if time.time() - mtime < CACHE_TTL_DAYS * 86400:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                codes = json.load(f)
            print(f"  📁 障害レースコード キャッシュ使用: {len(codes):,}件")
            return set(codes)

    sql = """
        SELECT DISTINCT race_code
        FROM race_shosai
        WHERE kyoso_shubetsu_code IN ('18', '19')
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    codes = df["race_code"].tolist()
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False)

    print(f"  🏇 障害レースコード取得: {len(codes):,}件 → キャッシュ保存")
    return set(codes)


def _load_jockey_shogai_rates(engine) -> pd.DataFrame:
    """
    騎手ごとの障害勝率を計算
    shussobetsu_kishu: shogai_1chaku_honnen/ruikei, shogai_chakugai_honnen/ruikei
    """
    sql = """
        SELECT
            kishu_code,
            COALESCE(shogai_1chaku_ruikei, 0)    AS win_ruikei,
            COALESCE(shogai_chakugai_ruikei, 0)  AS loss_ruikei,
            COALESCE(shogai_1chaku_honnen, 0)    AS win_honnen,
            COALESCE(shogai_chakugai_honnen, 0)  AS loss_honnen
        FROM shussobetsu_kishu
        WHERE shogai_1chaku_ruikei IS NOT NULL
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    df["total_ruikei"] = df["win_ruikei"] + df["loss_ruikei"]
    df["total_honnen"] = df["win_honnen"] + df["loss_honnen"]

    # 累計を優先、サンプル不足なら本年で補完
    df["shogai_win_rate"] = np.where(
        df["total_ruikei"] >= MIN_SHOGAI_RACES,
        df["win_ruikei"] / (df["total_ruikei"] + 1e-6),
        np.where(
            df["total_honnen"] >= MIN_SHOGAI_RACES,
            df["win_honnen"] / (df["total_honnen"] + 1e-6),
            np.nan,
        ),
    )

    valid = df.dropna(subset=["shogai_win_rate"])
    print(f"  🏇 騎手障害成績: {len(valid):,}名 有効")
    return valid[["kishu_code", "shogai_win_rate"]].set_index("kishu_code")


def _load_trainer_shogai_rates(engine) -> pd.DataFrame:
    """調教師ごとの障害勝率"""
    sql = """
        SELECT
            chokyoshi_code,
            COALESCE(shogai_1chaku_ruikei, 0)   AS win_ruikei,
            COALESCE(shogai_chakugai_ruikei, 0) AS loss_ruikei,
            COALESCE(shogai_1chaku_honnen, 0)   AS win_honnen,
            COALESCE(shogai_chakugai_honnen, 0) AS loss_honnen
        FROM shussobetsu_chokyoshi
        WHERE shogai_1chaku_ruikei IS NOT NULL
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    df["total_ruikei"] = df["win_ruikei"] + df["loss_ruikei"]
    df["total_honnen"] = df["win_honnen"] + df["loss_honnen"]

    df["shogai_win_rate"] = np.where(
        df["total_ruikei"] >= MIN_SHOGAI_RACES,
        df["win_ruikei"] / (df["total_ruikei"] + 1e-6),
        np.where(
            df["total_honnen"] >= MIN_SHOGAI_RACES,
            df["win_honnen"] / (df["total_honnen"] + 1e-6),
            np.nan,
        ),
    )

    valid = df.dropna(subset=["shogai_win_rate"])
    print(f"  🏋️ 調教師障害成績: {len(valid):,}名 有効")
    return valid[["chokyoshi_code", "shogai_win_rate"]].set_index("chokyoshi_code")


def _load_horse_shogai_keiken(engine, shogai_codes: set) -> pd.Series:
    """
    馬ごとの障害経験数（出走回数）
    umagoto_race_joho で shogai_codes に含まれる race_code をカウント
    """
    if not shogai_codes:
        return pd.Series(dtype=float)

    codes_list = list(shogai_codes)
    # PostgreSQL の IN 句は大量データ非効率 → 一時テーブル的アプローチ
    # まず全 umagoto_race_joho を取得してフィルタ（メモリ上で処理）
    sql = """
        SELECT bamei, race_code
        FROM umagoto_race_joho
        WHERE race_code = ANY(:codes)
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params={"codes": codes_list})

    keiken = df.groupby("bamei").size()
    print(f"  🐎 障害経験馬数: {len(keiken):,}頭")
    return keiken


def compute_shogai_features(
    df_feat: pd.DataFrame,
    shogai_codes: set,
    jockey_rates: pd.DataFrame,
    trainer_rates: pd.DataFrame,
    horse_keiken: pd.Series,
) -> pd.DataFrame:
    """
    df_feat に障害特徴量を追加して返す
    追加列:
      is_shogai              : 0/1
      jockey_shogai_win_rate : 騎手障害勝率
      trainer_shogai_win_rate: 調教師障害勝率
      shogai_keiken          : 馬の障害経験数
      shogai_score           : 総合障害スコア (0–1)
    """
    df = df_feat.copy()

    # 障害フラグ
    df["is_shogai"] = df["race_code"].isin(shogai_codes).astype(int)

    # 騎手勝率マージ
    if "kishu_code" in df.columns:
        df["jockey_shogai_win_rate"] = (
            df["kishu_code"]
            .map(jockey_rates["shogai_win_rate"])
            .fillna(0.0)
        )
    else:
        df["jockey_shogai_win_rate"] = 0.0

    # 調教師勝率マージ
    if "chokyoshi_code" in df.columns:
        df["trainer_shogai_win_rate"] = (
            df["chokyoshi_code"]
            .map(trainer_rates["shogai_win_rate"])
            .fillna(0.0)
        )
    else:
        df["trainer_shogai_win_rate"] = 0.0

    # 馬の障害経験数
    if "bamei" in df.columns:
        df["shogai_keiken"] = df["bamei"].map(horse_keiken).fillna(0).astype(int)
    else:
        df["shogai_keiken"] = 0

    # 障害スコア計算（障害レースのみ意味を持つ）
    # 経験(30%) + 騎手勝率(25%) + 調教師勝率(20%) + 調教スコア(15%) + 血統(10%)
    keiken_norm = np.clip(df["shogai_keiken"] / 20.0, 0, 1)  # 20戦以上で満点
    jockey_norm = np.clip(df["jockey_shogai_win_rate"] / 0.20, 0, 1)  # 20%以上で満点
    trainer_norm = np.clip(df["trainer_shogai_win_rate"] / 0.15, 0, 1)  # 15%以上で満点

    train_v2 = df.get("training_score_v2", pd.Series(0.5, index=df.index))
    train_norm = np.clip(train_v2 / 0.8, 0, 1)

    blood = df.get("blood_score", pd.Series(1.5, index=df.index))
    blood_norm = np.clip((blood - 1.0) / 2.0, 0, 1)

    shogai_score = (
        0.30 * keiken_norm
        + 0.25 * jockey_norm
        + 0.20 * trainer_norm
        + 0.15 * train_norm
        + 0.10 * blood_norm
    )

    df["shogai_score"] = np.where(df["is_shogai"] == 1, shogai_score, 0.0)

    shogai_rows = df[df["is_shogai"] == 1]
    print(f"  ✅ 障害レース: {len(shogai_rows):,}行")
    if len(shogai_rows) > 0:
        print(f"     shogai_score: avg={shogai_rows['shogai_score'].mean():.3f}"
              f" max={shogai_rows['shogai_score'].max():.3f}")
        top = shogai_rows.nlargest(3, "shogai_score")[
            ["bamei", "shogai_score", "shogai_keiken",
             "jockey_shogai_win_rate", "trainer_shogai_win_rate"]
        ]
        print("     TOP3:")
        for _, r in top.iterrows():
            print(f"       {r.get('bamei','?')} score={r['shogai_score']:.3f}"
                  f" 経験={r['shogai_keiken']}戦"
                  f" 騎手={r['jockey_shogai_win_rate']:.1%}"
                  f" 調教師={r['trainer_shogai_win_rate']:.1%}")

    return df


def run_shogai_analysis():
    """メインエントリーポイント"""
    print("\n【障害戦強化分析 shogai_analysis_40】")
    t0 = time.time()

    # 特徴量ファイル読み込み
    if not os.path.exists(FEAT_FILE):
        print(f"  ⚠️ 特徴量ファイルなし: {FEAT_FILE}")
        return

    df_feat = pd.read_csv(FEAT_FILE, on_bad_lines="skip", low_memory=False)
    print(f"  📊 特徴量: {len(df_feat):,}行")

    engine = create_engine(DB_URL)

    # 各種データ取得
    shogai_codes = _load_shogai_race_codes(engine)
    jockey_rates = _load_jockey_shogai_rates(engine)
    trainer_rates = _load_trainer_shogai_rates(engine)
    horse_keiken = _load_horse_shogai_keiken(engine, shogai_codes)

    # 特徴量追加
    df_feat = compute_shogai_features(
        df_feat, shogai_codes, jockey_rates, trainer_rates, horse_keiken
    )

    # 保存
    df_feat.to_csv(FEAT_FILE, index=False)
    elapsed = time.time() - t0
    print(f"  💾 保存完了: {FEAT_FILE} ({elapsed:.1f}秒)")

    engine.dispose()
    return df_feat


if __name__ == "__main__":
    run_shogai_analysis()
