"""
train_agent.py — モデル学習エージェント
========================================
pipeline/model_train_03.py をラップし、学習完了後に
model_registry テーブルへモデル情報を登録する。

manifest: train-agent v1.0.0
  purpose : LGB+XGB+CB アンサンブル学習 → model_registry 登録
  inputs  : feature_set_id, data_snapshot_id
  outputs : model_id, model_version, metrics
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from .base_agent import BaseAgent, AgentMeta

log = logging.getLogger(__name__)

BASE_DIR  = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
MODEL_PKL = BASE_DIR / "model_v8.pkl"
DB_URL    = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")

MODEL_NAME    = "LGB+XGB+CatBoost Ensemble"
MODEL_VERSION = "v8"
PURPOSE       = "publishing"


class TrainAgent(BaseAgent):
    """
    役割: 特徴量 CSV → アンサンブルモデル学習 → model_registry 登録
    対応: manifest train-agent v1.0.0
    """

    agent_id      = "train-agent"
    agent_version = "1.0.0"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        feature_set_id      = payload.get("feature_set_id", "")
        data_snapshot_id    = payload.get("data_snapshot_id", meta.data_snapshot_id or "")
        skip_train          = payload.get("skip_train", False)

        # ─── 学習実行 ────────────────────────────────────────────
        if not skip_train:
            ok = self._run_training(meta)
            if not ok:
                raise RuntimeError("model_train_03.py が失敗しました")
        else:
            log.info("[train-agent] skip_train=True: 学習をスキップし既存 pkl を使用")

        # ─── pkl 読み込み → メトリクス取得 ──────────────────────
        metrics = self._load_metrics()

        # ─── SHA-256 計算 ────────────────────────────────────────
        model_sha = self._sha256_file(MODEL_PKL) if MODEL_PKL.exists() else ""

        # ─── model_id 生成（再学習ごとに一意） ───────────────────
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_id = f"model_v8_{ts}"

        # ─── model_registry へ登録 ────────────────────────────────
        self._register_to_db(
            model_id=model_id,
            sha256=model_sha,
            metrics=metrics,
            feature_set_id=feature_set_id,
            training_snapshot_id=data_snapshot_id,
        )

        return {
            "model_id":       model_id,
            "model_version":  MODEL_VERSION,
            "model_path":     str(MODEL_PKL),
            "sha256":         model_sha,
            "metrics":        metrics,
            "feature_set_id": feature_set_id,
            "trained_at":     datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #

    def _run_training(self, meta: AgentMeta) -> bool:
        """model_train_03.py を subprocess で実行。"""
        script = BASE_DIR / "pipeline" / "model_train_03.py"
        if not script.exists():
            log.warning("model_train_03.py が見つかりません: %s", script)
            return False

        log.info("[train-agent] 学習開始: %s", script)
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script),
             "--trace_id", meta.trace_id,
             "--run_tag",  meta.run_tag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,  # 最大 1 時間
        )
        if result.stdout:
            log.info(result.stdout[-2000:].strip())
        if result.stderr:
            log.warning(result.stderr[-1000:].strip())

        success = result.returncode == 0
        log.info("[train-agent] 学習%s (returncode=%d)", "完了" if success else "失敗", result.returncode)
        return success

    def _load_metrics(self) -> dict:
        """model_v8.pkl から metrics を読み込む。"""
        if not MODEL_PKL.exists():
            log.warning("model_v8.pkl が見つかりません。空メトリクスを返します。")
            return {}
        try:
            with open(MODEL_PKL, "rb") as f:
                model_data = pickle.load(f)
            return model_data.get("metrics", {})
        except Exception as exc:
            log.warning("pkl 読み込みエラー: %s", exc)
            return {}

    @staticmethod
    def _sha256_file(path: pathlib.Path) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except Exception:
            return ""
        return h.hexdigest()

    def _register_to_db(
        self,
        model_id: str,
        sha256: str,
        metrics: dict,
        feature_set_id: str,
        training_snapshot_id: str,
    ) -> None:
        """model_registry テーブルへ INSERT し、旧モデルを retired に更新する。"""
        try:
            import psycopg2
        except ImportError:
            log.warning("psycopg2 未インストール。model_registry への登録をスキップします。")
            return

        upsert_sql = """
            INSERT INTO model_registry
                (model_id, model_name, model_version, purpose, file_path,
                 sha256, feature_set_id, training_snapshot_id, metrics,
                 active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            ON CONFLICT (model_id) DO UPDATE SET
                sha256               = EXCLUDED.sha256,
                metrics              = EXCLUDED.metrics,
                feature_set_id       = EXCLUDED.feature_set_id,
                training_snapshot_id = EXCLUDED.training_snapshot_id,
                active               = TRUE,
                created_at           = EXCLUDED.created_at
        """
        retire_sql = """
            UPDATE model_registry
            SET active = FALSE, retired_at = now()
            WHERE purpose = %s AND model_id != %s AND active = TRUE
        """

        now = datetime.now(timezone.utc)
        try:
            conn = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute(upsert_sql, (
                    model_id, MODEL_NAME, MODEL_VERSION, PURPOSE,
                    str(MODEL_PKL), sha256,
                    feature_set_id, training_snapshot_id,
                    json.dumps(metrics, ensure_ascii=False),
                    now,
                ))
                # 旧モデルを退役
                cur.execute(retire_sql, (PURPOSE, model_id))
                retired = cur.rowcount
            conn.commit()
            conn.close()
            log.info("[train-agent] model_registry 登録: %s (旧モデル %d 件を retired)", model_id, retired)
        except Exception as exc:
            log.warning("[train-agent] model_registry 登録エラー: %s", exc)
