"""
social_bot_agent.py — SNS 一括配信エージェント
================================================
pipeline/social_bot_27.py の broadcast_picks() を BaseAgent 規約でラップする。
X / Discord / Telegram / LINE への同時配信を管理する。

manifest: social-bot-agent v1.0.0
  purpose : 予想結果を全 SNS チャネルへ一括配信
  inputs  : custom_text (str, optional)
  outputs : posted_channels, failed_channels, post_text, result_path
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta
from .path_config import BASE_DIR, DATA_DIR

log = logging.getLogger(__name__)

RESULT_FILE = DATA_DIR / "social_bot_result.json"


class SocialBotAgent(BaseAgent):
    """
    X・Discord・Telegram・LINE へ予想を一括配信する。
    dry_run=True 時は broadcast_picks を呼ばず空結果を返す。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="social-bot-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        if self.dry_run:
            log.info("dry_run=True → SNS 配信をスキップ")
            return self._empty_result("dry_run")

        custom_text = payload.get("custom_text")

        mod = self._load_module()
        if mod is None:
            return self._empty_result("social_bot_27 未実装")

        try:
            result_dict = mod.broadcast_picks(custom_text=custom_text)
            if not isinstance(result_dict, dict):
                result_dict = {}

            posted  = [ch for ch, ok in result_dict.items() if ok]
            failed  = [ch for ch, ok in result_dict.items() if not ok]
            post_text = payload.get("custom_text", "")

            log.info("SNS 配信完了: posted=%s failed=%s", posted, failed)

            output = {
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "trace_id":        meta.trace_id,
                "posted_channels": posted,
                "failed_channels": failed,
                "post_text":       post_text,
            }
            RESULT_FILE.parent.mkdir(exist_ok=True)
            RESULT_FILE.write_text(
                json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            return {
                "posted_channels": posted,
                "failed_channels": failed,
                "post_text":       post_text,
                "result_path":     str(RESULT_FILE),
            }

        except Exception as exc:
            log.warning("social_bot_27 実行失敗: %s", exc)
            return self._empty_result(str(exc))

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "social_bot_27.py"
        if not script.exists():
            log.warning("social_bot_27.py が存在しません")
            return None
        try:
            spec = importlib.util.spec_from_file_location("social_bot_27", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("social_bot_27 ロード失敗: %s", exc)
            return None

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            "posted_channels": [],
            "failed_channels": [],
            "post_text":       "",
            "result_path":     str(RESULT_FILE),
            "skipped_reason":  reason,
        }
