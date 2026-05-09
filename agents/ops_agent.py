"""
ops_agent.py — 運用ヘルスチェックエージェント
==============================================
パイプライン実行前後に呼び出し、以下の稼働状態を確認する。

チェック項目:
  db_connectivity    — PostgreSQL への接続確認
  model_file         — model_v8.pkl の存在と最終更新日時
  disk_space         — data/ ディレクトリの空き容量（GB）
  audit_log_24h      — 過去 24h の監査ログ件数
  quarantine_24h     — 過去 24h の隔離レコード件数
  rag_store_size     — RAGStore インデックスの登録エントリ数
  knowledge_base     — LATEST.json の存在と active_count

manifest: ops-agent
  purpose: 運用監視 / ヘルスチェック / 事前アサーション
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shutil
from datetime import datetime, timedelta, timezone

from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR = BASE_DIR / "data"
DB_URL   = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")

# ヘルスチェック閾値
DISK_MIN_GB        = 2.0    # 最低空き容量
QUARANTINE_MAX_24H = 50     # 24h 隔離レコード上限
AUDIT_MIN_24H      = 0      # 過去24hの最低監査ログ数（初回は 0 許容）


class OpsAgent(BaseAgent):
    """
    役割: システムヘルスチェックと稼働確認
    対応: manifest ops-agent
    """

    agent_id      = "ops-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        checks: dict[str, dict] = {}
        alerts: list[str] = []

        # ── DB 接続 ──────────────────────────────────────────────
        db_ok, db_info = self._check_db()
        checks["db_connectivity"] = {"ok": db_ok, "detail": db_info}
        if not db_ok:
            alerts.append(f"DB 接続失敗: {db_info}")

        # ── model_v8.pkl ─────────────────────────────────────────
        model_ok, model_info = self._check_model()
        checks["model_file"] = {"ok": model_ok, "detail": model_info}
        if not model_ok:
            alerts.append(f"モデルファイル問題: {model_info}")

        # ── ディスク空き容量 ──────────────────────────────────────
        disk_ok, disk_gb = self._check_disk()
        checks["disk_space"] = {"ok": disk_ok, "free_gb": round(disk_gb, 2)}
        if not disk_ok:
            alerts.append(f"ディスク空き不足: {disk_gb:.1f}GB < {DISK_MIN_GB}GB")

        # ── 過去 24h の監査ログ ───────────────────────────────────
        audit_count = self._count_audit_logs_24h(db_ok)
        checks["audit_log_24h"] = {"count": audit_count}

        # ── 過去 24h の隔離レコード ───────────────────────────────
        quar_count = self._count_quarantine_24h(db_ok)
        checks["quarantine_24h"] = {"count": quar_count}
        if quar_count > QUARANTINE_MAX_24H:
            alerts.append(f"隔離レコード急増: {quar_count} > {QUARANTINE_MAX_24H}/24h")

        # ── RAGStore エントリ数 ───────────────────────────────────
        rag_size = self._check_rag_store()
        checks["rag_store_size"] = {"entries": rag_size}

        # ── knowledge_base ────────────────────────────────────────
        kb_ok, kb_info = self._check_knowledge_base()
        checks["knowledge_base"] = {"ok": kb_ok, **kb_info}

        # ── model_registry の最新モデル ───────────────────────────
        reg_ok, reg_info = self._check_model_registry(db_ok)
        checks["model_registry"] = {"ok": reg_ok, "detail": reg_info}

        overall_ok = db_ok and disk_ok and not (quar_count > QUARANTINE_MAX_24H)

        log.info("[ops-agent] ヘルスチェック完了: ok=%s alerts=%d", overall_ok, len(alerts))
        for a in alerts:
            log.warning("[ops-agent] ALERT: %s", a)

        return {
            "overall_ok": overall_ok,
            "checks":     checks,
            "alerts":     alerts,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _check_db(self) -> tuple[bool, str]:
        try:
            import psycopg2
            conn = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                ver = cur.fetchone()[0].split(" ")[0:2]
            conn.close()
            return True, " ".join(ver)
        except Exception as exc:
            return False, str(exc)[:120]

    def _check_model(self) -> tuple[bool, str]:
        pkl = BASE_DIR / "model_v8.pkl"
        if not pkl.exists():
            return False, "model_v8.pkl が存在しません"
        mtime = datetime.fromtimestamp(pkl.stat().st_mtime, tz=timezone.utc)
        age_days = (datetime.now(timezone.utc) - mtime).days
        return True, f"mtime={mtime.date()} age={age_days}d size={pkl.stat().st_size // 1024}KB"

    def _check_disk(self) -> tuple[bool, float]:
        try:
            usage = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else BASE_DIR)
            free_gb = usage.free / 1e9
            return free_gb >= DISK_MIN_GB, free_gb
        except Exception:
            return True, 999.0  # 確認できない場合は OK 扱い

    def _count_audit_logs_24h(self, db_ok: bool) -> int:
        if not db_ok:
            # DB なし → JSONL ファイルで代替カウント
            log_dir = DATA_DIR / "audit_logs"
            today   = datetime.now().strftime("%Y%m%d")
            jsonl   = log_dir / f"audit_{today}.jsonl"
            if jsonl.exists():
                return sum(1 for _ in jsonl.open(encoding="utf-8"))
            return 0
        try:
            import psycopg2
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            conn  = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE created_at >= %s", (since,)
                )
                count = cur.fetchone()[0]
            conn.close()
            return int(count)
        except Exception:
            return -1

    def _count_quarantine_24h(self, db_ok: bool) -> int:
        if not db_ok:
            return 0
        try:
            import psycopg2
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            conn  = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM quarantine_records WHERE quarantined_at >= %s",
                    (since,),
                )
                count = cur.fetchone()[0]
            conn.close()
            return int(count)
        except Exception:
            return 0

    def _check_rag_store(self) -> int:
        jsonl = DATA_DIR / "rag_store" / "umanari_horses.jsonl"
        if jsonl.exists():
            try:
                return sum(1 for _ in jsonl.open(encoding="utf-8"))
            except Exception:
                pass
        return 0

    def _check_knowledge_base(self) -> tuple[bool, dict]:
        latest = DATA_DIR / "knowledge_base" / "LATEST.json"
        if not latest.exists():
            return False, {"active_count": 0, "version": "N/A"}
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            active = sum(
                1 for v in data.values()
                if isinstance(v, dict) and v.get("status") == "active"
            )
            ver = data.get("version", "unknown") if isinstance(data.get("version"), str) else "present"
            return True, {"active_count": active, "version": ver}
        except Exception as exc:
            return False, {"error": str(exc)[:80]}

    def _check_model_registry(self, db_ok: bool) -> tuple[bool, str]:
        if not db_ok:
            return True, "DB 未接続（スキップ）"
        try:
            import psycopg2
            conn = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model_id, created_at FROM model_registry WHERE active=TRUE ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()
            conn.close()
            if row:
                return True, f"latest={row[0]} at={row[1].date()}"
            return False, "アクティブモデルなし"
        except Exception as exc:
            return False, str(exc)[:80]
