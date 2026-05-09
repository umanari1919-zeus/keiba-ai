"""
血統徹底分析システム
① 五代血統表の生成・表示
② 父系/母父系別の条件適性分析（馬場・距離・天候）
③ インブリード（近親交配）検出と係数計算
④ 血統スコアリング → model_v8.pkl の特徴量として追加可能
⑤ 穴馬を生む血統パターンの抽出
"""
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from collections import Counter, defaultdict
from sqlalchemy import create_engine, text

from pipeline.config import DB_URL, PEDIGREE_OUTPUT_DIR

OUT_DIR  = os.fspath(PEDIGREE_OUTPUT_DIR)

# 血統位置の定義（ketto番号 → 系譜ラベル）
KETTO_LABELS = {
    1: "父",       2: "母",
    3: "父父",     4: "父母",     5: "母父",     6: "母母",
    7: "父父父",   8: "父父母",   9: "父母父",  10: "父母母",
   11: "母父父",  12: "母父母",  13: "母母父",  14: "母母母",
}

# 5代目ラベル（bamei結合で取得）
GEN5_LABELS = {
    "父父父父": (7, 1), "父父父母": (7, 2),
    "父父母父": (8, 1), "父父母母": (8, 2),
    "父母父父": (9, 1), "父母父母": (9, 2),
    "父母母父": (10,1), "父母母母": (10,2),
    "母父父父": (11,1), "母父父母": (11,2),
    "母父母父": (12,1), "母父母母": (12,2),
    "母母父父": (13,1), "母母父母": (13,2),
    "母母母父": (14,1), "母母母母": (14,2),
}


def _engine():
    return create_engine(DB_URL)


def _to_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────
# ① 五代血統表の生成
# ──────────────────────────────────────────────────────────────

def build_pedigree_5gen(bamei: str) -> dict:
    """
    指定した馬名の五代血統表を辞書形式で返す。
    {
      '父': 'ディープインパクト',
      '母': 'スターアイル',
      '父父': 'サンデーサイレンス', ...
      '父父父父': 'Halo', ...
    }
    """
    engine = _engine()
    with engine.connect() as conn:
        # 対象馬の1〜4代目を取得
        row = conn.execute(text("""
            SELECT
                ketto1_bamei,  ketto2_bamei,
                ketto3_bamei,  ketto4_bamei,  ketto5_bamei,  ketto6_bamei,
                ketto7_bamei,  ketto8_bamei,  ketto9_bamei,  ketto10_bamei,
                ketto11_bamei, ketto12_bamei, ketto13_bamei, ketto14_bamei
            FROM kyosoba_master2
            WHERE TRIM(bamei) = :bamei
            LIMIT 1
        """), {"bamei": bamei.strip()}).fetchone()

    if row is None:
        return {}

    pedigree = {KETTO_LABELS[i+1]: (row[i] or "").strip()
                for i in range(14)}

    # 5代目: 3〜4代目の馬をDBで再検索
    engine = _engine()
    with engine.connect() as conn:
        for label, (parent_idx, child_pos) in GEN5_LABELS.items():
            parent_name = pedigree.get(KETTO_LABELS[parent_idx], "")
            if not parent_name:
                pedigree[label] = ""
                continue
            child_col = f"ketto{child_pos}_bamei"
            r = conn.execute(text(f"""
                SELECT {child_col} FROM kyosoba_master2
                WHERE TRIM(bamei) = :name LIMIT 1
            """), {"name": parent_name}).fetchone()
            pedigree[label] = (r[0] or "").strip() if r else ""

    return pedigree


def print_pedigree_5gen(bamei: str):
    """五代血統表を見やすくコンソール表示する。"""
    pg = build_pedigree_5gen(bamei)
    if not pg:
        print(f"❌ '{bamei}' の血統データが見つかりません")
        return

    print(f"\n{'='*70}")
    print(f"🐴 五代血統表: {bamei}")
    print(f"{'='*70}")

    structure = [
        ("2代", ["父", "母"]),
        ("3代", ["父父", "父母", "母父", "母母"]),
        ("4代", ["父父父","父父母","父母父","父母母","母父父","母父母","母母父","母母母"]),
        ("5代", ["父父父父","父父父母","父父母父","父父母母",
                  "父母父父","父母父母","父母母父","父母母母",
                  "母父父父","母父父母","母父母父","母父母母",
                  "母母父父","母母父母","母母母父","母母母母"]),
    ]

    for gen_label, positions in structure:
        print(f"\n【{gen_label}】")
        for pos in positions:
            name = pg.get(pos, "")
            if name:
                print(f"  {pos:8s}: {name}")

    return pg


# ──────────────────────────────────────────────────────────────
# ② 父系/母父系別の条件適性分析
# ──────────────────────────────────────────────────────────────

def load_race_pedigree_data(year_from: int = 2018) -> pd.DataFrame:
    """レース結果と血統情報を結合して返す。"""
    engine = _engine()
    query = text("""
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
            m.ketto2_bamei  AS haha,
            m.ketto3_bamei  AS chichi_chichi,
            m.ketto5_bamei  AS haha_chichi,
            m.ketto4_bamei  AS chichi_haha,
            m.ketto6_bamei  AS haha_haha,
            m.ketto7_bamei  AS chichi_chichi_chichi,
            m.ketto11_bamei AS haha_chichi_chichi
        FROM umagoto_race_joho u
        JOIN race_shosai r USING (race_code)
        JOIN kyosoba_master2 m
          ON m.ketto_toroku_bango = u.ketto_toroku_bango
        WHERE u.kaisai_nen::int >= :y
          AND u.kakutei_chakujun ~ '^[0-9]+$'
          AND u.tansho_odds IS NOT NULL
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"y": year_from})

    df["chakujun"]   = pd.to_numeric(df["kakutei_chakujun"], errors="coerce")
    df["odds"]       = pd.to_numeric(df["tansho_odds"],       errors="coerce") / 10
    df["ninkijun"]   = pd.to_numeric(df["tansho_ninkijun"],   errors="coerce")
    df["kyori"]      = pd.to_numeric(df["kyori"],             errors="coerce")
    df["win"]        = (df["chakujun"] == 1).astype(int)
    df["place"]      = (df["chakujun"] <= 3).astype(int)
    df["track_type"] = df["track_code"].astype(str).str[0].map(
        {"1": "芝", "2": "ダート", "3": "障害"}
    ).fillna("その他")
    df["distance_band"] = pd.cut(
        df["kyori"],
        bins=[0, 1400, 1800, 2200, 9999],
        labels=["短距離", "マイル", "中距離", "長距離"]
    )
    return df


def _calc_stats(g: pd.DataFrame) -> dict:
    total = len(g)
    if total == 0:
        return {}
    wins  = g["win"].sum()
    place = g["place"].sum()
    bet   = total * 100
    ret   = (g[g["win"] == 1]["odds"] * 100).sum()
    roi   = ret / bet if bet > 0 else 0
    return {
        "races":     total,
        "wins":      int(wins),
        "win_rate":  wins / total,
        "place_rate":place / total,
        "roi":       roi,
        "avg_odds":  g["odds"].mean(),
        "avg_pop":   g["ninkijun"].mean(),
    }


def analyze_sire_lines(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """父系統別の成績を集計する。"""
    results = []
    for sire, g in df.groupby("chichi"):
        if not sire or pd.isna(sire):
            continue
        s = _calc_stats(g)
        s["sire"] = sire
        results.append(s)

    result_df = pd.DataFrame(results).dropna()
    result_df  = result_df[result_df["races"] >= 30]
    return result_df.sort_values("roi", ascending=False).head(top_n)


def analyze_broodmare_sire(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """母父系統別の成績を集計する。"""
    results = []
    for bms, g in df.groupby("haha_chichi"):
        if not bms or pd.isna(bms):
            continue
        s = _calc_stats(g)
        s["broodmare_sire"] = bms
        results.append(s)

    result_df = pd.DataFrame(results).dropna()
    result_df  = result_df[result_df["races"] >= 30]
    return result_df.sort_values("roi", ascending=False).head(top_n)


def analyze_sire_x_condition(df: pd.DataFrame) -> pd.DataFrame:
    """父 × 馬場種別 × 距離帯 の3軸クロス分析。"""
    results = []
    for (sire, track, dist), g in df.groupby(
        ["chichi", "track_type", "distance_band"], observed=True
    ):
        if not sire or len(g) < 20:
            continue
        s = _calc_stats(g)
        s.update({"sire": sire, "track": track, "distance": str(dist)})
        results.append(s)

    result_df = pd.DataFrame(results).dropna()
    return result_df.sort_values("roi", ascending=False)


# ──────────────────────────────────────────────────────────────
# ③ インブリード検出と係数計算
# ──────────────────────────────────────────────────────────────

def detect_inbreeding(pedigree: dict) -> dict:
    """
    五代血統表からインブリードを検出する。
    同一祖先が複数箇所に現れた場合にインブリードと判定。

    Returns
    -------
    dict: {祖先名: [出現箇所リスト]}
    """
    # 各世代の重み（遺伝寄与度の近似: 2^n）
    gen_weight = {
        "父": 2, "母": 2,
        "父父": 4, "父母": 4, "母父": 4, "母母": 4,
        "父父父": 8, "父父母": 8, "父母父": 8, "父母母": 8,
        "母父父": 8, "母父母": 8, "母母父": 8, "母母母": 8,
        "父父父父": 16, "父父父母": 16, "父父母父": 16, "父父母母": 16,
        "父母父父": 16, "父母父母": 16, "父母母父": 16, "父母母母": 16,
        "母父父父": 16, "母父父母": 16, "母父母父": 16, "母父母母": 16,
        "母母父父": 16, "母母父母": 16, "母母母父": 16, "母母母母": 16,
    }

    name_positions = defaultdict(list)
    for pos, name in pedigree.items():
        if name:
            name_positions[name].append(pos)

    inbreeding = {}
    nc_coefficient = 0.0

    for name, positions in name_positions.items():
        if len(positions) >= 2:
            inbreeding[name] = positions
            # Wright係数の簡易近似: Σ(1/2)^(n+1) where n=世代数
            for pos in positions:
                gen = gen_weight.get(pos, 32)
                nc_coefficient += 1.0 / gen

    return {
        "inbred_ancestors": inbreeding,
        "nc_coefficient": round(nc_coefficient, 4),
        "inbred_count": len(inbreeding),
    }


def print_inbreeding_report(bamei: str):
    """インブリード情報を表示する。"""
    pg = build_pedigree_5gen(bamei)
    if not pg:
        print(f"❌ '{bamei}' の血統データなし")
        return

    result = detect_inbreeding(pg)
    print(f"\n{'='*55}")
    print(f"🧬 インブリード分析: {bamei}")
    print(f"{'='*55}")
    print(f"インブリード係数 (NC近似): {result['nc_coefficient']:.4f}")
    print(f"重複祖先数: {result['inbred_count']}頭")

    if result["inbred_ancestors"]:
        print("\n【インブリード祖先一覧】")
        for ancestor, positions in sorted(
            result["inbred_ancestors"].items(),
            key=lambda x: len(x[1]),
            reverse=True
        ):
            print(f"  {ancestor}: {' × '.join(positions)}")
    else:
        print("インブリードなし（完全異系交配）")


# ──────────────────────────────────────────────────────────────
# ④ 血統スコアリング（モデル特徴量用）
# ──────────────────────────────────────────────────────────────

def build_sire_score_table(df: pd.DataFrame,
                            out_path: str = None) -> pd.DataFrame:
    """
    父ごとに [win_rate, place_rate, roi, 条件別win_rate] をスコア化した
    テーブルを作成する。model_v8.pkl の追加特徴量として使用可能。
    """
    rows = []
    for sire, g in df.groupby("chichi"):
        if not sire or pd.isna(sire) or len(g) < 20:
            continue

        base  = _calc_stats(g)
        shiba = _calc_stats(g[g["track_type"] == "芝"])
        dirt  = _calc_stats(g[g["track_type"] == "ダート"])
        short = _calc_stats(g[g["distance_band"] == "短距離"])
        mile  = _calc_stats(g[g["distance_band"] == "マイル"])
        mid   = _calc_stats(g[g["distance_band"] == "中距離"])
        long_ = _calc_stats(g[g["distance_band"] == "長距離"])

        rows.append({
            "chichi":           sire,
            "sire_races":       base.get("races",      0),
            "sire_win_rate":    base.get("win_rate",   0),
            "sire_place_rate":  base.get("place_rate", 0),
            "sire_roi":         base.get("roi",        0),
            "sire_shiba_wr":    shiba.get("win_rate",  0),
            "sire_dirt_wr":     dirt.get("win_rate",   0),
            "sire_short_wr":    short.get("win_rate",  0),
            "sire_mile_wr":     mile.get("win_rate",   0),
            "sire_mid_wr":      mid.get("win_rate",    0),
            "sire_long_wr":     long_.get("win_rate",  0),
        })

    score_df = pd.DataFrame(rows)
    if out_path is None:
        out_path = os.path.join(OUT_DIR, "sire_score_table.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    score_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"💾 父スコアテーブル保存: {out_path} ({len(score_df)}頭)")
    return score_df


def build_bms_score_table(df: pd.DataFrame,
                           out_path: str = None) -> pd.DataFrame:
    """母父ごとのスコアテーブル。"""
    rows = []
    for bms, g in df.groupby("haha_chichi"):
        if not bms or pd.isna(bms) or len(g) < 20:
            continue
        base = _calc_stats(g)
        rows.append({
            "haha_chichi":      bms,
            "bms_races":        base.get("races",      0),
            "bms_win_rate":     base.get("win_rate",   0),
            "bms_place_rate":   base.get("place_rate", 0),
            "bms_roi":          base.get("roi",        0),
        })

    score_df = pd.DataFrame(rows)
    if out_path is None:
        out_path = os.path.join(OUT_DIR, "bms_score_table.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    score_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"💾 母父スコアテーブル保存: {out_path} ({len(score_df)}頭)")
    return score_df


# ──────────────────────────────────────────────────────────────
# ⑤ 穴馬を生む血統パターン
# ──────────────────────────────────────────────────────────────

def find_upset_bloodlines(df: pd.DataFrame,
                          min_odds: float = 10.0,
                          top_n: int = 20) -> pd.DataFrame:
    """
    オッズ min_odds 倍以上の穴馬が1着になる「穴血統」を特定する。
    父 × 母父の2軸で回収率ベースにランキング。
    """
    upset = df[(df["odds"] >= min_odds) & (df["win"] == 1)].copy()
    all_  = df[df["odds"] >= min_odds].copy()

    results = []
    for (sire, bms), g_upset in upset.groupby(["chichi", "haha_chichi"]):
        if not sire or not bms:
            continue
        g_all = all_[(all_["chichi"] == sire) & (all_["haha_chichi"] == bms)]
        if len(g_all) < 10:
            continue

        ret  = (g_upset["odds"] * 100).sum()
        bet  = len(g_all) * 100
        roi  = ret / bet if bet > 0 else 0

        results.append({
            "父":       sire,
            "母父":      bms,
            "穴馬出走":  len(g_all),
            "穴馬的中":  len(g_upset),
            "穴的中率":  len(g_upset) / len(g_all),
            "回収率":    roi,
            "平均配当":  g_upset["odds"].mean(),
        })

    result_df = pd.DataFrame(results).sort_values("回収率", ascending=False)
    return result_df.head(top_n)


# ──────────────────────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────────────────────

def run_full_pedigree_analysis(year_from: int = 2020,
                                target_horse: str = None):
    """
    血統徹底分析を全項目実行する。

    Parameters
    ----------
    year_from    : 分析対象の開始年
    target_horse : 五代血統表を表示する馬名（Noneでスキップ）
    """
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"🐴 血統徹底分析システム起動 ({year_from}年〜)")
    print(f"{'='*65}")

    # ─ データ取得 ─────────────────────────────────────────────
    print("\n📥 レース×血統データを取得中...")
    df = load_race_pedigree_data(year_from)
    print(f"   取得件数: {len(df):,}件 ({df['kaisai_nen'].min()}〜{df['kaisai_nen'].max()}年)")

    # ─ ① 五代血統表 ──────────────────────────────────────────
    if target_horse:
        print_pedigree_5gen(target_horse)
        print_inbreeding_report(target_horse)

    # ─ ② 父系TOP30（ROI順）──────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"📊 ② 父系統別成績TOP30（回収率順）")
    print(f"{'='*65}")
    sire_df = analyze_sire_lines(df, top_n=30)
    print(f"\n{'父':20s} {'出走':>6} {'勝率':>6} {'複勝率':>6} "
          f"{'回収率':>7} {'平均オッズ':>9}")
    print("─" * 65)
    for _, r in sire_df.iterrows():
        emoji = "🔥" if r["roi"] >= 1.5 else ("✅" if r["roi"] >= 1.0 else "📉")
        print(f"{emoji} {r['sire'][:18]:18s} {int(r['races']):>6} "
              f"{r['win_rate']*100:>5.1f}% {r['place_rate']*100:>5.1f}% "
              f"{r['roi']*100:>6.1f}% {r['avg_odds']:>8.1f}倍")

    out_sire = os.path.join(OUT_DIR, "sire_stats.csv")
    sire_df.to_csv(out_sire, index=False, encoding="utf-8-sig")

    # ─ ③ 母父TOP30 ───────────────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"📊 ③ 母父系統別成績TOP30（回収率順）")
    print(f"{'='*65}")
    bms_df = analyze_broodmare_sire(df, top_n=30)
    print(f"\n{'母父':20s} {'出走':>6} {'勝率':>6} {'複勝率':>6} {'回収率':>7}")
    print("─" * 55)
    for _, r in bms_df.iterrows():
        emoji = "🔥" if r["roi"] >= 1.5 else ("✅" if r["roi"] >= 1.0 else "📉")
        print(f"{emoji} {r['broodmare_sire'][:18]:18s} {int(r['races']):>6} "
              f"{r['win_rate']*100:>5.1f}% {r['place_rate']*100:>5.1f}% "
              f"{r['roi']*100:>6.1f}%")

    # ─ ④ 父×馬場×距離 適性マップ ──────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"📊 ④ 父×馬場×距離 適性マップ TOP30（回収率順）")
    print(f"{'='*65}")
    cond_df = analyze_sire_x_condition(df)
    out_cond = os.path.join(OUT_DIR, "sire_x_condition.csv")
    cond_df.to_csv(out_cond, index=False, encoding="utf-8-sig")

    print(f"\n{'父':15s} {'馬場':4s} {'距離':6s} {'出走':>5} "
          f"{'勝率':>5} {'回収率':>7}")
    print("─" * 55)
    for _, r in cond_df.head(30).iterrows():
        emoji = "🔥" if r["roi"] >= 2.0 else "✅"
        print(f"{emoji} {r['sire'][:13]:13s} {r['track']:3s} "
              f"{r['distance']:5s} {int(r['races']):>5} "
              f"{r['win_rate']*100:>4.1f}% {r['roi']*100:>6.1f}%")

    # ─ ⑤ 穴馬血統パターン ────────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"📊 ⑤ 穴馬血統パターン TOP20（10倍以上・回収率順）")
    print(f"{'='*65}")
    upset_df = find_upset_bloodlines(df, min_odds=10.0, top_n=20)
    out_upset = os.path.join(OUT_DIR, "upset_bloodlines.csv")
    upset_df.to_csv(out_upset, index=False, encoding="utf-8-sig")

    print(f"\n{'父':15s} × {'母父':15s}  {'出走':>5} "
          f"{'的中':>4} {'穴的中率':>8} {'回収率':>7} {'平均配当':>8}")
    print("─" * 75)
    for _, r in upset_df.iterrows():
        emoji = "💥" if r["回収率"] >= 3.0 else ("🔥" if r["回収率"] >= 2.0 else "🎯")
        print(f"{emoji} {r['父'][:13]:13s} × {r['母父'][:13]:13s}  "
              f"{int(r['穴馬出走']):>5} {int(r['穴馬的中']):>4} "
              f"{r['穴的中率']*100:>7.1f}% {r['回収率']*100:>6.1f}% "
              f"{r['平均配当']:>7.1f}倍")

    # ─ ⑥ 血統スコアテーブル生成（モデル強化用）──────────────
    print(f"\n\n{'='*65}")
    print(f"📊 ⑥ 血統スコアテーブル生成（model_v8.pkl 特徴量追加用）")
    print(f"{'='*65}")
    sire_score  = build_sire_score_table(df)
    bms_score   = build_bms_score_table(df)

    # ─ サマリー ──────────────────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"✅ 血統分析完了")
    print(f"{'='*65}")
    print(f"  出力先: {OUT_DIR}/")
    print(f"  📄 sire_stats.csv          — 父系統別成績")
    print(f"  📄 sire_x_condition.csv    — 父×馬場×距離 適性マップ")
    print(f"  📄 upset_bloodlines.csv    — 穴馬血統パターン")
    print(f"  📄 sire_score_table.csv    — 父スコアテーブル（特徴量）")
    print(f"  📄 bms_score_table.csv     — 母父スコアテーブル（特徴量）")

    return {
        "df":        df,
        "sire_df":   sire_df,
        "bms_df":    bms_df,
        "cond_df":   cond_df,
        "upset_df":  upset_df,
        "sire_score": sire_score,
        "bms_score":  bms_score,
    }


# ──────────────────────────────────────────────────────────────
# DB書き出し関数群（pedigree_ancestor / pedigree_metrics テーブル）
# ──────────────────────────────────────────────────────────────

def save_pedigree_ancestor_to_db(
    horse_id: str,
    pedigree: dict,
    data_snapshot_id: str = "",
) -> int:
    """
    build_pedigree_5gen() の結果を pedigree_ancestor テーブルに upsert する。
    Returns: 書き込み行数
    """
    if not pedigree:
        return 0

    # 位置ラベル → 世代番号マッピング
    gen_map = {
        "父": 1, "母": 1,
        "父父": 2, "父母": 2, "母父": 2, "母母": 2,
        "父父父": 3, "父父母": 3, "父母父": 3, "父母母": 3,
        "母父父": 3, "母父母": 3, "母母父": 3, "母母母": 3,
    }
    for k in GEN5_LABELS:
        gen_map[k] = 4  # 5代目は generation=4 として扱う（1-indexed offset 1）

    rows = []
    for pos_label, ancestor_name in pedigree.items():
        if not ancestor_name:
            continue
        rows.append({
            "horse_id":       horse_id,
            "generation":     gen_map.get(pos_label, 5),
            "position_label": pos_label,
            "ancestor_id":    ancestor_name,   # 名前をIDとして代用（JBIS ID未接続時）
            "ancestor_name":  ancestor_name,
        })

    if not rows:
        return 0

    sql = """
        INSERT INTO pedigree_ancestor
            (horse_id, generation, position_label, ancestor_id, ancestor_name, updated_at)
        VALUES
            (%(horse_id)s, %(generation)s, %(position_label)s,
             %(ancestor_id)s, %(ancestor_name)s, now())
        ON CONFLICT (horse_id, generation, position_label) DO UPDATE
          SET ancestor_id   = EXCLUDED.ancestor_id,
              ancestor_name = EXCLUDED.ancestor_name,
              updated_at    = now()
    """
    import psycopg2
    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://")
                            .replace("postgresql://", "postgresql://"))
    with conn, conn.cursor() as cur:
        for r in rows:
            cur.execute(sql, r)
    conn.close()
    return len(rows)


def save_pedigree_metrics_to_db(
    horse_id: str,
    inbreeding_result: dict,
    nick_score: float = 0.0,
    nick_sample_size: int = 0,
    data_snapshot_id: str = "",
) -> None:
    """
    detect_inbreeding() の結果と nick_score を pedigree_metrics テーブルに upsert する。
    """
    inbreeding_coeff      = inbreeding_result.get("nc_coefficient", 0.0)
    inbreeding_components = {
        k: len(v)
        for k, v in inbreeding_result.get("inbred_ancestors", {}).items()
    }

    # outcross_index: 1 - (共通祖先数 / 30 最大想定)
    inbred_count   = inbreeding_result.get("inbred_count", 0)
    outcross_index = max(0.0, 1.0 - inbred_count / 30)

    sql = """
        INSERT INTO pedigree_metrics
            (horse_id, true_nicks_score, nick_sample_size,
             inbreeding_coeff, inbreeding_components, outcross_index,
             data_snapshot_id, computed_at)
        VALUES
            (%(horse_id)s, %(nick_score)s, %(nick_sample_size)s,
             %(inbreeding_coeff)s, %(inbreeding_components)s, %(outcross_index)s,
             %(snapshot_id)s, now())
        ON CONFLICT (horse_id) DO UPDATE
          SET true_nicks_score      = EXCLUDED.true_nicks_score,
              nick_sample_size      = EXCLUDED.nick_sample_size,
              inbreeding_coeff      = EXCLUDED.inbreeding_coeff,
              inbreeding_components = EXCLUDED.inbreeding_components,
              outcross_index        = EXCLUDED.outcross_index,
              data_snapshot_id      = EXCLUDED.data_snapshot_id,
              computed_at           = now()
    """
    import psycopg2, json as _json
    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://"))
    with conn, conn.cursor() as cur:
        cur.execute(sql, {
            "horse_id":             horse_id,
            "nick_score":           nick_score,
            "nick_sample_size":     nick_sample_size,
            "inbreeding_coeff":     inbreeding_coeff,
            "inbreeding_components": _json.dumps(inbreeding_components, ensure_ascii=False),
            "outcross_index":       outcross_index,
            "snapshot_id":          data_snapshot_id,
        })
    conn.close()


def run_pedigree_db_batch(
    limit: int = 200,
    data_snapshot_id: str = "",
    year_from: int = 2020,
) -> dict:
    """
    kyosoba_master2 から馬を取得し、pedigree_ancestor / pedigree_metrics に一括書き出す。

    Parameters
    ----------
    limit           : 処理する馬の最大数（初回は小さく設定して確認）
    data_snapshot_id: スナップショットID
    year_from       : 対象年以降に出走実績のある馬のみ処理

    Returns
    -------
    dict: {"processed": N, "ancestor_rows": M, "metrics_rows": K, "errors": [...]}
    """
    engine   = _engine()
    query    = text("""
        SELECT DISTINCT m.ketto_toroku_bango, m.bamei
        FROM kyosoba_master2 m
        JOIN umagoto_race_joho u
          ON u.ketto_toroku_bango = m.ketto_toroku_bango
        WHERE u.kaisai_nen::int >= :y
          AND m.bamei IS NOT NULL
          AND m.bamei <> ''
        LIMIT :lim
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"y": year_from, "lim": limit}).fetchall()

    processed     = 0
    ancestor_rows = 0
    metrics_rows  = 0
    errors        = []

    print(f"[pedigree_batch] {len(rows)}頭の血統をDBに書き出し中...")
    for i, (horse_id, bamei) in enumerate(rows, 1):
        try:
            pedigree = build_pedigree_5gen(bamei)
            if not pedigree:
                continue

            n = save_pedigree_ancestor_to_db(
                horse_id=str(horse_id),
                pedigree=pedigree,
                data_snapshot_id=data_snapshot_id,
            )
            ancestor_rows += n

            inbreeding = detect_inbreeding(pedigree)
            save_pedigree_metrics_to_db(
                horse_id=str(horse_id),
                inbreeding_result=inbreeding,
                data_snapshot_id=data_snapshot_id,
            )
            metrics_rows += 1
            processed    += 1

            if i % 20 == 0:
                print(f"  {i}/{len(rows)} 処理済み (祖先行: {ancestor_rows})")

        except Exception as exc:
            errors.append({"horse_id": str(horse_id), "bamei": bamei, "error": str(exc)[:120]})

    print(f"[pedigree_batch] 完了: {processed}頭 / 祖先行: {ancestor_rows} / 指標行: {metrics_rows} / エラー: {len(errors)}")
    return {
        "processed":     processed,
        "ancestor_rows": ancestor_rows,
        "metrics_rows":  metrics_rows,
        "errors":        errors,
    }


if __name__ == "__main__":
    # コマンドライン引数で馬名を指定可能
    import sys
    horse = sys.argv[1] if len(sys.argv) > 1 else "ディープインパクト"

    if "--db-batch" in sys.argv:
        # python pedigree_analysis_17.py --db-batch [--limit N]
        limit = 200
        for a in sys.argv:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
        run_pedigree_db_batch(limit=limit)
    else:
        results = run_full_pedigree_analysis(year_from=2020,
                                             target_horse=horse)
