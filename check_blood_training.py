import psycopg2
conn=psycopg2.connect(host="localhost",port=5433,dbname="mykeibadb",user="postgres",password="")
cur=conn.cursor()

tables=["keito_joho2","hanro_chokyo","woodchip_chokyo","kyosoba_master2","hanshokuba_master2","sanku_master2"]
for t in tables:
    print(f"\n{'='*50}")
    print(f"テーブル: {t}")
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"件数: {cur.fetchone()[0]:,}")
        cur.execute(f"""SELECT column_name,data_type FROM information_schema.columns
            WHERE table_name='{t}' ORDER BY ordinal_position LIMIT 30""")
        for c in cur.fetchall():
            print(f"  {c[0]}: {c[1]}")
    except Exception as e:
        print(f"エラー: {e}")
        conn.rollback()

cur.close()
conn.close()
