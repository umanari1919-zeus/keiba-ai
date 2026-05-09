"""
06_publish.py  ─  うまなり地蔵AI / publish ステージ
====================================================
agents.PublishAgent を呼び出し、LLM 説明済みの予測を
X / note.com / LINE / Discord へ投稿する。
human_review が必要なエントリーは自動スキップ。

実行方法:
  python pipeline_v2/06_publish.py
  python pipeline_v2/06_publish.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
# プロジェクトルートを必ず先頭に (worktree より優先)
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR as CONFIG_BASE_DIR, DATA_DIR as CONFIG_DATA_DIR

BASE_DIR = pathlib.Path(CONFIG_BASE_DIR)
DATA_DIR = pathlib.Path(CONFIG_DATA_DIR)
BASE     = pathlib.Path(__file__).parent
LOG_DIR  = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"publish_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_llm_explanations() -> dict:
    """当日の llm_explanations_YYYYMMDD.json を読み込む。"""
    path = DATA_DIR / f"llm_explanations_{today}.json"
    if not path.exists():
        log.warning("llm_explanations_%s.json が見つかりません", today)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {"explanations": data, "requires_human_review": []}
        return data
    except Exception as exc:
        log.warning("説明ファイル読み込みエラー: %s", exc)
        return {}


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False, live: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== publish ステージ開始 trace=%s ===", trace_id)

    try:
        from agents.publish_agent import PublishAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    # 当日の LLM 説明を読み込む
    llm_data = _load_llm_explanations()
    explanations     = llm_data.get("explanations", llm_data.get("llm_explanations", []))
    requires_review  = llm_data.get("requires_human_review", [])
    publish_live = live or _env_truthy("KEIBA_PUBLISH_LIVE")
    if not publish_live and not dry_run:
        log.info("publish はドラフト生成モードです。実投稿は --live または KEIBA_PUBLISH_LIVE=1 が必要です。")

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = PublishAgent(dry_run=dry_run, publish_live=publish_live).execute(meta, {
        "llm_explanations":      explanations,
        "requires_human_review": requires_review,
    })

    if result.ok:
        out = result.output
        log.info(
            "publish 完了: published=%s skipped_review=%s",
            len(out.get("publications", [])),
            out.get("held_back_count", 0),
        )
        if out.get("draft_path"):
            log.info("publish draft 保存: %s", out["draft_path"])
        return 0
    log.error("publish 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--live",     action="store_true", help="実投稿を許可（デフォルトはドラフト生成のみ）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()
    sys.exit(main(args.trace_id, args.run_tag, args.dry_run, args.live))
