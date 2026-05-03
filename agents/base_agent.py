"""
base_agent.py — 全エージェントの基底クラス
==========================================
マニフェスト要件:
  - trace_id / run_tag / agent_id / agent_version / input_hash / output_hash / timestamp を付与
  - 入出力スキーマ検証
  - 監査ログ（DB + ファイル）
  - 自動停止条件チェック
  - quarantine 記録
"""

from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .audit_logger import AuditLogger, sha256_of
from .schema_registry import SchemaRegistry

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# データ構造
# ------------------------------------------------------------------ #

@dataclass
class AgentMeta:
    """エージェント実行のトレースメタデータ。"""
    trace_id:         str = field(default_factory=lambda: str(uuid.uuid4()))
    run_tag:          str = ""
    data_snapshot_id: str = ""

    def __post_init__(self) -> None:
        if not self.run_tag:
            today = datetime.now().strftime("%Y%m%d")
            self.run_tag = f"run_{today}_{self.trace_id[:8]}"


@dataclass
class AgentResult:
    """エージェント実行結果。"""
    ok:          bool
    output:      dict = field(default_factory=dict)
    output_hash: str  = ""
    quarantined: bool = False
    error:       str  = ""

    def __post_init__(self) -> None:
        if self.output and not self.output_hash:
            self.output_hash = sha256_of(self.output)


# ------------------------------------------------------------------ #
# 基底クラス
# ------------------------------------------------------------------ #

class BaseAgent(abc.ABC):
    """
    全エージェント共通の実行ハーネス。

    サブクラスで実装するもの:
      - agent_id   (クラス変数)
      - agent_version (クラス変数)
      - _run(meta, payload) -> dict  ← 実ロジック
      - input_schema_name  (任意)
      - output_schema_name (任意)
    """

    agent_id:      str = "base-agent"
    agent_version: str = "0.0.0"

    input_schema_name:  str | None = None
    output_schema_name: str | None = None

    def __init__(
        self,
        *,
        agent_id:      str | None = None,
        agent_version: str | None = None,
        dry_run:       bool = False,
        strict_schema: bool = True,
    ):
        if agent_id is not None:
            self.__class__.agent_id      = agent_id
        if agent_version is not None:
            self.__class__.agent_version = agent_version
        self.dry_run   = dry_run
        self._auditor  = AuditLogger(self.agent_id, self.agent_version)
        self._registry = SchemaRegistry(strict=strict_schema)

    # ------------------------------------------------------------------ #
    # 公開 API
    # ------------------------------------------------------------------ #

    def execute(self, meta: AgentMeta, payload: dict) -> AgentResult:
        """
        エージェントを実行する。
        1. 入力スキーマ検証
        2. 監査ログ（start）
        3. _run() 呼び出し
        4. 出力スキーマ検証
        5. 監査ログ（success / failure）
        """
        input_hash = sha256_of(payload)

        # ── 入力検証 ─────────────────────────────────────────────
        if self.input_schema_name:
            envelope = self._make_envelope(meta, payload, input_hash)
            ok, errs = self._registry.validate(self.input_schema_name, envelope)
            if not ok:
                return self._fail(meta, input_hash, f"入力スキーマ検証失敗: {errs}")

        self._auditor.log_event(
            trace_id=meta.trace_id,
            run_tag=meta.run_tag,
            event_type="start",
            data_snapshot_id=meta.data_snapshot_id,
            input_hash=input_hash,
        )

        # ── 実行 ────────────────────────────────────────────────
        if self.dry_run:
            log.info("[DRY-RUN] %s - 実行をスキップ", self.agent_id)
            result = AgentResult(ok=True, output={"dry_run": True, "agent_id": self.agent_id})
        else:
            try:
                output = self._run(meta, payload)
                result = AgentResult(ok=True, output=output)
            except Exception as exc:
                return self._fail(meta, input_hash, str(exc))

        # ── 出力検証 ─────────────────────────────────────────────
        if self.output_schema_name and not self.dry_run:
            envelope = self._make_output_envelope(meta, result)
            ok, errs = self._registry.validate(self.output_schema_name, envelope)
            if not ok:
                log.warning("[%s] 出力スキーマ警告: %s", self.agent_id, errs)

        self._auditor.log_event(
            trace_id=meta.trace_id,
            run_tag=meta.run_tag,
            event_type="success",
            data_snapshot_id=meta.data_snapshot_id,
            input_hash=input_hash,
            output_hash=result.output_hash,
        )
        return result

    def quarantine(self, meta: AgentMeta, reason: str, payload: dict | None = None) -> None:
        """カランタイン（隔離）記録を残す。"""
        self._auditor.log_event(
            trace_id=meta.trace_id,
            run_tag=meta.run_tag,
            event_type="quarantine",
            data_snapshot_id=meta.data_snapshot_id,
            error=reason,
            payload=payload,
        )
        self._write_quarantine_db(meta, reason)
        log.warning("[%s] QUARANTINE: %s", self.agent_id, reason)

    # ------------------------------------------------------------------ #
    # サブクラスが実装
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        """実際の処理ロジック。成功時は output dict を返す。"""

    # ------------------------------------------------------------------ #
    # 内部ヘルパー
    # ------------------------------------------------------------------ #

    def _fail(self, meta: AgentMeta, input_hash: str, error: str) -> AgentResult:
        self._auditor.log_event(
            trace_id=meta.trace_id,
            run_tag=meta.run_tag,
            event_type="failure",
            data_snapshot_id=meta.data_snapshot_id,
            input_hash=input_hash,
            error=error,
        )
        log.error("[%s] FAILURE: %s", self.agent_id, error)
        return AgentResult(ok=False, error=error)

    def _make_envelope(self, meta: AgentMeta, payload: dict, input_hash: str) -> dict:
        return {
            "trace_id":         meta.trace_id,
            "run_tag":          meta.run_tag,
            "agent_id":         self.agent_id,
            "agent_version":    self.agent_version,
            "data_snapshot_id": meta.data_snapshot_id,
            "input_hash":       input_hash,
            "payload":          payload,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        }

    def _make_output_envelope(self, meta: AgentMeta, result: AgentResult) -> dict:
        return {
            "trace_id":         meta.trace_id,
            "run_tag":          meta.run_tag,
            "agent_id":         self.agent_id,
            "agent_version":    self.agent_version,
            "data_snapshot_id": meta.data_snapshot_id,
            "output_hash":      result.output_hash,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            **result.output,
        }

    def _write_quarantine_db(self, meta: AgentMeta, reason: str) -> None:
        try:
            import psycopg2
            import os
            db_url = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")
            sql = """
                INSERT INTO quarantine_records
                    (trace_id, run_tag, agent_id, data_snapshot_id, reason, created_at)
                VALUES (%(trace_id)s, %(run_tag)s, %(agent_id)s,
                        %(snap)s, %(reason)s, now())
            """
            conn = psycopg2.connect(db_url)
            with conn, conn.cursor() as cur:
                cur.execute(sql, {
                    "trace_id": meta.trace_id,
                    "run_tag":  meta.run_tag,
                    "agent_id": self.agent_id,
                    "snap":     meta.data_snapshot_id,
                    "reason":   reason,
                })
        except Exception:
            pass  # DB 不在でも処理継続（ファイルログに記録済み）
