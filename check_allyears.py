import psycopg2
from pipeline.config import DB_CONFIG

conn=psycopg2.connect(**DB_CONFIG)
cur=conn.cursor()
cur.execute("""
SELECT
    kaisai_nen,
    COUNT(DISTINCT race_code) AS races,
    COUNT(*) AS horses,
    COUNT(CASE WHEN kakutei_chakujun='01' THEN 1 END) AS winners
FROM umagoto_race_joho
WHERE data_kubun='7'
GROUP BY kaisai_nen
ORDER BY kaisai_nen
""")
rows=cur.fetchall()
print(f"{'年':>6} {'レース':>8} {'頭数':>10} {'勝ち馬':>8}")
print("-"*40)
total_r,total_h=0,0
for r in rows:
    print(f"  {r[0]}年: {r[1]:>6,}レース {r[2]:>8,}頭 勝ち馬:{r[3]:>6,}")
    total_r+=r[1]; total_h+=r[2]
print("-"*40)
print(f"  合計: {total_r:>6,}レース {total_h:>8,}頭")
cur.close()
conn.close()
