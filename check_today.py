import psycopg2
from pipeline.config import DB_CONFIG

conn=psycopg2.connect(**DB_CONFIG)
cur=conn.cursor()
print("=== 本日のレース一覧 ===")
cur.execute("""
SELECT DISTINCT
    r.race_code,
    r.keibajo_code,
    r.race_bango,
    r.kyori,
    r.track_code,
    r.tenko_code,
    r.shiba_babajotai_code,
    r.toroku_tosu,
    r.hasso_jikoku
FROM race_shosai r
WHERE r.kaisai_gappi='0502' AND r.kaisai_nen='2026'
ORDER BY r.keibajo_code, r.race_bango
""")
races=cur.fetchall()
print(f"レース数: {len(races)}")
for r in races:
    print(f"  {r[0]} 競馬場:{r[1]} {r[2]}R 距離:{r[3]}m トラック:{r[4]} 天気:{r[5]} 馬場:{r[6]} 登録:{r[7]}頭 発走:{r[8]}")

print()
print("=== 本日の出走馬サンプル（1R） ===")
cur.execute("""
SELECT
    u.race_code, u.umaban, u.bamei,
    u.kishumei_ryakusho, u.futan_juryo,
    CAST(o.odds AS FLOAT)/10 AS tansho_odds
FROM umagoto_race_joho u
LEFT JOIN odds1_tansho o
    ON u.race_code=o.race_code AND u.umaban=o.umaban
WHERE u.kaisai_gappi='0502' AND u.kaisai_nen='2026'
  AND u.race_bango='01'
  AND u.keibajo_code='05'
ORDER BY CAST(u.umaban AS INTEGER)
LIMIT 18
""")
horses=cur.fetchall()
for h in horses:
    odds=f"{h[5]:.1f}倍" if h[5] else "---"
    print(f"  {h[2]}番 {h[3]}　騎手:{h[4]}　斤量:{int(h[5] or 0)/10}　オッズ:{odds}")

cur.close()
conn.close()
