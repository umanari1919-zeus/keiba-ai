import psycopg2
conn=psycopg2.connect(host="localhost",port=5433,dbname="mykeibadb",user="postgres",password="")
cur=conn.cursor()
cur.execute("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name='umagoto_race_joho'
ORDER BY ordinal_position
""")
cols=cur.fetchall()
print(f"列数: {len(cols)}")
for c in cols:
    print(f"  {c[0]}: {c[1]}")
cur.close()
conn.close()
