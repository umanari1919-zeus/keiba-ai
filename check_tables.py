import psycopg2
from pipeline.config import DB_CONFIG

conn=psycopg2.connect(**DB_CONFIG)
cur=conn.cursor()

tables=["yasuji_predictions","yasuji_horse_features","umagoto_race_joho","race_shosai","odds1_tansho"]
for t in tables:
    print(f"\n{'='*50}")
    print(f"テーブル: {t}")
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        count=cur.fetchone()[0]
        print(f"件数: {count:,}")
        cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{t}' ORDER BY ordinal_position LIMIT 20")
        cols=cur.fetchall()
        for c in cols:
            print(f"  {c[0]}: {c[1]}")
        if count>0:
            cur.execute(f"SELECT * FROM {t} ORDER BY 1 DESC LIMIT 2")
            rows=cur.fetchall()
            colnames=[d[0] for d in cur.description]
            print(f"最新2件:")
            for row in rows:
                for k,v in zip(colnames,row):
                    print(f"    {k}: {v}")
                print()
    except Exception as e:
        print(f"エラー: {e}")
        conn.rollback()

cur.close()
conn.close()
