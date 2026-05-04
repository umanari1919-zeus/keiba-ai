"""
19_auto_learn.py  ─  うまなり地蔵AI / auto_learn ステージ
==========================================================
agents.AutoLearnAgent を呼び出し、直近のパフォーマンス履歴から
再学習の要否を判定する。週次 DAG の最終ステップとして実行されるが、
日次 monitor の auto_stop 後にも単独で起動できる。

実行方法:
  python pipeline_v2/19_auto_learn.py
  python pipeline_v2/19_auto_learn.py --dry-run
  python pipeline_v2/19_auto_learn.py --force     # 強制再学習
"""

from __future__ import annotations

import argparse
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
        logging.FileHandler(LOG_DIR / f"auto_learn_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(
    trace_id: str = "",
    run_tag: str = "",
    dry_run: bool = False,
    force: bool = False,
) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== auto_learn ステージ開始 trace=%s force=%s ===", trace_id, force)

    try:
        from agents.auto_learn_agent import AutoLearnAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = AutoLearnAgent(dry_run=dry_run).execute(meta, {"force": force})

    if result.ok:
        out = result.output
        if out.get("retrain_triggered"):
            log.info(
                "auto_learn: 再学習実行 model_id=%s reason=%s",
                out.get("model_id", "N/A"),
                out.get("reason", ""),
            )
        else:
            log.info("auto_learn: 再学習不要 reason=%s", out.get("reason", ""))
        return 0

    log.error("auto_learn 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--force",    action="store_true", help="強制再学習")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.force))
