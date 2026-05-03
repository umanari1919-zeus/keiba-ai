"""
03_feature_gen.py  ─  うまなり地蔵AI / feature_gen ステージ
============================================================
agents.FeatureAgent を呼び出して全特徴量スクリプトを順次実行する。

実行方法:
  python pipeline_v2/03_feature_gen.py
  python pipeline_v2/03_feature_gen.py --dry-run
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
        logging.FileHandler(LOG_DIR / f"feature_gen_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== feature_gen ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.feature_agent import FeatureAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = FeatureAgent(dry_run=dry_run).execute(meta, {})

    if result.ok:
        out = result.output
        log.info(
            "feature_gen 完了: feature_set_id=%s scripts_ok=%s/%s",
            out.get("feature_set_id"),
            sum(1 for v in out.get("script_results", {}).values() if v == "ok"),
            len(out.get("script_results", {})),
        )
        return 0
    log.error("feature_gen 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
