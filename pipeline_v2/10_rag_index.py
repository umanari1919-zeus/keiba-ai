"""
10_rag_index.py  ─  うまなり地蔵AI / rag_index ステージ
========================================================
keiba_data_features.csv から RAG ベクトルインデックスを構築する。
agents.RAGStore.build_from_features_csv() を利用。
特徴量更新後に実行することで LLMExplainAgent の類似馬検索精度が向上する。

実行方法:
  python pipeline_v2/10_rag_index.py
  python pipeline_v2/10_rag_index.py --dry-run   # 行数確認のみ
  python pipeline_v2/10_rag_index.py --limit 5000
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime

_BASE_DIR = pathlib.Path(r"D:\keiba_ai")
# BASE_DIR を必ず先頭に (worktree より優先)
if str(_BASE_DIR) in sys.path:
    sys.path.remove(str(_BASE_DIR))
sys.path.insert(0, str(_BASE_DIR))

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
BASE     = pathlib.Path(__file__).parent
LOG_DIR  = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"rag_index_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

FEAT_CSV = BASE_DIR / "keiba_data_features.csv"


def build_rag_index(limit: int = 0, dry_run: bool = False) -> dict:
    """
    keiba_data_features.csv から RAGStore インデックスを構築する。

    Parameters
    ----------
    limit   : 0 = 全行, 正値 = 先頭 N 行のみ（開発・テスト用）
    dry_run : True = CSV 行数確認のみ、インデックス構築スキップ

    Returns
    -------
    dict: {indexed, backend, csv_rows, skipped}
    """
    if not FEAT_CSV.exists():
        log.error("keiba_data_features.csv が見つかりません: %s", FEAT_CSV)
        return {"error": "features csv not found"}

    # CSV 行数の確認
    import pandas as pd
    log.info("CSV 読み込み中: %s", FEAT_CSV)
    df = pd.read_csv(FEAT_CSV, on_bad_lines="skip", low_memory=False)
    csv_rows = len(df)
    log.info("  総行数: %d", csv_rows)

    if limit > 0:
        df = df.head(limit)
        log.info("  limit=%d 適用 → %d 行", limit, len(df))

    if dry_run:
        log.info("[DRY-RUN] インデックス構築をスキップします。")
        return {"indexed": 0, "csv_rows": csv_rows, "dry_run": True}

    # RAGStore インポートと構築
    try:
        from agents.rag_store import get_default_store, BACKEND
    except ImportError as exc:
        log.error("agents.rag_store インポート失敗: %s", exc)
        return {"error": str(exc)}

    log.info("RAGStore バックエンド: %s", BACKEND)
    store = get_default_store()

    # 行ごとにエンベッディング追加
    indexed = 0
    skipped = 0
    for _, row in df.iterrows():
        horse_id = str(row.get("ketto_toroku_bango", row.get("horse_id", f"row_{indexed}")))
        features = row.to_dict()
        metadata = {
            "race_code": str(row.get("race_code", "")),
            "race_date": str(row.get("race_date", "")),
            "bamei":     str(row.get("bamei", "")),
        }
        try:
            store.add(horse_id, features, metadata)
            indexed += 1
        except Exception as exc:
            log.debug("add エラー (horse_id=%s): %s", horse_id, exc)
            skipped += 1

        if indexed % 1000 == 0 and indexed > 0:
            log.info("  インデックス構築中: %d 行完了", indexed)

    log.info("RAG インデックス構築完了: indexed=%d skipped=%d backend=%s", indexed, skipped, BACKEND)
    return {"indexed": indexed, "skipped": skipped, "csv_rows": csv_rows, "backend": BACKEND}


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, limit: int = 0) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== rag_index ステージ開始 trace=%s ===", trace_id)

    result = build_rag_index(limit=limit, dry_run=dry_run)

    if "error" in result:
        log.error("rag_index 失敗: %s", result["error"])
        return 1

    log.info("rag_index 完了: %s", result)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG ベクトルインデックス構築")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--limit",    type=int, default=0, help="インデックス対象行数（0=全件）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.limit))
