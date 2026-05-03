"""
20_bankroll.py  ─  うまなり地蔵AI / bankroll ステージ
======================================================
agents.BankrollAgent を呼び出し、ドローダウン評価とポートフォリオ
リスク上限適用を行う。stop_betting=True の場合は終了コード 2 を返す。

実行方法:
  python pipeline_v2/20_bankroll.py
  python pipeline_v2/20_bankroll.py --dry-run
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
        logging.FileHandler(LOG_DIR / f"bankroll_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_adjusted_bets() -> list:
    for path in [
        DATA_DIR / f"adjusted_bets_{today}.json",
        DATA_DIR / f"finalized_bets_{today}.json",
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                bets = data.get("adjusted_bets", data.get("finalized_bets", []))
                log.info("ベット読み込み: %s (%d件)", path.name, len(bets))
                return bets
            except Exception as exc:
                log.warning("読み込みエラー: %s", exc)
    return []


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== bankroll ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.bankroll_agent import BankrollAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    adjusted_bets = _load_adjusted_bets()

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = BankrollAgent(dry_run=dry_run).execute(meta, {"adjusted_bets": adjusted_bets})

    if result.ok:
        out = result.output
        log.info(
            "bankroll 完了: bankroll=%.0f drawdown=%.1f%% multiplier=%.2f stop=%s bets=%d",
            out.get("bankroll", 0),
            out.get("drawdown", 0) * 100,
            out.get("multiplier", 1.0),
            out.get("stop_betting", False),
            len(out.get("adjusted_bets", [])),
        )

        save_path = DATA_DIR / f"bankroll_bets_{today}.json"
        save_path.write_text(
            json.dumps(
                {"adjusted_bets": out.get("adjusted_bets", []),
                 "bankroll_info": {k: out[k] for k in
                                   ("bankroll", "peak", "drawdown", "multiplier")
                                   if k in out}},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        log.info("資金管理済みベット保存: %s", save_path)

        if out.get("stop_betting", False):
            log.error("[STOP-BETTING] ドローダウン超過 → ベット停止")
            return 2  # オーケストレーターが STOP として扱う
        return 0

    log.error("bankroll 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
