import psycopg2
conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="mykeibadb", user="postgres")
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='woodchip_chokyo' ORDER BY ordinal_position")
print("=== woodchip_chokyo ===")
for r in cur.fetchall(): print(r)

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='race_shosai' ORDER BY ordinal_position")
print("=== race_shosai ===")
for r in cur.fetchall(): print(r)

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='umagoto_race_joho' AND column_name IN ('kaisai_nen','kaisai_gappi') ORDER BY ordinal_position")
print("=== umagoto_race_joho kaisai_nen/gappi ===")
for r in cur.fetchall(): print(r)

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='hanro_chokyo' ORDER BY ordinal_position")
print("=== hanro_chokyo ===")
for r in cur.fetchall(): print(r)

conn.close()
print("完了")
