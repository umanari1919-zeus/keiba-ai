"""
18_condition_adjust.py  ─  うまなり地蔵AI / condition_adjust ステージ
======================================================================
agents.ConditionAdjusterAgent を呼び出し、
競馬場×距離×季節の実績係数で finalized_bets のベット額を補正する。

実行方法:
  python pipeline_v2/18_condition_adjust.py
  python pipeline_v2/18_condition_adjust.py --dry-run
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"condition_adjust_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_finalized_bets() -> list:
    path = DATA_DIR / f"finalized_bets_{today}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            bets = data.get("finalized_bets", [])
            log.info("finalized_bets 読み込み: %d件", len(bets))
            return bets
        except Exception as exc:
            log.warning("読み込みエラー: %s", exc)
    log.warning("finalized_bets_%s.json が見つかりません", today)
    return []


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== condition_adjust ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.condition_adjuster_agent import ConditionAdjusterAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    finalized_bets = _load_finalized_bets()

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = ConditionAdjusterAgent(dry_run=dry_run).execute(meta, {
        "finalized_bets": finalized_bets,
    })

    if result.ok:
        out = result.output
        log.info(
            "condition_adjust 完了: adjusted=%d avg_coeff=%.3f",
            out.get("coeff_applied", 0),
            out.get("avg_coeff", 1.0),
        )
        save_path = DATA_DIR / f"adjusted_bets_{today}.json"
        save_path.write_text(
            json.dumps(
                {"adjusted_bets": out.get("adjusted_bets", []),
                 "avg_coeff": out.get("avg_coeff", 1.0)},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        log.info("調整済みベット保存: %s", save_path)
        return 0

    log.error("condition_adjust 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
