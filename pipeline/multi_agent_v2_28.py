"""
うまなり地蔵AI マルチエージェント v2
─────────────────────────────────────
14エージェント 並列・階層型アーキテクチャ

Supervisor (Claude Sonnet) が全体を統括
  ├── [並列フェーズ]
  │   ├── DataAgent       DB データ取得
  │   ├── BloodAgent      血統・ニックス分析
  │   ├── PaceAgent       ペース・調教分析
  │   ├── TrainingAgent   調教マルチセッション v2
  │   ├── TrainerAgent    調教師特性分析
  │   ├── DebutAgent      新馬戦強化分析
  │   ├── ShogaiAgent     障害戦強化分析
  │   └── OddsSignalAgent SHARP/STEAM シグナル
  ├── MLEnsembleAgent   LGB+XGB+CB+NN アンサンブル
  ├── EVAgent           期待値フィルタ（新馬戦・障害戦専用式）
  ├── RiskAgent         高度リスク管理
  ├── CommentaryAgent   Claude Haiku コメント生成
  └── PublisherAgent    全 SNS 一括配信

依存: pip install langgraph langchain langchain-anthropic anthropic
"""

from __future__ import annotations

import os
import sys
import json
import pickle
import operator
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any, Optional, Sequence

# Allow `from pipeline.xxx` imports when run directly
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import pandas as pd
import numpy as np
from pipeline.config import BASE_DIR, CSV_FEATURES, CSV_RAW, DATA_DIR, PEDIGREE_OUTPUT_DIR
from pipeline.native_runtime import ensure_native_runtime

from langgraph.graph import StateGraph, END
from langgraph.types import Send

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────

ensure_native_runtime()

MODEL_FILE  = os.path.join(BASE_DIR, "model_v8.pkl")
FEAT_FILE   = CSV_FEATURES
RAW_FILE    = CSV_RAW

EV_THRESHOLD   = 0.15
MIN_ODDS       = 10.0
MAX_DAY_RATIO  = 0.20
MAX_BET_RATIO  = 0.05
MIN_BANKROLL   = 10_000

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ─────────────────────────────────────────────────────────────
# 共有ステート
# ─────────────────────────────────────────────────────────────

class HorsePick(TypedDict):
    race_code:            str
    umaban:               int
    bamei:                str
    odds:                 float
    win_probability:      float
    expected_value:       float
    kelly_bet:            int
    risk_approved:        bool
    comment:              str
    nick_index:           float
    training_score:       float
    training_score_v2:    float
    training_form:        str
    jt_win_rate:          float
    blood_score:          float
    trainer_hot_cold:     float
    trainer_specialty:    float
    odds_signal_boost:       float
    is_shogai:               int
    jockey_shogai_win_rate:  float
    trainer_shogai_win_rate: float
    shogai_keiken:           int
    shogai_score:            float
    confidence:              float   # 総合確信度 0〜1


class AgentState(TypedDict):
    year:             int
    bankroll:         float
    # フェーズ1 並列出力（7エージェント）
    data_ready:       bool
    blood_results:    List[Dict]
    pace_results:     List[Dict]
    training_results: List[Dict]   # TrainingAgent: training_score_v2 / form
    trainer_results:  List[Dict]   # TrainerAgent: hot_cold / specialty
    debut_results:    List[Dict]   # DebutAgent: 新馬戦特化スコア
    shogai_results:   List[Dict]   # ShogaiAgent: 障害戦特化スコア
    odds_signals:     List[Dict]   # OddsSignalAgent: SHARP/STEAM race_code別
    # フェーズ2 ML
    ev_candidates:    List[Dict]
    # フェーズ3 以降
    predictions:      List[HorsePick]
    approved_bets:    List[HorsePick]
    risk_summary:     Dict[str, Any]
    # コメント
    comments:         Dict[str, str]   # bamei → comment
    # 発信
    post_text:        str
    supervisor_notes: str
    # ログ
    errors:           Annotated[List[str], operator.add]
    log:              Annotated[List[str], operator.add]


# ─────────────────────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _load_bankroll() -> float:
    path = os.path.join(DATA_DIR, "bankroll.json")
    if not os.path.exists(path):
        return 100_000.0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return float(data.get("current", data.get("bankroll", 100_000)))


def _call_claude(system: str, user: str, model: str = "claude-haiku-4-5-20251001",
                 max_tokens: int = 200) -> str:
    """Anthropic API 呼び出し。キー未設定時は空文字を返す。"""
    if not _ANTHROPIC_KEY:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"[API エラー: {e}]"


# ─────────────────────────────────────────────────────────────
# エージェント 1: DataAgent
# ─────────────────────────────────────────────────────────────

def data_agent(state: AgentState) -> AgentState:
    tag = "[DataAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    feat_ok = os.path.exists(FEAT_FILE)
    if feat_ok:
        age_h = (datetime.now().timestamp() - os.path.getmtime(FEAT_FILE)) / 3600
        if age_h < 6:
            log.append(f"{tag} キャッシュ使用（{age_h:.1f}h前）")
            return {**state, "data_ready": True, "log": log}

    try:
        from pipeline.data_fetch_01 import fetch_data
        from pipeline.feature_eng_02 import feature_engineering
        log.append(f"{tag} DB 取得中...")
        fetch_data()
        log.append(f"{tag} 特徴量計算中...")
        feature_engineering()
        log.append(f"{tag} 完了")
        return {**state, "data_ready": True, "log": log}
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "data_ready": feat_ok, "errors": [err], "log": log + [err]}


# ─────────────────────────────────────────────────────────────
# エージェント 2: BloodAgent（血統・ニックス）
# ─────────────────────────────────────────────────────────────

def blood_agent(state: AgentState) -> AgentState:
    tag = "[BloodAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        nicks_path = os.path.join(PEDIGREE_OUTPUT_DIR, "nicks_feature.csv")
        if not os.path.exists(nicks_path):
            log.append(f"{tag} nicks_feature.csv なし（スキップ）")
            return {**state, "blood_results": [], "log": log}

        nicks = pd.read_csv(nicks_path, encoding="utf-8-sig")
        # 高ニックス（>1.5）かつ有意なコンボ
        hot = nicks[
            (nicks["nick_index"] >= 1.5) &
            (nicks.get("nick_significant", True) == True)
        ].head(200)

        for _, row in hot.iterrows():
            results.append({
                "chichi":      row.get("chichi", ""),
                "haha_chichi": row.get("haha_chichi", ""),
                "nick_index":  float(row.get("nick_index", 1.0)),
                "nick_roi":    float(row.get("nick_roi", 1.0)),
                "nick_win_rate": float(row.get("nick_win_rate", 0.0)),
            })

        log.append(f"{tag} 高ニックス組合せ: {len(results)}件")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "blood_results": [], "errors": [err], "log": log + [err]}

    return {**state, "blood_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3: PaceAgent（ペース・調教）
# ─────────────────────────────────────────────────────────────

def pace_agent(state: AgentState) -> AgentState:
    tag = "[PaceAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        if not os.path.exists(FEAT_FILE):
            log.append(f"{tag} 特徴量ファイルなし")
            return {**state, "pace_results": [], "log": log}

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False)
        year = state.get("year", datetime.now().year)
        df = df[df["kaisai_nen"] == year].fillna(0)

        if "training_score" not in df.columns:
            df["training_score"] = 0.0

        # 調教スコア上位馬をリストアップ
        top_training = df.nlargest(500, "training_score")
        for _, row in top_training.iterrows():
            if float(row.get("training_score", 0)) > 0.01:
                results.append({
                    "ketto_toroku_bango": str(row.get("ketto_toroku_bango", "")),
                    "bamei":             str(row.get("bamei", "")),
                    "training_score":    float(row.get("training_score", 0)),
                    "dist_category":     int(row.get("dist_category", 1)),
                    "pace_consistency":  float(row.get("pace_consistency", 0)),
                })

        log.append(f"{tag} 高調教スコア馬: {len(results)}頭")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "pace_results": [], "errors": [err], "log": log + [err]}

    return {**state, "pace_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3b: TrainingAgent（調教マルチセッション v2）
# ─────────────────────────────────────────────────────────────

def training_agent(state: AgentState) -> AgentState:
    tag = "[TrainingAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        if not os.path.exists(FEAT_FILE):
            return {**state, "training_results": [], "log": log}

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                         on_bad_lines='skip')
        year = state.get("year", datetime.now().year)
        df = df[df["kaisai_nen"] == year].fillna(0)

        score_col = "training_score_v2" if "training_score_v2" in df.columns else "training_score"
        form_col  = "training_form"      if "training_form"      in df.columns else None

        top = df.nlargest(1000, score_col)
        for _, row in top.iterrows():
            sc = float(row.get(score_col, 0))
            if sc < 0.01:
                continue
            results.append({
                "ketto_toroku_bango": str(row.get("ketto_toroku_bango", "")),
                "bamei":              str(row.get("bamei", "")),
                "training_score_v2":  sc,
                "training_form":      str(row.get(form_col, "D")) if form_col else "D",
                "wood_trend":         float(row.get("wood_trend", 0)),
                "wood_sessions14d":   int(row.get("wood_sessions14d", 0)),
            })

        log.append(f"{tag} 調教スコアv2上位馬: {len(results)}頭  "
                   f"FormA={sum(1 for r in results if r['training_form']=='A')}頭")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "training_results": [], "errors": [err], "log": log + [err]}

    return {**state, "training_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3c: TrainerAgent（調教師特性）
# ─────────────────────────────────────────────────────────────

def trainer_agent(state: AgentState) -> AgentState:
    tag = "[TrainerAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        if not os.path.exists(FEAT_FILE):
            return {**state, "trainer_results": [], "log": log}

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                         on_bad_lines='skip')
        year = state.get("year", datetime.now().year)
        df = df[df["kaisai_nen"] == year].fillna(0)

        has_hot  = "trainer_hot_cold"      in df.columns
        has_spec = "trainer_specialty_score" in df.columns
        if not (has_hot or has_spec):
            log.append(f"{tag} 調教師特徴量なし（trainer_analysis_38 未実行？）")
            return {**state, "trainer_results": [], "log": log}

        for _, row in df.iterrows():
            hc   = float(row.get("trainer_hot_cold", 0))
            spec = float(row.get("trainer_specialty_score", 0))
            if hc < 0.01 and spec < 0.01:
                continue
            results.append({
                "ketto_toroku_bango":  str(row.get("ketto_toroku_bango", "")),
                "bamei":               str(row.get("bamei", "")),
                "trainer_hot_cold":    hc,
                "trainer_specialty":   spec,
                "trainer_tozai":       int(row.get("trainer_tozai", 0)),
                "trainer_win_rate":    float(row.get("trainer_win_rate_honnen", 0)),
            })

        log.append(f"{tag} 調教師特徴量: {len(results)}頭  "
                   f"好調(>0.6)={sum(1 for r in results if r['trainer_hot_cold']>0.6)}頭")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "trainer_results": [], "errors": [err], "log": log + [err]}

    return {**state, "trainer_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3c2: DebutAgent（新馬戦強化）
# ─────────────────────────────────────────────────────────────

def debut_agent(state: AgentState) -> AgentState:
    tag = "[DebutAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        if not os.path.exists(FEAT_FILE):
            return {**state, "debut_results": [], "log": log}

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                         on_bad_lines='skip')
        year = state.get("year", datetime.now().year)
        df = df[df["kaisai_nen"] == year].fillna(0)

        has_debut = "is_debut" in df.columns
        if not has_debut:
            log.append(f"{tag} debut特徴量なし（debut_analysis_39 未実行？）")
            return {**state, "debut_results": [], "log": log}

        debut_df = df[df["is_debut"] == 1]

        # 当年データでis_debut=1がない場合は barei+prev_chakujun でフォールバック
        if len(debut_df) == 0 and "barei" in df.columns:
            prev_col = "prev_chakujun" if "prev_chakujun" in df.columns else None
            if prev_col:
                mask = (pd.to_numeric(df["barei"], errors='coerce') <= 2) & \
                       (pd.to_numeric(df[prev_col], errors='coerce').isna() |
                        (pd.to_numeric(df[prev_col], errors='coerce') == 0))
            else:
                mask = pd.to_numeric(df["barei"], errors='coerce') <= 2
            debut_df = df[mask]
            log.append(f"{tag} フォールバック検出: barei<=2+前走なし → {len(debut_df)}頭")
        for _, row in debut_df.iterrows():
            results.append({
                "race_code":             str(row.get("race_code", "")),
                "ketto_toroku_bango":    str(row.get("ketto_toroku_bango", "")),
                "bamei":                 str(row.get("bamei", "")),
                "debut_score":           float(row.get("debut_score", 0)),
                "jockey_debut_win_rate": float(row.get("jockey_debut_win_rate", 0.1)),
                "trainer_debut_win_rate":float(row.get("trainer_debut_win_rate", 0.1)),
                "sire_debut_win_rate":   float(row.get("sire_debut_win_rate", 0.1)),
                "debut_weight_bonus":    float(row.get("debut_weight_bonus", 0.5)),
            })

        log.append(f"{tag} 新馬戦エントリ: {len(results)}頭  "
                   f"debut_score≥0.5: {sum(1 for r in results if r['debut_score']>=0.5)}頭")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "debut_results": [], "errors": [err], "log": log + [err]}

    return {**state, "debut_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3c3: ShogaiAgent（障害戦強化）
# ─────────────────────────────────────────────────────────────

def shogai_agent(state: AgentState) -> AgentState:
    tag = "[ShogaiAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    results: List[Dict] = []
    try:
        if not os.path.exists(FEAT_FILE):
            return {**state, "shogai_results": [], "log": log}

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False,
                         on_bad_lines='skip')
        year = state.get("year", datetime.now().year)
        df = df[df["kaisai_nen"] == year].fillna(0)

        if "is_shogai" not in df.columns:
            log.append(f"{tag} 障害特徴量なし（shogai_analysis_40 未実行？）")
            return {**state, "shogai_results": [], "log": log}

        shogai_df = df[df["is_shogai"] == 1]
        for _, row in shogai_df.iterrows():
            results.append({
                "race_code":                str(row.get("race_code", "")),
                "ketto_toroku_bango":       str(row.get("ketto_toroku_bango", "")),
                "bamei":                    str(row.get("bamei", "")),
                "shogai_score":             float(row.get("shogai_score", 0)),
                "shogai_keiken":            int(row.get("shogai_keiken", 0)),
                "jockey_shogai_win_rate":   float(row.get("jockey_shogai_win_rate", 0)),
                "trainer_shogai_win_rate":  float(row.get("trainer_shogai_win_rate", 0)),
            })

        log.append(f"{tag} 障害レースエントリ: {len(results)}頭  "
                   f"shogai_score≥0.5: {sum(1 for r in results if r['shogai_score']>=0.5)}頭")
    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "shogai_results": [], "errors": [err], "log": log + [err]}

    return {**state, "shogai_results": results, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 3d: OddsSignalAgent（SHARP/STEAM シグナル検知）
# ─────────────────────────────────────────────────────────────

def odds_signal_agent(state: AgentState) -> AgentState:
    tag = "[OddsSignal]"
    log = [f"{tag} 起動 {_ts()}"]

    signals: List[Dict] = []
    try:
        data_dir = DATA_DIR
        date_str  = datetime.now().strftime('%Y%m%d')
        snap_path = f"{data_dir}\\odds_snapshot_{date_str}.json"

        if not os.path.exists(snap_path):
            log.append(f"{tag} 本日スナップショットなし ({snap_path})")
            return {**state, "odds_signals": [], "log": log}

        with open(snap_path, encoding='utf-8') as f:
            snapshot_now = json.load(f)

        # 前回スナップショットを探す（同日の古いもの）
        import glob as _glob
        prev_snaps = sorted(
            _glob.glob(f"{data_dir}\\odds_snapshot_*.json"),
            key=os.path.getmtime
        )
        # 今日以外の直近スナップ
        others = [p for p in prev_snaps if date_str not in os.path.basename(p)]

        if others:
            with open(others[-1], encoding='utf-8') as f:
                snapshot_prev = json.load(f)
            try:
                from pipeline.odds_scraper_36 import detect_movements
                raw_signals = detect_movements(snapshot_prev, snapshot_now)
                for s in raw_signals:
                    s['boost'] = 0.10 if s['movement'] == 'SHARP' else 0.05
                signals = raw_signals
                log.append(f"{tag} SHARP/STEAM シグナル: {len(signals)}件")
            except Exception as e:
                log.append(f"{tag} detect_movements エラー: {e}")
        else:
            # スナップショット1枚だけ → 単騎分析（単勝1倍台/30倍超を記録）
            for race in snapshot_now:
                for bamei, h in race.get('horses', {}).items():
                    od = h.get('tansho', 0)
                    if od > 0 and od < 2.0 and h.get('ninki', 99) == 1:
                        signals.append({
                            'race_id': race['race_id'], 'bamei': bamei,
                            'movement': 'HEAVY_FAV', 'pct': 0, 'boost': -0.05
                        })
            log.append(f"{tag} 単一スナップ分析: 断然人気 {len(signals)}頭をマイナスシグナル登録")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "odds_signals": [], "errors": [err], "log": log + [err]}

    return {**state, "odds_signals": signals, "log": log}


# ─────────────────────────────────────────────────────────────
# 並列フェーズのルーティング
# ─────────────────────────────────────────────────────────────

def route_parallel(state: AgentState) -> List[Send]:
    """DataAgent 完了後に BloodAgent と PaceAgent を並列起動。"""
    return [
        Send("blood_agent", state),
        Send("pace_agent",  state),
    ]


def merge_parallel(state: AgentState) -> AgentState:
    """並列結果をマージ（ステートはすでに統合されている）。"""
    log = [f"[Merge] 並列分析完了 {_ts()} "
           f"blood={len(state.get('blood_results', []))} "
           f"pace={len(state.get('pace_results', []))} "
           f"training={len(state.get('training_results', []))} "
           f"trainer={len(state.get('trainer_results', []))} "
           f"debut={len(state.get('debut_results', []))} "
           f"shogai={len(state.get('shogai_results', []))} "
           f"signals={len(state.get('odds_signals', []))}"]
    return {**state, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 4: MLEnsembleAgent
# ─────────────────────────────────────────────────────────────

def ml_ensemble_agent(state: AgentState) -> AgentState:
    tag = "[MLEnsemble]"
    log = [f"{tag} 起動 {_ts()}"]

    if not state.get("data_ready") or not os.path.exists(FEAT_FILE):
        return {**state, "ev_candidates": [], "log": log + [f"{tag} データ未準備"]}

    try:
        with open(MODEL_FILE, "rb") as f:
            saved = pickle.load(f)

        lgb_model = saved["lgb_model"]
        xgb_model = saved["xgb_model"]
        cb_model  = saved["cb_model"]
        le        = saved["le"]
        features  = saved["features"]
        weights   = saved.get("ensemble_weights", [0.5, 0.3, 0.2])
        log.append(f"{tag} モデル読込 ({len(features)}特徴量)")

        year = state.get("year", datetime.now().year)

        # 当日出馬表ファイルがあれば優先使用（バックテスト回避）
        today_str  = datetime.now().strftime("%Y%m%d")
        today_file = os.path.join(DATA_DIR, f"today_entries_{today_str}.csv")
        if os.path.exists(today_file):
            df = pd.read_csv(today_file, encoding="utf-8-sig", low_memory=False)
            log.append(f"{tag} 当日出馬表使用: {today_file} ({len(df)}頭)")
        else:
            df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False)
            df = df[df["kaisai_nen"] == year]
            log.append(f"{tag} 特徴量CSV使用: {len(df)}行 (バックテストモード)")

        df = df.fillna(0)
        if len(df) == 0:
            return {**state, "ev_candidates": [], "log": log + [f"{tag} {year}年データなし"]}

        # object型列を数値変換（seibetsu_codeなど文字列で入るカラム対策）
        for col in df.select_dtypes(include='object').columns:
            if col in features:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 欠損特徴量を0で補完（モデルの期待する列数を保証）
        for f in features:
            if f not in df.columns:
                df[f] = 0

        feats = [f for f in features if f in df.columns]
        X = df[feats]

        lgb_p = lgb_model.predict_proba(X)
        xgb_p = xgb_model.predict_proba(X)
        cb_p  = (cb_model.predict_proba(X) if cb_model is not None else 0)

        # NN モデルがあれば追加
        nn_path = os.path.join(BASE_DIR, "model_nn.pth")
        if os.path.exists(nn_path):
            try:
                import torch
                from pipeline.nn_stacking_22 import RaceMLP, nn_predict_proba
                nn_saved = torch.load(nn_path, map_location="cpu", weights_only=False)
                nn_model = RaceMLP(nn_saved["input_dim"], nn_saved["num_classes"])
                nn_model.load_state_dict(nn_saved["model_state"])
                nn_scaler = nn_saved["scaler"]
                nn_p = nn_predict_proba(nn_model, nn_scaler, X.values)
                # 重みに NN を追加（正規化）
                w = np.array(weights[:3] + [0.1])
                w = w / w.sum()
                ensemble_p = (w[0] * lgb_p + w[1] * xgb_p +
                              w[2] * cb_p  + w[3] * nn_p)
                log.append(f"{tag} NN 追加（重み: {w}）")
            except Exception as e:
                ensemble_p = (weights[0] * lgb_p + weights[1] * xgb_p +
                              weights[2] * cb_p)
                log.append(f"{tag} NN スキップ: {e}")
        else:
            ensemble_p = (weights[0] * lgb_p + weights[1] * xgb_p +
                          weights[2] * cb_p)

        classes = list(le.classes_)
        win_idx = classes.index(1) if 1 in classes else 0
        win_probs = ensemble_p[:, win_idx]

        df = df.copy()
        df["win_probability"] = win_probs
        df["odds_decimal"]    = pd.to_numeric(
            df["tansho_odds"], errors="coerce").fillna(0) / 10
        df["expected_value"]  = df["win_probability"] * df["odds_decimal"] - 1.0

        # 血統スコアをマージ
        blood_map: Dict[str, float] = {}
        if state.get("blood_results") and "chichi" in df.columns and "haha_chichi" in df.columns:
            for b in state["blood_results"]:
                key = f"{b['chichi']}_{b['haha_chichi']}"
                blood_map[key] = b.get("nick_index", 1.0)
            df["blood_score"] = df.apply(
                lambda r: blood_map.get(f"{r.get('chichi','')}_{r.get('haha_chichi','')}", 1.0),
                axis=1
            )
        else:
            df["blood_score"] = 1.0

        # 調教スコア（旧）をマージ
        pace_map: Dict[str, float] = {}
        for p in state.get("pace_results", []):
            pace_map[str(p.get("ketto_toroku_bango", ""))] = p.get("training_score", 0)
        df["training_score_enriched"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: pace_map.get(k, df["training_score"].mean() if "training_score" in df else 0)
        )

        # 調教スコアv2（training_analysis_37）をマージ
        train_v2_map: Dict[str, Dict] = {}
        for t in state.get("training_results", []):
            train_v2_map[str(t.get("ketto_toroku_bango", ""))] = t
        df["training_score_v2_enr"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: train_v2_map.get(k, {}).get("training_score_v2",
                      df.get("training_score_v2", pd.Series([0])).mean())
        )
        df["training_form_enr"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: train_v2_map.get(k, {}).get("training_form", "D")
        )

        # 調教師特性（trainer_analysis_38）をマージ
        trainer_map: Dict[str, Dict] = {}
        for t in state.get("trainer_results", []):
            trainer_map[str(t.get("ketto_toroku_bango", ""))] = t
        df["trainer_hot_cold_enr"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: trainer_map.get(k, {}).get("trainer_hot_cold", 0.5)
        )
        df["trainer_specialty_enr"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: trainer_map.get(k, {}).get("trainer_specialty", 0.5)
        )

        # 新馬戦スコア（debut_analysis_39）をマージ
        debut_map: Dict[str, Dict] = {}
        for d in state.get("debut_results", []):
            key = str(d.get("race_code", "")) + str(d.get("bamei", ""))
            debut_map[key] = d
        df["is_debut_enr"] = df.apply(
            lambda r: 1 if (str(r.get("race_code",""))+str(r.get("bamei",""))) in debut_map else 0,
            axis=1
        )
        df["debut_score_enr"] = df.apply(
            lambda r: debut_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("debut_score", 0.0), axis=1
        )
        df["jockey_debut_rate_enr"] = df.apply(
            lambda r: debut_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("jockey_debut_win_rate", 0.1), axis=1
        )
        df["trainer_debut_rate_enr"] = df.apply(
            lambda r: debut_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("trainer_debut_win_rate", 0.1), axis=1
        )

        # 障害戦スコア（shogai_analysis_40）をマージ
        shogai_map: Dict[str, Dict] = {}
        for s in state.get("shogai_results", []):
            key = str(s.get("race_code", "")) + str(s.get("bamei", ""))
            shogai_map[key] = s
        df["is_shogai_enr"] = df.apply(
            lambda r: 1 if (str(r.get("race_code",""))+str(r.get("bamei",""))) in shogai_map else 0,
            axis=1
        )
        df["shogai_score_enr"] = df.apply(
            lambda r: shogai_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("shogai_score", 0.0), axis=1
        )
        df["jockey_shogai_rate_enr"] = df.apply(
            lambda r: shogai_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("jockey_shogai_win_rate", 0.0), axis=1
        )
        df["trainer_shogai_rate_enr"] = df.apply(
            lambda r: shogai_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("trainer_shogai_win_rate", 0.0), axis=1
        )
        df["shogai_keiken_enr"] = df.apply(
            lambda r: shogai_map.get(
                str(r.get("race_code",""))+str(r.get("bamei","")), {}
            ).get("shogai_keiken", 0), axis=1
        )

        # オッズシグナルをレース単位でマージ
        # netkeiba 12桁 (YYYYKKAANNRR) と JV 16桁 (YYYYMMDDKKAANNRR) を統一
        # 変換: jv16[:4] + jv16[8:] = netkeiba12
        def _to_net12(key: str) -> str:
            k = str(key).strip()
            return k[:4] + k[8:] if len(k) == 16 else k

        signal_map: Dict[str, float] = {}
        for s in state.get("odds_signals", []):
            raw = s.get("race_id", s.get("race_code", ""))
            rc_key = _to_net12(raw)
            signal_map[rc_key] = signal_map.get(rc_key, 0) + s.get("boost", 0)

        # EV フィルタ（EV≥5% かつオッズ≥10倍）
        top = df[
            (df["expected_value"] >= EV_THRESHOLD) &
            (df["odds_decimal"]   >= MIN_ODDS)
        ].sort_values("expected_value", ascending=False)

        candidates = []
        for rc, race in top.groupby("race_code"):
            best = race.iloc[0]
            rc_str = str(rc)
            candidates.append({
                "race_code":          rc_str,
                "umaban":             int(best.get("umaban", 0)),
                "bamei":              str(best.get("bamei", "")),
                "odds":               float(best["odds_decimal"]),
                "win_probability":    float(best["win_probability"]),
                "expected_value":     float(best["expected_value"]),
                "blood_score":        float(best.get("blood_score", 1.0)),
                "training_score":     float(best.get("training_score_enriched", 0)),
                "training_score_v2":  float(best.get("training_score_v2_enr", 0)),
                "training_form":      str(best.get("training_form_enr", "D")),
                "trainer_hot_cold":   float(best.get("trainer_hot_cold_enr", 0.5)),
                "trainer_specialty":  float(best.get("trainer_specialty_enr", 0.5)),
                "odds_signal_boost":  float(signal_map.get(_to_net12(rc_str), 0)),
                "is_debut":             int(best.get("is_debut_enr", 0)),
                "debut_score":          float(best.get("debut_score_enr", 0)),
                "jockey_debut_rate":    float(best.get("jockey_debut_rate_enr", 0.1)),
                "trainer_debut_rate":   float(best.get("trainer_debut_rate_enr", 0.1)),
                "is_shogai":            int(best.get("is_shogai_enr", 0)),
                "shogai_score":         float(best.get("shogai_score_enr", 0)),
                "jockey_shogai_rate":   float(best.get("jockey_shogai_rate_enr", 0)),
                "trainer_shogai_rate":  float(best.get("trainer_shogai_rate_enr", 0)),
                "shogai_keiken":        int(best.get("shogai_keiken_enr", 0)),
                "jt_win_rate":          float(best.get("jt_win_rate", 0)),
                "nick_index":         float(best.get("nick_index", 1.0)),
                "kishumei":           str(best.get("kishumei_ryakusho", "")),
                "barei":              int(best.get("barei", 0)),
                "bataiju":            int(best.get("bataiju", 0)),
            })

        log.append(f"{tag} EV候補: {len(candidates)}R")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "ev_candidates": [], "errors": [err], "log": log + [err]}

    return {**state, "ev_candidates": candidates, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 5: EVAgent（期待値フィルタ + 信頼スコア）
# ─────────────────────────────────────────────────────────────

def ev_agent(state: AgentState) -> AgentState:
    tag = "[EVAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    cands = state.get("ev_candidates", [])
    if not cands:
        return {**state, "predictions": [], "log": log + [f"{tag} 候補なし"]}

    try:
        bankroll = state.get("bankroll", _load_bankroll())
        from pipeline.kelly_bankroll_09 import calculate_kelly_bet

        # レース価値スコアをロード（race_selector_31 の出力）
        race_scores: Dict[str, float] = {}
        rs_path = os.path.join(DATA_DIR, f"race_selector_{state.get('year', 2026)}.json")
        if os.path.exists(rs_path):
            with open(rs_path, encoding='utf-8') as f:
                rs_data = json.load(f)
            race_scores = {r['race_code']: r.get('value_score', 0.5) for r in rs_data}
            log.append(f"{tag} レース価値スコア読込: {len(race_scores)}R")

        # 馬券種選択モジュールをロード
        try:
            from pipeline.ticket_optimizer_30 import select_optimal_ticket, calc_all_ticket_ev
            use_ticket_opt = True
        except ImportError:
            use_ticket_opt = False

        predictions: List[HorsePick] = []
        for c in cands:
            p    = c["win_probability"]
            odds = c["odds"]
            ev   = c["expected_value"]
            bet  = calculate_kelly_bet(bankroll, p, odds)
            rc   = c["race_code"]

            # レース価値スコアを確信度に組み込み
            race_val = race_scores.get(rc, 0.5)

            # 調教スコアv2: FormA=0.9/B=0.7/C=0.5/D=0.3 を基準に補正
            form_bonus = {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.3}.get(
                c.get("training_form", "D"), 0.5)
            train_v2_norm = min(
                0.6 * min(c.get("training_score_v2", 0) / 0.8, 1.0)
                + 0.4 * form_bonus, 1.0)

            is_debut  = c.get("is_debut", 0) == 1
            is_shogai = c.get("is_shogai", 0) == 1

            # ── 知識ベース EVboost（全レース共通） ────────────────────
            kb_boost = 0.0
            try:
                from pipeline.knowledge_curator_41 import load_ev_boost_for_race
                # c に df_row 相当の情報があるので Series に変換して渡す
                _row = pd.Series(c)
                kb_boost = load_ev_boost_for_race(rc, _row)
            except Exception:
                pass

            if is_shogai:
                # ── 障害戦専用確信度フォーミュラ ─────────────────────────
                # 経験(30%) + 騎手障害(25%) + 調教師障害(20%) + 調教v2(15%) + 血統(10%)
                keiken_norm  = min(c.get("shogai_keiken", 0) / 20.0, 1.0)
                j_sh_norm    = min(c.get("jockey_shogai_rate", 0) / 0.20, 1.0)
                t_sh_norm    = min(c.get("trainer_shogai_rate", 0) / 0.15, 1.0)
                confidence = min(1.0, max(0.0,
                    0.30 * keiken_norm                                           # 障害経験
                  + 0.25 * j_sh_norm                                             # 騎手障害勝率
                  + 0.20 * t_sh_norm                                             # 調教師障害勝率
                  + 0.15 * train_v2_norm                                         # 調教スコアv2
                  + 0.10 * min((c["blood_score"] - 1.0) / 2.0, 1.0)             # 血統
                  + kb_boost                                                     # 知識ベースboost
                ))
            elif is_debut:
                # ── 新馬戦専用確信度フォーミュラ ─────────────────────────
                # 過去成績なし → 調教・血統・騎手調教師の新馬戦実績を重視
                j_d_norm = min(c.get("jockey_debut_rate",  0.1) / 0.25, 1.0)
                t_d_norm = min(c.get("trainer_debut_rate", 0.1) / 0.25, 1.0)
                confidence = min(1.0, max(0.0,
                    0.35 * train_v2_norm                                     # 調教（最重要）
                  + 0.25 * min((c["blood_score"] - 1.0) / 2.0, 1.0)         # 血統ニックス
                  + 0.20 * t_d_norm                                          # 調教師の新馬戦勝率
                  + 0.15 * j_d_norm                                          # 騎手の新馬戦勝率
                  + 0.05 * c.get("odds_signal_boost", 0.0)                   # オッズシグナル
                  + kb_boost                                                  # 知識ベースboost
                ))
            else:
                # ── 通常レース確信度フォーミュラ（6シグナル × 重み）──────
                confidence = min(1.0, max(0.0,
                    0.28 * min(ev / 0.5, 1.0)                                # EV
                  + 0.18 * min((c["blood_score"] - 1.0) / 2.0, 1.0)         # 血統ニックス
                  + 0.18 * train_v2_norm                                     # 調教スコアv2
                  + 0.14 * min(c.get("trainer_hot_cold", 0.5), 1.0)          # 調教師好調度
                  + 0.12 * min(c["jt_win_rate"] * 5, 1.0)                   # 騎手×調教師
                  + 0.10 * race_val                                          # レース価値
                  + c.get("odds_signal_boost", 0.0)                         # SHARP/STEAMシグナル
                  + kb_boost                                                  # 知識ベースboost
                ))

            # 最適馬券種を選択
            ticket_type = "単勝"
            ticket_odds = odds
            if use_ticket_opt:
                try:
                    n_h = 12  # 頭数不明時のデフォルト
                    rec = select_optimal_ticket([c], bankroll, rc, n_h)
                    if rec:
                        ticket_type = rec.get("ticket_type", "単勝")
                        ticket_odds = rec.get("est_odds", odds)
                except Exception:
                    pass

            predictions.append({
                "race_code":          rc,
                "umaban":             c.get("umaban", 0),
                "bamei":              c["bamei"],
                "odds":               odds,
                "win_probability":    p,
                "expected_value":     ev,
                "kelly_bet":          bet,
                "risk_approved":      False,
                "comment":            "",
                "nick_index":         c.get("nick_index", 1.0),
                "training_score":     c.get("training_score", 0.0),
                "training_score_v2":  c.get("training_score_v2", 0.0),
                "training_form":      c.get("training_form", "D"),
                "jt_win_rate":        c.get("jt_win_rate", 0.0),
                "blood_score":        c.get("blood_score", 1.0),
                "trainer_hot_cold":   c.get("trainer_hot_cold", 0.5),
                "trainer_specialty":  c.get("trainer_specialty", 0.5),
                "odds_signal_boost":  c.get("odds_signal_boost", 0.0),
                "is_debut":             c.get("is_debut", 0),
                "debut_score":          c.get("debut_score", 0.0),
                "jockey_debut_rate":    c.get("jockey_debut_rate", 0.1),
                "trainer_debut_rate":   c.get("trainer_debut_rate", 0.1),
                "is_shogai":            c.get("is_shogai", 0),
                "shogai_score":         c.get("shogai_score", 0.0),
                "jockey_shogai_win_rate":  c.get("jockey_shogai_rate", 0.0),
                "trainer_shogai_win_rate": c.get("trainer_shogai_rate", 0.0),
                "shogai_keiken":        c.get("shogai_keiken", 0),
                "confidence":           round(confidence, 3),
                "ticket_type":        ticket_type,
                "ticket_odds":        ticket_odds,
                "race_value":         round(race_val, 3),
            })

        # 信頼スコア降順でソート
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        log.append(f"{tag} 確信度付き予想: {len(predictions)}頭")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "predictions": [], "errors": [err], "log": log + [err]}

    return {**state, "predictions": predictions, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 6: SupervisorAgent（Ollama優先 → Claude Sonnet → ルールベース）
# ─────────────────────────────────────────────────────────────

_SUPERVISOR_SYSTEM = """あなたは競馬予想AIの統括エージェント「うまなり地蔵」です。
各分析エージェントからの結果を受け取り、最終的な投資戦略を判断します。
回答は必ず JSON 形式で返してください。"""


def _supervisor_via_ollama(summary: str, bankroll: float) -> Optional[Dict]:
    """
    Ollama で Supervisor 判断を行う。
    Returns: {"top_picks": [...], "max_bet_fraction": float,
              "strategy": str, "confidence_overall": float}
    失敗時は None。
    """
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return None
        # JSON構造出力 → "json" プロファイル（deepseek-r1/phi4 優先）
        model = get_model_for_task("json")
        if not model:
            return None

        user_msg = (
            "現在資金: " + f"{bankroll:,.0f}" + "円\n"
            "本日の予想候補（信頼スコア降順）:\n" + summary + "\n\n"
            "以下をJSON形式で返してください（他の文字は不要）:\n"
            '{"top_picks": ["馬名1", "馬名2", "馬名3"], '
            '"max_bet_fraction": 0.15, '
            '"strategy": "戦略コメント（50文字以内）", '
            '"confidence_overall": 0.7}'
        )
        resp = _generate(user_msg, system=_SUPERVISOR_SYSTEM,
                         model=model, temperature=0.3, stream=False,
                         task="json")
        if not resp:
            return None
        import re
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            return json.loads(m.group())
        return None
    except Exception as e:
        print("  [Supervisor/Ollama] スキップ: " + str(e))
        return None


def supervisor_agent(state: AgentState) -> AgentState:
    tag = "[Supervisor]"
    log = [f"{tag} 起動 {_ts()}"]

    preds = state.get("predictions", [])
    if not preds:
        return {**state, "supervisor_notes": "候補なし", "log": log}

    summary_lines = []
    for p in preds[:10]:
        form  = p.get("training_form", "D")
        hc    = p.get("trainer_hot_cold", 0.5)
        sig   = p.get("odds_signal_boost", 0.0)
        sig_s = f" 🔥SHARP" if sig > 0.05 else ("⚠️断然" if sig < -0.03 else "")
        summary_lines.append(
            f"{p['bamei']}: EV={p['expected_value']*100:.0f}% "
            f"オッズ{p['odds']:.1f}x 確信度{p['confidence']*100:.0f}% "
            f"血統={p['blood_score']:.2f} 調教v2={p.get('training_score_v2',0):.3f}({form}) "
            f"調教師好調={hc:.2f}{sig_s}"
        )
    summary = "\n".join(summary_lines)
    bankroll = state.get("bankroll", 100_000)

    # 優先: Ollama（無料）→ Claude Sonnet（有料）→ ルールベース
    supervisor_data = _supervisor_via_ollama(summary, bankroll)
    llm_source = "Ollama"

    if supervisor_data is None and _ANTHROPIC_KEY:
        user_msg = (
            "現在資金: " + f"{bankroll:,.0f}" + "円\n"
            "本日の予想候補（信頼スコア降順）:\n" + summary + "\n\n"
            "以下を JSON で返してください:\n"
            '{"top_picks": ["馬名1", "馬名2", "馬名3"], '
            '"max_bet_fraction": 0.15, '
            '"strategy": "今日の戦略コメント（50文字以内）", '
            '"confidence_overall": 0.7}'
        )
        resp = _call_claude(
            system=_SUPERVISOR_SYSTEM, user=user_msg,
            model="claude-haiku-4-5-20251001", max_tokens=300  # Sonnet→Haiku でコスト削減
        )
        try:
            import re
            json_match = re.search(r"\{.*\}", resp, re.DOTALL)
            if json_match:
                supervisor_data = json.loads(json_match.group())
                llm_source = "Claude Haiku"
        except Exception:
            supervisor_data = None

    notes = "自動判断"
    if supervisor_data:
        notes = supervisor_data.get("strategy", "自動判断")
        top_picks = set(supervisor_data.get("top_picks", []))
        if top_picks:
            state["predictions"] = sorted(
                preds,
                key=lambda x: (x["bamei"] in top_picks, x["confidence"]),
                reverse=True
            )
        log.append(f"{tag} {llm_source} 判断完了: {notes}")
    else:
        # ルールベース: 確信度上位3頭を自動選定
        top3 = [p["bamei"] for p in preds[:3]]
        notes = "自動選定: " + ", ".join(top3)
        log.append(f"{tag} ルールベース判断")

    return {**state, "supervisor_notes": notes, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 7: RiskAgent（高度リスク管理）
# ─────────────────────────────────────────────────────────────

def risk_agent(state: AgentState) -> AgentState:
    tag = "[RiskAgent]"
    log = [f"{tag} 起動 {_ts()}"]

    preds    = state.get("predictions", [])
    bankroll = state.get("bankroll", _load_bankroll())

    # ドローダウン確認
    try:
        from pipeline.bankroll_advanced_24 import calc_drawdown, get_bet_multiplier
        from pipeline.bankroll_advanced_24 import get_current_bankroll
        bk_data = get_current_bankroll()
        dd = calc_drawdown(bk_data)
        mult = get_bet_multiplier(dd)
        if dd > 0.05:
            log.append(f"{tag} ドローダウン {dd*100:.1f}% → ベット乗数 {mult:.2f}x")
    except Exception:
        mult = 1.0

    if not preds:
        return {**state, "approved_bets": [], "risk_summary": {}, "log": log}

    # ポートフォリオ最適化でベット額を上書き
    try:
        from pipeline.bet_portfolio_29 import portfolio_optimize_all
        optimized, port_summary = portfolio_optimize_all(preds, bankroll)
        # portfolio_bet をケリーベットに反映
        port_map = {p.get("race_code", "") + p.get("bamei", ""): p.get("portfolio_bet", 0)
                    for p in optimized}
        for pred in preds:
            key = pred.get("race_code", "") + pred.get("bamei", "")
            if key in port_map and port_map[key] > 0:
                pred["kelly_bet"] = port_map[key]
        log.append(f"{tag} ポートフォリオ最適化: {port_summary.get('total_bets', 0)}点 "
                   f"{port_summary.get('total_amount', 0):,}円")
    except Exception as e:
        log.append(f"{tag} ポートフォリオ最適化スキップ: {e}")

    # 条件別係数テーブルをロード
    try:
        from pipeline.condition_adjuster_34 import get_bet_coefficient
        use_coeff = True
        log.append(f"{tag} 条件別係数テーブル読込")
    except ImportError:
        use_coeff = False

    # オッズ変動モニタリング設定をロード
    try:
        from pipeline.odds_monitor_33 import adjust_ev_for_movement, OddsMovement
        use_odds_adj = True
    except ImportError:
        use_odds_adj = False

    total_alloc = 0.0
    approved, rejected = [], []

    for pred in sorted(preds, key=lambda x: x["confidence"], reverse=True):
        bet = pred["kelly_bet"] * mult

        # 条件別係数を適用
        if use_coeff:
            try:
                rc    = pred.get("race_code", "")
                # race_codeからkeibajo(6-7文字目)、kyori(8-11文字目)などを取得
                kb    = rc[6:8]  if len(rc) >= 8  else "00"
                kyori = int(rc[11:15]) if len(rc) >= 15 else 1600
                month = datetime.now().month
                coeff, grade = get_bet_coefficient(kb, kyori, 0, month)
                bet = bet * coeff
                pred["condition_coeff"] = round(coeff, 3)
                pred["condition_grade"] = grade
            except Exception:
                pass

        bet = max(100, round(bet / 100) * 100)

        # 最低残高チェック
        if bankroll - total_alloc - bet < MIN_BANKROLL:
            rejected.append({**pred, "reason": "最低残高割れ"})
            continue
        # 1日上限チェック
        if (total_alloc + bet) / bankroll > MAX_DAY_RATIO:
            rejected.append({**pred, "reason": "1日上限超過"})
            continue
        # 1レース上限チェック
        if bet / bankroll > MAX_BET_RATIO:
            bet = int(bankroll * MAX_BET_RATIO / 100) * 100

        approved.append({**pred, "kelly_bet": int(bet), "risk_approved": True})
        total_alloc += bet

    risk_summary = {
        "bankroll":        bankroll,
        "total_allocated": total_alloc,
        "approved_count":  len(approved),
        "rejected_count":  len(rejected),
        "day_ratio":       total_alloc / bankroll if bankroll > 0 else 0,
        "dd_multiplier":   mult,
    }
    log.append(f"{tag} 承認 {len(approved)}R / 却下 {len(rejected)}R "
               f"({total_alloc:,.0f}円 / {total_alloc/bankroll*100:.1f}%)")

    return {**state, "approved_bets": approved, "risk_summary": risk_summary, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 8: CommentaryAgent（Ollama優先 → Claude Haiku → テンプレート）
# ─────────────────────────────────────────────────────────────

_PERSONA = (
    "あなたは競馬予想AI「うまなり地蔵」です。"
    "閻魔大王の目で穴馬の魅力を簡潔に語ります（60文字以内）。"
)


def _call_ollama_comment(user_msg: str) -> str:
    """Ollama でX投稿コメントを生成（japanese プロファイル）。失敗時は空文字。"""
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return ""
        model = get_model_for_task("japanese")
        if not model:
            return ""
        result = _generate(user_msg, system=_PERSONA, model=model,
                           temperature=0.8, stream=False, task="japanese")
        return (result or "").strip()
    except Exception as e:
        print(f"  [Commentary/Ollama] スキップ: {e}")
        return ""


def commentary_agent(state: AgentState) -> AgentState:
    tag = "[Commentary]"
    log = [f"{tag} 起動 {_ts()}"]

    approved = state.get("approved_bets", [])
    if not approved:
        return {**state, "comments": {}, "log": log}

    comments: Dict[str, str] = {}

    for bet in approved:
        bamei  = bet["bamei"]
        odds   = bet["odds"]
        ev     = bet["expected_value"] * 100
        conf   = bet["confidence"] * 100
        blood  = bet["blood_score"]
        form   = bet.get("training_form", "D")
        hc     = bet.get("trainer_hot_cold", 0.5)
        sig    = bet.get("odds_signal_boost", 0.0)

        is_debut  = bet.get("is_debut", 0) == 1
        debut_sc  = bet.get("debut_score", 0.0)
        is_shogai = bet.get("is_shogai", 0) == 1
        shogai_sc = bet.get("shogai_score", 0.0)
        sh_keiken = bet.get("shogai_keiken", 0)
        j_sh_rate = bet.get("jockey_shogai_win_rate", 0.0)

        # 共通プロンプト（Ollama / Claude API 両用）
        debut_note  = f" 新馬戦(デビュースコア:{debut_sc:.2f})" if is_debut else ""
        shogai_note = (
            f" 障害戦(経験{sh_keiken}戦・騎手障害勝率{j_sh_rate:.0%})" if is_shogai else ""
        )
        user_msg = (
            f"馬名:{bamei} オッズ:{odds:.1f}倍 EV:{ev:.0f}% "
            f"確信度:{conf:.0f}% 血統相性:{blood:.2f} "
            f"調教フォーム:{form} 調教師好調度:{hc:.2f} "
            f"オッズシグナル:{'SHARP上昇' if sig>0.05 else '通常'}{debut_note}{shogai_note}"
        )

        # 優先: Ollama（無料・ローカル）→ Claude API（有料）→ テンプレート
        comment = _call_ollama_comment(user_msg)

        if not comment and _ANTHROPIC_KEY:
            comment = _call_claude(
                system=_PERSONA, user=user_msg,
                model="claude-haiku-4-5-20251001", max_tokens=80
            )
        else:
            # テンプレートフォールバック（シグナル優先度順）
            if is_shogai and shogai_sc >= 0.6:
                comment = (f"障害巧者。経験{sh_keiken}戦×騎手障害勝率{j_sh_rate:.0%}。"
                           f"{odds:.1f}倍の障害穴馬候補。")
            elif is_shogai:
                comment = f"障害出走。経験{sh_keiken}戦、スコア{shogai_sc:.2f}。{odds:.1f}倍注目。"
            elif is_debut and debut_sc >= 0.7:
                j_dr = bet.get("jockey_debut_rate", 0.1)
                t_dr = bet.get("trainer_debut_rate", 0.1)
                comment = (f"新馬戦注目馬。調教A級×騎手新馬{j_dr:.0%}×"
                           f"調教師新馬{t_dr:.0%}。{odds:.1f}倍の大穴候補。")
            elif is_debut:
                comment = f"新馬デビュー戦。調教スコア{form}、血統相性{blood:.1f}x。{odds:.1f}倍注目。"
            elif sig > 0.05:
                comment = f"オッズ急落のSHARPシグナル！{bamei} {odds:.1f}倍は見逃せない。"
            elif form == "A" and hc > 0.6:
                comment = f"調教フォームA×調教師好調W。{bamei} {odds:.1f}倍は狙い目。"
            elif blood >= 2.0:
                comment = f"血統相性抜群({blood:.1f}x)の隠れた実力馬。{odds:.1f}倍は美味しい。"
            elif ev >= 30:
                comment = f"期待値{ev:.0f}%超えの超穴候補。地蔵が目を光らせる一頭。"
            else:
                comment = f"EV{ev:.0f}%、確信度{conf:.0f}%。データが静かに語る穴馬。"

        comments[bamei] = comment
        log.append(f"{tag} {bamei}: {comment[:30]}...")

    log.append(f"{tag} コメント生成: {len(comments)}頭")
    return {**state, "comments": comments, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 9: PublisherAgent
# ─────────────────────────────────────────────────────────────

def publisher_agent(state: AgentState) -> AgentState:
    tag = "[Publisher]"
    log = [f"{tag} 起動 {_ts()}"]

    approved = state.get("approved_bets", [])
    comments = state.get("comments", {})
    risk     = state.get("risk_summary", {})
    notes    = state.get("supervisor_notes", "")

    now = datetime.now()

    if not approved:
        post_text = "🙏 本日は条件を満たすレースがありません。地蔵は待機中です。"
    else:
        # Ollama で冒頭の一言コメントを生成（失敗時はデフォルト文）
        _intro = ""
        try:
            from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
            _pub_model = get_model_for_task("japanese") if is_ollama_running() else None
            if _pub_model:
                _picks_summary = "、".join(
                    b["bamei"] + "(" + str(round(b["odds"], 1)) + "倍)"
                    for b in approved[:3]
                )
                _intro_prompt = (
                    "本日の穴馬予想: " + _picks_summary + "\n"
                    "うまなり地蔵として、上記の予想について30文字以内で一言コメントしてください。"
                )
                _intro_sys = (
                    "あなたは競馬予想AI「うまなり地蔵」です。"
                    "閻魔大王・地蔵・業火などの言葉を使い、熱量のある一言を出力してください。"
                )
                _intro = _generate(_intro_prompt, system=_intro_sys,
                                   model=_pub_model, temperature=0.9,
                                   stream=False, task="japanese") or ""
        except Exception:
            pass

        lines = [
            f"🙏【うまなり地蔵AI {now.strftime('%m/%d')}】",
            f"💰 本日投入: {risk.get('total_allocated', 0):,.0f}円"
            f" ({risk.get('day_ratio', 0)*100:.1f}%)",
            "",
        ]
        if _intro:
            lines.append(f"✨ {_intro.strip()}")
            lines.append("")
        if notes:
            lines.append(f"📌 {notes}")
            lines.append("")

        for i, bet in enumerate(approved[:5], 1):
            ev_pct  = bet["expected_value"] * 100
            conf    = bet["confidence"] * 100
            comment = comments.get(bet["bamei"], "")
            lines.append(
                f"{'🔥' if ev_pct >= 30 else '🎯'}#{i} "
                f"**{bet['bamei']}** {bet['odds']:.1f}倍"
                f" EV{ev_pct:+.0f}% 確信{conf:.0f}%"
                f" {bet['kelly_bet']:,}円"
            )
            if comment:
                lines.append(f"   💬 {comment}")

        lines += [
            "",
            f"承認{len(approved)}R | 候補{len(state.get('ev_candidates',[]))}R",
            "#競馬 #穴馬予想 #うまなり地蔵AI",
        ]
        post_text = "\n".join(lines)

    # JSON 保存
    out_path = os.path.join(BASE_DIR, f"agent_picks_{now.strftime('%Y%m%d')}.json")
    payload = {
        "generated_at":   now.isoformat(),
        "approved_bets":  approved,
        "risk_summary":   risk,
        "comments":       comments,
        "supervisor_notes": notes,
        "post_text":      post_text,
        "approved_races": [
            {"race_code": b["race_code"], "bamei": b["bamei"],
             "odds": b["odds"], "ev": b["expected_value"]}
            for b in approved
        ],
    }
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.append(f"{tag} 保存: {out_path}")
    except Exception as e:
        log.append(f"{tag} 保存エラー: {e}")

    # SNS 配信
    try:
        from pipeline.social_bot_27 import broadcast_picks
        broadcast_picks(post_text)
        log.append(f"{tag} SNS配信完了")
    except Exception as e:
        log.append(f"{tag} SNS配信スキップ: {e}")

    log.append(f"{tag} 投稿文 ({len(post_text)}文字) 生成完了")
    return {**state, "post_text": post_text, "log": log}


# ─────────────────────────────────────────────────────────────
# グラフ構築
# ─────────────────────────────────────────────────────────────

def _should_continue_after_data(state: AgentState) -> str:
    return "parallel_analysis" if state.get("data_ready") else "publisher"


def _should_predict(state: AgentState) -> str:
    return "ev_agent" if state.get("ev_candidates") else "publisher"


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # ノード登録
    g.add_node("data_agent",       data_agent)
    g.add_node("blood_agent",      blood_agent)
    g.add_node("pace_agent",       pace_agent)
    g.add_node("merge_parallel",   merge_parallel)
    g.add_node("ml_ensemble_agent", ml_ensemble_agent)
    g.add_node("ev_agent",         ev_agent)
    g.add_node("supervisor_agent", supervisor_agent)
    g.add_node("risk_agent",       risk_agent)
    g.add_node("commentary_agent", commentary_agent)
    g.add_node("publisher_agent",  publisher_agent)

    # エントリポイント
    g.set_entry_point("data_agent")

    # データ取得後 → 並列分析へ（条件付き）
    g.add_conditional_edges(
        "data_agent",
        _should_continue_after_data,
        {
            "parallel_analysis": "blood_agent",  # 並列の代表としてbloodを先に
            "publisher": "publisher_agent",
        }
    )

    # 並列: blood と pace は独立実行し merge へ収束
    g.add_edge("blood_agent", "merge_parallel")
    g.add_edge("pace_agent",  "merge_parallel")

    # merge → ML アンサンブル
    g.add_edge("merge_parallel",    "ml_ensemble_agent")

    # ML → EV フィルタ（条件付き）
    g.add_conditional_edges(
        "ml_ensemble_agent",
        _should_predict,
        {"ev_agent": "ev_agent", "publisher": "publisher_agent"}
    )

    # EV → Supervisor → Risk → Commentary → Publisher
    g.add_edge("ev_agent",         "supervisor_agent")
    g.add_edge("supervisor_agent", "risk_agent")
    g.add_edge("risk_agent",       "commentary_agent")
    g.add_edge("commentary_agent", "publisher_agent")
    g.add_edge("publisher_agent",  END)

    return g.compile()


# ─────────────────────────────────────────────────────────────
# 並列実行ヘルパー（blood + pace を同時起動）
# ─────────────────────────────────────────────────────────────

def _run_parallel_analysis(state: AgentState) -> AgentState:
    """7エージェントを Python スレッドで並列実行する。"""
    import threading

    results: dict = {k: state for k in
                     ("blood", "pace", "training", "trainer", "debut", "shogai", "odds_signal")}

    def run(key, fn):
        results[key] = fn(state)

    threads = [
        threading.Thread(target=run, args=("blood",       blood_agent)),
        threading.Thread(target=run, args=("pace",        pace_agent)),
        threading.Thread(target=run, args=("training",    training_agent)),
        threading.Thread(target=run, args=("trainer",     trainer_agent)),
        threading.Thread(target=run, args=("debut",       debut_agent)),
        threading.Thread(target=run, args=("shogai",      shogai_agent)),
        threading.Thread(target=run, args=("odds_signal", odds_signal_agent)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_log    = []
    all_errors = []
    for r in results.values():
        all_log    += r.get("log", [])
        all_errors += r.get("errors", [])

    merged = {
        **state,
        "blood_results":    results["blood"].get("blood_results", []),
        "pace_results":     results["pace"].get("pace_results", []),
        "training_results": results["training"].get("training_results", []),
        "trainer_results":  results["trainer"].get("trainer_results", []),
        "debut_results":    results["debut"].get("debut_results", []),
        "shogai_results":   results["shogai"].get("shogai_results", []),
        "odds_signals":     results["odds_signal"].get("odds_signals", []),
        "log":    all_log,
        "errors": all_errors,
    }
    return merged


# ─────────────────────────────────────────────────────────────
# メイン実行（並列版）
# ─────────────────────────────────────────────────────────────

def run_multi_agent_v2(year: Optional[int] = None) -> AgentState:
    year = year or datetime.now().year
    now  = datetime.now()

    print(f"\n{'='*60}")
    print(f"🤖 うまなり地蔵AI マルチエージェント v3")
    print(f"   13エージェント並列・階層型アーキテクチャ")
    print(f"   対象年: {year}  開始: {now.strftime('%H:%M:%S')}")
    print(f"   Claude API: {'✅ 有効' if _ANTHROPIC_KEY else '⏩ 未設定（テンプレート動作）'}")
    print(f"{'='*60}")

    bankroll = _load_bankroll()

    # 初期ステート
    state: AgentState = {
        "year":             year,
        "bankroll":         bankroll,
        "data_ready":       False,
        "blood_results":    [],
        "pace_results":     [],
        "training_results": [],
        "trainer_results":  [],
        "debut_results":    [],
        "shogai_results":   [],
        "odds_signals":     [],
        "ev_candidates":    [],
        "predictions":      [],
        "approved_bets":    [],
        "comments":         {},
        "supervisor_notes": "",
        "risk_assessment":  {},
        "log":              [],
        "error":            None,
    }


def run_pipeline(date_str: str = None) -> AgentState:
    """パイプライン全体を実行する。"""
    from langgraph.graph import StateGraph, END
    graph = StateGraph(AgentState)

    graph.add_node("data",       data_agent)
    graph.add_node("blood",      blood_agent)
    graph.add_node("pace",       pace_agent)
    graph.add_node("training",   training_agent)
    graph.add_node("trainer",    trainer_agent)
    graph.add_node("debut",      debut_agent)
    graph.add_node("shogai",     shogai_agent)
    graph.add_node("odds",       odds_signal_agent)
    graph.add_node("ml",         ml_ensemble_agent)
    graph.add_node("ev",         ev_agent)
    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("risk",       risk_agent)
    graph.add_node("commentary", commentary_agent)
    graph.add_node("publisher",  publisher_agent)

    graph.set_entry_point("data")
    for src, dst in [
        ("data",       "blood"),
        ("blood",      "pace"),
        ("pace",       "training"),
        ("training",   "trainer"),
        ("trainer",    "debut"),
        ("debut",      "shogai"),
        ("shogai",     "odds"),
        ("odds",       "ml"),
        ("ml",         "ev"),
        ("ev",         "supervisor"),
        ("supervisor", "risk"),
        ("risk",       "commentary"),
        ("commentary", "publisher"),
        ("publisher",  END),
    ]:
        graph.add_edge(src, dst)

    app = graph.compile()
    return app.invoke(_initial_state(date_str))


if __name__ == "__main__":
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    result = run_pipeline(date_arg)
    approved = result.get("approved_bets", [])
    print(f"\n承認ベット: {len(approved)}頭")
    for b in approved:
        print(f"  {b['bamei']} {b['odds']:.1f}倍  EV={b['expected_value']*100:.0f}%")
