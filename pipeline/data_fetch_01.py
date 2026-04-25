from sqlalchemy import create_engine
import pandas as pd
from datetime import datetime

def fetch_data():
    print(f"📂 [{datetime.now()}] データ取得開始...")
    
    engine = create_engine(
        "postgresql://postgres:trust@localhost:5433/mykeibadb"
    )
    
    with engine.connect() as conn:
        df = pd.read_sql("""
            SELECT 
                u.race_code,
                u.kaisai_nen,
                u.kaisai_gappi,
                u.keibajo_code,
                u.bamei,
                u.ketto_toroku_bango,
                u.barei,
                u.seibetsu_code,
                u.kishu_code,
                u.kishumei_ryakusho,
                u.chokyoshi_code,
                u.futan_juryo,
                u.bataiju,
                u.zogen_sa,
                u.zogen_fugo,
                u.tansho_odds,
                u.tansho_ninkijun,
                u.kyakushitsu_hantei,
                u.kakutei_chakujun,
                u.wakuban,
                u.umaban,
                r.kyori,
                r.track_code,
                r.tenko_code,
                r.shiba_babajotai_code,
                r.dirt_babajotai_code,
                r.shusso_tosu,
                r.kaisai_kai,
                r.kaisai_nichime,
                -- 血統情報
                m.ketto1_bamei as chichi,
                m.ketto2_bamei as haha,
                m.ketto3_bamei as chichi_chichi,
                m.ketto5_bamei as haha_chichi,
                -- 馬場状態別成績
                m.shiba_ryo_1chaku,
                m.shiba_ryo_2chaku,
                m.shiba_ryo_3chaku,
                m.dirt_ryo_1chaku,
                m.dirt_ryo_2chaku,
                m.dirt_ryo_3chaku,
                -- 距離別成績
                m.shiba_short_1chaku,
                m.shiba_middle_1chaku,
                m.shiba_long_1chaku,
                m.dirt_short_1chaku,
                m.dirt_middle_1chaku,
                m.dirt_long_1chaku,
                -- 脚質傾向
                m.kyakushitsu_keiko_nige,
                m.kyakushitsu_keiko_senko,
                m.kyakushitsu_keiko_sashi,
                m.kyakushitsu_keiko_oikomi,
                -- 通算成績
                m.sogo_1chaku,
                m.sogo_2chaku,
                m.sogo_3chaku,
                -- 調教タイム（直近1本）
                c.time_gokei_3furlong as chokyo_3f,
                c.lap_time_3furlong as chokyo_lap_3f,
                c.lap_time_1furlong as chokyo_lap_1f,
                c.time_gokei_4furlong as chokyo_4f
            FROM umagoto_race_joho u
            JOIN race_shosai r 
                ON u.race_code = r.race_code
            LEFT JOIN kyosoba_master2 m
                ON u.ketto_toroku_bango = m.ketto_toroku_bango
            LEFT JOIN (
                SELECT DISTINCT ON (ketto_toroku_bango)
                    ketto_toroku_bango,
                    time_gokei_3furlong,
                    lap_time_3furlong,
                    lap_time_1furlong,
                    time_gokei_4furlong
                FROM hanro_chokyo
                WHERE time_gokei_3furlong > '0'
                ORDER BY ketto_toroku_bango, chokyo_nengappi DESC
            ) c ON u.ketto_toroku_bango = c.ketto_toroku_bango
            WHERE u.kaisai_nen >= '2020'
            AND u.kakutei_chakujun IS NOT NULL
            AND u.kakutei_chakujun != '00'
        """, conn)
    
    # クレンジング
    df['bataiju'] = pd.to_numeric(df['bataiju'], errors='coerce')
    df['zogen_sa'] = pd.to_numeric(df['zogen_sa'], errors='coerce')
    df['zogen_fugo'] = df['zogen_fugo'].map({'+': 1, '-': -1}).fillna(0)
    df['kakutei_chakujun'] = pd.to_numeric(
        df['kakutei_chakujun'], errors='coerce'
    )
    
    # 血統をコード化
    df['chichi_code'] = pd.Categorical(df['chichi']).codes
    df['haha_code'] = pd.Categorical(df['haha']).codes
    df['chichi_chichi_code'] = pd.Categorical(df['chichi_chichi']).codes
    
    df = df.fillna(0)
    
    # 保存
    df.to_csv("D:\\keiba_ai\\keiba_data.csv", 
              index=False, encoding="utf-8-sig")
    
    print(f"✅ データ取得完了！件数：{len(df):,}件")
    print(f"📋 列数：{len(df.columns)}列")
    return df

if __name__ == "__main__":
    fetch_data()