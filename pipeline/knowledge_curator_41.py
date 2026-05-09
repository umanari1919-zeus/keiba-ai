"""
知識ベース自動進化システム (knowledge_curator_41)

レース結果をLLM(Haiku)で解析し、再現性のある統計パターンを
バージョン管理しながら蓄積。高確信度の知見を予測モデルに自動反映。

アーキテクチャ:
  レース結果 → Haiku抽出 → イベントソーシング → LATEST.json
                               ↓
                          Confirm/Refute（着順照合）
                               ↓
                          Feature feedback（特徴量・EVboost）
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from pipeline.config import BASE_DIR, DATA_DIR, DB_URL

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────

KB_DIR     = os.path.join(DATA_DIR, "knowledge_base")
SNAP_DIR   = os.path.join(KB_DIR, "snapshots")
EVT_DIR    = os.path.join(KB_DIR, "events")
LATEST     = os.path.join(KB_DIR, "LATEST.json")
CHANGELOG  = os.path.join(KB_DIR, "changelog.md")
CONF_LOG   = os.path.join(KB_DIR, "confidence_history.csv")
FEAT_FILE  = os.path.join(DATA_DIR, "keiba_data_features.csv")

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# 信頼度閾値
CONF_DEPRECATE = 0.20   # 廃止
CONF_SOFT      = 0.50   # EVboost開始
CONF_MEDIUM    = 0.70   # 特徴量追加
CONF_HARD      = 0.80   # ハードルール
MIN_SAMPLES    = 10     # 信頼判定の最小サンプル数

# カテゴリ定義
CATEGORIES = ["BLD", "JKY", "TRK", "MKT", "TRN", "SEA", "DBT", "SHG"]
CAT_LABELS = {
    "BLD": "血統パターン",
    "JKY": "騎手パターン",
    "TRK": "コース・展開特性",
    "MKT": "市場歪み",
    "TRN": "調教シグナル",
    "SEA": "季節パターン",
    "DBT": "新馬戦パターン",
    "SHG": "障害戦パターン",
}

# EV boost マッピング（confidence × この値 = boost額）
BOOST_SCALE = 0.08

_CONDITION_KEY_ALIASES = {
    "baba": "baba_jotai",
    "baba_jotai_code": "baba_jotai",
    "kishu": "kishu_code",
    "jockey": "kishu_code",
    "keibajo": "keibajo_code",
    "track": "track_code",
    "style": "kyakushitsu",
    "kyakushitsu_hantei": "kyakushitsu",
    "dist": "dist_cat",
}

_KYAKUSHITSU_ALIASES = {
    "逃げ": "1",
    "先行": "2",
    "差し": "3",
    "追込": "4",
    "nige": "1",
    "senko": "2",
    "sashi": "3",
    "oikomi": "4",
}

_KEY_LABELS = {
    "chichi": "父馬",
    "baba_jotai": "馬場",
    "keibajo_code": "競馬場",
    "kyakushitsu": "脚質",
    "dist_cat": "距離",
    "month": "月",
    "barei": "馬齢",
    "ninki": "人気",
    "ninki_min": "人気下限",
    "ninki_max": "人気上限",
    "weight_change": "体重変化",
    "kishu_code": "騎手",
    "track_code": "トラック",
    "is_debut": "新馬フラグ",
    "debut_score_min": "新馬スコア下限",
    "jockey_debut_win_rate_min": "新馬騎手下限",
    "trainer_debut_win_rate_min": "新馬調教師下限",
    "sire_debut_win_rate_min": "新馬父馬下限",
    "training_score_v2_min": "調教スコア下限",
    "is_shogai": "障害フラグ",
    "shogai_score_min": "障害スコア下限",
    "shogai_keiken_min": "障害経験下限",
    "jockey_shogai_win_rate_min": "障害騎手下限",
    "trainer_shogai_win_rate_min": "障害調教師下限",
}


# ─────────────────────────────────────────────────────────────
# ストレージ管理
# ─────────────────────────────────────────────────────────────

class KnowledgeStore:
    """イベントソーシング型知識ベース"""

    def __init__(self):
        for d in [KB_DIR, SNAP_DIR, EVT_DIR]:
            os.makedirs(d, exist_ok=True)

    # ── 状態の読み込み ──────────────────────────────────────

    def load_latest(self) -> Dict[str, Dict]:
        """LATEST.json から全知見を読み込む（id → item）"""
        if not os.path.exists(LATEST):
            return {}
        with open(LATEST, encoding="utf-8") as f:
            state = json.load(f)
        for item_id, item in state.items():
            _ensure_item_schema(item, item_id=item_id)
        return state

    def _today_event_path(self) -> str:
        return os.path.join(EVT_DIR, f"{datetime.now().strftime('%Y%m%d')}.jsonl")

    # ── イベント追記 ─────────────────────────────────────────

    def append_event(self, event: Dict):
        event["timestamp"] = datetime.now().isoformat()
        path = self._today_event_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ── LATEST 再構築 ────────────────────────────────────────

    def rebuild_latest(self) -> Dict[str, Dict]:
        """最新スナップショット + 全イベントを適用してLATESTを生成"""
        # 最新スナップを探す
        snaps = sorted(
            [f for f in os.listdir(SNAP_DIR) if f.endswith(".json")]
        )
        if snaps:
            with open(os.path.join(SNAP_DIR, snaps[-1]), encoding="utf-8") as f:
                state: Dict[str, Dict] = json.load(f)
            for item_id, item in state.items():
                _ensure_item_schema(item, item_id=item_id)
            snap_date = snaps[-1][2:10]  # vXXX_YYYYMMDD.json
        else:
            state = {}
            snap_date = "19000101"

        # スナップ以降のイベントを適用
        evt_files = sorted(
            [f for f in os.listdir(EVT_DIR) if f.endswith(".jsonl") and f[:8] >= snap_date]
        )
        for ef in evt_files:
            path = os.path.join(EVT_DIR, ef)
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                        state = _apply_event(state, evt)
                    except json.JSONDecodeError:
                        continue

        with open(LATEST, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        return state

    # ── 週次スナップ作成 ─────────────────────────────────────

    def create_snapshot(self, state: Dict[str, Dict]) -> str:
        existing = sorted(
            [f for f in os.listdir(SNAP_DIR) if f.endswith(".json")]
        )
        ver = len(existing) + 1
        fname = f"v{ver:03d}_{datetime.now().strftime('%Y%m%d')}.json"
        path = os.path.join(SNAP_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return fname

    # ── 信頼度履歴ログ ───────────────────────────────────────

    def log_confidence(self, item_id: str, confidence: float, samples: int):
        row = f"{item_id},{datetime.now().strftime('%Y-%m-%d')},{confidence:.4f},{samples}\n"
        header = "id,date,confidence,sample_count\n"
        if not os.path.exists(CONF_LOG):
            with open(CONF_LOG, "w", encoding="utf-8") as f:
                f.write(header)
        with open(CONF_LOG, "a", encoding="utf-8") as f:
            f.write(row)


def _apply_event(state: Dict[str, Dict], evt: Dict) -> Dict[str, Dict]:
    """単一イベントをステートに適用"""
    etype = evt.get("event")
    item_id = evt.get("id", "")

    if etype == "CREATE":
        if item_id not in state:
            state[item_id] = _ensure_item_schema(evt["data"], item_id=item_id)
    elif etype == "CONFIRM":
        if item_id in state:
            item = state[item_id]
            a, b = item.get("alpha", 2), item.get("beta", 2)
            a += 1
            item["alpha"], item["beta"] = a, b
            item["confidence"] = round(a / (a + b), 4)
            item["sample_count"] = item.get("sample_count", 0) + 1
            rc = evt.get("race_code")
            if rc and rc not in item.get("evidence_race_codes", []):
                item.setdefault("evidence_race_codes", []).append(rc)
            item["last_verified"] = evt.get("timestamp", "")[:10]
            _ensure_item_schema(item, item_id=item_id)
    elif etype == "REFUTE":
        if item_id in state:
            item = state[item_id]
            a, b = item.get("alpha", 2), item.get("beta", 2)
            b += 1
            item["alpha"], item["beta"] = a, b
            item["confidence"] = round(a / (a + b), 4)
            item["sample_count"] = item.get("sample_count", 0) + 1
            if item["confidence"] < CONF_DEPRECATE:
                item["status"] = "deprecated"
            _ensure_item_schema(item, item_id=item_id)
    elif etype == "DEPRECATE":
        if item_id in state:
            state[item_id]["status"] = "deprecated"
            state[item_id]["deprecate_reason"] = evt.get("reason", "")
    elif etype == "MERGE":
        id_from = evt.get("id_from")
        if id_from in state and item_id in state:
            src = state.pop(id_from)
            dst = state[item_id]
            dst["alpha"] = dst.get("alpha", 2) + src.get("alpha", 2) - 2
            dst["beta"]  = dst.get("beta",  2) + src.get("beta",  2) - 2
            dst["confidence"] = round(dst["alpha"] / (dst["alpha"] + dst["beta"]), 4)
            dst["sample_count"] = (dst.get("sample_count", 0) +
                                   src.get("sample_count", 0))
            dst["evidence_race_codes"] = list(set(
                dst.get("evidence_race_codes", []) +
                src.get("evidence_race_codes", [])
            ))
            _ensure_item_schema(dst, item_id=item_id)
    elif etype == "UPDATE_STATUS":
        if item_id in state:
            state[item_id]["status"] = evt.get("status", "active")

    return state


def _normalize_scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)) and pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if float(value).is_integer():
            return str(int(value))
        return f"{float(value):g}"
    return str(value).strip()


def _normalize_condition_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return _normalize_condition_dict(value)
    if isinstance(value, (list, tuple, set)):
        cleaned = [_normalize_condition_value(key, v) for v in value]
        cleaned = [v for v in cleaned if v not in ("", None, {}, [])]
        return sorted(dict.fromkeys(cleaned))

    key = _CONDITION_KEY_ALIASES.get(str(key).strip(), str(key).strip())
    text = _normalize_scalar_text(value)
    if not text:
        return ""

    if key == "kyakushitsu":
        return _KYAKUSHITSU_ALIASES.get(text, text)
    if key == "keibajo_code" and text.isdigit() and len(text) == 1:
        return text.zfill(2)
    if key in {"month", "barei", "ninki", "ninki_min", "ninki_max"} and text.isdigit():
        return str(int(text))
    return text


def _normalize_condition_dict(cond: Dict[str, Any]) -> Dict[str, Any]:
    if not cond:
        return {}
    normalized: Dict[str, Any] = {}
    for raw_key, raw_value in cond.items():
        key = _CONDITION_KEY_ALIASES.get(str(raw_key).strip(), str(raw_key).strip())
        value = _normalize_condition_value(key, raw_value)
        if value in ("", None, {}, []):
            continue
        normalized[key] = value
    return dict(sorted(normalized.items(), key=lambda kv: kv[0]))


def _condition_signature(category: str, cond: Dict[str, Any]) -> str:
    payload = {
        "category": category or "",
        "condition": _normalize_condition_dict(cond),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _condition_summary(cond: Dict[str, Any]) -> str:
    if not cond:
        return "条件なし"
    parts = []
    for key, value in _normalize_condition_dict(cond).items():
        label = _KEY_LABELS.get(key, key)
        if isinstance(value, list):
            text = "・".join(map(str, value))
        elif isinstance(value, dict):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            text = str(value)
        parts.append(f"{label}={text}")
    return " / ".join(parts)


def _ensure_item_schema(item: Dict[str, Any], item_id: str = "") -> Dict[str, Any]:
    item.setdefault("id", item_id)
    item["category"] = item.get("category", "MKT")
    item["status"] = item.get("status", "active")
    item["condition"] = _normalize_condition_dict(item.get("condition", {}))
    item["condition_norm"] = item["condition"]
    item["condition_key"] = _condition_signature(item["category"], item["condition"])
    item["condition_summary"] = _condition_summary(item["condition"])
    item.setdefault("claim", "")
    metrics = item.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {"estimated_lift": 1.0}
    metrics["estimated_lift"] = float(metrics.get("estimated_lift", 1.0) or 1.0)
    item["metrics"] = metrics
    item["confidence"] = float(item.get("confidence", 0.5) or 0.5)
    item["alpha"] = int(item.get("alpha", 2) or 2)
    item["beta"] = int(item.get("beta", 2) or 2)
    item["sample_count"] = int(item.get("sample_count", 0) or 0)
    item["evidence_race_codes"] = list(dict.fromkeys(item.get("evidence_race_codes", []) or []))
    item["version_created"] = item.get("version_created", "")
    item["version_modified"] = item.get("version_modified", item["version_created"])
    item["created_at"] = item.get("created_at", datetime.now().strftime("%Y-%m-%d"))
    item["last_verified"] = item.get("last_verified", item["created_at"])
    item.setdefault("source", "unknown")
    return item


def _derive_weight_change(row: Dict[str, Any]) -> str:
    fugo = _normalize_scalar_text(row.get("zogen_fugo", ""))
    sa = _normalize_scalar_text(row.get("zogen_sa", ""))
    if not sa.isdigit():
        return ""
    kg = int(sa)
    if fugo == "1":
        if kg >= 10:
            return "大幅増（+10kg以上）"
        if kg >= 2:
            return "微増（+2〜9kg）"
        return "同体重"
    if fugo == "2":
        if kg >= 10:
            return "大幅減（-10kg以上）"
        if kg >= 2:
            return "微減（-2〜9kg）"
        return "同体重"
    if fugo == "0":
        return "同体重"
    return ""


# ─────────────────────────────────────────────────────────────
# レース結果取得
# ─────────────────────────────────────────────────────────────

def fetch_recent_results(days: int = 7) -> List[Dict]:
    """直近N日分のレース結果をDBから取得"""
    try:
        engine = create_engine(DB_URL)
        since = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        sql = """
            SELECT
                u.race_code,
                u.bamei,
                u.kishu_code,
                u.chokyoshi_code,
                u.chakujun,
                u.tansho_odds,
                u.ninki,
                r.kyoso_joken_code_2sai,
                r.kyoso_shubetsu_code,
                r.keibajo_code,
                r.track_code,
                r.kyori,
                r.baba_jotai_code,
                r.tenki_code
            FROM umagoto_race_joho u
            LEFT JOIN race_shosai r ON u.race_code = r.race_code
            WHERE LEFT(u.race_code, 8) >= :since
            ORDER BY u.race_code, u.chakujun
            LIMIT 5000
        """
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params={"since": since})
        engine.dispose()

        results = []
        for rc, grp in df.groupby("race_code"):
            grp = grp.sort_values("chakujun")
            winner = grp[grp["chakujun"] == 1].iloc[0] if len(grp[grp["chakujun"] == 1]) > 0 else None
            if winner is None:
                continue
            results.append({
                "race_code":       str(rc),
                "n_horses":        len(grp),
                "is_debut":        1 if str(winner.get("kyoso_joken_code_2sai", "")) == "701" else 0,
                "is_shogai":       1 if str(winner.get("kyoso_shubetsu_code", "")) in ("18", "19") else 0,
                "keibajo_code":    str(winner.get("keibajo_code", "")),
                "track_code":      str(winner.get("track_code", "")),
                "kyori":           int(winner.get("kyori", 0) or 0),
                "baba_jotai":      str(winner.get("baba_jotai_code", "")),
                "tenki":           str(winner.get("tenki_code", "")),
                "winner_bamei":    str(winner.get("bamei", "")),
                "winner_odds":     float(winner.get("tansho_odds", 0) or 0) / 10,
                "winner_ninki":    int(winner.get("ninki", 0) or 0),
                "winner_kishu":    str(winner.get("kishu_code", "")),
                "winner_chokyoshi":str(winner.get("chokyoshi_code", "")),
                "top3": [
                    {
                        "bamei":  str(r["bamei"]),
                        "chakujun": int(r["chakujun"]),
                        "odds":   float(r.get("tansho_odds", 0) or 0) / 10,
                        "ninki":  int(r.get("ninki", 0) or 0),
                    }
                    for _, r in grp[grp["chakujun"] <= 3].iterrows()
                ],
            })
        print(f"  📊 直近{days}日 レース結果: {len(results)}R")
        return results
    except Exception as e:
        print(f"  ⚠️ DB取得エラー: {e} → CSVフォールバック")
        return _fetch_from_csv(days)


def _fetch_from_csv(days: int) -> List[Dict]:
    """DB不可時はsimulation CSVからフォールバック"""
    year = datetime.now().year
    path = os.path.join(BASE_DIR, f"simulation_{year}.csv")
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
    results = []
    for rc, grp in df.groupby("race_code"):
        winner = grp[grp["actual_chakujun"] == 1]
        if len(winner) == 0:
            continue
        w = winner.iloc[0]
        results.append({
            "race_code":    str(rc),
            "n_horses":     len(grp),
            "winner_bamei": str(w.get("bamei", "")),
            "winner_odds":  float(w.get("odds", 0)),
            "winner_ninki": 0,
            "top3": [],
        })
    return results[-200:]  # 直近200レース


# ─────────────────────────────────────────────────────────────
# LLM知見抽出
# ─────────────────────────────────────────────────────────────

_EXTRACT_SYSTEM = """あなたは競馬統計の専門家です。
レース結果から再現性のある統計パターンを抽出します。

【抽出ルール】
1. 最低3レース以上で観察されるパターンのみ
2. 「良馬場が有利」など常識的すぎる内容は除外
3. 数値で裏付けられる具体的な条件のみ
4. 条件は可能な限り厳密に（曖昧な条件は除外）

【カテゴリ】
BLD=血統, JKY=騎手×条件, TRK=コース特性, MKT=市場歪み,
TRN=調教シグナル, SEA=季節パターン, DBT=新馬戦, SHG=障害戦

必ず以下のJSONのみを返してください（説明文不要）:
{
  "insights": [
    {
      "category": "BLD",
      "condition": {"field": "value"},
      "claim": "簡潔な日本語説明（50文字以内）",
      "evidence_count": 5,
      "estimated_lift": 1.5
    }
  ]
}"""


def _call_ollama_curator(user_msg: str, system: str = "",
                         temperature: float = 0.3) -> Optional[str]:
    """Ollama でテキスト生成（知識抽出・JSON出力用、stream=False）。失敗時はNone。"""
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return None
        # 知識抽出・重複判定・JSON出力 → "json" プロファイル（deepseek-r1/phi4 優先）
        model = get_model_for_task("json")
        if not model:
            return None
        result = _generate(user_msg, system=system or _EXTRACT_SYSTEM,
                           model=model, temperature=temperature,
                           stream=False, task="json")
        return result or None
    except Exception as e:
        print(f"  [knowledge_curator/Ollama] スキップ: {e}")
        return None


def _call_haiku(user_msg: str, max_tokens: int = 500) -> Optional[str]:
    """Ollama優先 → Claude Haiku フォールバック。"""
    # 1. Ollama（無料・ローカル）
    result = _call_ollama_curator(user_msg, system=_EXTRACT_SYSTEM)
    if result:
        return result
    # 2. Claude Haiku API（有料）
    if not _ANTHROPIC_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=_EXTRACT_SYSTEM,
            messages=[{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": _EXTRACT_SYSTEM,
                    "cache_control": {"type": "ephemeral"}
                }, {
                    "type": "text",
                    "text": user_msg,
                }]
            }],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠️ Haiku API エラー: {e}")
        return None


def extract_insights_llm(races: List[Dict]) -> List[Dict]:
    """レース結果をLLMに渡して知見を抽出"""
    if not races:
        return []

    # 1チャンク = 50レース（コスト削減）
    chunk_size = 50
    all_insights = []

    for i in range(0, len(races), chunk_size):
        chunk = races[i:i + chunk_size]
        user_msg = f"""以下の{len(chunk)}レースの結果から統計パターンを抽出してください。

レース結果:
{json.dumps(chunk, ensure_ascii=False, indent=2)[:3000]}
"""
        resp = _call_haiku(user_msg)
        if not resp:
            continue

        try:
            m = re.search(r"\{.*\}", resp, re.DOTALL)
            if m:
                data = json.loads(m.group())
                insights = data.get("insights", [])
                all_insights.extend(insights)
                print(f"  📎 チャンク{i//chunk_size+1}: {len(insights)}件抽出")
        except json.JSONDecodeError:
            print(f"  ⚠️ JSON解析失敗: {resp[:100]}")

        time.sleep(0.5)  # レートリミット回避

    return all_insights


def extract_insights_template(races: List[Dict]) -> List[Dict]:
    """API未設定時のテンプレートベース抽出（ルールベース）"""
    insights = []

    # 穴馬（10番人気以下）の勝率分析
    upsets = [r for r in races if r.get("winner_ninki", 0) >= 10]
    if len(upsets) >= 3:
        avg_odds = sum(r.get("winner_odds", 0) for r in upsets) / len(upsets)
        insights.append({
            "category": "MKT",
            "condition": {"winner_ninki_min": 10},
            "claim": f"10番人気以下の勝利 {len(upsets)}件、平均オッズ{avg_odds:.0f}倍",
            "evidence_count": len(upsets),
            "estimated_lift": len(upsets) / max(len(races) * 0.05, 1),
        })

    # 単勝1倍台（断然人気）の信頼性
    heavies = [r for r in races if 0 < r.get("winner_odds", 99) <= 2.0]
    total_fav = [r for r in races if r.get("winner_ninki", 99) == 1]
    if total_fav:
        win_rate = sum(1 for r in total_fav if r.get("winner_ninki", 99) == 1
                      and r.get("winner_odds", 99) <= 2.0) / len(total_fav)
        insights.append({
            "category": "MKT",
            "condition": {"winner_ninki": 1},
            "claim": f"1番人気の信頼度 {win_rate:.0%}（サンプル{len(total_fav)}件）",
            "evidence_count": len(total_fav),
            "estimated_lift": win_rate / 0.08,
        })

    return insights


# ─────────────────────────────────────────────────────────────
# 重複チェック・マージ判定
# ─────────────────────────────────────────────────────────────

def _condition_overlap(c1: Dict, c2: Dict) -> float:
    """2条件のオーバーラップ率（0〜1）"""
    n1 = _normalize_condition_dict(c1)
    n2 = _normalize_condition_dict(c2)
    if not n1 or not n2:
        return 0.0
    keys1, keys2 = set(n1.keys()), set(n2.keys())
    common = keys1 & keys2
    if not common:
        return 0.0
    match = sum(1 for k in common if n1[k] == n2[k])
    return match / len(keys1 | keys2)


def deduplicate_and_assign(
    new_insights: List[Dict],
    existing: Dict[str, Dict],
) -> Tuple[List[Dict], List[Tuple[str, str]], List[Dict]]:
    """
    新規知見を既存と照合。
    Returns:
        creates  : 新規作成リスト
        confirms : (id, race_code) 確認リスト
        merges   : マージ候補リスト
    """
    creates, confirms, merges = [], [], []
    active = {k: v for k, v in existing.items() if v.get("status") == "active"}
    indexed: Dict[Tuple[str, str], str] = {}
    for eid, eitem in active.items():
        category = eitem.get("category", "")
        indexed[(category, _condition_signature(category, eitem.get("condition", {})))] = eid

    for ins in new_insights:
        best_id, best_score = None, 0.0
        ins = _ensure_item_schema(dict(ins))
        cond_new = ins.get("condition", {})
        cat_new  = ins.get("category", "")
        exact_id = indexed.get((cat_new, _condition_signature(cat_new, cond_new)))
        if exact_id:
            confirms.append((exact_id, "batch_extract"))
            continue

        for eid, eitem in active.items():
            if eitem.get("category") != cat_new:
                continue
            score = _condition_overlap(cond_new, eitem.get("condition", {}))
            if score > best_score:
                best_score, best_id = score, eid

        if best_score >= 0.7 and best_id:
            # 高重複 → 既存の証拠追加（CONFIRM相当）
            confirms.append((best_id, "batch_extract"))
        elif best_score >= 0.4 and best_id:
            # 部分重複 → マージ候補
            merges.append({"new": ins, "existing_id": best_id, "score": best_score})
        else:
            # 新規
            creates.append(ins)

    return creates, confirms, merges


def resolve_merge_with_llm(
    new_ins: Dict,
    existing_item: Dict,
    overlap_score: float,
) -> str:
    """
    部分重複（0.4〜0.7）の知見をLLMで判定（Ollama優先 → Claude Haiku → デフォルト）。
    Returns: "merge" | "create" | "skip"
    """
    _merge_system = (
        "競馬知見の重複判定エージェントです。"
        "2つの知見を比較し、'merge'/'create'/'skip' の1語のみを返してください。"
    )
    prompt = (
        "以下の2つの競馬知見を比較して、どう扱うべきか判定してください。\n\n"
        "【新規抽出された知見】\n"
        "カテゴリ: " + str(new_ins.get('category')) + "\n"
        "条件: " + json.dumps(new_ins.get('condition', {}), ensure_ascii=False) + "\n"
        "主張: " + str(new_ins.get('claim')) + "\n\n"
        "【既存の知見】\n"
        "カテゴリ: " + str(existing_item.get('category')) + "\n"
        "条件: " + json.dumps(existing_item.get('condition', {}), ensure_ascii=False) + "\n"
        "主張: " + str(existing_item.get('claim')) + "\n"
        "信頼度: " + str(round(existing_item.get('confidence', 0), 2)) +
        " サンプル数: " + str(existing_item.get('sample_count', 0)) + "\n\n"
        "オーバーラップスコア: " + str(round(overlap_score, 2)) + "\n\n"
        "以下のいずれか1語のみ返してください:\n"
        "- merge  : 同じ現象を指しており、既存に統合すべき\n"
        "- create : 異なる現象であり、新規知見として追加すべき\n"
        "- skip   : 既存の方が詳細・正確であり、新規は不要"
    )

    # 1. Ollama（無料）
    ollama_resp = _call_ollama_curator(prompt, system=_merge_system, temperature=0.1)
    if ollama_resp:
        v = ollama_resp.strip().lower().split()[0] if ollama_resp.strip() else ""
        if v in ("merge", "create", "skip"):
            return v

    # 2. Claude Haiku（有料フォールバック）
    if not _ANTHROPIC_KEY:
        return "create"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        verdict = msg.content[0].text.strip().lower()
        if verdict in ("merge", "create", "skip"):
            return verdict
        return "create"
    except Exception:
        return "create"


def _new_item(ins: Dict, version: str) -> Dict:
    """知見辞書から知識ベースエントリを生成"""
    item = {
        "id":                  "",  # 後でセット
        "category":            ins.get("category", "MKT"),
        "status":              "active",
        "condition":           ins.get("condition", {}),
        "claim":               ins.get("claim", ""),
        "metrics": {
            "estimated_lift":  ins.get("estimated_lift", 1.0),
        },
        "confidence":          0.50,  # 初期値（α=β=2 → 0.5）
        "alpha":               2,
        "beta":                2,
        "sample_count":        ins.get("evidence_count", 0),
        "evidence_race_codes": [],
        "version_created":     version,
        "version_modified":    version,
        "created_at":          datetime.now().strftime("%Y-%m-%d"),
        "last_verified":       datetime.now().strftime("%Y-%m-%d"),
        "source":              ins.get("source", "unknown"),
    }
    return _ensure_item_schema(item)


# ─────────────────────────────────────────────────────────────
# Confirm / Refute（着順照合）
# ─────────────────────────────────────────────────────────────

def verify_existing_items(
    store: KnowledgeStore,
    state: Dict[str, Dict],
    races: List[Dict],
):
    """
    既存知見を最新レース結果で検証（Confirm/Refute）
    条件マッチングはシンプルなルールベース
    """
    verified = 0
    for race in races:
        rc = race.get("race_code", "")
        winner_odds = race.get("winner_odds", 0)
        winner_ninki = race.get("winner_ninki", 99)
        winner_baba = str(race.get("baba_jotai", ""))
        winner_keibajo = str(race.get("keibajo_code", ""))
        winner_track = str(race.get("track_code", ""))
        winner_kyori = float(race.get("kyori", 0) or 0)
        winner_kishu = str(race.get("winner_kishu", ""))
        race_month = str(rc)[4:6].lstrip("0") if len(str(rc)) >= 6 else ""

        for item_id, item in state.items():
            if item.get("status") != "active":
                continue
            cond = _normalize_condition_dict(item.get("condition", {}))
            cat  = item.get("category", "")

            matched = False
            confirmed = False

            if cat == "MKT":
                if "winner_ninki_min" in cond:
                    thresh = cond["winner_ninki_min"]
                    if winner_ninki >= thresh:
                        matched = True
                        confirmed = True  # 穴が勝った = 知見確認
                elif "ninki" in cond and str(winner_ninki) == str(cond["ninki"]):
                    matched = True
                    confirmed = True
            elif cat == "BLD":
                if "baba_jotai" in cond and winner_baba == str(cond["baba_jotai"]):
                    matched = True
                    confirmed = True
            elif cat == "JKY":
                if "kishu_code" in cond and winner_kishu == str(cond["kishu_code"]):
                    matched = True
                    confirmed = True
            elif cat == "TRK":
                if "keibajo_code" in cond and winner_track == str(cond["keibajo_code"]):
                    matched = True
                    confirmed = True
                if "keibajo_code" in cond and winner_keibajo == str(cond["keibajo_code"]):
                    matched = True
                    confirmed = True
                if "dist_cat" in cond:
                    dist = "短距離" if winner_kyori <= 1400 else "中距離" if winner_kyori <= 2000 else "長距離"
                    if dist == str(cond["dist_cat"]):
                        matched = True
                        confirmed = True
            elif cat == "SEA":
                if "month" in cond and race_month == str(cond["month"]):
                    matched = True
                    confirmed = True
            elif cat == "TRN":
                if "weight_change" in cond and _derive_weight_change(race) == str(cond["weight_change"]):
                    matched = True
                    confirmed = True

            # 条件一致した場合のみ更新
            if matched:
                evt_type = "CONFIRM" if confirmed else "REFUTE"
                store.append_event({
                    "event":      evt_type,
                    "id":         item_id,
                    "race_code":  rc,
                })
                verified += 1

    print(f"  ✅ 既存知見 検証: {verified}件")


# ─────────────────────────────────────────────────────────────
# フィードバック: 高確信度知見 → 予測モデルへ反映
# ─────────────────────────────────────────────────────────────

def generate_ev_boost_map(state: Dict[str, Dict]) -> Dict[str, float]:
    """
    confidence >= CONF_SOFT の知見からEVboostマップを生成
    race_code単位ではなく条件ラベル → boost値
    """
    boost_map = {}
    for item_id, item in state.items():
        if item.get("status") != "active":
            continue
        conf = item.get("confidence", 0)
        if conf < CONF_SOFT:
            continue
        cat = item.get("category", "")
        label = f"{cat}_{item_id}"
        boost_map[label] = round((conf - CONF_SOFT) * BOOST_SCALE, 4)

    path = os.path.join(KB_DIR, "ev_boost_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(boost_map, f, ensure_ascii=False, indent=2)

    print(f"  💡 EVboostマップ: {len(boost_map)}件 → {path}")
    return boost_map


def apply_knowledge_to_features(state: Dict[str, Dict]):
    """
    confidence >= CONF_MEDIUM の知見を特徴量CSVに反映
    （新規フラグ列を追加）
    """
    if not os.path.exists(FEAT_FILE):
        return

    medium_items = [
        item for item in state.values()
        if item.get("status") == "active"
        and item.get("confidence", 0) >= CONF_MEDIUM
        and item.get("sample_count", 0) >= MIN_SAMPLES
    ]

    if not medium_items:
        print("  ℹ️ 特徴量追加対象の知見なし（confidence >= 0.70 かつ n >= 10）")
        return

    print(f"  🔧 特徴量追加対象: {len(medium_items)}件")
    df = pd.read_csv(FEAT_FILE, on_bad_lines="skip", low_memory=False)
    added = 0

    def _series_text(series: pd.Series) -> pd.Series:
        return series.fillna("").astype(str).str.strip()

    def _dist_series(frame: pd.DataFrame) -> pd.Series:
        if "kyori" not in frame.columns:
            return pd.Series([""] * len(frame), index=frame.index)
        ky = pd.to_numeric(frame["kyori"], errors="coerce").fillna(0)
        return pd.Series(np.where(
            ky <= 1400, "短距離",
            np.where(ky <= 2000, "中距離", "長距離")
        ), index=frame.index)

    for item in medium_items:
        item_id  = item.get("id", "")
        cat      = item.get("category", "")
        cond     = _normalize_condition_dict(item.get("condition", {}))
        col_name = f"kb_{cat.lower()}_{item_id.lower()}_flag"

        if col_name in df.columns:
            continue  # 既存列はスキップ

        flag_mask = pd.Series(True, index=df.index)
        used_condition = False

        # 条件別フラグ生成（ルールベース）
        if cat == "MKT" and "winner_ninki_min" in cond:
            pass  # レース後情報なので特徴量化できない

        elif cat == "BLD":
            if "chichi" in cond and "chichi" in df.columns:
                flag_mask &= _series_text(df["chichi"]) == str(cond["chichi"])
                used_condition = True
            if "baba_jotai" in cond and "baba_jotai" in df.columns:
                flag_mask &= _series_text(df["baba_jotai"]) == str(cond["baba_jotai"])
                used_condition = True
            if "keibajo_code" in cond and "keibajo_code" in df.columns:
                flag_mask &= _series_text(df["keibajo_code"]) == str(cond["keibajo_code"])
                used_condition = True
            if "dist_cat" in cond:
                flag_mask &= _dist_series(df) == str(cond["dist_cat"])
                used_condition = True

        elif cat == "JKY":
            if "kishu_code" in cond and "kishu_code" in df.columns:
                flag_mask &= _series_text(df["kishu_code"]) == str(cond["kishu_code"])
                used_condition = True
            if "keibajo_code" in cond and "keibajo_code" in df.columns:
                flag_mask &= _series_text(df["keibajo_code"]) == str(cond["keibajo_code"])
                used_condition = True
            if "dist_cat" in cond:
                flag_mask &= _dist_series(df) == str(cond["dist_cat"])
                used_condition = True

        elif cat == "TRK":
            if "keibajo_code" in cond and "keibajo_code" in df.columns:
                flag_mask &= _series_text(df["keibajo_code"]) == str(cond["keibajo_code"])
                used_condition = True
            if "kyakushitsu" in cond and "kyakushitsu_hantei" in df.columns:
                flag_mask &= _series_text(df["kyakushitsu_hantei"]) == str(cond["kyakushitsu"])
                used_condition = True
            if "dist_cat" in cond:
                flag_mask &= _dist_series(df) == str(cond["dist_cat"])
                used_condition = True
            if "weight_change" in cond:
                derived = df.apply(_derive_weight_change, axis=1)
                flag_mask &= derived == str(cond["weight_change"])
                used_condition = True

        elif cat == "SEA":
            if "month" in cond and "race_code" in df.columns:
                month_series = df["race_code"].astype(str).str[4:6].str.lstrip("0")
                flag_mask &= month_series == str(cond["month"])
                used_condition = True
            if "barei" in cond and "barei" in df.columns:
                flag_mask &= _series_text(df["barei"]) == str(cond["barei"])
                used_condition = True
            if "dist_cat" in cond:
                flag_mask &= _dist_series(df) == str(cond["dist_cat"])
                used_condition = True

        elif cat == "TRN":
            if "weight_change" in cond:
                derived = df.apply(_derive_weight_change, axis=1)
                flag_mask &= derived == str(cond["weight_change"])
                used_condition = True
            if "training_score_v2_min" in cond and "training_score_v2" in df.columns:
                flag_mask &= pd.to_numeric(df["training_score_v2"], errors="coerce").fillna(0).ge(float(cond["training_score_v2_min"]))
                used_condition = True
            if "ninki_max" in cond and "tansho_ninkijun" in df.columns:
                ninki = pd.to_numeric(df["tansho_ninkijun"], errors="coerce").fillna(99)
                flag_mask &= ninki <= int(cond["ninki_max"])
                used_condition = True

        elif cat in {"DBT", "SHG"}:
            if cat == "DBT":
                if "is_debut" in cond and "is_debut" in df.columns:
                    flag_mask &= pd.to_numeric(df["is_debut"], errors="coerce").fillna(0).eq(int(cond["is_debut"]))
                    used_condition = True
                if "debut_score_min" in cond and "debut_score" in df.columns:
                    flag_mask &= pd.to_numeric(df["debut_score"], errors="coerce").fillna(0).ge(float(cond["debut_score_min"]))
                    used_condition = True
                if "training_score_v2_min" in cond and "training_score_v2" in df.columns:
                    flag_mask &= pd.to_numeric(df["training_score_v2"], errors="coerce").fillna(0).ge(float(cond["training_score_v2_min"]))
                    used_condition = True
                if "jockey_debut_win_rate_min" in cond and "jockey_debut_win_rate" in df.columns:
                    flag_mask &= pd.to_numeric(df["jockey_debut_win_rate"], errors="coerce").fillna(0).ge(float(cond["jockey_debut_win_rate_min"]))
                    used_condition = True
                if "trainer_debut_win_rate_min" in cond and "trainer_debut_win_rate" in df.columns:
                    flag_mask &= pd.to_numeric(df["trainer_debut_win_rate"], errors="coerce").fillna(0).ge(float(cond["trainer_debut_win_rate_min"]))
                    used_condition = True
                if "sire_debut_win_rate_min" in cond and "sire_debut_win_rate" in df.columns:
                    flag_mask &= pd.to_numeric(df["sire_debut_win_rate"], errors="coerce").fillna(0).ge(float(cond["sire_debut_win_rate_min"]))
                    used_condition = True
            if cat == "SHG":
                if "is_shogai" in cond and "is_shogai" in df.columns:
                    flag_mask &= pd.to_numeric(df["is_shogai"], errors="coerce").fillna(0).eq(int(cond["is_shogai"]))
                    used_condition = True
                if "shogai_score_min" in cond and "shogai_score" in df.columns:
                    flag_mask &= pd.to_numeric(df["shogai_score"], errors="coerce").fillna(0).ge(float(cond["shogai_score_min"]))
                    used_condition = True
                if "shogai_keiken_min" in cond and "shogai_keiken" in df.columns:
                    flag_mask &= pd.to_numeric(df["shogai_keiken"], errors="coerce").fillna(0).ge(float(cond["shogai_keiken_min"]))
                    used_condition = True
                if "training_score_v2_min" in cond and "training_score_v2" in df.columns:
                    flag_mask &= pd.to_numeric(df["training_score_v2"], errors="coerce").fillna(0).ge(float(cond["training_score_v2_min"]))
                    used_condition = True
                if "jockey_shogai_win_rate_min" in cond and "jockey_shogai_win_rate" in df.columns:
                    flag_mask &= pd.to_numeric(df["jockey_shogai_win_rate"], errors="coerce").fillna(0).ge(float(cond["jockey_shogai_win_rate_min"]))
                    used_condition = True
                if "trainer_shogai_win_rate_min" in cond and "trainer_shogai_win_rate" in df.columns:
                    flag_mask &= pd.to_numeric(df["trainer_shogai_win_rate"], errors="coerce").fillna(0).ge(float(cond["trainer_shogai_win_rate_min"]))
                    used_condition = True

        flag_series = flag_mask.astype(int)
        if used_condition and flag_series.sum() > 0:
            df[col_name] = flag_series
            added += 1
            print(f"    + {col_name}: {flag_series.sum():,}行 にフラグ")

    if added > 0:
        df.to_csv(FEAT_FILE, index=False)
        print(f"  💾 特徴量更新: {added}列追加")


# ─────────────────────────────────────────────────────────────
# Changelog生成
# ─────────────────────────────────────────────────────────────

def update_changelog(
    created: int,
    confirmed: int,
    deprecated: int,
    state: Dict[str, Dict],
    version: str,
):
    active     = sum(1 for v in state.values() if v.get("status") == "active")
    high_conf  = sum(1 for v in state.values()
                     if v.get("status") == "active" and v.get("confidence", 0) >= CONF_HARD)
    entry = f"""
## {version} — {datetime.now().strftime('%Y-%m-%d %H:%M')}

| 指標 | 値 |
|------|-----|
| 新規作成 | {created}件 |
| 既存確認 | {confirmed}件 |
| 廃止 | {deprecated}件 |
| 総アクティブ知見 | {active}件 |
| 高確信度 (≥0.80) | {high_conf}件 |

"""
    if not os.path.exists(CHANGELOG):
        header = "# 知識ベース 変更履歴\n"
        with open(CHANGELOG, "w", encoding="utf-8") as f:
            f.write(header)

    with open(CHANGELOG, "a", encoding="utf-8") as f:
        f.write(entry)


def write_knowledge_summary(state: Dict[str, Dict], version: str) -> Dict[str, Any]:
    active = [v for v in state.values() if v.get("status") == "active"]
    deprecated = [v for v in state.values() if v.get("status") == "deprecated"]
    by_cat = defaultdict(list)
    for item in active:
        by_cat[item.get("category", "?")].append(item)

    def _top_items(items: List[Dict], n: int = 10) -> List[Dict[str, Any]]:
        out = []
        for item in sorted(items, key=lambda x: (x.get("confidence", 0), x.get("sample_count", 0)), reverse=True)[:n]:
            out.append({
                "id": item.get("id", ""),
                "category": item.get("category", ""),
                "confidence": round(float(item.get("confidence", 0)), 4),
                "sample_count": int(item.get("sample_count", 0)),
                "claim": item.get("claim", ""),
                "condition": item.get("condition", {}),
                "condition_summary": item.get("condition_summary", _condition_summary(item.get("condition", {}))),
                "lift": float(item.get("metrics", {}).get("estimated_lift", 1.0) or 1.0),
            })
        return out

    summary = {
        "version": version,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_count": len(active),
        "deprecated_count": len(deprecated),
        "high_conf_count": sum(1 for v in active if v.get("confidence", 0) >= CONF_HARD),
        "medium_conf_count": sum(1 for v in active if CONF_MEDIUM <= v.get("confidence", 0) < CONF_HARD),
        "low_conf_count": sum(1 for v in active if v.get("confidence", 0) < CONF_MEDIUM),
        "categories": {},
        "top_items": _top_items(active, 20),
        "recent_items": _top_items(
            [v for v in active if str(v.get("version_modified", "")) == str(version) or str(v.get("version_created", "")) == str(version)],
            20,
        ),
    }
    for cat, items in by_cat.items():
        confs = [float(v.get("confidence", 0)) for v in items]
        summary["categories"][cat] = {
            "label": CAT_LABELS.get(cat, cat),
            "count": len(items),
            "high_conf": sum(1 for v in items if v.get("confidence", 0) >= CONF_HARD),
            "avg_confidence": round(sum(confs) / max(len(confs), 1), 4),
        }

    path = os.path.join(KB_DIR, "knowledge_summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  [KB] knowledge summary: {path}")
    return summary


# ─────────────────────────────────────────────────────────────
# レポート出力
# ─────────────────────────────────────────────────────────────

def print_knowledge_report(state: Dict[str, Dict]):
    active = {k: v for k, v in state.items() if v.get("status") == "active"}
    by_cat = defaultdict(list)
    for item in active.values():
        by_cat[item.get("category", "?")].append(item)

    print(f"\n{'─'*60}")
    print(f"📚 知識ベース サマリー（アクティブ: {len(active)}件）")
    print(f"{'─'*60}")

    for cat in CATEGORIES:
        items = by_cat.get(cat, [])
        if not items:
            continue
        high = [i for i in items if i.get("confidence", 0) >= CONF_HARD]
        print(f"  [{cat}] {CAT_LABELS[cat]}: {len(items)}件"
              f"（高確信度: {len(high)}件）")
        for item in sorted(items, key=lambda x: (x.get("confidence", 0), x.get("sample_count", 0)), reverse=True)[:3]:
            conf = item.get("confidence", 0)
            n    = item.get("sample_count", 0)
            bar  = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            print(f"    {bar} {conf:.2f} n={n:3d}  {item.get('condition_summary', _condition_summary(item.get('condition', {})))[:40]}")

    deprecated = sum(1 for v in state.values() if v.get("status") == "deprecated")
    print(f"\n  廃止済み: {deprecated}件")
    print(f"{'─'*60}")


# ─────────────────────────────────────────────────────────────
# メインエントリ
# ─────────────────────────────────────────────────────────────

def run_knowledge_curator(days: int = 7, force_snapshot: bool = False):
    """
    Args:
        days: 分析対象の直近日数
        force_snapshot: True なら強制的に週次スナップを作成
    """
    print("\n【知識ベース自動進化システム knowledge_curator_41】")
    t0 = time.time()

    store = KnowledgeStore()

    # ── 現在状態の読み込み ──
    print("  📂 LATEST.json 読み込み...")
    state = store.rebuild_latest()
    print(f"     既存知見: {len(state)}件（active={sum(1 for v in state.values() if v.get('status')=='active')}件）")

    # バージョン番号を決定
    snaps = sorted([f for f in os.listdir(SNAP_DIR) if f.endswith(".json")])
    version = f"v{len(snaps)+1:03d}"

    # ── レース結果取得 ──
    print(f"  🏇 直近{days}日のレース結果を取得...")
    races = fetch_recent_results(days)
    if not races:
        print("  ⚠️ レース結果なし → 終了")
        return state

    # ── 既存知見の Confirm/Refute ──
    print("  🔍 既存知見の検証...")
    verify_existing_items(store, state, races)

    # ── 新規知見の抽出 ──
    print(f"  🤖 知見抽出 {'（Haiku API）' if _ANTHROPIC_KEY else '（テンプレートモード）'}...")
    if _ANTHROPIC_KEY:
        new_insights = extract_insights_llm(races)
    else:
        new_insights = extract_insights_template(races)
    print(f"     抽出候補: {len(new_insights)}件")

    # ── 重複チェック・分類 ──
    creates, confirms, merges = deduplicate_and_assign(new_insights, state)
    print(f"     新規: {len(creates)}件 / 重複確認: {len(confirms)}件 / マージ候補: {len(merges)}件")

    # ── CREATE イベント発行 ──
    created_count = 0
    for ins in creates:
        new_id = f"{ins.get('category','XX')}-{str(uuid.uuid4())[:6].upper()}"
        item   = _new_item(ins, version)
        item["id"] = new_id
        store.append_event({"event": "CREATE", "id": new_id, "data": item})
        created_count += 1

    # ── CONFIRM イベント発行 ──
    for item_id, rc in confirms:
        store.append_event({"event": "CONFIRM", "id": item_id, "race_code": rc})

    # ── マージイベント発行（LLM判断 0.4〜0.7、ルール判断 0.7以上） ──
    for m in merges:
        existing_item = state.get(m["existing_id"], {})
        if m["score"] >= 0.7:
            verdict = "merge"  # 高重複はルールで直接マージ
        else:
            # 部分重複(0.4〜0.7) → LLMに判断委任
            verdict = resolve_merge_with_llm(m["new"], existing_item, m["score"])
            print(f"    🤖 マージ判定 [{m['existing_id']}]: {verdict} (overlap={m['score']:.2f})")

        if verdict == "merge":
            store.append_event({
                "event":   "MERGE",
                "id":      m["existing_id"],
                "id_from": f"TEMP_{uuid.uuid4().hex[:6]}",
                "reason":  f"overlap={m['score']:.2f}",
            })
        elif verdict == "create":
            new_id = f"{m['new'].get('category','XX')}-{str(uuid.uuid4())[:6].upper()}"
            item   = _new_item(m["new"], version)
            item["id"] = new_id
            store.append_event({"event": "CREATE", "id": new_id, "data": item})
            created_count += 1
        # skip は何もしない

    # ── LATEST 再構築 ──
    print("  🔄 LATEST.json 再構築...")
    state = store.rebuild_latest()

    # ── 廃止チェック ──
    deprecated_count = 0
    for item_id, item in state.items():
        if item.get("status") == "active":
            conf = item.get("confidence", 0.5)
            n    = item.get("sample_count", 0)
            if n >= MIN_SAMPLES and conf < CONF_DEPRECATE:
                store.append_event({
                    "event":  "DEPRECATE",
                    "id":     item_id,
                    "reason": f"confidence={conf:.3f} < {CONF_DEPRECATE}",
                })
                deprecated_count += 1

    # 廃止後に最終再構築
    if deprecated_count > 0:
        state = store.rebuild_latest()

    # ── 信頼度履歴ログ ──
    for item_id, item in state.items():
        if item.get("status") == "active":
            store.log_confidence(
                item_id,
                item.get("confidence", 0),
                item.get("sample_count", 0),
            )

    # ── フィードバック ──
    print("  📡 予測モデルへフィードバック...")
    generate_ev_boost_map(state)
    apply_knowledge_to_features(state)

    # ── スナップショット（週次 or 強制） ──
    weekday = datetime.now().weekday()
    if force_snapshot or weekday == 0:  # 月曜日
        snap_name = store.create_snapshot(state)
        print(f"  📸 スナップショット作成: {snap_name}")

    # ── Changelog更新 ──
    update_changelog(created_count, len(confirms), deprecated_count, state, version)

    # ── 知識サマリー更新 ──
    write_knowledge_summary(state, version)

    # ── レポート ──
    print_knowledge_report(state)

    elapsed = time.time() - t0
    print(f"\n  ✅ 完了 ({elapsed:.1f}秒)")
    print(f"  📁 知識ベース: {KB_DIR}")
    print(f"  📋 変更履歴: {CHANGELOG}")

    return state


# ─────────────────────────────────────────────────────────────
# EV boost を EVAgent から参照するユーティリティ
# ─────────────────────────────────────────────────────────────

def load_ev_boost_for_race(race_code: str, df_row: pd.Series) -> float:
    """
    EVAgent から呼び出す: 1馬についてEVboostを計算して返す。
    race_code と 特徴量行を受け取り、マッチする知見のboostを合計。
    """
    boost_path = os.path.join(KB_DIR, "ev_boost_map.json")
    latest_path = LATEST

    if not os.path.exists(boost_path) or not os.path.exists(latest_path):
        return 0.0

    with open(boost_path, encoding="utf-8") as f:
        boost_map = json.load(f)
    with open(latest_path, encoding="utf-8") as f:
        state = json.load(f)

    total_boost = 0.0
    for label, boost_val in boost_map.items():
        # label = "BLD_BLD-XXXXXX"
        parts = label.split("_", 1)
        if len(parts) < 2:
            continue
        cat, item_id = parts[0], parts[1]
        item = state.get(item_id, {})
        if not item or item.get("status") != "active":
            continue

        cond = item.get("condition", {})
        matched = _match_condition(cond, cat, df_row)
        if matched:
            total_boost += boost_val

    return min(total_boost, 0.15)  # 上限15%


def _match_condition(cond: Dict, cat: str, row: pd.Series) -> bool:
    """特徴量行が知見の条件に合致するか判定"""
    cond = _normalize_condition_dict(cond)
    if cat == "BLD":
        if "chichi" in cond:
            if str(row.get("chichi", "")) != str(cond["chichi"]):
                return False
        if "baba_jotai" in cond:
            if str(row.get("baba_jotai", row.get("baba_jotai_code", ""))) != str(cond["baba_jotai"]):
                return False
        if "keibajo_code" in cond and str(row.get("keibajo_code", "")) != str(cond["keibajo_code"]):
            return False
        if "dist_cat" in cond:
            kyori = float(row.get("kyori", 0) or 0)
            dist = "短距離" if kyori <= 1400 else "中距離" if kyori <= 2000 else "長距離"
            if dist != str(cond["dist_cat"]):
                return False
        return True
    elif cat == "JKY":
        if "kishu_code" in cond and str(row.get("kishu_code", "")) != str(cond["kishu_code"]):
            return False
        if "keibajo_code" in cond and str(row.get("keibajo_code", "")) != str(cond["keibajo_code"]):
            return False
        if "dist_cat" in cond:
            kyori = float(row.get("kyori", 0) or 0)
            dist = "短距離" if kyori <= 1400 else "中距離" if kyori <= 2000 else "長距離"
            if dist != str(cond["dist_cat"]):
                return False
        return True
    elif cat == "TRK":
        if "keibajo_code" in cond and str(row.get("keibajo_code", "")) != str(cond["keibajo_code"]):
            return False
        if "kyakushitsu" in cond and str(row.get("kyakushitsu_hantei", row.get("kyakushitsu", ""))) != str(cond["kyakushitsu"]):
            return False
        if "dist_cat" in cond:
            kyori = float(row.get("kyori", 0) or 0)
            dist = "短距離" if kyori <= 1400 else "中距離" if kyori <= 2000 else "長距離"
            if dist != str(cond["dist_cat"]):
                return False
        if "weight_change" in cond and _derive_weight_change(row) != str(cond["weight_change"]):
            return False
        return True
    elif cat == "SEA":
        if "month" in cond:
            month = str(row.get("month", ""))
            if not month and "race_code" in row:
                rc = str(row.get("race_code", ""))
                month = rc[4:6].lstrip("0")
            if month != str(cond["month"]):
                return False
        if "barei" in cond and str(row.get("barei", "")) != str(cond["barei"]):
            return False
        if "dist_cat" in cond:
            kyori = float(row.get("kyori", 0) or 0)
            dist = "短距離" if kyori <= 1400 else "中距離" if kyori <= 2000 else "長距離"
            if dist != str(cond["dist_cat"]):
                return False
        return True
    elif cat == "TRN":
        if "weight_change" in cond and _derive_weight_change(row) != str(cond["weight_change"]):
            return False
        if "training_score_v2_min" in cond and float(row.get("training_score_v2", 0) or 0) < float(cond["training_score_v2_min"]):
            return False
        if "ninki_max" in cond:
            ninki = pd.to_numeric(pd.Series([row.get("tansho_ninkijun", row.get("ninki", 99))]), errors="coerce").fillna(99).iloc[0]
            if ninki > float(cond["ninki_max"]):
                return False
        return True
    elif cat == "DBT":
        if "is_debut" in cond and int(row.get("is_debut", 0) or 0) != int(cond["is_debut"]):
            return False
        if "debut_score_min" in cond and float(row.get("debut_score", 0) or 0) < float(cond["debut_score_min"]):
            return False
        if "training_score_v2_min" in cond and float(row.get("training_score_v2", 0) or 0) < float(cond["training_score_v2_min"]):
            return False
        if "jockey_debut_win_rate_min" in cond and float(row.get("jockey_debut_win_rate", 0) or 0) < float(cond["jockey_debut_win_rate_min"]):
            return False
        if "trainer_debut_win_rate_min" in cond and float(row.get("trainer_debut_win_rate", 0) or 0) < float(cond["trainer_debut_win_rate_min"]):
            return False
        if "sire_debut_win_rate_min" in cond and float(row.get("sire_debut_win_rate", 0) or 0) < float(cond["sire_debut_win_rate_min"]):
            return False
        return True
    elif cat == "SHG":
        if "is_shogai" in cond and int(row.get("is_shogai", 0) or 0) != int(cond["is_shogai"]):
            return False
        if "shogai_score_min" in cond and float(row.get("shogai_score", 0) or 0) < float(cond["shogai_score_min"]):
            return False
        if "shogai_keiken_min" in cond and float(row.get("shogai_keiken", 0) or 0) < float(cond["shogai_keiken_min"]):
            return False
        if "training_score_v2_min" in cond and float(row.get("training_score_v2", 0) or 0) < float(cond["training_score_v2_min"]):
            return False
        if "jockey_shogai_win_rate_min" in cond and float(row.get("jockey_shogai_win_rate", 0) or 0) < float(cond["jockey_shogai_win_rate_min"]):
            return False
        if "trainer_shogai_win_rate_min" in cond and float(row.get("trainer_shogai_win_rate", 0) or 0) < float(cond["trainer_shogai_win_rate_min"]):
            return False
        return True
    elif cat == "MKT":
        # MKTは馬個別ではなくレース全体の特性なので常にFalse
        return False
    return False


# ─────────────────────────────────────────────────────────────
# 歴史的バッチ処理（2000年〜）
# ─────────────────────────────────────────────────────────────

# コース名マスタ（keibajo_code → 名称）
_KEIBAJO = {
    "01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京",
    "06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉",
}
# 馬場状態
_BABA = {"1":"良","2":"稍重","3":"重","4":"不良"}
# 脚質
_KYAKUSHITSU = {"1":"逃げ","2":"先行","3":"差し","4":"追込"}


def _compute_historical_stats(engine, year_from: int = 2000) -> Dict[str, pd.DataFrame]:
    """
    2000年〜現在の全レース結果からカテゴリ別集計統計を計算。
    LLMに渡す前の事前集計フェーズ。
    """
    stats: Dict[str, pd.DataFrame] = {}
    since = str(year_from)

    print(f"  📊 統計集計開始（{year_from}年〜）...")

    # ── 1. 父馬別 × 馬場状態 勝率 (BLD) ──────────────────────
    print("    [1/7] 父馬×馬場状態 勝率...")
    sql_bld = text("""
        SELECT
            m.ketto1_bamei                        AS chichi,
            COALESCE(r.shiba_babajotai_code,
                     r.dirt_babajotai_code, '1')  AS baba,
            COUNT(*)                              AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            AVG(u.tansho_odds::float / 10)        AS avg_odds
        FROM umagoto_race_joho u
        JOIN kyosoba_master2 m ON u.ketto_toroku_bango = m.ketto_toroku_bango
        JOIN race_shosai r     ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND m.ketto1_bamei IS NOT NULL
          AND m.ketto1_bamei != ''
        GROUP BY 1,2
        HAVING COUNT(*) >= 30
        ORDER BY (SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END)::float/COUNT(*)) DESC
        LIMIT 200
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql_bld, conn, params={"since": since})
    df["win_rate"] = df["wins"] / df["n"]
    df["baba_name"] = df["baba"].map(_BABA)
    stats["BLD_baba"] = df

    # ── 2. 父馬別 × 距離ブラケット 勝率 (BLD) ──────────────────
    print("    [2/7] 父馬×距離 勝率...")
    sql_bld2 = text("""
        SELECT
            m.ketto1_bamei AS chichi,
            CASE
                WHEN r.kyori::integer <= 1400 THEN '短距離'
                WHEN r.kyori::integer <= 2000 THEN '中距離'
                ELSE '長距離'
            END            AS dist_cat,
            COUNT(*)       AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN kyosoba_master2 m ON u.ketto_toroku_bango = m.ketto_toroku_bango
        JOIN race_shosai r     ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND m.ketto1_bamei IS NOT NULL
          AND m.ketto1_bamei != ''
        GROUP BY 1,2
        HAVING COUNT(*) >= 50
        ORDER BY 4 DESC
        LIMIT 200
    """)
    with engine.connect() as conn:
        df2 = pd.read_sql(sql_bld2, conn, params={"since": since})
    df2["win_rate"] = df2["wins"] / df2["n"]
    stats["BLD_dist"] = df2

    # ── 3. 騎手 × 競馬場 勝率 (JKY) ────────────────────────────
    print("    [3/7] 騎手×競馬場 勝率...")
    sql_jky = text("""
        SELECT
            u.kishu_code,
            u.kishumei_ryakusho                   AS kishu,
            r.keibajo_code,
            COUNT(*)                              AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN u.kakutei_chakujun::integer<=3 THEN 1 ELSE 0 END) AS shows
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.kishumei_ryakusho IS NOT NULL
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 20
        ORDER BY (SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END)::float/COUNT(*)) DESC
        LIMIT 300
    """)
    with engine.connect() as conn:
        df3 = pd.read_sql(sql_jky, conn, params={"since": since})
    df3["win_rate"]   = df3["wins"] / df3["n"]
    df3["show_rate"]  = df3["shows"] / df3["n"]
    df3["keibajo"]    = df3["keibajo_code"].map(_KEIBAJO).fillna(df3["keibajo_code"])
    stats["JKY"] = df3

    # ── 4. 脚質 × 競馬場 勝率 (TRK) ────────────────────────────
    print("    [4/7] 脚質×競馬場 勝率...")
    sql_trk = text("""
        SELECT
            r.keibajo_code,
            u.kyakushitsu_hantei                  AS kyakushitsu,
            COUNT(*)                              AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.kyakushitsu_hantei IN ('1','2','3','4')
        GROUP BY 1,2
        HAVING COUNT(*) >= 50
        ORDER BY 1, 2
    """)
    with engine.connect() as conn:
        df4 = pd.read_sql(sql_trk, conn, params={"since": since})
    df4["win_rate"]   = df4["wins"] / df4["n"]
    df4["keibajo"]    = df4["keibajo_code"].map(_KEIBAJO).fillna(df4["keibajo_code"])
    df4["style"]      = df4["kyakushitsu"].map(_KYAKUSHITSU)
    stats["TRK"] = df4

    # ── 5. 月別 穴馬出現率 (MKT・SEA) ──────────────────────────
    print("    [5/7] 月別 穴馬出現率...")
    sql_sea = text("""
        SELECT
            SUBSTRING(u.race_code, 5, 2)::int AS month,
            COUNT(*)                           AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' AND u.tansho_ninkijun::integer >= 10
                     THEN 1 ELSE 0 END)        AS upset_wins,
            AVG(CASE WHEN u.kakutei_chakujun='01'
                     THEN u.tansho_odds::float/10 ELSE NULL END) AS avg_winner_odds
        FROM umagoto_race_joho u
        WHERE LEFT(u.race_code,4) >= :since
          AND u.kakutei_chakujun IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    with engine.connect() as conn:
        df5 = pd.read_sql(sql_sea, conn, params={"since": since})
    df5["upset_rate"] = df5["upset_wins"] / df5["n"]
    stats["SEA"] = df5

    # ── 6. 人気別 実際の勝率 vs 期待値 (MKT) ───────────────────
    print("    [6/7] 人気別 実勝率 vs 単勝回収率...")
    sql_mkt = text("""
        SELECT
            u.tansho_ninkijun                     AS ninki,
            COUNT(*)                              AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            AVG(CASE WHEN u.kakutei_chakujun='01'
                     THEN u.tansho_odds::float/10 ELSE NULL END) AS avg_hit_odds,
            AVG(u.tansho_odds::float/10)          AS avg_odds
        FROM umagoto_race_joho u
        WHERE LEFT(u.race_code,4) >= :since
          AND u.tansho_ninkijun ~ '^[0-9]+$' AND u.tansho_ninkijun::integer BETWEEN 1 AND 18
        GROUP BY 1
        ORDER BY 1
    """)
    with engine.connect() as conn:
        df6 = pd.read_sql(sql_mkt, conn, params={"since": since})
    df6["win_rate"] = df6["wins"] / df6["n"]
    df6["avg_hit_odds"] = pd.to_numeric(df6["avg_hit_odds"], errors="coerce").fillna(0)
    df6["roi"]      = df6["win_rate"] * df6["avg_hit_odds"]
    stats["MKT"] = df6

    # ── 7. グレード × 人気外 勝率 (MKT) ────────────────────────
    print("    [7/7] グレード別 穴馬勝率...")
    sql_grade = text("""
        SELECT
            r.grade_code,
            COUNT(*)  AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' AND u.tansho_ninkijun::integer >= 6
                     THEN 1 ELSE 0 END) AS upset_wins,
            AVG(CASE WHEN u.kakutei_chakujun='01' AND u.tansho_ninkijun::integer >= 6
                     THEN u.tansho_odds::float/10 ELSE NULL END) AS avg_upset_odds
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND r.grade_code IS NOT NULL
          AND r.grade_code != ''
        GROUP BY 1
        HAVING COUNT(*) >= 100
        ORDER BY 1
    """)
    with engine.connect() as conn:
        df7 = pd.read_sql(sql_grade, conn, params={"since": since})
    df7["upset_rate"] = df7["upset_wins"] / df7["n"]
    stats["GRADE"] = df7

    # ── 8. 父馬 × 競馬場 × 距離 (BLD 細分化) ─────────────────
    print("    [8/14] 父馬×競馬場×距離 勝率...")
    sql_bld3 = text("""
        SELECT
            m.ketto1_bamei AS chichi,
            r.keibajo_code,
            CASE WHEN r.kyori::integer <= 1400 THEN '短距離'
                 WHEN r.kyori::integer <= 2000 THEN '中距離'
                 ELSE '長距離' END AS dist_cat,
            COUNT(*) AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN kyosoba_master2 m ON u.ketto_toroku_bango = m.ketto_toroku_bango
        JOIN race_shosai r     ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND m.ketto1_bamei IS NOT NULL AND m.ketto1_bamei != ''
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 30
        ORDER BY (SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END)::float/COUNT(*)) DESC
        LIMIT 200
    """)
    with engine.connect() as conn:
        df8 = pd.read_sql(sql_bld3, conn, params={"since": since})
    df8["win_rate"] = df8["wins"] / df8["n"]
    df8["keibajo"]  = df8["keibajo_code"].map(_KEIBAJO).fillna(df8["keibajo_code"])
    stats["BLD_venue"] = df8

    # ── 9. 馬齢 × 距離 × 季節 (SEA 細分化) ──────────────────
    print("    [9/14] 馬齢×距離×月 勝率...")
    sql_age = text("""
        SELECT
            u.barei::integer                  AS barei,
            CASE WHEN r.kyori::integer <= 1400 THEN '短距離'
                 WHEN r.kyori::integer <= 2000 THEN '中距離'
                 ELSE '長距離' END            AS dist_cat,
            SUBSTRING(u.race_code,5,2)::int  AS month,
            COUNT(*)                          AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.barei IS NOT NULL
          AND u.barei ~ '^[0-9]+$'
          AND u.barei::integer BETWEEN 2 AND 8
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 50
        ORDER BY 5 DESC
        LIMIT 300
    """)
    with engine.connect() as conn:
        df9 = pd.read_sql(sql_age, conn, params={"since": since})
    df9["win_rate"] = df9["wins"] / df9["n"]
    stats["AGE_dist_season"] = df9

    # ── 10. 体重増減 × 人気 (TRN 細分化) ─────────────────────
    print("    [10/14] 体重増減×人気 勝率...")
    sql_weight = text("""
        SELECT
            CASE
                WHEN u.zogen_fugo='1' AND u.zogen_sa::integer >= 10 THEN '大幅増（+10kg以上）'
                WHEN u.zogen_fugo='1' AND u.zogen_sa::integer BETWEEN 2 AND 9 THEN '微増（+2〜9kg）'
                WHEN u.zogen_fugo='0'                                          THEN '同体重'
                WHEN u.zogen_fugo='2' AND u.zogen_sa::integer BETWEEN 2 AND 9 THEN '微減（-2〜9kg）'
                WHEN u.zogen_fugo='2' AND u.zogen_sa::integer >= 10           THEN '大幅減（-10kg以上）'
                ELSE 'その他'
            END                                 AS weight_change,
            u.tansho_ninkijun::integer          AS ninki,
            COUNT(*)                            AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN u.kakutei_chakujun::integer <= 3 THEN 1 ELSE 0 END) AS shows
        FROM umagoto_race_joho u
        WHERE LEFT(u.race_code,4) >= :since
          AND u.zogen_fugo IN ('0','1','2')
          AND u.zogen_sa IS NOT NULL
          AND u.zogen_sa ~ '^[0-9]+$'
          AND u.tansho_ninkijun ~ '^[0-9]+$'
          AND u.tansho_ninkijun::integer BETWEEN 1 AND 18
        GROUP BY 1,2
        HAVING COUNT(*) >= 100
        ORDER BY 1, 2
    """)
    with engine.connect() as conn:
        df10 = pd.read_sql(sql_weight, conn, params={"since": since})
    df10["win_rate"]  = df10["wins"] / df10["n"]
    df10["show_rate"] = df10["shows"] / df10["n"]
    stats["TRN_weight"] = df10

    # ── 11. 騎手 × 馬場状態 × 距離 (JKY 細分化) ──────────────
    print("    [11/14] 騎手×馬場×距離 勝率...")
    sql_jky2 = text("""
        SELECT
            u.kishumei_ryakusho AS kishu,
            COALESCE(r.shiba_babajotai_code, r.dirt_babajotai_code,'1') AS baba,
            CASE WHEN r.kyori::integer <= 1400 THEN '短距離'
                 WHEN r.kyori::integer <= 2000 THEN '中距離'
                 ELSE '長距離' END AS dist_cat,
            COUNT(*) AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.kishumei_ryakusho IS NOT NULL
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 20
        ORDER BY (SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END)::float/COUNT(*)) DESC
        LIMIT 200
    """)
    with engine.connect() as conn:
        df11 = pd.read_sql(sql_jky2, conn, params={"since": since})
    df11["win_rate"] = df11["wins"] / df11["n"]
    df11["baba_name"] = df11["baba"].map(_BABA).fillna("良")
    stats["JKY_baba_dist"] = df11

    # ── 12. 人気 × 月 の回収率 (MKT 細分化) ──────────────────
    print("    [12/14] 人気×月 回収率...")
    sql_mkt2 = text("""
        SELECT
            u.tansho_ninkijun::integer          AS ninki,
            SUBSTRING(u.race_code,5,2)::int     AS month,
            COUNT(*)                            AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            AVG(CASE WHEN u.kakutei_chakujun='01'
                     THEN u.tansho_odds::float/10 ELSE NULL END)     AS avg_win_odds
        FROM umagoto_race_joho u
        WHERE LEFT(u.race_code,4) >= :since
          AND u.tansho_ninkijun ~ '^[0-9]+$'
          AND u.tansho_ninkijun::integer BETWEEN 6 AND 18
        GROUP BY 1,2
        HAVING COUNT(*) >= 500
        ORDER BY 1,2
    """)
    with engine.connect() as conn:
        df12 = pd.read_sql(sql_mkt2, conn, params={"since": since})
    df12["win_rate"] = df12["wins"] / df12["n"]
    df12["roi"]      = df12["win_rate"] * pd.to_numeric(df12["avg_win_odds"], errors="coerce").fillna(0)
    stats["MKT_ninki_month"] = df12

    # ── 13. コース × 距離 × 脚質 (TRK 細分化) ────────────────
    print("    [13/14] コース×距離×脚質 勝率...")
    sql_trk2 = text("""
        SELECT
            r.keibajo_code,
            CASE WHEN r.kyori::integer <= 1400 THEN '短距離'
                 WHEN r.kyori::integer <= 2000 THEN '中距離'
                 ELSE '長距離' END             AS dist_cat,
            u.kyakushitsu_hantei               AS kyakushitsu,
            COUNT(*)                           AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.kyakushitsu_hantei IN ('1','2','3','4')
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 50
        ORDER BY 1,2,3
    """)
    with engine.connect() as conn:
        df13 = pd.read_sql(sql_trk2, conn, params={"since": since})
    df13["win_rate"] = df13["wins"] / df13["n"]
    df13["keibajo"]  = df13["keibajo_code"].map(_KEIBAJO).fillna(df13["keibajo_code"])
    df13["style"]    = df13["kyakushitsu"].map(_KYAKUSHITSU)
    stats["TRK_venue_dist"] = df13

    # ── 14. 前走人気外×今走人気外 (MKT 穴馬継続性) ────────────
    print("    [14/14] 穴→穴 継続出走パターン...")
    sql_upset_cont = text("""
        SELECT
            CASE WHEN u.tansho_ninkijun::integer >= 10 THEN '大穴(10番人気+)'
                 WHEN u.tansho_ninkijun::integer >= 6  THEN '穴(6-9番人気)'
                 ELSE '上位人気'
            END                                        AS ninki_cat,
            CASE WHEN r.kyori::integer <= 1400 THEN '短距離'
                 WHEN r.kyori::integer <= 2000 THEN '中距離'
                 ELSE '長距離' END                     AS dist_cat,
            r.grade_code,
            COUNT(*)                                   AS n,
            SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END) AS wins,
            AVG(u.tansho_odds::float/10)               AS avg_odds
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code = r.race_code
        WHERE LEFT(u.race_code,4) >= :since
          AND u.tansho_ninkijun ~ '^[0-9]+$'
          AND u.tansho_ninkijun::integer >= 6
          AND r.grade_code IS NOT NULL AND r.grade_code != ''
        GROUP BY 1,2,3
        HAVING COUNT(*) >= 200
        ORDER BY (SUM(CASE WHEN u.kakutei_chakujun='01' THEN 1 ELSE 0 END)::float/COUNT(*)) DESC
        LIMIT 100
    """)
    with engine.connect() as conn:
        df14 = pd.read_sql(sql_upset_cont, conn, params={"since": since})
    df14["win_rate"] = df14["wins"] / df14["n"]
    df14["roi"]      = df14["win_rate"] * df14["avg_odds"]
    stats["MKT_upset_profile"] = df14

    # ── 15. 新馬戦・障害戦 特化集計（特徴量CSV） ────────────
    print("    [15/16] 新馬戦・障害戦 特化集計...")
    if os.path.exists(FEAT_FILE):
        try:
            header_cols = set(pd.read_csv(FEAT_FILE, nrows=0).columns)
            feature_cols = [
                "race_code", "kakutei_chakujun", "is_debut", "debut_score",
                "jockey_debut_win_rate", "trainer_debut_win_rate",
                "sire_debut_win_rate", "training_score_v2",
                "is_shogai", "shogai_score", "shogai_keiken",
                "jockey_shogai_win_rate", "trainer_shogai_win_rate",
                "barei", "bataiju", "kyori",
            ]
            usecols = [c for c in feature_cols if c in header_cols]
            if "kakutei_chakujun" not in usecols:
                usecols.append("kakutei_chakujun")
            df_feat = pd.read_csv(FEAT_FILE, on_bad_lines="skip", low_memory=False, usecols=usecols)
            df_feat["kakutei_chakujun"] = pd.to_numeric(df_feat["kakutei_chakujun"], errors="coerce").fillna(99)
            df_feat["win"] = (df_feat["kakutei_chakujun"] == 1).astype(int)

            debut_rows = []
            if {"is_debut", "debut_score"} <= set(df_feat.columns):
                debut = df_feat[df_feat["is_debut"] == 1].copy()
                debut_thresholds = [
                    ("debut_score_min", "debut_score", [0.60, 0.70, 0.80], 60),
                    ("training_score_v2_min", "training_score_v2", [0.60, 0.70], 60),
                    ("jockey_debut_win_rate_min", "jockey_debut_win_rate", [0.15, 0.20], 40),
                    ("trainer_debut_win_rate_min", "trainer_debut_win_rate", [0.15, 0.20], 40),
                    ("sire_debut_win_rate_min", "sire_debut_win_rate", [0.15, 0.20], 40),
                ]
                for signal, col, thresholds, min_n in debut_thresholds:
                    if col not in debut.columns:
                        continue
                    for thr in thresholds:
                        sub = debut[pd.to_numeric(debut[col], errors="coerce").fillna(0) >= thr]
                        if len(sub) >= min_n:
                            debut_rows.append({
                                "signal": signal,
                                "threshold": thr,
                                "n": len(sub),
                                "wins": int(sub["win"].sum()),
                                "win_rate": float(sub["win"].mean()),
                                "avg_score": float(pd.to_numeric(sub.get("debut_score", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "debut_score" in sub.columns else 0.0,
                                "avg_train": float(pd.to_numeric(sub.get("training_score_v2", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "training_score_v2" in sub.columns else 0.0,
                                "avg_jockey": float(pd.to_numeric(sub.get("jockey_debut_win_rate", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "jockey_debut_win_rate" in sub.columns else 0.0,
                                "avg_trainer": float(pd.to_numeric(sub.get("trainer_debut_win_rate", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "trainer_debut_win_rate" in sub.columns else 0.0,
                                "avg_sire": float(pd.to_numeric(sub.get("sire_debut_win_rate", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "sire_debut_win_rate" in sub.columns else 0.0,
                            })
            if debut_rows:
                stats["DBT"] = pd.DataFrame(debut_rows).sort_values(["win_rate", "n"], ascending=False)

            shogai_rows = []
            if {"is_shogai", "shogai_score"} <= set(df_feat.columns):
                shogai = df_feat[df_feat["is_shogai"] == 1].copy()
                shogai_thresholds = [
                    ("shogai_score_min", "shogai_score", [0.60, 0.70, 0.80], 20),
                    ("shogai_keiken_min", "shogai_keiken", [1, 3, 5], 20),
                    ("jockey_shogai_win_rate_min", "jockey_shogai_win_rate", [0.10, 0.15, 0.20], 20),
                    ("trainer_shogai_win_rate_min", "trainer_shogai_win_rate", [0.10, 0.15, 0.20], 20),
                    ("training_score_v2_min", "training_score_v2", [0.60, 0.70], 20),
                ]
                for signal, col, thresholds, min_n in shogai_thresholds:
                    if col not in shogai.columns:
                        continue
                    for thr in thresholds:
                        sub = shogai[pd.to_numeric(shogai[col], errors="coerce").fillna(0) >= thr]
                        if len(sub) >= min_n:
                            shogai_rows.append({
                                "signal": signal,
                                "threshold": thr,
                                "n": len(sub),
                                "wins": int(sub["win"].sum()),
                                "win_rate": float(sub["win"].mean()),
                                "avg_score": float(pd.to_numeric(sub.get("shogai_score", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "shogai_score" in sub.columns else 0.0,
                                "avg_keiken": float(pd.to_numeric(sub.get("shogai_keiken", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "shogai_keiken" in sub.columns else 0.0,
                                "avg_jockey": float(pd.to_numeric(sub.get("jockey_shogai_win_rate", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "jockey_shogai_win_rate" in sub.columns else 0.0,
                                "avg_trainer": float(pd.to_numeric(sub.get("trainer_shogai_win_rate", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "trainer_shogai_win_rate" in sub.columns else 0.0,
                                "avg_train": float(pd.to_numeric(sub.get("training_score_v2", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if "training_score_v2" in sub.columns else 0.0,
                            })
            if shogai_rows:
                stats["SHG"] = pd.DataFrame(shogai_rows).sort_values(["win_rate", "n"], ascending=False)

            if "training_score_v2" in df_feat.columns:
                trn = df_feat.copy()
                trn["training_score_v2"] = pd.to_numeric(trn["training_score_v2"], errors="coerce").fillna(0)
                trn_rows = []
                for thr in [0.50, 0.60, 0.70, 0.80]:
                    sub = trn[trn["training_score_v2"] >= thr]
                    if len(sub) >= 100:
                        trn_rows.append({
                            "signal": "training_score_v2_min",
                            "threshold": thr,
                            "n": len(sub),
                            "wins": int(sub["win"].sum()),
                            "win_rate": float(sub["win"].mean()),
                            "avg_train": float(sub["training_score_v2"].mean()),
                        })
                if trn_rows:
                    stats["TRN_training"] = pd.DataFrame(trn_rows).sort_values(["win_rate", "n"], ascending=False)
        except Exception as e:
            print(f"      ⚠️ 新馬/障害集計スキップ: {e}")

    total_races = sum(len(df) for df in stats.values())
    print(f"  ✅ 集計完了: {len(stats)}カテゴリ / {total_races}行")
    return stats


def _format_stats_for_llm(stats: Dict[str, pd.DataFrame], category: str) -> str:
    """集計統計をLLMに渡す簡潔なテキスト形式に変換"""

    if category == "BLD_baba":
        df = stats.get("BLD_baba", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【父馬×馬場状態 勝率TOP30（サンプル数>=30）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['chichi']} × {r['baba_name']}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f} 平均オッズ{r['avg_odds']:.1f}倍"
            )
        return "\n".join(lines)

    elif category == "BLD_dist":
        df = stats.get("BLD_dist", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【父馬×距離ブラケット 勝率TOP30（サンプル数>=50）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['chichi']} × {r['dist_cat']}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "JKY":
        df = stats.get("JKY", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【騎手×競馬場 勝率TOP30（サンプル数>=20）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['kishu']} × {r['keibajo']}: "
                f"勝率{r['win_rate']:.1%} 複勝率{r['show_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "TRK":
        df = stats.get("TRK", pd.DataFrame())
        if df.empty:
            return ""
        lines = ["【脚質×競馬場 勝率（2000年〜全集計）】"]
        for kb in df["keibajo"].unique():
            sub = df[df["keibajo"] == kb].sort_values("win_rate", ascending=False)
            best = sub.iloc[0]
            lines.append(
                f"  {kb}: {best['style']}が最強 勝率{best['win_rate']:.1%} n={best['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "SEA":
        df = stats.get("SEA", pd.DataFrame())
        if df.empty:
            return ""
        lines = ["【月別 穴馬出現率・平均勝馬オッズ（2000年〜）】"]
        for _, r in df.iterrows():
            lines.append(
                f"  {r['month']:2d}月: 穴馬率{r['upset_rate']:.1%} "
                f"平均勝馬オッズ{r['avg_winner_odds']:.1f}倍 n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "MKT":
        df = stats.get("MKT", pd.DataFrame())
        if df.empty:
            return ""
        lines = ["【人気別 実勝率・単勝回収率（2000年〜）】"]
        for _, r in df.iterrows():
            roi_mark = "✓" if r["roi"] >= 0.75 else "✗"
            lines.append(
                f"  {r['ninki']:2d}番人気: 勝率{r['win_rate']:.1%} "
                f"ROI{r['roi']:.2f} {roi_mark} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "GRADE":
        df = stats.get("GRADE", pd.DataFrame())
        if df.empty:
            return ""
        lines = ["【グレード別 6番人気以下の穴馬勝率（2000年〜）】"]
        for _, r in df.iterrows():
            lines.append(
                f"  Grade{r['grade_code']}: 穴馬率{r['upset_rate']:.1%} "
                f"平均穴馬オッズ{r['avg_upset_odds']:.1f}倍 n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "BLD_venue":
        df = stats.get("BLD_venue", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【父馬×競馬場×距離 勝率TOP30（サンプル数>=30）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['chichi']} × {r['keibajo']} × {r['dist_cat']}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "AGE_dist_season":
        df = stats.get("AGE_dist_season", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【馬齢×距離×月 勝率TOP30（サンプル数>=50）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['barei']:.0f}歳 × {r['dist_cat']} × {r['month']:.0f}月: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "TRN_weight":
        df = stats.get("TRN_weight", pd.DataFrame())
        if df.empty:
            return ""
        lines = ["【体重増減カテゴリ×人気 勝率・複勝率（サンプル数>=100）】"]
        for wc in df["weight_change"].unique():
            sub = df[df["weight_change"] == wc].sort_values("ninki")
            best = sub.nlargest(1, "win_rate").iloc[0]
            lines.append(
                f"  {wc}: 最高勝率={best['win_rate']:.1%}（{best['ninki']:.0f}番人気） "
                f"複勝率{best['show_rate']:.1%}"
            )
        return "\n".join(lines)

    elif category == "DBT":
        df = stats.get("DBT", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(20, "win_rate")
        lines = ["【新馬戦スコア・新馬実績 閾値別成績】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['signal']} >= {r['threshold']:.2f}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f} "
                f"(train={r.get('avg_train', 0):.2f}, jockey={r.get('avg_jockey', 0):.2f})"
            )
        return "\n".join(lines)

    elif category == "SHG":
        df = stats.get("SHG", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(20, "win_rate")
        lines = ["【障害戦スコア・経験 閾値別成績】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['signal']} >= {r['threshold']:.2f}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f} "
                f"(keiken={r.get('avg_keiken', 0):.1f}, jockey={r.get('avg_jockey', 0):.2f})"
            )
        return "\n".join(lines)

    elif category == "TRN_training":
        df = stats.get("TRN_training", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(20, "win_rate")
        lines = ["【調教スコア閾値別成績】"]
        for _, r in top.iterrows():
            lines.append(
                f"  training_score_v2 >= {r['threshold']:.2f}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f} "
                f"(avg_train={r.get('avg_train', 0):.2f})"
            )
        return "\n".join(lines)

    elif category == "JKY_baba_dist":
        df = stats.get("JKY_baba_dist", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【騎手×馬場×距離 勝率TOP30（サンプル数>=20）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['kishu']} × {r['baba_name']} × {r['dist_cat']}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "MKT_ninki_month":
        df = stats.get("MKT_ninki_month", pd.DataFrame())
        if df.empty:
            return ""
        top = df[df["roi"] >= 0.80].nlargest(20, "roi")
        lines = ["【穴人気（6-18番人気）×月 ROI高値TOP20（サンプル数>=500）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['ninki']:.0f}番人気 × {r['month']:.0f}月: "
                f"ROI={r['roi']:.2f} 勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "TRK_venue_dist":
        df = stats.get("TRK_venue_dist", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(30, "win_rate")
        lines = ["【競馬場×距離×脚質 勝率TOP30（サンプル数>=50）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['keibajo']} × {r['dist_cat']} × {r['style']}: "
                f"勝率{r['win_rate']:.1%} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    elif category == "MKT_upset_profile":
        df = stats.get("MKT_upset_profile", pd.DataFrame())
        if df.empty:
            return ""
        top = df.nlargest(20, "win_rate")
        lines = ["【穴馬プロファイル（人気帯×距離×グレード）勝率TOP20（サンプル数>=200）】"]
        for _, r in top.iterrows():
            lines.append(
                f"  {r['ninki_cat']} × {r['dist_cat']} × Grade{r['grade_code']}: "
                f"勝率{r['win_rate']:.1%} ROI={r['roi']:.2f} n={r['n']:.0f}"
            )
        return "\n".join(lines)

    return ""


_HIST_EXTRACT_SYSTEM = """あなたは競馬統計の専門家です。
25年分の統計データから、再現性が高く実用的な知見を抽出します。

【重要な基準】
- 常識的すぎる知見（「良馬場は速い」等）は除外
- サンプル数が少ない（n<30）ものは除外
- 勝率差が5%以上あるもののみ抽出
- 条件は具体的な数値で表現

必ずJSONのみ返してください:
{
  "insights": [
    {
      "category": "BLD|JKY|TRK|MKT|SEA|TRN|DBT|SHG",
      "condition": {"field": "value"},
      "claim": "50文字以内の日本語",
      "evidence_count": N,
      "estimated_lift": 1.XX,
      "confidence_prior": 0.XX
    }
  ]
}"""


def _extract_historical_insights_llm(stats_text: str, cat_label: str) -> List[Dict]:
    """統計サマリーをLLMに渡して知見を抽出（Ollama優先 → Claude Haiku → 空リスト）"""
    user_msg = "以下の" + cat_label + "統計から知見を抽出してください:\n\n" + stats_text

    # 1. Ollama（無料）
    ollama_resp = _call_ollama_curator(
        user_msg, system=_HIST_EXTRACT_SYSTEM, temperature=0.3
    )
    if ollama_resp:
        try:
            m = re.search(r"\{.*\}", ollama_resp, re.DOTALL)
            if m:
                return json.loads(m.group()).get("insights", [])
        except Exception:
            pass

    # 2. Claude Haiku（有料フォールバック）
    if not _ANTHROPIC_KEY:
        return []
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_HIST_EXTRACT_SYSTEM,
            messages=[{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": _HIST_EXTRACT_SYSTEM,
                    "cache_control": {"type": "ephemeral"}
                }, {
                    "type": "text",
                    "text": user_msg,
                }]
            }],
        )
        resp = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            return json.loads(m.group()).get("insights", [])
    except Exception as e:
        print("    LLM抽出エラー: " + str(e))
    return []


def _extract_historical_insights_rule(stats: Dict[str, pd.DataFrame]) -> List[Dict]:
    """
    APIなし時のルールベース歴史的知見抽出。
    統計的に有意な差があるパターンを直接抽出。
    """
    insights = []

    # BLD: 父馬×馬場 – 勝率が全体平均+10%以上のもの
    baseline_win = 1 / 8  # 8頭立て平均勝率目安
    df_bld = stats.get("BLD_baba", pd.DataFrame())
    for _, r in df_bld.iterrows():
        if r["win_rate"] >= baseline_win + 0.10 and r["n"] >= 50:
            insights.append({
                "category": "BLD",
                "condition": {"chichi": r["chichi"], "baba_jotai": r["baba"]},
                "claim": f"{r['chichi']}×{r['baba_name']}で勝率{r['win_rate']:.0%}（n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.5 + (r["n"] - 50) / 1000, 0.75),
            })

    # TRK: 脚質×競馬場 – 逃げ馬勝率が高い競馬場
    df_trk = stats.get("TRK", pd.DataFrame())
    nige = df_trk[df_trk["kyakushitsu"] == "1"]
    for _, r in nige.iterrows():
        if r["win_rate"] >= 0.15 and r["n"] >= 100:
            insights.append({
                "category": "TRK",
                "condition": {"keibajo_code": r["keibajo_code"], "kyakushitsu": "逃げ"},
                "claim": f"{r['keibajo']}は逃げ有利（勝率{r['win_rate']:.0%}、n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": 0.70,
            })

    # SEA: 月別 穴馬出現率の高低
    df_sea = stats.get("SEA", pd.DataFrame())
    if not df_sea.empty:
        avg_upset = df_sea["upset_rate"].mean()
        for _, r in df_sea.iterrows():
            if abs(r["upset_rate"] - avg_upset) >= 0.005:
                hi_lo = "高い" if r["upset_rate"] > avg_upset else "低い"
                insights.append({
                    "category": "SEA",
                    "condition": {"month": int(r["month"])},
                    "claim": f"{r['month']:.0f}月は穴馬出現率が{hi_lo}（{r['upset_rate']:.1%}）",
                    "evidence_count": int(r["n"]),
                    "estimated_lift": round(r["upset_rate"] / max(avg_upset, 0.001), 2),
                    "confidence_prior": 0.65,
                })

    # MKT: 単勝回収率が高い人気帯
    df_mkt = stats.get("MKT", pd.DataFrame())
    for _, r in df_mkt.iterrows():
        if r["roi"] >= 0.80 and r["n"] >= 10000:
            insights.append({
                "category": "MKT",
                "condition": {"ninki": int(r["ninki"])},
                "claim": f"{r['ninki']:.0f}番人気の単勝回収率{r['roi']:.2f}（勝率{r['win_rate']:.1%}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["roi"], 2),
                "confidence_prior": 0.75,
            })

    # BLD_venue: 父馬×競馬場×距離 – 勝率が基準+12%以上のもの
    df_bv = stats.get("BLD_venue", pd.DataFrame())
    for _, r in df_bv.iterrows():
        if r["win_rate"] >= baseline_win + 0.12 and r["n"] >= 30:
            insights.append({
                "category": "BLD",
                "condition": {"chichi": r["chichi"], "keibajo_code": r["keibajo_code"], "dist_cat": r["dist_cat"]},
                "claim": f"{r['chichi']}×{r['keibajo']}×{r['dist_cat']}で勝率{r['win_rate']:.0%}（n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.50 + (r["n"] - 30) / 800, 0.75),
            })

    # AGE_dist_season: 馬齢×距離×月 – 勝率が基準+8%以上かつ n>=100
    df_age = stats.get("AGE_dist_season", pd.DataFrame())
    for _, r in df_age.iterrows():
        if r["win_rate"] >= baseline_win + 0.08 and r["n"] >= 100:
            insights.append({
                "category": "SEA",
                "condition": {"barei": int(r["barei"]), "dist_cat": r["dist_cat"], "month": int(r["month"])},
                "claim": f"{r['barei']:.0f}歳×{r['dist_cat']}×{r['month']:.0f}月は勝率{r['win_rate']:.0%}（n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": 0.60,
            })

    # TRN_weight: 大幅減（-10kg以上）の1-3番人気が特に高勝率なら警告（negative信号）
    df_wt = stats.get("TRN_weight", pd.DataFrame())
    for _, r in df_wt.iterrows():
        if r["weight_change"] == "大幅増（+10kg以上）" and r["ninki"] <= 3 and r["win_rate"] < 0.10:
            insights.append({
                "category": "TRK",
                "condition": {"weight_change": r["weight_change"], "ninki_max": int(r["ninki"])},
                "claim": f"大幅体重増（+10kg以上）の{r['ninki']:.0f}番人気以内は勝率低下（{r['win_rate']:.0%}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": 0.62,
            })
        if r["weight_change"] == "大幅減（-10kg以上）" and r["ninki"] <= 5 and r["win_rate"] >= baseline_win + 0.05:
            insights.append({
                "category": "TRK",
                "condition": {"weight_change": r["weight_change"], "ninki_max": int(r["ninki"])},
                "claim": f"大幅体重減（-10kg以上）の{r['ninki']:.0f}番人気以内は勝率{r['win_rate']:.0%}と高め",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": 0.60,
            })

    # JKY_baba_dist: 騎手×馬場×距離 – 勝率20%超のパターン
    df_jbd = stats.get("JKY_baba_dist", pd.DataFrame())
    for _, r in df_jbd.iterrows():
        if r["win_rate"] >= 0.20 and r["n"] >= 30:
            insights.append({
                "category": "JKY",
                "condition": {"kishu": r["kishu"], "baba": r["baba"], "dist_cat": r["dist_cat"]},
                "claim": f"{r['kishu']}は{r['baba_name']}×{r['dist_cat']}で勝率{r['win_rate']:.0%}（n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.55 + (r["n"] - 30) / 500, 0.78),
            })

    # MKT_ninki_month: ROI>=0.85 の穴人気×月の組み合わせ
    df_nm = stats.get("MKT_ninki_month", pd.DataFrame())
    for _, r in df_nm.iterrows():
        if r["roi"] >= 0.85 and r["n"] >= 1000:
            insights.append({
                "category": "MKT",
                "condition": {"ninki": int(r["ninki"]), "month": int(r["month"])},
                "claim": f"{r['ninki']:.0f}番人気×{r['month']:.0f}月のROI={r['roi']:.2f}（穴馬市場非効率）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["roi"], 2),
                "confidence_prior": 0.65,
            })

    # TRK_venue_dist: 逃げ馬勝率が高い会場×距離パターン
    df_tvd = stats.get("TRK_venue_dist", pd.DataFrame())
    nige_vd = df_tvd[df_tvd["kyakushitsu"] == "1"]
    for _, r in nige_vd.iterrows():
        if r["win_rate"] >= 0.17 and r["n"] >= 80:
            insights.append({
                "category": "TRK",
                "condition": {"keibajo_code": r["keibajo_code"], "dist_cat": r["dist_cat"], "kyakushitsu": "逃げ"},
                "claim": f"{r['keibajo']}×{r['dist_cat']}は逃げ有利（勝率{r['win_rate']:.0%}、n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": 0.68,
            })

    # MKT_upset_profile: 大穴プロファイルでROI>=1.0の組み合わせ
    df_up = stats.get("MKT_upset_profile", pd.DataFrame())
    for _, r in df_up.iterrows():
        if r["roi"] >= 1.0 and r["n"] >= 300:
            insights.append({
                "category": "MKT",
                "condition": {"ninki_cat": r["ninki_cat"], "dist_cat": r["dist_cat"], "grade_code": r["grade_code"]},
                "claim": f"{r['ninki_cat']}×{r['dist_cat']}×Grade{r['grade_code']}でROI={r['roi']:.2f}（n={r['n']:.0f}）",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["roi"], 2),
                "confidence_prior": 0.60,
            })

    # DBT: 新馬戦の高スコア・高実績条件
    df_dbt = stats.get("DBT", pd.DataFrame())
    for _, r in df_dbt.iterrows():
        if r["win_rate"] >= baseline_win + 0.10 and r["n"] >= 40:
            signal = str(r["signal"])
            thr = float(r["threshold"])
            if signal == "debut_score_min":
                cond = {"is_debut": 1, "debut_score_min": thr}
                claim = f"新馬戦でdebut_score≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            elif signal == "training_score_v2_min":
                cond = {"is_debut": 1, "training_score_v2_min": thr}
                claim = f"新馬戦で調教スコア≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            elif signal == "jockey_debut_win_rate_min":
                cond = {"is_debut": 1, "jockey_debut_win_rate_min": thr}
                claim = f"新馬戦で騎手新馬率≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            elif signal == "trainer_debut_win_rate_min":
                cond = {"is_debut": 1, "trainer_debut_win_rate_min": thr}
                claim = f"新馬戦で調教師新馬率≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            else:
                cond = {"is_debut": 1, "sire_debut_win_rate_min": thr}
                claim = f"新馬戦で父馬新馬率≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            insights.append({
                "category": "DBT",
                "condition": cond,
                "claim": claim,
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.55 + (r["n"] - 40) / 800, 0.78),
            })

    # SHG: 障害戦の高スコア・高経験条件
    df_shg = stats.get("SHG", pd.DataFrame())
    for _, r in df_shg.iterrows():
        if r["win_rate"] >= baseline_win + 0.08 and r["n"] >= 20:
            signal = str(r["signal"])
            thr = float(r["threshold"])
            if signal == "shogai_score_min":
                cond = {"is_shogai": 1, "shogai_score_min": thr}
                claim = f"障害戦でshogai_score≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            elif signal == "shogai_keiken_min":
                cond = {"is_shogai": 1, "shogai_keiken_min": thr}
                claim = f"障害戦で経験{thr:.0f}戦以上は勝率{r['win_rate']:.0%}"
            elif signal == "jockey_shogai_win_rate_min":
                cond = {"is_shogai": 1, "jockey_shogai_win_rate_min": thr}
                claim = f"障害戦で騎手障害率≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            elif signal == "trainer_shogai_win_rate_min":
                cond = {"is_shogai": 1, "trainer_shogai_win_rate_min": thr}
                claim = f"障害戦で調教師障害率≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            else:
                cond = {"is_shogai": 1, "training_score_v2_min": thr}
                claim = f"障害戦で調教スコア≥{thr:.2f}は勝率{r['win_rate']:.0%}"
            insights.append({
                "category": "SHG",
                "condition": cond,
                "claim": claim,
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.55 + (r["n"] - 20) / 400, 0.78),
            })

    # TRN_training: 調教スコアの閾値パターン
    df_trn = stats.get("TRN_training", pd.DataFrame())
    for _, r in df_trn.iterrows():
        if r["win_rate"] >= baseline_win + 0.08 and r["n"] >= 100:
            thr = float(r["threshold"])
            insights.append({
                "category": "TRN",
                "condition": {"training_score_v2_min": thr},
                "claim": f"調教スコア≥{thr:.2f}は勝率{r['win_rate']:.0%}",
                "evidence_count": int(r["n"]),
                "estimated_lift": round(r["win_rate"] / baseline_win, 2),
                "confidence_prior": min(0.58 + (r["n"] - 100) / 1000, 0.80),
            })

    return insights


def run_historical_batch(year_from: int = 2000, use_llm: bool = True):
    """
    2000年〜現在までの全レース結果から知見を一括抽出・登録。

    Args:
        year_from: 集計開始年（デフォルト2000）
        use_llm:   True=Haiku API使用 / False=ルールベース
    """
    print(f"\n{'='*60}")
    print(f"📚 歴史的知見バッチ処理 ({year_from}年〜{datetime.now().year}年)")
    print(f"   モード: {'Haiku API' if use_llm and _ANTHROPIC_KEY else 'ルールベース'}")
    print(f"{'='*60}")
    t0 = time.time()

    store = KnowledgeStore()
    state = store.rebuild_latest()
    snaps = sorted([f for f in os.listdir(SNAP_DIR) if f.endswith(".json")])
    version = f"v{len(snaps)+1:03d}_hist"

    # ── Phase 1: DB集計 ───────────────────────────────────────
    engine = create_engine(DB_URL)
    try:
        stats = _compute_historical_stats(engine, year_from)
    finally:
        engine.dispose()

    # ── Phase 2: 知見抽出 ─────────────────────────────────────
    all_insights: List[Dict] = []

    cat_map = {
        "BLD_baba":         "父馬×馬場状態 血統パターン",
        "BLD_dist":         "父馬×距離 血統パターン",
        "BLD_venue":        "父馬×競馬場×距離 3way血統パターン",
        "JKY":              "騎手×競馬場パターン",
        "JKY_baba_dist":    "騎手×馬場×距離 細分化パターン",
        "TRK":              "脚質×コース特性",
        "TRK_venue_dist":   "競馬場×距離×脚質 細分化パターン",
        "SEA":              "季節・月別パターン",
        "AGE_dist_season":  "馬齢×距離×季節 細分化パターン",
        "MKT":              "市場効率性（人気別）",
        "MKT_ninki_month":  "穴人気×月 ROIパターン",
        "MKT_upset_profile":"穴馬プロファイル（人気帯×距離×グレード）",
        "TRN_weight":       "体重増減×人気 勝率パターン",
        "TRN_training":     "調教スコア閾値",
        "GRADE":            "グレード別穴馬出現",
        "DBT":              "新馬戦スコア・新馬実績",
        "SHG":              "障害戦スコア・障害経験",
    }

    if use_llm and _ANTHROPIC_KEY:
        print("\n  🤖 Haiku APIで知見抽出中...")
        for cat_key, cat_label in cat_map.items():
            stats_text = _format_stats_for_llm(stats, cat_key)
            if not stats_text:
                continue
            print(f"    📎 {cat_label}...")
            insights = _extract_historical_insights_llm(stats_text, cat_label)
            print(f"       → {len(insights)}件")
            all_insights.extend(insights)
            time.sleep(0.3)
    else:
        print("\n  ⚙️ ルールベースで知見抽出中...")
        all_insights = _extract_historical_insights_rule(stats)
        print(f"  → {len(all_insights)}件抽出")

    # ── Phase 3: 重複チェック・登録 ──────────────────────────
    print(f"\n  📥 知識ベースへ登録（候補: {len(all_insights)}件）...")
    creates, confirms, merges = deduplicate_and_assign(all_insights, state)
    print(f"     新規: {len(creates)}件 / 重複確認: {len(confirms)}件 / マージ候補: {len(merges)}件")

    created_count = 0
    for ins in creates:
        new_id = f"{ins.get('category','XX')}-{str(uuid.uuid4())[:6].upper()}"
        item   = _new_item(ins, version)
        item["id"] = new_id
        # 歴史データ由来 → 信頼度を事前情報で初期化
        prior = ins.get("confidence_prior", 0.5)
        n_eff = ins.get("evidence_count", 0)
        # α,β を事前確率と証拠数から逆算
        alpha = max(2, round(prior * min(n_eff / 10, 50)))
        beta  = max(2, round((1 - prior) * min(n_eff / 10, 50)))
        item["alpha"]       = alpha
        item["beta"]        = beta
        item["confidence"]  = round(alpha / (alpha + beta), 4)
        item["sample_count"] = n_eff
        item["source"]      = f"historical_batch_{year_from}_{datetime.now().year}"
        store.append_event({"event": "CREATE", "id": new_id, "data": item})
        created_count += 1

    for item_id, rc in confirms:
        store.append_event({"event": "CONFIRM", "id": item_id, "race_code": rc})

    # マージ（LLM判断）
    for m in merges:
        existing_item = state.get(m["existing_id"], {})
        verdict = resolve_merge_with_llm(m["new"], existing_item, m["score"]) \
                  if (use_llm and _ANTHROPIC_KEY and m["score"] < 0.7) else \
                  ("merge" if m["score"] >= 0.7 else "create")
        if verdict == "merge":
            store.append_event({
                "event": "MERGE", "id": m["existing_id"],
                "id_from": f"TEMP_{uuid.uuid4().hex[:6]}", "reason": f"hist_overlap={m['score']:.2f}",
            })
        elif verdict == "create":
            new_id = f"{m['new'].get('category','XX')}-{str(uuid.uuid4())[:6].upper()}"
            item   = _new_item(m["new"], version)
            item["id"] = new_id
            store.append_event({"event": "CREATE", "id": new_id, "data": item})
            created_count += 1

    # ── Phase 4: 最終確定 ─────────────────────────────────────
    state = store.rebuild_latest()

    # 廃止チェック
    for item_id, item in state.items():
        if item.get("status") == "active":
            conf = item.get("confidence", 0.5)
            n    = item.get("sample_count", 0)
            if n >= MIN_SAMPLES and conf < CONF_DEPRECATE:
                store.append_event({
                    "event": "DEPRECATE", "id": item_id,
                    "reason": f"confidence={conf:.3f}",
                })

    state = store.rebuild_latest()

    # スナップショット（歴史バッチは必ず作成）
    snap_name = store.create_snapshot(state)
    print(f"\n  📸 スナップショット: {snap_name}")

    # フィードバック
    generate_ev_boost_map(state)
    apply_knowledge_to_features(state)

    # Changelog
    update_changelog(created_count, len(confirms), 0, state, version)

    # レポート
    print_knowledge_report(state)

    elapsed = time.time() - t0
    active  = sum(1 for v in state.values() if v.get("status") == "active")
    high    = sum(1 for v in state.values()
                  if v.get("status") == "active" and v.get("confidence", 0) >= CONF_HARD)

    print(f"\n{'='*60}")
    print(f"✅ 歴史的バッチ完了 ({elapsed:.1f}秒)")
    print(f"   総アクティブ知見: {active}件  高確信度: {high}件")
    print(f"   今回新規登録:     {created_count}件")
    print(f"{'='*60}")

    return state


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",        type=int,  default=7)
    parser.add_argument("--snapshot",    action="store_true")
    parser.add_argument("--historical",  action="store_true", help="2000年〜一括処理")
    parser.add_argument("--year-from",   type=int,  default=2000)
    parser.add_argument("--no-llm",      action="store_true",
                        help="LLMを使わずルールベースのみ")
    args = parser.parse_args()

    if args.check:
        check_knowledge_base()
    elif args.historical:
        run_historical_ingestion(year_from=args.year_from, use_llm=not args.no_llm)
    else:
        run_knowledge_curator(use_llm=not args.no_llm)
