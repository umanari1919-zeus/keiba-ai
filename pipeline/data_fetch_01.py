"""
data_fetch_01.py  --  PostgreSQL -> keiba_data.csv / DB snapshot
新規列: grade_score, prev_chakujun, prev_odds, prev_keibajo, prev_kyori,
        prev_grade_score, grade_up, kishu_change, weeks_since_last_race,
        chokyo_3f_avg3, chokyo_3f_best, chokyo_3f_std, chokyo_trend,
        chokyo_improving, fresh_improving,
        kishu_keibajo_win_rate, chokyoshi_place_win_rate
"""
import pandas as pd
import numpy as np
from datetime import datetime

from pipeline.db_sync_42 import add_ingest_meta, get_engine, write_snapshot

DB_URL = "postgresql://postgres:trust@localhost:5433/mykeibadb"

GRADE_SCORE = {
    "G1":10,"GI":10,"G2":8,"GII":8,"G3":6,"GIII":6,
    "OP":4,"L":4,"3chi":3,"2chi":2,"1chi":1,
    "shinba":1,"mishouri":1,"shogai":5,
}

def _grade_to_score(g):
    if not g: return 1
    g = str(g).strip()
    if "G1" in g or "GI" == g: return 10
    if "G2" in g or "GII" == g: return 8
    if "G3" in g or "GIII" == g: return 6
    if "OP" in g or "L" in g: return 4
    if "3" in g and "chi" not in g: return 3
    if "2" in g and "chi" not in g: return 2
    return 1

def fetch_data():
    print(f"[data_fetch_01] {datetime.now().strftime('%H:%M:%S')} データ取得開始...")
    engine = get_engine(DB_URL)

    with engine.connect() as conn:
        # ① メインクエリ
        print("  (1) メインクエリ...")
        df = pd.read_sql("""
            SELECT
                u.race_code, u.kaisai_nen, u.kaisai_gappi, u.keibajo_code,
                u.bamei, u.ketto_toroku_bango, u.barei, u.seibetsu_code,
                u.kishu_code, u.kishumei_ryakusho,
                u.chokyoshi_code, u.chokyoshimei_ryakusho,
                u.futan_juryo, u.bataiju, u.zogen_sa, u.zogen_fugo,
                u.tansho_odds, u.tansho_ninkijun, u.kyakushitsu_hantei,
                u.kakutei_chakujun, u.wakuban, u.umaban,
                r.kyori, r.track_code, r.tenko_code,
                r.shiba_babajotai_code, r.dirt_babajotai_code,
                r.shusso_tosu, r.kaisai_kai, r.kaisai_nichime,
                COALESCE(r.grade,'') AS race_grade,
                m.ketto1_bamei AS chichi, m.ketto2_bamei AS haha,
                m.ketto3_bamei AS chichi_chichi, m.ketto5_bamei AS haha_chichi,
                m.shiba_ryo_1chaku, m.shiba_ryo_2chaku, m.shiba_ryo_3chaku,
                m.dirt_ryo_1chaku, m.dirt_ryo_2chaku, m.dirt_ryo_3chaku,
                m.shiba_short_1chaku, m.shiba_middle_1chaku, m.shiba_long_1chaku,
                m.dirt_short_1chaku, m.dirt_middle_1chaku, m.dirt_long_1chaku,
                m.kyakushitsu_keiko_nige, m.kyakushitsu_keiko_senko,
                m.kyakushitsu_keiko_sashi, m.kyakushitsu_keiko_oikomi,
                m.sogo_1chaku, m.sogo_2chaku, m.sogo_3chaku
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code
            LEFT JOIN kyosoba_master2 m ON u.ketto_toroku_bango = m.ketto_toroku_bango
            WHERE u.kaisai_nen >= '2020'
              AND u.kakutei_chakujun IS NOT NULL
              AND u.kakutei_chakujun != '00'
        """, conn)
        print(f"     -> {len(df):,} rows")

        # ② 調教タイム直近3本
        print("  (2) 調教タイム3本...")
        chokyo_df = pd.read_sql("""
            WITH ranked AS (
                SELECT ketto_toroku_bango,
                    time_gokei_3furlong::numeric AS t3f,
                    ROW_NUMBER() OVER (PARTITION BY ketto_toroku_bango
                                       ORDER BY chokyo_nengappi DESC) AS rn
                FROM hanro_chokyo
                WHERE time_gokei_3furlong ~ '^[0-9]+'
                  AND time_gokei_3furlong::numeric > 0
            )
            SELECT
                ketto_toroku_bango,
                MAX(CASE WHEN rn=1 THEN t3f END) AS chokyo_3f,
                AVG(CASE WHEN rn<=3 THEN t3f END) AS chokyo_3f_avg3,
                MIN(CASE WHEN rn<=3 THEN t3f END) AS chokyo_3f_best,
                STDDEV(CASE WHEN rn<=3 THEN t3f END) AS chokyo_3f_std,
                (MAX(CASE WHEN rn=3 THEN t3f END)
                 - MAX(CASE WHEN rn=1 THEN t3f END)) AS chokyo_trend
            FROM ranked WHERE rn<=3
            GROUP BY ketto_toroku_bango
        """, conn)
        print(f"     -> {len(chokyo_df):,} horses")

        # 調教ラップ（直近1本）
        chokyo_lap = pd.read_sql("""
            SELECT DISTINCT ON (ketto_toroku_bango)
                ketto_toroku_bango,
                lap_time_3furlong::numeric  AS chokyo_lap_3f,
                lap_time_1furlong::numeric  AS chokyo_lap_1f,
                time_gokei_4furlong::numeric AS chokyo_4f
            FROM hanro_chokyo
            WHERE time_gokei_3furlong > '0'
            ORDER BY ketto_toroku_bango, chokyo_nengappi DESC
        """, conn)

        chokyo_df = chokyo_df.merge(chokyo_lap, on="ketto_toroku_bango", how="left")

        # ③ 前走情報
        print("  (3) 前走情報...")
        prev_df = pd.read_sql("""
            WITH ord AS (
                SELECT u.ketto_toroku_bango, u.race_code,
                    u.kishu_code,
                    u.kakutei_chakujun::int  AS chakujun,
                    u.tansho_odds::numeric   AS odds,
                    u.keibajo_code,
                    r.kyori, r.grade,
                    u.kaisai_nen||u.kaisai_gappi AS rdate,
                    LAG(u.kishu_code)   OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_kishu,
                    LAG(u.kakutei_chakujun::int) OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_chak,
                    LAG(u.tansho_odds::numeric)  OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_od,
                    LAG(u.keibajo_code) OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_kei,
                    LAG(r.kyori)        OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_kyo,
                    LAG(r.grade)        OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_grd,
                    LAG(u.kaisai_nen||u.kaisai_gappi) OVER (PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code) AS prev_dt
                FROM umagoto_race_joho u
                JOIN race_shosai r ON u.race_code = r.race_code
                WHERE u.kakutei_chakujun ~ '^[0-9]+'
                  AND u.tansho_odds ~ '^[0-9]+'
                  AND u.kaisai_nen >= '2019'
            )
            SELECT race_code, ketto_toroku_bango,
                prev_chak  AS prev_chakujun,
                prev_od/10 AS prev_odds,
                prev_kei   AS prev_keibajo,
                prev_kyo   AS prev_kyori,
                prev_grd   AS prev_grade,
                CASE WHEN prev_kishu IS NOT NULL
                          AND prev_kishu != kishu_code THEN 1 ELSE 0 END AS kishu_change,
                CASE WHEN prev_dt IS NOT NULL THEN
                    GREATEST(0, (TO_DATE(rdate,'YYYYMMDD')
                                 - TO_DATE(prev_dt,'YYYYMMDD')) / 7)
                ELSE 0 END AS weeks_since_last_race
            FROM ord WHERE prev_chak IS NOT NULL
        """, conn)
        print(f"     -> {len(prev_df):,} rows")

        # ④ 騎手×競馬場別勝率
        print("  (4) 騎手x競馬場勝率...")
        kk_df = pd.read_sql("""
            SELECT kishu_code, keibajo_code,
                SUM(CASE WHEN kakutei_chakujun='1' THEN 1 ELSE 0 END)::float
                    / NULLIF(COUNT(*),0) AS kishu_keibajo_win_rate
            FROM umagoto_race_joho
            WHERE kakutei_chakujun ~ '^[0-9]+'
              AND kakutei_chakujun::int > 0
              AND kishu_code ~ '^[0-9]+'
            GROUP BY kishu_code, keibajo_code HAVING COUNT(*) >= 5
        """, conn)
        print(f"     -> {len(kk_df):,} rows")

        # ⑤ 調教師×競馬場×距離別勝率
        print("  (5) 調教師x競馬場x距離勝率...")
        cp_df = pd.read_sql("""
            SELECT u.chokyoshi_code, u.keibajo_code,
                CASE WHEN r.kyori::int<=1400 THEN 'short'
                     WHEN r.kyori::int<=2000 THEN 'middle'
                     ELSE 'long' END AS kyori_group,
                SUM(CASE WHEN u.kakutei_chakujun='1' THEN 1 ELSE 0 END)::float
                    / NULLIF(COUNT(*),0) AS chokyoshi_place_win_rate
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code
            WHERE u.kakutei_chakujun ~ '^[0-9]+' AND u.kakutei_chakujun::int>0
              AND u.chokyoshi_code ~ '^[0-9]+' AND r.kyori ~ '^[0-9]+'
            GROUP BY u.chokyoshi_code, u.keibajo_code, kyori_group
            HAVING COUNT(*) >= 5
        """, conn)
        print(f"     -> {len(cp_df):,} rows")

    # ── マージ ──────────────────────────────────────────────
    print("  (6) データ結合中...")

    df = df.merge(chokyo_df, on="ketto_toroku_bango", how="left")
    df = df.merge(
        prev_df[["race_code","ketto_toroku_bango","prev_chakujun","prev_odds",
                 "prev_keibajo","prev_kyori","prev_grade",
                 "kishu_change","weeks_since_last_race"]],
        on=["race_code","ketto_toroku_bango"], how="left"
    )

    # 騎手×競馬場
    df["_kc"] = df["kishu_code"].astype(str)
    df["_kj"] = df["keibajo_code"].astype(str)
    kk_df["kishu_code"]   = kk_df["kishu_code"].astype(str)
    kk_df["keibajo_code"] = kk_df["keibajo_code"].astype(str)
    df = df.merge(kk_df, left_on=["_kc","_kj"],
                  right_on=["kishu_code","keibajo_code"], how="left",
                  suffixes=("","_kk"))
    for c in [x for x in df.columns if x.endswith("_kk")] + ["_kc","_kj"]:
        if c in df.columns: df.drop(columns=c, inplace=True)

    # 調教師×競馬場×距離
    def _kg(k):
        try:
            v=int(k); return "short" if v<=1400 else "middle" if v<=2000 else "long"
        except: return "middle"
    df["_kg"] = df["kyori"].apply(_kg)
    df["_cc"] = df["chokyoshi_code"].astype(str)
    df["_kj2"]= df["keibajo_code"].astype(str)
    cp_df["chokyoshi_code"] = cp_df["chokyoshi_code"].astype(str)
    cp_df["keibajo_code"]   = cp_df["keibajo_code"].astype(str)
    df = df.merge(cp_df, left_on=["_cc","_kj2","_kg"],
                  right_on=["chokyoshi_code","keibajo_code","kyori_group"],
                  how="left", suffixes=("","_cp"))
    for c in [x for x in df.columns if x.endswith("_cp")] + ["_kg","_cc","_kj2","kyori_group"]:
        if c in df.columns: df.drop(columns=c, inplace=True)

    # ── クレンジング ────────────────────────────────────────
    print("  (7) クレンジング...")
    for col in ["bataiju","zogen_sa","tansho_odds","tansho_ninkijun",
                "kyori","shusso_tosu","futan_juryo",
                "sogo_1chaku","sogo_2chaku","sogo_3chaku",
                "chokyo_3f","chokyo_lap_3f","chokyo_lap_1f","chokyo_4f",
                "chokyo_3f_avg3","chokyo_3f_best","chokyo_3f_std","chokyo_trend",
                "prev_chakujun","prev_odds","prev_kyori",
                "kishu_change","weeks_since_last_race",
                "kishu_keibajo_win_rate","chokyoshi_place_win_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["zogen_fugo"]       = df["zogen_fugo"].map({"+":1,"-":-1}).fillna(0)
    df["kakutei_chakujun"] = pd.to_numeric(df["kakutei_chakujun"], errors="coerce")

    df["grade_score"]      = df["race_grade"].apply(_grade_to_score)
    df["prev_grade_score"] = df["prev_grade"].apply(
        lambda x: _grade_to_score(x) if pd.notna(x) else 1)
    df["grade_up"]         = (df["grade_score"] > df["prev_grade_score"]).astype(int)

    df["chokyo_improving"] = (df["chokyo_trend"].fillna(0) > 0).astype(int)
    df["fresh_improving"]  = (
        (df["weeks_since_last_race"].fillna(0) >= 8) &
        (df["chokyo_improving"] == 1)
    ).astype(int)

    df["chichi_code"]        = pd.Categorical(df["chichi"]).codes
    df["haha_code"]          = pd.Categorical(df["haha"]).codes
    df["chichi_chichi_code"] = pd.Categorical(df["chichi_chichi"]).codes

    df = df.fillna(0)

    # ── 保存 ───────────────────────────────────────────────
    out_path = "D:\\keiba_ai\\keiba_data.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    try:
        snapshot = add_ingest_meta(df, source_name="data_fetch_01")
        ok = write_snapshot(
            snapshot,
            "keiba_data_raw_snapshot",
            if_exists="replace",
            source_name="data_fetch_01",
        )
        if ok:
            print("  💾 DB同期: keiba_data_raw_snapshot")
    except Exception as e:
        print(f"  ⚠️ DB同期スキップ: {e}")

    new_cols = ["race_grade","grade_score","prev_grade_score","grade_up",
                "prev_chakujun","prev_odds","prev_keibajo","prev_kyori",
                "kishu_change","weeks_since_last_race",
                "chokyo_3f_avg3","chokyo_3f_best","chokyo_3f_std","chokyo_trend",
                "chokyo_improving","fresh_improving",
                "kishu_keibajo_win_rate","chokyoshi_place_win_rate"]
    found = [c for c in new_cols if c in df.columns]
    print(f"\n[data_fetch_01] 完了!")
    print(f"  件数: {len(df):,}件  列数: {len(df.columns)}列 (+{len(found)}新規列)")
    print(f"  新規: {', '.join(found)}")
    return df

if __name__ == "__main__":
    fetch_data()
