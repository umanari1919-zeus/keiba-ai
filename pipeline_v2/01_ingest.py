"""
01_ingest.py  ─  うまなり地蔵AI / ingest ステージ
=================================================
agents.IngestAgent を呼び出してデータ取得・スナップショット登録を行う。

実行方法:
  python pipeline_v2/01_ingest.py
  python pipeline_v2/01_ingest.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
import uuid
from datetime import datetime

_WORKTREE = pathlib.Path(r"D:\keiba_ai\.claude\worktrees\brave-kilby-e79e98")
if _WORKTREE.exists() and str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"ingest_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== ingest ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.ingest_agent import IngestAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = IngestAgent(dry_run=dry_run).execute(meta, {})

    if result.ok:
        log.info("ingest 完了: snapshot_id=%s", result.output.get("data_snapshot_id"))
        return 0
    log.error("ingest 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
