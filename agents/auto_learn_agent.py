"""
auto_learn_agent.py — 自動再学習トリガーエージェント
====================================================
pipeline/auto_learn_13.py をラップし、直近の回収率トレンドから
再学習の要否を判定する。should_retrain() が True の場合、
TrainAgent を起動してモデルを更新する。

manifest: auto-learn-agent v1.0.0
  purpose : 精度劣化時の自動再学習トリガ
  inputs  : force (bool, default False)
  outputs : retrain_triggered (bool), reason (str), model_id (str or None)
"""

from __future__ import annotations

import importlib.util
import logging
import os
import pathlib
from typing import Any

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))


class AutoLearnAgent(BaseAgent):
    """
    パフォーマンス履歴を評価し、回収率が閾値を下回った場合に
    TrainAgent を呼び出してモデルを再学習する。

    dry_run=True の場合は should_retrain() の判定のみ行い、
    実際の再学習はスキップする。
    """

    def __init__(self, dry_run: bool = False) -> None:
        super().__init__(
            agent_id="auto-learn-agent",
            agent_version="1.0.0",
            dry_run=dry_run,
        )

    def _run(self, meta: AgentMeta, payload: dict) -> dict[str, Any]:
        force = payload.get("force", False)

        mod = self._load_module()
        if mod is None:
            log.warning("auto_learn_13.py なし → 再学習スキップ")
            return {"retrain_triggered": False, "reason": "auto_learn_13.py 未検出", "model_id": None}

        # ─── 再学習要否判定 ───────────────────────────────────────
        try:
            needs_retrain, reason = mod.should_retrain()
        except Exception as exc:
            log.warning("should_retrain 失敗: %s", exc)
            needs_retrain, reason = False, f"判定エラー: {exc}"

        log.info("再学習判定: needed=%s reason=%s", needs_retrain, reason)

        if not needs_retrain and not force:
            return {
                "retrain_triggered": False,
                "reason":            reason,
                "model_id":          None,
            }

        # ─── 再学習実行（dry_run=True ならスキップ） ─────────────
        if self.dry_run:
            log.info("[DRY-RUN] 再学習をスキップ: %s", reason)
            return {
                "retrain_triggered": False,
                "reason":            f"[dry-run] {reason}",
                "model_id":          None,
            }

        log.info("再学習開始: %s", reason)
        try:
            from .train_agent import TrainAgent
            train_result = TrainAgent(dry_run=False).execute(meta, {})
            if train_result.ok:
                model_id = train_result.output.get("model_id", "")
                log.info("再学習完了: model_id=%s", model_id)
                return {
                    "retrain_triggered": True,
                    "reason":            reason,
                    "model_id":          model_id,
                    "train_metrics":     train_result.output.get("metrics", {}),
                }
            else:
                log.error("TrainAgent 失敗: %s", train_result.error)
                return {
                    "retrain_triggered": True,
                    "reason":            reason,
                    "model_id":          None,
                    "train_error":       train_result.error,
                }
        except Exception as exc:
            log.error("TrainAgent 呼び出し例外: %s", exc)
            return {
                "retrain_triggered": True,
                "reason":            reason,
                "model_id":          None,
                "train_error":       str(exc),
            }

    def _load_module(self):
        script = BASE_DIR / "pipeline" / "auto_learn_13.py"
        if not script.exists():
            log.warning("auto_learn_13.py が見つかりません: %s", script)
            return None
        try:
            spec = importlib.util.spec_from_file_location("auto_learn_13", script)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as exc:
            log.warning("auto_learn_13 ロード失敗: %s", exc)
            return None
