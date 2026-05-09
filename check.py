from sqlalchemy import create_engine, text
import pandas as pd

from pipeline.config import DB_URL

engine = create_engine(DB_URL)
with engine.connect() as conn:
    df = pd.read_sql(text(
        "SELECT race_code, umaban, odds_saitei FROM odds1_fukusho LIMIT 5"
    ), conn)

print(df)
print(df.dtypes)
