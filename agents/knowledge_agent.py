"""
knowledge_agent.py — 知識ベース自動進化エージェント
=====================================================
pipeline/knowledge_curator_41.py の run_knowledge_curator() をラップし、
レース結果から抽出した知見を knowledge_base/LATEST.json に蓄積する。

manifest: knowledge-agent
  purpose: レース結果 → LLM 抽出 → イベントソーシング → EV boost
  inputs:  days (過去何日分を処理), force_snapshot
  outputs: insights_added, insights_verified, ev_boost_entries, version
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
KB_DIR   = BASE_DIR / "data" / "knowledge_base"


class KnowledgeAgent(BaseAgent):
    """
    役割: レース結果 → 知識ベース自動進化（Haiku 抽出 + イベントソーシング）
    対応: manifest knowledge-agent
    """

    agent_id      = "knowledge-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        days           = int(payload.get("days", 7))
        force_snapshot = bool(payload.get("force_snapshot", False))

        # ── subprocess で knowledge_curator_41.py を実行 ──────────
        result = self._run_curator(days=days, force_snapshot=force_snapshot, meta=meta)

        # ── LATEST.json から統計を収集 ─────────────────────────────
        stats = self._load_kb_stats()

        log.info(
            "[knowledge-agent] 完了: active=%d pending=%d deprecated=%d",
            stats.get("active_count", 0),
            stats.get("pending_count", 0),
            stats.get("deprecated_count", 0),
        )

        return {
            "curator_ok":       result,
            "days_processed":   days,
            "force_snapshot":   force_snapshot,
            **stats,
            "kb_dir":           str(KB_DIR),
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _run_curator(self, days: int, force_snapshot: bool, meta: AgentMeta) -> bool:
        script = BASE_DIR / "pipeline" / "knowledge_curator_41.py"
        if not script.exists():
            log.warning("knowledge_curator_41.py が見つかりません: %s", script)
            return False

        cmd = [
            sys.executable, "-X", "utf8", str(script),
            "--days",     str(days),
            "--trace_id", meta.trace_id,
            "--run_tag",  meta.run_tag,
        ]
        if force_snapshot:
            cmd.append("--force-snapshot")

        log.info("[knowledge-agent] 実行: %s (days=%d)", script.name, days)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            if proc.stdout:
                log.info(proc.stdout[-1500:].strip())
            if proc.stderr:
                log.debug(proc.stderr[-500:].strip())
            if proc.returncode != 0:
                log.warning("[knowledge-agent] returncode=%d", proc.returncode)
                return False
            return True
        except subprocess.TimeoutExpired:
            log.warning("[knowledge-agent] タイムアウト (600s)")
            return False
        except Exception as exc:
            log.warning("[knowledge-agent] 実行エラー: %s", exc)
            return False

    def _load_kb_stats(self) -> dict:
        """LATEST.json から知識ベース統計を返す。"""
        latest = KB_DIR / "LATEST.json"
        if not latest.exists():
            return {"active_count": 0, "pending_count": 0, "deprecated_count": 0,
                    "ev_boost_entries": 0, "version": "N/A"}
        try:
            import json
            data = json.loads(latest.read_text(encoding="utf-8"))
            active = pending = deprecated = ev_boost = 0
            for v in data.values():
                if not isinstance(v, dict):
                    continue
                st = v.get("status", "")
                if st == "active":
                    active += 1
                    if float(v.get("confidence", 0)) >= 0.50:
                        ev_boost += 1
                elif st == "pending":
                    pending += 1
                elif st in ("deprecated", "refuted"):
                    deprecated += 1

            # summary キーがある場合はそこから取得
            summary = data.get("knowledge_summary", {})
            ver     = data.get("version", summary.get("version", "present"))

            return {
                "active_count":    active,
                "pending_count":   pending,
                "deprecated_count": deprecated,
                "ev_boost_entries": ev_boost,
                "version":          str(ver),
            }
        except Exception as exc:
            log.debug("LATEST.json 読み込みエラー: %s", exc)
            return {"active_count": 0, "pending_count": 0, "deprecated_count": 0,
                    "ev_boost_entries": 0, "version": "error"}
