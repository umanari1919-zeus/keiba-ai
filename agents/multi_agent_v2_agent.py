"""
multi_agent_v2_agent.py — LangGraph マルチエージェント v2 ラッパー
==================================================================
pipeline/multi_agent_v2_28.py の run_pipeline() / run_multi_agent_v2() を
BaseAgent 規約でラップし、trace_id・監査ログ・dry_run に対応させる。

manifest: multi-agent-v2-agent v1.0.0
  purpose : 14エージェント協調予測（LangGraph）→ best_picks / publish_result
  inputs  : date_str (str, YYYYMMDD), year (int), mode ("pipeline"|"batch")
  outputs : best_picks, total_bets, published, final_bankroll, result_path
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR    = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
RESULT_FILE = BASE_DIR / "data" / "multi_agent_v2_result.json"


class MultiAgentV2Agent(BaseAgent):
    """
    14エージェント LangGraph パイプラインを BaseAgent 規約でラップする。
    dry_run=True 時は run_pipeline / run_multi_agent_v2 を呼ばず空結果を返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="multi-agent-v2-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        if self.dry_run:
            log.info("dry_run=True → multi_agent_v2_28 をスキップ")
            return self._empty_result("dry_run")

        mode     = payload.get("mode", "pipeline")
        date_str = payload.get("date_str") or datetime.now().strftime("%Y%m%d")
        year     = payload.get("year")

        mod = self._load_module()
        if mod is None:
            return self._empty_result("multi_agent_v2_28 未実装")

        try:
            if mode == "batch":
                state = mod.run_multi_agent_v2(year=year)
            else:
                state = mod.run_pipeline(date_str=date_str)

            best_picks    = state.get("best_picks",    [])
            final_bank    = float(state.get("bankroll", 0.0))
            published     = bool(state.get("published", False))
            total_bets    = len(best_picks)

            log.info(
                "マルチエージェント完了: picks=%d bankroll=%.0f published=%s",
                total_bets, final_bank, published,
            )

            output = {
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "trace_id":      meta.trace_id,
                "date_str":      date_str,
                "mode":          mode,
                "best_picks":    best_picks[:20],  # 上位20件のみ保存
                "total_bets":    total_bets,
                "published":     published,
                "final_bankroll": final_bank,
            }
            RESULT_FILE.parent.mkdir(exist_ok=True)
            RESULT_FILE.write_text(
                json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            return {
                "best_picks":     best_picks,
                "total_bets":     total_bets,
                "published":      published,
                "final_bankroll": final_bank,
                "result_path":    str(RESULT_FILE),
            }

        except Exception as exc:
            log.warning("multi_agent_v2_28 実行失敗: %s", exc)
            return self._empty_result(str(exc))

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "multi_agent_v2_28.py"
        if not script.exists():
            log.warning("multi_agent_v2_28.py が存在しません")
            return None
        try:
            spec = importlib.util.spec_from_file_location("multi_agent_v2_28", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("multi_agent_v2_28 ロード失敗: %s", exc)
            return None

    def _empty_result(self, reason: str) -> dict[str, Any]:
        log.info("MultiAgentV2Agent スキップ: %s", reason)
        return {
            "best_picks":     [],
            "total_bets":     0,
            "published":      False,
            "final_bankroll": 0.0,
            "result_path":    str(RESULT_FILE),
            "skipped_reason": reason,
        }
