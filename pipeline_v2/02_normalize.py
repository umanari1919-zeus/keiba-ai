"""
02_normalize.py  ─  うまなり地蔵AI / normalize ステージ
========================================================
agents.NormalizerAgent を呼び出してデータ正規化・品質チェックを行う。

実行方法:
  python pipeline_v2/02_normalize.py
  python pipeline_v2/02_normalize.py --dry-run
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
        logging.FileHandler(LOG_DIR / f"normalize_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== normalize ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.normalizer_agent import NormalizerAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = NormalizerAgent(dry_run=dry_run).execute(meta, {})

    if result.ok:
        out = result.output
        log.info(
            "normalize 完了: rows=%s mismatch_rate=%s quarantined=%s",
            out.get("rows_normalized"), out.get("mismatch_rate"), result.quarantined,
        )
        return 0
    log.error("normalize 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
