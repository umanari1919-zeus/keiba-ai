"""
ingest_agent.py — データ取得エージェント
=========================================
pipeline/data_fetch_01.py + odds_scraper_36.py をラップし、
data_snapshot_id と SHA-256 を付与する。
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime, timezone

from .base_agent import BaseAgent, AgentMeta, AgentResult
from .audit_logger import sha256_of
from .path_config import BASE_DIR, DATA_DIR, PIPELINE_DIR

log = logging.getLogger(__name__)

PIPELINE = PIPELINE_DIR


class IngestAgent(BaseAgent):
    """
    役割: JV-Link / DB / オッズスクレイピング → data_snapshot_id + raw_files
    対応: manifest ingest-agent v1.0.0
    """

    agent_id      = "ingest-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        today     = datetime.now().strftime("%Y%m%d")
        snap_id   = f"snap_{today}_{meta.trace_id[:8]}"
        raw_files = []

        # ── 1. DB → CSV (data_fetch_01.py) ────────────────────────
        csv_path  = DATA_DIR / "keiba_data.csv"
        fetch_ok  = self._run_script("pipeline/data_fetch_01.py", meta)
        if fetch_ok and csv_path.exists():
            raw_files.append(self._file_record(csv_path))

        # ── 2. オッズスナップショット (odds_scraper_36.py) ────────
        odds_path = DATA_DIR / f"odds_snapshot_{today}.json"
        odds_ok   = self._run_script("pipeline/odds_scraper_36.py", meta)
        if odds_ok and odds_path.exists():
            raw_files.append(self._file_record(odds_path))

        if not fetch_ok and not odds_ok:
            raise RuntimeError("ingest sources failed: pipeline/data_fetch_01.py, pipeline/odds_scraper_36.py")

        # ── 3. スナップショット登録 ───────────────────────────────
        self._register_snapshot(snap_id, raw_files, meta)

        return {
            "data_snapshot_id": snap_id,
            "raw_files":        raw_files,
            "fetch_ok":         fetch_ok,
            "odds_ok":          odds_ok,
        }

    # ------------------------------------------------------------------ #

    def _run_script(self, rel_path: str, meta: AgentMeta) -> bool:
        script = BASE_DIR / rel_path
        if not script.exists():
            log.warning("スクリプトが見つかりません: %s", script)
            return False

        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(BASE_DIR)}
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script),
             "--trace_id", meta.trace_id,
             "--run_tag",  meta.run_tag],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(BASE_DIR), env=env,
        )
        if result.stdout:
            log.info(result.stdout.rstrip())
        if result.returncode != 0:
            log.warning("スクリプト終了コード %d: %s\n%s",
                        result.returncode, rel_path, result.stderr[:500])
            return False
        return True

    @staticmethod
    def _file_record(path: pathlib.Path) -> dict:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": str(path), "sha256": sha, "size": path.stat().st_size}

    def _register_snapshot(self, snap_id: str, files: list, meta: AgentMeta) -> None:
        try:
            import psycopg2, json
            from pipeline.config import DB_URL
            sql = """
                INSERT INTO data_snapshots (snapshot_id, trace_id, run_tag, files, created_at)
                VALUES (%(snap_id)s, %(trace_id)s, %(run_tag)s, %(files)s, now())
                ON CONFLICT (snapshot_id) DO NOTHING
            """
            conn = psycopg2.connect(DB_URL)
            with conn, conn.cursor() as cur:
                cur.execute(sql, {
                    "snap_id":  snap_id,
                    "trace_id": meta.trace_id,
                    "run_tag":  meta.run_tag,
                    "files":    json.dumps(files),
                })
        except Exception as exc:
            log.debug("スナップショット DB 登録スキップ: %s", exc)
