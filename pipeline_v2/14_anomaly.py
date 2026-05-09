"""
14_anomaly.py  ─  うまなり地蔵AI / anomaly ステージ
=====================================================
agents.AnomalyAgent を呼び出し、
① モデル精度劣化 ② オッズ異常変動 ③ レースパターン不正兆候
を検知する。CRITICAL アラートが閾値以上の場合は終了コード 2 を返し、
オーケストレーターが auto_stop として扱えるようにする。

実行方法:
  python pipeline_v2/14_anomaly.py
  python pipeline_v2/14_anomaly.py --dry-run
  python pipeline_v2/14_anomaly.py --no-db    # DB アクセスなし（モデル劣化のみ）
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
        logging.FileHandler(LOG_DIR / f"anomaly_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main(
    trace_id: str = "",
    run_tag: str = "",
    dry_run: bool = False,
    use_db: bool = True,
) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== anomaly ステージ開始 trace=%s use_db=%s ===", trace_id, use_db)

    try:
        from agents.anomaly_agent import AnomalyAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = AnomalyAgent(dry_run=dry_run).execute(meta, {
        "use_db": use_db,
    })

    if result.ok:
        out      = result.output
        critical = out.get("critical_count", 0)
        warning  = out.get("warning_count",  0)
        total    = len(out.get("alerts", []))
        log.info(
            "anomaly 完了: 合計=%d CRITICAL=%d WARNING=%d",
            total, critical, warning,
        )
        if out.get("auto_stop", False):
            log.error("[AUTO-STOP] CRITICAL アラート多発 → パイプライン停止")
            return 2  # オーケストレーターが AUTO_STOP として認識するコード
        return 0

    log.error("anomaly 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--no-db",    action="store_true", help="DB アクセスなし（モデル劣化検知のみ）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, not args.no_db))
