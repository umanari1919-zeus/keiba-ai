"""
publish_agent.py — 発信エージェント
=====================================
social_bot_27.py / note_07.py / post_x_05.py をラップ。
human_review_gate を通過した説明のみ公開する。
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR = BASE_DIR / "data"


class PublishAgent(BaseAgent):
    """
    役割: 承認済み説明文 → X / note.com / LINE / Discord に配信
    対応: manifest publish-agent v1.0.0
    """

    agent_id      = "publish-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        explanations   = payload.get("llm_explanations", [])
        requires_review = set(payload.get("requires_human_review", []))

        # human_review_gate: フラグ付き説明はスキップ
        approved = [
            e for e in explanations
            if e.get("entry_id") not in requires_review
        ]
        held_back = len(explanations) - len(approved)

        publications = []
        drafts       = []

        for expl in approved:
            draft = self._create_draft(expl, meta)
            drafts.append(draft)

            if not self.dry_run:
                pub_result = self._publish_draft(draft, meta)
                publications.append(pub_result)

        return {
            "drafts":           drafts,
            "publications":     publications,
            "approved_count":   len(approved),
            "held_back_count":  held_back,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _create_draft(self, expl: dict, meta: AgentMeta) -> dict:
        entry_id = expl.get("entry_id", "")
        short    = expl.get("explanation_short", "")
        rec      = expl.get("bet_recommendation", {})
        conf     = expl.get("confidence", 0.0)

        text = (
            f"🎯 穴馬候補 #{entry_id}\n"
            f"{short}\n"
            f"Kelly推奨: {rec.get('kelly_pct', 0):.1%} | 信頼度: {conf:.0%}\n"
            f"#競馬予想 #うまなり地蔵AI"
        )
        return {
            "entry_id":    entry_id,
            "race_id":     expl.get("race_id", ""),
            "text":        text,
            "model_version": expl.get("model_version", ""),
            "prompt_hash": expl.get("prompt_hash", ""),
            "run_tag":     meta.run_tag,
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }

    def _publish_draft(self, draft: dict, meta: AgentMeta) -> dict:
        # social_bot_27.py を呼び出し
        script = BASE_DIR / "pipeline" / "social_bot_27.py"
        status = "skipped"

        if script.exists():
            today    = datetime.now().strftime("%Y%m%d")
            msg_path = DATA_DIR / f"draft_publish_{today}_{meta.trace_id[:8]}.json"
            msg_path.write_text(
                json.dumps(draft, ensure_ascii=False), encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(script),
                 "--draft_path", str(msg_path),
                 "--trace_id",   meta.trace_id],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(BASE_DIR),
            )
            status = "published" if result.returncode == 0 else "error"
            if result.stderr:
                log.warning("social_bot_27 stderr: %s", result.stderr[:200])

        return {**draft, "publish_status": status}
