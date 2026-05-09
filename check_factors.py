import psycopg2, pandas as pd
from pipeline.config import DB_CONFIG

conn=psycopg2.connect(**DB_CONFIG)
cur=conn.cursor()

# umagoto_race_johoの全カラムサンプル値を確認
cur.execute("""
SELECT column_name FROM information_schema.columns
WHERE table_name='umagoto_race_joho' ORDER BY ordinal_position
""")
cols=[r[0] for r in cur.fetchall()]

# 過去レース（確定済み）と未来レース（当日）のサンプルを比較
cur.execute("""
SELECT * FROM umagoto_race_joho
WHERE race_code='2026042005020911' AND data_kubun='7'
LIMIT 1
""")
row=cur.fetchone()
if row:
    print("=== 確定済みレースのサンプル ===")
    for k,v in zip(cols,row):
        print(f"  {k:35s}: {repr(v)}")

print()
# 当日（未確定）データ
cur.execute("""
SELECT * FROM umagoto_race_joho
WHERE kaisai_nen='2026' AND kaisai_gappi='0502' AND race_bango='01' AND keibajo_code='05'
AND umaban='01'
LIMIT 1
""")
row2=cur.fetchone()
if row2:
    print("=== 当日（未確定）レースのサンプル ===")
    for k,v in zip(cols,row2):
        print(f"  {k:35s}: {repr(v)}")

cur.close()
conn.close()
