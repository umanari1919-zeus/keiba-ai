"""
schema_registry.py — エージェント間 I/O スキーマ検証
=====================================================
マニフェスト umanari_unified_manifest_v1 の schema_registry セクションを
Python で実装。jsonschema を使った実行時バリデーション。
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# マニフェスト定義スキーマ（verbatim from manifest）
# ------------------------------------------------------------------ #
SCHEMAS: dict[str, dict] = {
    "ingest_to_normalize_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "data_snapshot_id", "input_hash", "payload", "timestamp",
        ],
        "properties": {
            "trace_id":         {"type": "string"},
            "run_tag":          {"type": "string"},
            "agent_id":         {"type": "string"},
            "agent_version":    {"type": "string"},
            "data_snapshot_id": {"type": "string"},
            "input_hash":       {"type": "string"},
            "payload":          {"type": "object"},
            "timestamp":        {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },

    "normalize_to_feature_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "data_snapshot_id", "normalized_rows", "timestamp",
        ],
        "properties": {
            "trace_id":         {"type": "string"},
            "run_tag":          {"type": "string"},
            "agent_id":         {"type": "string"},
            "agent_version":    {"type": "string"},
            "data_snapshot_id": {"type": "string"},
            "normalized_rows":  {"type": "array", "items": {"type": "object"}},
            "quarantine_flags": {"type": "array", "items": {"type": "object"}},
            "timestamp":        {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },

    "feature_to_train_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "feature_set_id", "feature_manifest", "timestamp",
        ],
        "properties": {
            "trace_id":           {"type": "string"},
            "run_tag":            {"type": "string"},
            "agent_id":           {"type": "string"},
            "agent_version":      {"type": "string"},
            "feature_set_id":     {"type": "string"},
            "feature_manifest":   {"type": "object"},
            "training_snapshot_id": {"type": "string"},
            "timestamp":          {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },

    "inference_output_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "data_snapshot_id", "predictions", "timestamp", "output_hash",
        ],
        "properties": {
            "trace_id":         {"type": "string"},
            "run_tag":          {"type": "string"},
            "agent_id":         {"type": "string"},
            "agent_version":    {"type": "string"},
            "data_snapshot_id": {"type": "string"},
            "predictions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "race_id", "entry_id", "win_prob", "place_prob",
                        "expected_return", "uncertainty",
                    ],
                    "properties": {
                        "race_id":               {"type": "string"},
                        "entry_id":              {"type": "string"},
                        "win_prob":              {"type": "number"},
                        "place_prob":            {"type": "number"},
                        "expected_return":       {"type": "number"},
                        "uncertainty":           {"type": "number"},
                        "model_agreement_count": {"type": "integer"},
                    },
                },
            },
            "output_hash": {"type": "string"},
            "timestamp":   {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },

    "llm_explain_request_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "prompt_id", "prompt_hash", "input", "timestamp",
        ],
        "properties": {
            "trace_id":      {"type": "string"},
            "run_tag":       {"type": "string"},
            "agent_id":      {"type": "string"},
            "agent_version": {"type": "string"},
            "prompt_id":     {"type": "string"},
            "prompt_hash":   {"type": "string"},
            "input": {
                "type": "object",
                "required": ["entry_id", "race_id", "prediction", "shap_top", "evidence"],
                "properties": {
                    "entry_id":   {"type": "string"},
                    "race_id":    {"type": "string"},
                    "prediction": {"type": "object"},
                    "shap_top":   {"type": "array", "items": {"type": "object"}},
                    "evidence":   {"type": "array", "items": {"type": "string"}},
                },
            },
            "timestamp": {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },

    "llm_explain_response_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "explanation", "prompt_id", "prompt_hash",
            "model_name", "model_version", "created_at", "output_hash",
        ],
        "properties": {
            "trace_id":      {"type": "string"},
            "run_tag":       {"type": "string"},
            "agent_id":      {"type": "string"},
            "agent_version": {"type": "string"},
            "explanation": {
                "type": "object",
                "required": [
                    "entry_id", "race_id", "prediction", "top_features",
                    "explanation_short", "explanation_long",
                    "bet_recommendation", "uncertainty", "confidence", "evidence_links",
                ],
                "properties": {
                    "entry_id":           {"type": "string"},
                    "race_id":            {"type": "string"},
                    "prediction":         {"type": "object"},
                    "top_features":       {"type": "array", "items": {"type": "object"}},
                    "explanation_short":  {"type": "string"},
                    "explanation_long":   {"type": "string"},
                    "bet_recommendation": {"type": "object"},
                    "uncertainty":        {"type": "number"},
                    "confidence":         {"type": "number"},
                    "evidence_links":     {"type": "object"},
                },
            },
            "prompt_id":     {"type": "string"},
            "prompt_hash":   {"type": "string"},
            "model_name":    {"type": "string"},
            "model_version": {"type": "string"},
            "created_at":    {"type": "string", "format": "date-time"},
            "output_hash":   {"type": "string"},
        },
        "additionalProperties": False,
    },

    "trade_execution_v1": {
        "type": "object",
        "required": [
            "trace_id", "run_tag", "agent_id", "agent_version",
            "candidate_bets", "authorization", "timestamp",
        ],
        "properties": {
            "trace_id":      {"type": "string"},
            "run_tag":       {"type": "string"},
            "agent_id":      {"type": "string"},
            "agent_version": {"type": "string"},
            "candidate_bets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "race_id", "entry_id", "bet_type", "odds",
                        "win_prob", "kelly_fraction", "stake_pct",
                    ],
                    "properties": {
                        "race_id":       {"type": "string"},
                        "entry_id":      {"type": "string"},
                        "bet_type":      {"type": "string"},
                        "odds":          {"type": "number"},
                        "win_prob":      {"type": "number"},
                        "kelly_fraction": {"type": "number"},
                        "stake_pct":     {"type": "number"},
                    },
                },
            },
            "simulate_slippage": {"type": "boolean"},
            "authorization":    {"type": "string"},
            "timestamp":        {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },
}


class SchemaRegistry:
    """マニフェスト定義のスキーマを使った実行時バリデーター。"""

    def __init__(self, strict: bool = True):
        self.strict = strict
        self._validator_available = self._check_jsonschema()

    @staticmethod
    def _check_jsonschema() -> bool:
        try:
            import jsonschema  # noqa: F401
            return True
        except ImportError:
            log.warning("jsonschema 未インストール。スキーマ検証をスキップします。pip install jsonschema")
            return False

    def validate(self, schema_name: str, data: Any) -> tuple[bool, list[str]]:
        """
        data を schema_name で検証する。
        Returns: (ok: bool, errors: list[str])
        """
        if not self._validator_available:
            return True, []

        schema = SCHEMAS.get(schema_name)
        if schema is None:
            msg = f"未知のスキーマ: {schema_name}"
            if self.strict:
                return False, [msg]
            log.warning(msg)
            return True, []

        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errors = [e.message for e in validator.iter_errors(data)]
        return (len(errors) == 0), errors

    def validate_or_raise(self, schema_name: str, data: Any) -> None:
        ok, errors = self.validate(schema_name, data)
        if not ok:
            raise ValueError(
                f"スキーマ検証失敗 [{schema_name}]:\n" + "\n".join(f"  - {e}" for e in errors)
            )

    def register_to_db(self) -> None:
        """全スキーマ定義を schema_registry テーブルに登録/更新する。"""
        try:
            import psycopg2
        except ImportError:
            log.warning("psycopg2 未インストール。DB登録をスキップします。")
            return

        import os
        db_url = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")
        sql = """
            INSERT INTO schema_registry (schema_name, schema_def, registered_at)
            VALUES (%(name)s, %(def)s, now())
            ON CONFLICT (schema_name) DO UPDATE
              SET schema_def = EXCLUDED.schema_def,
                  registered_at = now()
        """
        try:
            conn = psycopg2.connect(db_url)
            with conn, conn.cursor() as cur:
                for name, definition in SCHEMAS.items():
                    cur.execute(sql, {"name": name, "def": json.dumps(definition)})
            log.info("schema_registry: %d スキーマを DB に登録しました", len(SCHEMAS))
        except Exception as exc:
            log.warning("schema_registry DB 登録失敗: %s", exc)
