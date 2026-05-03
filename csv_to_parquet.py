# csv_to_parquet.py
import sys
import pandas as pd
in_path = sys.argv[1]
out_path = sys.argv[2]
df = pd.read_csv(in_path)
df.to_parquet(out_path, compression='snappy', index=False)
print("Converted", in_path, "->", out_path)
