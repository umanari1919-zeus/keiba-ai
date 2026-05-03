"""
05_explain.py  ─  うまなり地蔵AI / explain ステージ
=====================================================
agents.LLMExplainAgent を呼び出し、batch_inference の予測結果に
LLM 説明文を付与して llm_explanations_{today}.json に保存する。
human_review_gate を超えたエントリーは requires_human_review リストに格納。

実行方法:
  python pipeline_v2/05_explain.py
  python pipeline_v2/05_explain.py --dry-run
  python pipeline_v2/05_explain.py --test      # Ollama接続確認（旧互換）
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
        logging.FileHandler(LOG_DIR / f"explain_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _load_predictions() -> list:
    """batch_inference の出力 CSV から当日の予測を読み込む。"""
    year = datetime.now().year
    for search in [DATA_DIR, BASE_DIR]:
        path = search / f"ev_analysis_{year}.csv"
        if path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
                preds = []
                for _, row in df.iterrows():
                    tansho = float(row.get("tansho_odds", row.get("odds_decimal", 100)))
                    odds   = tansho / 100 if tansho > 100 else tansho
                    preds.append({
                        "race_id":               str(row.get("race_code", row.get("race_id", ""))),
                        "entry_id":              str(row.get("umaban",    row.get("entry_id", ""))),
                        "win_prob":              float(row.get("win_probability",  0)),
                        "place_prob":            float(row.get("place_probability", 0)),
                        "expected_return":       float(row.get("expected_value",   row.get("ev", 0))),
                        "uncertainty":           float(row.get("uncertainty", 0.30)),
                        "odds":                  odds,
                        "model_agreement_count": int(row.get("model_agreement_count", 2)),
                    })
                log.info("予測読み込み: %s (%d件)", path.name, len(preds))
                return preds
            except Exception as exc:
                log.warning("予測読み込みエラー: %s", exc)
    log.warning("ev_analysis CSV が見つかりません")
    return []


def main(trace_id: str = "", run_tag: str = "", dry_run: bool = False) -> int:
    trace_id = trace_id or str(uuid.uuid4())
    run_tag  = run_tag  or f"run_{today}_{uuid.uuid4().hex[:8]}"
    log.info("=== explain ステージ開始 trace=%s dry_run=%s ===", trace_id, dry_run)

    try:
        from agents.llm_explain_agent import LLMExplainAgent
        from agents.base_agent import AgentMeta
    except ImportError as exc:
        log.error("agents インポート失敗: %s", exc)
        return 1

    predictions = _load_predictions()

    meta   = AgentMeta(trace_id=trace_id, run_tag=run_tag)
    result = LLMExplainAgent(dry_run=dry_run).execute(meta, {
        "predictions": predictions,
    })

    if result.ok:
        out          = result.output
        explanations = out.get("llm_explanations", out.get("explanations", []))
        requires_rev = out.get("requires_human_review", [])
        log.info(
            "explain 完了: explanations=%d requires_review=%d",
            len(explanations),
            len(requires_rev),
        )

        # llm_explanations_{today}.json に保存（PublishAgent が読み込む）
        save_path = DATA_DIR / f"llm_explanations_{today}.json"
        save_path.write_text(
            json.dumps(
                {"explanations": explanations, "requires_human_review": requires_rev},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        log.info("説明保存: %s", save_path)
        return 0

    log.error("explain 失敗: %s", result.error)
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--test",     action="store_true", help="Ollama接続テスト（旧互換）")
    parser.add_argument("--trace_id", default="")
    parser.add_argument("--run_tag",  default="")
    args = parser.parse_args()

    if args.test:
        # 旧 --test モードは dry-run として扱う
        log.info("--test フラグ: dry-run モードで explain を実行します")
        sys.exit(main(args.trace_id, args.run_tag, dry_run=True))

    sys.exit(main(args.trace_id, args.run_tag, args.dry_run))
