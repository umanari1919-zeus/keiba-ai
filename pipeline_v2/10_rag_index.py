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
  python pipeline_v2/10_rag_index.py --limit 50000 --rebuild
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
# プロジェクトルートを必ず先頭に (worktree より優先)
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

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

try:
    from pipeline.config import CSV_FEATURES
except ImportError:
    CSV_FEATURES = str(PROJECT_ROOT / "keiba_data_features.csv")

FEAT_CSV = pathlib.Path(CSV_FEATURES)


def _clean_id_part(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def make_doc_id(row_index: int, row: object) -> str:
    """CSV 行から再実行しても安定する RAG document ID を作る。"""
    race_code = _clean_id_part(row.get("race_code", ""))
    horse_id = _clean_id_part(row.get("ketto_toroku_bango", row.get("horse_id", "")))
    umaban = _clean_id_part(row.get("umaban", ""))
    return f"row:{row_index}:race:{race_code}:horse:{horse_id}:umaban:{umaban}"


def count_csv_rows(csv_path: pathlib.Path) -> int:
    """pandas がなくても dry-run 用に CSV 行数だけ確認する。"""
    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        row_count = sum(1 for _ in f)
    return max(row_count - 1, 0)


def build_rag_index(limit: int = 0, dry_run: bool = False, rebuild: bool = False) -> dict:
    """
    keiba_data_features.csv から RAGStore インデックスを構築する。

    Parameters
    ----------
    limit   : 0 = 全行, 正値 = 先頭 N 行のみ（開発・テスト用）
    dry_run : True = CSV 行数確認のみ、インデックス構築スキップ
    rebuild : True = 既存ストアを消してから構築

    Returns
    -------
    dict: {indexed, backend, csv_rows, skipped}
    """
    if not FEAT_CSV.exists():
        log.error("keiba_data_features.csv が見つかりません: %s", FEAT_CSV)
        return {"error": "features csv not found"}

    if not dry_run and limit <= 0 and os.getenv("KEIBA_RAG_FULL", "").strip().lower() not in {"1", "true", "yes", "on"}:
        limit = int(os.getenv("KEIBA_RAG_DEFAULT_LIMIT", "5000"))
        log.info("日次安全上限を適用: limit=%d（全件は KEIBA_RAG_FULL=1）", limit)

    # CSV 行数の確認
    log.info("CSV 読み込み中: %s", FEAT_CSV)
    try:
        import pandas as pd
    except ImportError:
        if dry_run:
            csv_rows = count_csv_rows(FEAT_CSV)
            log.info("  総行数: %d (csv フォールバック)", csv_rows)
            log.info("[DRY-RUN] pandas 未導入のため行数確認のみ実施しました。")
            return {"indexed": 0, "csv_rows": csv_rows, "dry_run": True}
        log.error("pandas インポート失敗: rag_index 本実行には pandas が必要です")
        return {"error": "pandas not installed"}

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
    if rebuild:
        before_count = store.count()
        store.clear()
        log.info("RAGStore rebuild: 既存 %d 件をクリア", before_count)
        existing_ids: set[str] = set()
    else:
        existing_ids = store.existing_ids()
        log.info("RAGStore 既存ID: %d 件", len(existing_ids))

    # 行ごとにエンベッディング追加
    indexed = 0
    skipped = 0
    skipped_existing = 0
    for row_index, row in df.iterrows():
        raw_horse_id = _clean_id_part(row.get("ketto_toroku_bango", row.get("horse_id", "")))
        doc_id = make_doc_id(int(row_index), row)
        if doc_id in existing_ids:
            skipped_existing += 1
            continue
        features = row.to_dict()
        metadata = {
            "race_code": str(row.get("race_code", "")),
            "race_date": str(row.get("race_date", "")),
            "bamei":     str(row.get("bamei", "")),
            "horse_id":  raw_horse_id,
            "row_index": int(row_index),
        }
        try:
            store.add(doc_id, features, metadata)
            existing_ids.add(doc_id)
            indexed += 1
        except Exception as exc:
            log.debug("add エラー (doc_id=%s): %s", doc_id, exc)
            skipped += 1

        if indexed % 1000 == 0 and indexed > 0:
            log.info("  インデックス構築中: %d 行完了", indexed)

    log.info(
        "RAG インデックス構築完了: indexed=%d skipped=%d existing=%d backend=%s",
        indexed, skipped, skipped_existing, BACKEND,
    )
    return {
        "indexed": indexed,
        "skipped": skipped,
        "skipped_existing": skipped_existing,
        "csv_rows": csv_rows,
        "backend": BACKEND,
    }


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, limit: int = 0, rebuild: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== rag_index ステージ開始 trace=%s ===", trace_id)

    result = build_rag_index(limit=limit, dry_run=dry_run, rebuild=rebuild)

    if "error" in result:
        log.error("rag_index 失敗: %s", result["error"])
        return 1

    log.info("rag_index 完了: %s", result)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG ベクトルインデックス構築")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--limit",    type=int, default=0, help="インデックス対象行数（0=全件）")
    parser.add_argument("--rebuild",  action="store_true", help="既存 RAGStore を消してから構築")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.limit, args.rebuild))
