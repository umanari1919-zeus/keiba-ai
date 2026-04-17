from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('postgresql://postgres:trust@localhost:5433/mykeibadb')
with engine.connect() as conn:
    df = pd.read_sql(text(
        "SELECT race_code, umaban, odds_saitei FROM odds1_fukusho LIMIT 5"
    ), conn)

print(df)
print(df.dtypes)