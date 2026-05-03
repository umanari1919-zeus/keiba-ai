"""
17_race_select.py  ─  うまなり地蔵AI / race_select ステージ
============================================================
agents.RaceSelectorAgent を呼び出し、当日レースを Grade S/A/B/C に格付けして
推奨レースリストを data/race_ranking_{year}.json に保存する。

実行方法:
  python pipeline_v2/17_race_select.py
  python pipeline_v2/17_race_select.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import uuid
from datetime import datetime

_WORKTREE = pathlib.Path(r"D:\keiba_ai\.claude\worktrees\brave-kilby-e79e98")
if _WORKTREE.exists() and str(_WORKTREE) not in sys.path:
    sys.path.insert(0, str(_WORKTREE))

BASE_DIR = pathlib.Path("D:/keiba_ai")
DATA_DIR = BASE_DIR / "data"
BASE     = pathlib.Path(__file__).parent
LOG_DIR  = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
year  = datetime.now().year
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"race_select_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== race_select ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.race_selector_agent import RaceSelectorAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = RaceSelectorAgent(dry_run=dry_run).execute(meta, {"year": year})

    if result.ok:
        out = result.output
        gc  = out.get("grade_counts", {})
        log.info(
            "race_select 完了: 合計=%d S=%d A=%d B=%d C=%d 推奨=%d",
            len(out.get("ranked_races", [])),
            gc.get("S", 0), gc.get("A", 0), gc.get("B", 0), gc.get("C", 0),
            len(out.get("recommended", [])),
        )
        save_path = DATA_DIR / f"race_ranking_{year}.json"
        save_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("レースランキング保存: %s", save_path)
        return 0

    log.error("race_select 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
