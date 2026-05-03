import sys
from pathlib import Path
import json

def inspect_pickle(p):
    try:
        with open(p, "rb") as f:
            header = f.read(4)
            f.seek(0, 2)
            size = f.tell()
        return {"path": str(p), "size": size, "header_bytes": header.hex()}
    except Exception as e:
        return {"path": str(p), "error": str(e)}

def main(root):
    rootp = Path(root)
    out = []
    for p in rootp.rglob("*.pkl"):
        out.append(inspect_pickle(p))
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    main(root)
