"""
audit_logger.py — トレース・監査ログ ユーティリティ
=====================================================
全エージェントが共通で使用。
- trace_id / run_tag / agent_id / agent_version を付与
- 入出力の SHA-256 ハッシュを記録
- PostgreSQL audit_log テーブル + ローカルファイルに二重書き込み
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from .path_config import DATA_DIR
from pipeline.config import DB_URL

log = logging.getLogger(__name__)

AUDIT_DIR  = DATA_DIR / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def sha256_of(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class AuditLogger:
    """エージェント実行の監査ログを記録するクラス。"""

    def __init__(self, agent_id: str, agent_version: str):
        self.agent_id      = agent_id
        self.agent_version = agent_version
        self._log_file     = AUDIT_DIR / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

    # ------------------------------------------------------------------ #
    def log_event(
        self,
        *,
        trace_id: str,
        run_tag: str,
        event_type: str,           # "start" | "success" | "failure" | "quarantine"
        data_snapshot_id: str | None = None,
        input_hash:  str | None = None,
        output_hash: str | None = None,
        payload: dict | None = None,
        error: str | None = None,
    ) -> None:
        record = {
            "trace_id":        trace_id,
            "run_tag":         run_tag,
            "agent_id":        self.agent_id,
            "agent_version":   self.agent_version,
            "event_type":      event_type,
            "data_snapshot_id": data_snapshot_id,
            "input_hash":      input_hash,
            "output_hash":     output_hash,
            "error":           error,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }
        if payload:
            record["payload_summary"] = _truncate(payload)

        # ファイル書き込み（常時）
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # DB書き込み（接続できる場合のみ）
        self._write_to_db(record)

        level = logging.ERROR if event_type == "failure" else logging.INFO
        log.log(level, "[AUDIT] %s agent=%s run_tag=%s", event_type, self.agent_id, run_tag)

    # ------------------------------------------------------------------ #
    def _write_to_db(self, record: dict) -> None:
        try:
            import psycopg2  # type: ignore
        except ImportError:
            return

        sql = """
            INSERT INTO audit_log
                (trace_id, run_tag, agent_id, agent_version, event_type,
                 data_snapshot_id, input_hash, output_hash, error, timestamp)
            VALUES
                (%(trace_id)s, %(run_tag)s, %(agent_id)s, %(agent_version)s,
                 %(event_type)s, %(data_snapshot_id)s, %(input_hash)s,
                 %(output_hash)s, %(error)s, %(timestamp)s)
        """
        try:
            conn = psycopg2.connect(DB_URL)
            with conn, conn.cursor() as cur:
                cur.execute(sql, record)
        except Exception as exc:
            log.debug("audit DB 書き込みスキップ: %s", exc)


# ------------------------------------------------------------------ #
def _truncate(obj: Any, max_len: int = 200) -> Any:
    """ペイロードを安全に短縮する（ログ肥大防止）。"""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) <= max_len:
        return obj
    return s[:max_len] + "…"
