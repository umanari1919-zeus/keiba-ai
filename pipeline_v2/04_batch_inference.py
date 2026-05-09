"""
04_batch_inference.py  ─  うまなり地蔵AI / batch_inference ステージ
===================================================================
agents.BatchInferenceAgent を呼び出して予測・EV算出を行う。

実行方法:
  python pipeline_v2/04_batch_inference.py
  python pipeline_v2/04_batch_inference.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
import uuid
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
# プロジェクトルートを必ず先頭に (worktree より優先)
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

BASE    = pathlib.Path(__file__).parent
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"batch_inference_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== batch_inference ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.batch_inference_agent import BatchInferenceAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = BatchInferenceAgent(dry_run=dry_run).execute(meta, {})

    if result.ok:
        out = result.output
        log.info(
            "batch_inference 完了: candidates=%s ev_threshold=%s",
            out.get("candidate_count"), out.get("ev_threshold"),
        )
        return 0
    log.error("batch_inference 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
