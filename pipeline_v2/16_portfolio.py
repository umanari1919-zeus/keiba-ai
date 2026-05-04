"""
16_portfolio.py  ─  うまなり地蔵AI / portfolio ステージ
=========================================================
agents.PortfolioAgent を呼び出し、TradingAgent の candidate_bets に
対して馬券種選択・多点買い配分最適化を実施する。

実行方法:
  python pipeline_v2/16_portfolio.py
  python pipeline_v2/16_portfolio.py --dry-run
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
        logging.FileHandler(LOG_DIR / f"portfolio_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_candidate_bets() -> list:
    """07_trade.py が保存したトレードログから candidate_bets を読み込む。"""
    for pattern in [
        DATA_DIR / f"trade_log_{today}.json",
        DATA_DIR / "trade_log_latest.json",
    ]:
        if pattern.exists():
            try:
                data = json.loads(pattern.read_text(encoding="utf-8"))
                bets = data.get("candidate_bets", data if isinstance(data, list) else [])
                log.info("candidate_bets 読み込み: %s (%d件)", pattern.name, len(bets))
                return bets
            except Exception as exc:
                log.warning("読み込みエラー: %s", exc)
    log.warning("candidate_bets ファイルが見つかりません")
    return []


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== portfolio ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.portfolio_agent import PortfolioAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    candidate_bets = _load_candidate_bets()

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = PortfolioAgent(dry_run=dry_run).execute(meta, {
        "candidate_bets": candidate_bets,
    })

    if result.ok:
        out     = result.output
        summary = out.get("summary", {})
        log.info(
            "portfolio 完了: finalized=%d total_amount=%d ratio=%.3f",
            len(out.get("finalized_bets", [])),
            summary.get("total_amount", 0),
            summary.get("portfolio_ratio", 0.0),
        )

        # finalized_bets を保存（roi_track が参照できるよう）
        save_path = DATA_DIR / f"finalized_bets_{today}.json"
        save_path.write_text(
            json.dumps(
                {"finalized_bets": out.get("finalized_bets", []), "summary": summary},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        log.info("確定ベット保存: %s", save_path)
        return 0

    log.error("portfolio 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
