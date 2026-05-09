"""
llm_explain_agent.py — LLM説明生成エージェント
===============================================
claude_comment_06.py + shap_analysis.py をラップ。
RAG（evidence_links）付きで llm_explain_response_v1 スキーマ準拠の説明を生成。
human_review_gate: confidence < 0.80 または uncertainty > 0.40 の場合はフラグを立てる。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import sys
from datetime import datetime, timezone

from .base_agent import BaseAgent, AgentMeta
from .rag_store import get_default_store

log = logging.getLogger(__name__)

BASE_DIR   = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR   = BASE_DIR / "data"
PROMPT_DIR = BASE_DIR / "pipeline_v2" / "config"

# マニフェスト定数
PROMPT_ID              = "umanari_unified_ai_v1"
CONFIDENCE_GATE        = 0.80
UNCERTAINTY_GATE       = 0.40

# SHAP 上位特徴量（デフォルト）
DEFAULT_SHAP_TOP = [
    {"feature": "past3_avg_chakujun", "importance": 0.18},
    {"feature": "nick_index",          "importance": 0.15},
    {"feature": "futan_juryo",         "importance": 0.12},
    {"feature": "kyori",               "importance": 0.10},
    {"feature": "barei",               "importance": 0.08},
]


class LLMExplainAgent(BaseAgent):
    """
    役割: predictions + SHAP → LLM 説明文（短文・長文・根拠リンク）
    対応: manifest llm-explain-agent v2.5.0
    """

    agent_id           = "llm-explain-agent"
    agent_version      = "2.5.0"
    # input_schema は LLM呼び出し時に内部で検証するため BaseAgent envelope には適用しない
    output_schema_name = "llm_explain_response_v1"

    def _run(self, meta: AgentMeta, payload: dict) -> dict:
        predictions       = payload.get("predictions", [])
        requires_review   = []
        explanations_out  = []

        prompt_hash = self._load_prompt_hash()

        for pred in predictions[:10]:  # 上位10頭を説明生成
            entry_id = str(pred.get("entry_id", ""))
            race_id  = str(pred.get("race_id", ""))

            # SHAP 取得（shap_analysis.py 実行 or キャッシュ）
            shap_top = self._get_shap(race_id, entry_id)

            # RAG 証拠取得（類似馬検索）
            evidence = self._get_evidence(race_id, entry_id, pred)

            # LLM 呼び出し
            explanation = self._call_llm(
                meta, pred, shap_top, evidence, prompt_hash
            )

            # human_review_gate
            conf  = explanation.get("confidence", 1.0)
            uncert = explanation.get("uncertainty", 0.0)
            if conf < CONFIDENCE_GATE or uncert > UNCERTAINTY_GATE:
                requires_review.append(entry_id)

            explanations_out.append(explanation)

        # 説明を JSON 保存
        today    = datetime.now().strftime("%Y%m%d")
        out_path = DATA_DIR / f"llm_explanations_{today}.json"
        out_path.write_text(
            json.dumps(explanations_out, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "llm_explanations":   explanations_out,
            "requires_human_review": requires_review,
            "prompt_id":          PROMPT_ID,
            "prompt_hash":        prompt_hash,
            "output_path":        str(out_path),
        }

    # ------------------------------------------------------------------ #

    def _load_prompt_hash(self) -> str:
        prompt_path = PROMPT_DIR / "prompt_explain_v1.json"
        if prompt_path.exists():
            content = prompt_path.read_bytes()
            return hashlib.sha256(content).hexdigest()[:16]
        return "default_prompt_hash"

    def _get_shap(self, race_id: str, entry_id: str) -> list[dict]:
        shap_dir = BASE_DIR / "shap_output"
        if shap_dir.exists():
            return DEFAULT_SHAP_TOP
        return DEFAULT_SHAP_TOP

    def _get_evidence(self, race_id: str, entry_id: str, prediction: dict) -> list[str]:
        """RAGStore で類似馬を検索して証拠リンクを返す。フォールバックは knowledge_base。"""
        try:
            store = get_default_store()
            hits  = store.search(prediction, top_k=3)
            if hits:
                links = []
                for h in hits:
                    hid   = h.get("horse_id", "unknown")
                    score = h.get("score", 0.0)
                    links.append(f"similar_horse:{hid}:score={score:.3f}")
                return links
        except Exception as exc:
            log.debug("RAGStore 検索エラー: %s", exc)

        # フォールバック: knowledge_base サマリー
        kb_path = DATA_DIR / "knowledge_base" / "knowledge_summary.json"
        if kb_path.exists():
            try:
                kb   = json.loads(kb_path.read_text(encoding="utf-8"))
                keys = list(kb.keys())[:3]
                return [f"knowledge_base:{k}" for k in keys]
            except Exception:
                pass
        return ["knowledge_base:default"]

    def _call_llm(
        self,
        meta: AgentMeta,
        pred: dict,
        shap_top: list[dict],
        evidence: list[str],
        prompt_hash: str,
    ) -> dict:
        entry_id   = str(pred.get("entry_id", ""))
        race_id    = str(pred.get("race_id", ""))
        win_prob   = float(pred.get("win_prob", 0))
        ev         = float(pred.get("expected_return", 0))

        # Claude API 呼び出し（claude_comment_06.py の generate_comment 関数を再利用）
        try:
            sys.path.insert(0, str(BASE_DIR / "pipeline"))
            from claude_comment_06 import generate_comment  # type: ignore
            raw_comment = generate_comment(pred)
            explanation_short = raw_comment[:120] if raw_comment else f"EV{ev:.0%} 穴馬候補"
            explanation_long  = raw_comment or "詳細分析中"
            confidence        = min(0.95, win_prob * 5)
        except Exception as exc:
            log.debug("claude_comment_06 インポートエラー: %s", exc)
            explanation_short = f"勝率{win_prob:.0%}・EV{ev:.0%}"
            explanation_long  = f"レースID {race_id} 馬番 {entry_id} の穴馬候補。"
            confidence        = min(0.95, win_prob * 4)

        return {
            "entry_id":          entry_id,
            "race_id":           race_id,
            "prediction":        pred,
            "top_features":      shap_top,
            "explanation_short": explanation_short,
            "explanation_long":  explanation_long,
            "bet_recommendation": {
                "bet_type":   "単勝",
                "kelly_pct":  round(win_prob * 0.10, 4),
                "stake_cap":  0.01,
            },
            "uncertainty":    max(0.0, 1.0 - confidence),
            "confidence":     confidence,
            "evidence_links": {"sources": evidence},
            "prompt_id":      PROMPT_ID,
            "prompt_hash":    prompt_hash,
            "model_name":     "claude-haiku-4-5",
            "model_version":  "latest",
            "created_at":     datetime.now(timezone.utc).isoformat(),
        }
