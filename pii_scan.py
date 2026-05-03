import argparse
from pathlib import Path
import json
import pandas as pd

PII_KEYWORDS = [
    "name","full_name","firstname","lastname","email","mail","phone","tel","mobile",
    "address","addr","zip","postal","ssn","id_number","id","passport","birth","dob"
]

def scan_csv(path: Path, sample_rows: int = 5):
    try:
        df = pd.read_csv(path, nrows=sample_rows, dtype=str, encoding='utf-8', engine='c', low_memory=True)
        cols = [c.lower() for c in df.columns]
        suspects = [c for c in cols if any(k in c for k in PII_KEYWORDS)]
        return {"file": str(path), "suspect_columns": suspects} if suspects else None
    except Exception as e:
        return {"file": str(path), "error": str(e)}

def main(root, out, sample_rows):
    rootp = Path(root)
    results = []
    for p in rootp.rglob("*.csv"):
        res = scan_csv(p, sample_rows)
        if res:
            results.append(res)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"PII candidates written to {out}. Found {len(results)} files.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan CSV files for potential PII columns")
    parser.add_argument("--root", required=True, help="Root folder to scan")
    parser.add_argument("--out", required=False, default="pii_candidates.json", help="Output JSON path")
    parser.add_argument("--sample_rows", type=int, default=5, help="Rows to sample per CSV")
    args = parser.parse_args()
    main(args.root, args.out, args.sample_rows)
