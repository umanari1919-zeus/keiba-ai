import psycopg2
conn=psycopg2.connect(host="localhost",port=5433,dbname="mykeibadb",user="postgres",password="")
cur=conn.cursor()
cur.execute("""
SELECT
    kaisai_nen,
    COUNT(DISTINCT race_code) AS races,
    COUNT(*) AS horses,
    COUNT(CASE WHEN kakutei_chakujun='01' THEN 1 END) AS winners
FROM umagoto_race_joho
WHERE data_kubun='7'
  AND kaisai_nen IN ('2023','2024','2025','2026')
GROUP BY kaisai_nen
ORDER BY kaisai_nen
""")
for r in cur.fetchall():
    print(f"  {r[0]}年: {r[1]:,}レース {r[2]:,}頭 勝ち馬:{r[3]:,}")
cur.close()
conn.close()
