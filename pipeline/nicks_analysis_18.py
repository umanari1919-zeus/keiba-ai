"""
ニックス（配合相性）徹底分析システム

ニックスとは「父×母父」の特定組み合わせが、個々の能力の合計を
超えた相乗効果を発揮する血統配合の法則。

分析項目：
  ① ニックス指数（相乗効果スコア）の算出
  ② 統計的有意性フィルタリング（カイ二乗・Fisher's exact）
  ③ 条件別ニックス（馬場・距離・季節）
  ④ 3代ニックス（父×母父×母母父）
  ⑤ ニックス予測スコアのCSV出力（model_v8 特徴量化）
"""
import os
import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime
from sqlalchemy import create_engine, text

DB_URL  = "postgresql://postgres:trust@localhost:5433/mykeibadb"
OUT_DIR = "D:\\keiba_ai\\pedigree_output"


# ──────────────────────────────────────────────────────────────
# データ取得
# ──────────────────────────────────────────────────────────────

def load_nicks_data(year_from: int = 2018) -> pd.DataFrame:
    engine = create_engine(DB_URL)
    query  = text("""
        SELECT
            u.race_code,
            u.kaisai_nen,
            u.bamei,
            u.kakutei_chakujun,
            u.tansho_odds,
            u.tansho_ninkijun,
            r.kyori,
            r.track_code,
            r.tenko_code,
            r.shiba_babajotai_code,
            r.dirt_babajotai_code,
            m.ketto1_bamei  AS chichi,
            m.ketto5_bamei  AS haha_chichi,
            m.ketto3_bamei  AS chichi_chichi,
            m.ketto11_bamei AS haha_chichi_chichi,
            m.ketto13_bamei AS haha_haha_chichi
        FROM umagoto_race_joho u
        JOIN race_shosai r USING (race_code)
        JOIN kyosoba_master2 m
          ON m.ketto_toroku_bango = u.ketto_toroku_bango
        WHERE u.kaisai_nen::int >= :y
          AND u.kakutei_chakujun ~ '^[0-9]+'
          AND m.ketto1_bamei IS NOT NULL
          AND m.ketto5_bamei IS NOT NULL
          AND u.tansho_odds IS NOT NULL
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"y": year_from})

    df["chakujun"] = pd.to_numeric(df["kakutei_chakujun"], errors="coerce")
    df["odds"]     = pd.to_numeric(df["tansho_odds"],       errors="coerce") / 10
    df["ninkijun"] = pd.to_numeric(df["tansho_ninkijun"],   errors="coerce")
    df["kyori"]    = pd.to_numeric(df["kyori"],             errors="coerce")
    df["win"]      = (df["chakujun"] == 1).astype(int)
    df["place"]    = (df["chakujun"] <= 3).astype(int)

    df["track_type"] = df["track_code"].astype(str).str[0].map(
        {"1": "芝", "2": "ダート", "3": "障害"}
    ).fillna("その他")

    df["distance_band"] = pd.cut(
        df["kyori"],
        bins=[0, 1400, 1800, 2200, 9999],
        labels=["短距離", "マイル", "中距離", "長距離"]
    )
    return df.dropna(subset=["chakujun", "odds"])


# ──────────────────────────────────────────────────────────────
# ① ニックス指数の算出
# ──────────────────────────────────────────────────────────────

def calc_nick_index(
    df: pd.DataFrame,
    min_combo_races: int = 20,
    min_sire_races:  int = 50,
    min_bms_races:   int = 50,
) -> pd.DataFrame:
    """
    ニックス指数 = 組み合わせ勝率 ÷ (父単独勝率 × 母父単独勝率)^0.5

    1.0 を超えると相乗効果あり（ニックス）。
    値が大きいほど組み合わせの相性が良い。
    """
    # 父・母父それぞれの単独成績
    sire_stats = (
        df.groupby("chichi")
          .agg(sire_races=("win","count"), sire_wins=("win","sum"))
          .reset_index()
    )
    sire_stats["sire_wr"] = sire_stats["sire_wins"] / sire_stats["sire_races"]
    sire_stats = sire_stats[sire_stats["sire_races"] >= min_sire_races]

    bms_stats = (
        df.groupby("haha_chichi")
          .agg(bms_races=("win","count"), bms_wins=("win","sum"))
          .reset_index()
    )
    bms_stats["bms_wr"] = bms_stats["bms_wins"] / bms_stats["bms_races"]
    bms_stats = bms_stats[bms_stats["bms_races"] >= min_bms_races]

    # 組み合わせ成績
    combo = (
        df.groupby(["chichi","haha_chichi"])
          .agg(
              races      = ("win",   "count"),
              wins       = ("win",   "sum"),
              place_cnt  = ("place", "sum"),
              total_ret  = ("odds",  lambda x: (x * df.loc[x.index, "win"] * 100).sum()),
              avg_odds   = ("odds",  "mean"),
              avg_pop    = ("ninkijun", "mean"),
          )
          .reset_index()
    )
    combo["win_rate"]   = combo["wins"]     / combo["races"]
    combo["place_rate"] = combo["place_cnt"]/ combo["races"]
    combo["roi"]        = combo["total_ret"]/ (combo["races"] * 100)
    combo = combo[combo["races"] >= min_combo_races]

    # 3者をマージ
    merged = (
        combo
        .merge(sire_stats[["chichi","sire_wr","sire_races"]], on="chichi", how="inner")
        .merge(bms_stats[["haha_chichi","bms_wr","bms_races"]], on="haha_chichi", how="inner")
    )

    # ニックス指数 = 実際勝率 / 期待勝率(幾何平均)
    # 期待勝率: sqrt(父勝率 × 母父勝率)  ← 独立なら期待されるベースライン
    merged["expected_wr"] = np.sqrt(merged["sire_wr"] * merged["bms_wr"])
    merged["nick_index"]  = merged["win_rate"] / (merged["expected_wr"] + 1e-6)

    # Fisher's exact test で有意性を検定
    # H0: 組み合わせの勝率 = 期待勝率
    p_values = []
    for _, row in merged.iterrows():
        observed_win  = int(row["wins"])
        observed_loss = int(row["races"] - row["wins"])
        exp_win_rate  = row["expected_wr"]
        expected_win  = row["races"] * exp_win_rate
        expected_loss = row["races"] - expected_win
        # 二項検定（H0: 勝率 = 期待勝率）
        result = stats.binomtest(observed_win, n=int(row["races"]),
                                  p=max(exp_win_rate, 1e-6),
                                  alternative="greater")
        p_values.append(result.pvalue)

    merged["p_value"]     = p_values
    merged["significant"] = merged["p_value"] < 0.10   # 10%水準

    return merged.sort_values("nick_index", ascending=False)


# ──────────────────────────────────────────────────────────────
# ② 条件別ニックス
# ──────────────────────────────────────────────────────────────

def calc_conditional_nicks(
    df: pd.DataFrame,
    min_races: int = 15
) -> dict:
    """馬場・距離帯ごとにニックス指数を計算する。"""
    results = {}

    for condition, sub in [
        ("芝_短距離",  df[(df["track_type"]=="芝")    & (df["distance_band"]=="短距離")]),
        ("芝_マイル",  df[(df["track_type"]=="芝")    & (df["distance_band"]=="マイル")]),
        ("芝_中距離",  df[(df["track_type"]=="芝")    & (df["distance_band"]=="中距離")]),
        ("芝_長距離",  df[(df["track_type"]=="芝")    & (df["distance_band"]=="長距離")]),
        ("ダ_短距離",  df[(df["track_type"]=="ダート") & (df["distance_band"]=="短距離")]),
        ("ダ_マイル",  df[(df["track_type"]=="ダート") & (df["distance_band"]=="マイル")]),
        ("ダ_中距離",  df[(df["track_type"]=="ダート") & (df["distance_band"]=="中距離")]),
    ]:
        if len(sub) < 500:
            continue
        nicks = calc_nick_index(sub, min_combo_races=min_races,
                                min_sire_races=30, min_bms_races=30)
        results[condition] = nicks

    return results


# ──────────────────────────────────────────────────────────────
# ③ 3代ニックス（父×母父×母母父）
# ──────────────────────────────────────────────────────────────

def calc_3gen_nicks(
    df: pd.DataFrame,
    min_races: int = 15
) -> pd.DataFrame:
    """
    父×母父×母母父 の3代組み合わせ分析。
    より深い血統の相性を見る。
    """
    valid = df.dropna(subset=["haha_haha_chichi"])
    valid = valid[valid["haha_haha_chichi"] != ""]

    combo3 = (
        valid.groupby(["chichi","haha_chichi","haha_haha_chichi"])
             .agg(
                 races     = ("win",   "count"),
                 wins      = ("win",   "sum"),
                 total_ret = ("odds",  lambda x: (x * valid.loc[x.index,"win"] * 100).sum()),
                 avg_odds  = ("odds",  "mean"),
             )
             .reset_index()
    )
    combo3["win_rate"] = combo3["wins"]     / combo3["races"]
    combo3["roi"]      = combo3["total_ret"]/ (combo3["races"] * 100)
    combo3 = combo3[combo3["races"] >= min_races]
    return combo3.sort_values("roi", ascending=False)


# ──────────────────────────────────────────────────────────────
# ④ ニックススコアの特徴量化
# ──────────────────────────────────────────────────────────────

def build_nick_feature_table(nicks_df: pd.DataFrame) -> pd.DataFrame:
    """
    ニックスDF から (父, 母父) → nick_index / roi の対応テーブルを作成する。
    keiba_data_features.csv とのマージ用。
    """
    feat = nicks_df[["chichi","haha_chichi","nick_index","roi","win_rate",
                      "place_rate","avg_odds","races","significant"]].copy()
    feat.columns = ["chichi","haha_chichi","nick_index","nick_roi",
                    "nick_win_rate","nick_place_rate","nick_avg_odds",
                    "nick_races","nick_significant"]
    return feat


# ──────────────────────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────────────────────

def run_nicks_analysis(year_from: int = 2018, top_n: int = 30):
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"\n{'='*68}")
    print(f"🧬 ニックス（配合相性）徹底分析システム")
    print(f"   対象: {year_from}年〜 / 統計的有意性検定あり")
    print(f"{'='*68}")

    # ── データ読込 ────────────────────────────────────────────
    print("\n📥 データ取得中...")
    df = load_nicks_data(year_from)
    print(f"   {len(df):,}件 / 父{df['chichi'].nunique()}頭 "
          f"× 母父{df['haha_chichi'].nunique()}頭")

    # ── ① 全体ニックスTOP ────────────────────────────────────
    print("\n⚙️  ニックス指数を計算中...")
    nicks = calc_nick_index(df)

    print(f"\n\n{'='*68}")
    print(f"📊 ① ニックスTOP{top_n}（ニックス指数順・相乗効果が大きい順）")
    print(f"   ニックス指数>1.0 = 相乗効果あり / 統計的有意（p<0.10）を★で表示")
    print(f"{'='*68}")
    header = (f"\n{'父':16s} × {'母父':16s}  "
              f"{'出走':>5} {'勝率':>5} {'父勝率':>6} {'母父勝率':>7} "
              f"{'指数':>6} {'回収率':>7}")
    print(header)
    print("─" * 80)

    shown = 0
    for _, r in nicks.head(top_n * 2).iterrows():
        if shown >= top_n:
            break
        sig   = "★" if r["significant"] else "  "
        emoji = "💥" if r["nick_index"] >= 3.0 else ("🔥" if r["nick_index"] >= 2.0 else "✅")
        print(f"{sig}{emoji} {r['chichi'][:14]:14s} × {r['haha_chichi'][:14]:14s}  "
              f"{int(r['races']):>5} {r['win_rate']*100:>4.1f}% "
              f"{r['sire_wr']*100:>5.1f}% {r['bms_wr']*100:>6.1f}% "
              f"{r['nick_index']:>5.2f}x {r['roi']*100:>6.1f}%")
        shown += 1

    # ── ROI順TOP ─────────────────────────────────────────────
    nicks_roi = nicks[nicks["nick_index"] >= 1.5].sort_values("roi", ascending=False)
    print(f"\n\n{'='*68}")
    print(f"📊 ① ニックスTOP{top_n}（回収率順・ニックス指数1.5以上のみ）")
    print(f"{'='*68}")
    print(f"\n{'父':16s} × {'母父':16s}  "
          f"{'出走':>5} {'勝率':>5} {'指数':>6} {'回収率':>7} {'平均配当':>8}")
    print("─" * 72)

    for _, r in nicks_roi.head(top_n).iterrows():
        sig   = "★" if r["significant"] else "  "
        emoji = "💥" if r["roi"] >= 3.0 else ("🔥" if r["roi"] >= 2.0 else "✅")
        print(f"{sig}{emoji} {r['chichi'][:14]:14s} × {r['haha_chichi'][:14]:14s}  "
              f"{int(r['races']):>5} {r['win_rate']*100:>4.1f}% "
              f"{r['nick_index']:>5.2f}x {r['roi']*100:>6.1f}% "
              f"{r['avg_odds']:>7.1f}倍")

    # ── ② 条件別ニックス ─────────────────────────────────────
    print(f"\n\n{'='*68}")
    print(f"📊 ② 条件別ニックス TOP10（各条件の最強組み合わせ）")
    print(f"{'='*68}")
    cond_nicks = calc_conditional_nicks(df)

    for cond, df_cond in cond_nicks.items():
        best = df_cond[df_cond["nick_index"] >= 1.2].head(5)
        if len(best) == 0:
            continue
        print(f"\n【{cond}】")
        for _, r in best.iterrows():
            sig = "★" if r.get("significant", False) else "  "
            print(f"  {sig} {r['chichi'][:12]:12s} × {r['haha_chichi'][:12]:12s}  "
                  f"{int(r['races'])}出走 "
                  f"勝率{r['win_rate']*100:.1f}% "
                  f"指数{r['nick_index']:.2f}x "
                  f"回収率{r['roi']*100:.1f}%")

    # ── ③ 3代ニックス ────────────────────────────────────────
    print(f"\n\n{'='*68}")
    print(f"📊 ③ 3代ニックス TOP20（父×母父×母母父・回収率順）")
    print(f"{'='*68}")
    nicks3 = calc_3gen_nicks(df)
    print(f"\n{'父':13s} × {'母父':13s} × {'母母父':13s}  "
          f"{'出走':>5} {'勝率':>5} {'回収率':>7} {'平均配当':>8}")
    print("─" * 80)
    for _, r in nicks3.head(20).iterrows():
        emoji = "💥" if r["roi"] >= 5.0 else ("🔥" if r["roi"] >= 3.0 else "✅")
        print(f"{emoji} {r['chichi'][:11]:11s} × {r['haha_chichi'][:11]:11s} "
              f"× {r['haha_haha_chichi'][:11]:11s}  "
              f"{int(r['races']):>5} {r['win_rate']*100:>4.1f}% "
              f"{r['roi']*100:>6.1f}% {r['avg_odds']:>7.1f}倍")

    # ── ④ 保存 ───────────────────────────────────────────────
    print(f"\n\n{'='*68}")
    print(f"💾 結果を保存中...")

    nick_feat = build_nick_feature_table(nicks)
    paths = {
        "nicks_all.csv":        nicks,
        "nicks_roi_top.csv":    nicks_roi.head(200),
        "nicks_3gen.csv":       nicks3,
        "nicks_feature.csv":    nick_feat,
    }
    for fname, data in paths.items():
        p = os.path.join(OUT_DIR, fname)
        data.to_csv(p, index=False, encoding="utf-8-sig")
        print(f"   {p} ({len(data):,}件)")

    # 条件別も保存
    for cond, df_c in cond_nicks.items():
        p = os.path.join(OUT_DIR, f"nicks_{cond}.csv")
        df_c.to_csv(p, index=False, encoding="utf-8-sig")

    # ── ⑤ 現在の予想への適用 ─────────────────────────────────
    print(f"\n\n{'='*68}")
    print(f"🎯 ⑤ 本年予想への適用（simulation_2025.csv との照合）")
    print(f"{'='*68}")
    try:
        import pandas as pd
        sim = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                          encoding="utf-8-sig", on_bad_lines="skip")
        feat_df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                              encoding="utf-8-sig", low_memory=False,
                              on_bad_lines="skip",
                              usecols=["race_code","bamei","chichi"])
        feat_df["race_code"] = feat_df["race_code"].astype(str)
        sim["race_code"]     = sim["race_code"].astype(str)

        # DBから母父を追加取得
        engine2 = create_engine(DB_URL)
        bms_map = pd.read_sql(text("""
            SELECT DISTINCT u.race_code, u.bamei, m.ketto5_bamei AS haha_chichi
            FROM umagoto_race_joho u
            JOIN kyosoba_master2 m ON m.ketto_toroku_bango = u.ketto_toroku_bango
            WHERE u.kaisai_nen = '2025'
              AND m.ketto5_bamei IS NOT NULL
        """), engine2.connect())
        bms_map["race_code"] = bms_map["race_code"].astype(str)
        sim["race_code"]     = sim["race_code"].astype(str)

        merged_sim = (sim
            .merge(feat_df, on=["race_code","bamei"], how="left")
            .merge(bms_map,  on=["race_code","bamei"], how="left")
            .merge(
                nick_feat[["chichi","haha_chichi","nick_index","nick_roi","nick_significant"]],
                on=["chichi","haha_chichi"], how="left"
            ))

        has_nick = merged_sim[
            (merged_sim["nick_index"] >= 2.0) &
            (merged_sim["nick_significant"] == True)
        ].sort_values("nick_index", ascending=False)

        print(f"\n統計的有意なニックス保有馬（指数2.0以上）: {len(has_nick)}頭")
        if len(has_nick) > 0:
            cols = ["race_code","bamei","odds","hit",
                    "chichi","haha_chichi","nick_index","nick_roi"]
            cols = [c for c in cols if c in has_nick.columns]
            print(has_nick[cols].head(15).to_string(index=False))

    except FileNotFoundError as e:
        print(f"   ⚠️ {e}")

    print(f"\n{'='*68}")
    print(f"✅ ニックス分析完了")
    print(f"{'='*68}")

    return nicks


if __name__ == "__main__":
    run_nicks_analysis(year_from=2018, top_n=30)
