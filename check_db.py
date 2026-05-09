import psycopg2
from pipeline.config import DB_CONFIG

conn=psycopg2.connect(**DB_CONFIG)
cur=conn.cursor()
cur.execute("""
SELECT table_schema, table_name 
FROM information_schema.tables 
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY table_schema, table_name
""")
rows=cur.fetchall()
print(f"テーブル数: {len(rows)}")
for r in rows:
    print(f"  {r[0]}.{r[1]}")
cur.close()
conn.close()
