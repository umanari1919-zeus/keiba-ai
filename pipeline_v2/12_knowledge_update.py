"""
12_knowledge_update.py  ─  うまなり地蔵AI / knowledge_update ステージ
======================================================================
agents.KnowledgeAgent を呼び出し、knowledge_curator_41.py を実行して
知識ベースを更新・スナップショットを保存する。

実行方法:
  python pipeline_v2/12_knowledge_update.py
  python pipeline_v2/12_knowledge_update.py --dry-run
  python pipeline_v2/12_knowledge_update.py --days 14
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import uuid
from datetime import datetime

_BASE_DIR = pathlib.Path(r"D:\keiba_ai")
# BASE_DIR を必ず先頭に (worktree より優先)
if str(_BASE_DIR) in sys.path:
    sys.path.remove(str(_BASE_DIR))
sys.path.insert(0, str(_BASE_DIR))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"knowledge_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, days: int = 7) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== knowledge_update ステージ開始 trace=%s days=%d ===", trace_id, days)

    try:
        from agents.knowledge_agent import KnowledgeAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = KnowledgeAgent(dry_run=dry_run).execute(meta, {
        "days":           days,
        "force_snapshot": True,
    })

    if result.ok:
        out = result.output
        log.info(
            "knowledge_update 完了: active=%s pending=%s ev_boost=%s version=%s",
            out.get("active_count", 0),
            out.get("pending_count", 0),
            out.get("ev_boost_entries", 0),
            out.get("version", ""),
        )
        return 0

    log.error("knowledge_update 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--days",     type=int, default=7, help="処理対象日数")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.days))
