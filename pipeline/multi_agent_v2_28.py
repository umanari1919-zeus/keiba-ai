"""
うまなり地蔵AI マルチエージェント v2
─────────────────────────────────────
9エージェント 並列・階層型アーキテクチャ

Supervisor (Claude Sonnet) が全体を統括
  ├── [並列フェーズ]
  │   ├── DataAgent     DB データ取得
  │   ├── BloodAgent    血統・ニックス分析
  │   └── PaceAgent     ペース・調教分析
  ├── MLEnsembleAgent   LGB+XGB+CB+NN アンサンブル
  ├── EVAgent           期待値フィルタ
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

from langgraph.graph import StateGraph, END
from langgraph.types import Send

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────

BASE_DIR    = "D:\\keiba_ai"
MODEL_FILE  = f"{BASE_DIR}\\model_v8.pkl"
FEAT_FILE   = f"{BASE_DIR}\\keiba_data_features.csv"
RAW_FILE    = f"{BASE_DIR}\\keiba_data.csv"

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
    race_code:       str
    bamei:           str
    odds:            float
    win_probability: float
    expected_value:  float
    kelly_bet:       int
    risk_approved:   bool
    comment:         str
    nick_index:      float
    training_score:  float
    jt_win_rate:     float
    blood_score:     float
    confidence:      float   # Supervisor の総合確信度 0〜1


class AgentState(TypedDict):
    year:             int
    bankroll:         float
    # フェーズ1 並列出力
    data_ready:       bool
    blood_results:    List[Dict]
    pace_results:     List[Dict]
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
    path = f"{BASE_DIR}\\data\\bankroll.json"
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
        nicks_path = f"{BASE_DIR}\\pedigree_output\\nicks_feature.csv"
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
           f"pace={len(state.get('pace_results', []))}"]
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

        df = pd.read_csv(FEAT_FILE, encoding="utf-8-sig", low_memory=False)
        year = state.get("year", datetime.now().year)
        df   = df[df["kaisai_nen"] == year].fillna(0)
        if len(df) == 0:
            return {**state, "ev_candidates": [], "log": log + [f"{tag} {year}年データなし"]}

        feats = [f for f in features if f in df.columns]
        X = df[feats]

        lgb_p = lgb_model.predict_proba(X)
        xgb_p = xgb_model.predict_proba(X)
        cb_p  = cb_model.predict_proba(X)

        # NN モデルがあれば追加
        nn_path = f"{BASE_DIR}\\model_nn.pth"
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

        # 調教スコアをマージ
        pace_map: Dict[str, float] = {}
        for p in state.get("pace_results", []):
            pace_map[str(p.get("ketto_toroku_bango", ""))] = p.get("training_score", 0)
        df["training_score_enriched"] = df["ketto_toroku_bango"].astype(str).map(
            lambda k: pace_map.get(k, df["training_score"].mean() if "training_score" in df else 0)
        )

        # EV フィルタ（EV≥5% かつオッズ≥10倍）
        top = df[
            (df["expected_value"] >= EV_THRESHOLD) &
            (df["odds_decimal"]   >= MIN_ODDS)
        ].sort_values("expected_value", ascending=False)

        candidates = []
        for rc, race in top.groupby("race_code"):
            best = race.iloc[0]
            candidates.append({
                "race_code":       str(rc),
                "bamei":           str(best.get("bamei", "")),
                "odds":            float(best["odds_decimal"]),
                "win_probability": float(best["win_probability"]),
                "expected_value":  float(best["expected_value"]),
                "blood_score":     float(best.get("blood_score", 1.0)),
                "training_score":  float(best.get("training_score_enriched", 0)),
                "jt_win_rate":     float(best.get("jt_win_rate", 0)),
                "nick_index":      float(best.get("nick_index", 1.0)),
                "kishumei":        str(best.get("kishumei_ryakusho", "")),
                "barei":           int(best.get("barei", 0)),
                "bataiju":         int(best.get("bataiju", 0)),
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
        rs_path = f"{BASE_DIR}\\data\\race_selector_{state.get('year', 2026)}.json"
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

            # 総合確信度スコア（EV + 血統 + 調教 + レース価値）
            confidence = min(1.0,
                0.40 * min(ev / 0.5, 1.0) +
                0.20 * min((c["blood_score"] - 1.0) / 2.0, 1.0) +
                0.15 * min(c["training_score"] / 0.1, 1.0) +
                0.10 * min(c["jt_win_rate"] * 5, 1.0) +
                0.15 * race_val
            )

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
                "race_code":       rc,
                "bamei":           c["bamei"],
                "odds":            odds,
                "win_probability": p,
                "expected_value":  ev,
                "kelly_bet":       bet,
                "risk_approved":   False,
                "comment":         "",
                "nick_index":      c.get("nick_index", 1.0),
                "training_score":  c.get("training_score", 0.0),
                "jt_win_rate":     c.get("jt_win_rate", 0.0),
                "blood_score":     c.get("blood_score", 1.0),
                "confidence":      round(confidence, 3),
                "ticket_type":     ticket_type,
                "ticket_odds":     ticket_odds,
                "race_value":      round(race_val, 3),
            })

        # 信頼スコア降順でソート
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        log.append(f"{tag} 確信度付き予想: {len(predictions)}頭")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        return {**state, "predictions": [], "errors": [err], "log": log + [err]}

    return {**state, "predictions": predictions, "log": log}


# ─────────────────────────────────────────────────────────────
# エージェント 6: SupervisorAgent（Claude Sonnet で戦略判断）
# ─────────────────────────────────────────────────────────────

_SUPERVISOR_SYSTEM = """あなたは競馬予想AIの統括エージェント「うまなり地蔵」です。
各分析エージェントからの結果を受け取り、最終的な投資戦略を判断します。
回答は必ず JSON 形式で返してください。"""


def supervisor_agent(state: AgentState) -> AgentState:
    tag = "[Supervisor]"
    log = [f"{tag} 起動 {_ts()}"]

    preds = state.get("predictions", [])
    if not preds:
        return {**state, "supervisor_notes": "候補なし", "log": log}

    summary_lines = []
    for p in preds[:10]:
        summary_lines.append(
            f"{p['bamei']}: EV={p['expected_value']*100:.0f}% "
            f"オッズ{p['odds']:.1f}x 確信度{p['confidence']*100:.0f}% "
            f"血統={p['blood_score']:.2f} 調教={p['training_score']:.3f}"
        )
    summary = "\n".join(summary_lines)
    bankroll = state.get("bankroll", 100_000)

    if _ANTHROPIC_KEY:
        user_msg = f"""
現在資金: {bankroll:,.0f}円
本日の予想候補（信頼スコア降順）:
{summary}

以下を JSON で返してください:
{{
  "top_picks": ["馬名1", "馬名2", "馬名3"],
  "max_bet_fraction": 0.15,
  "strategy": "今日の戦略コメント（50文字以内）",
  "confidence_overall": 0.7
}}
"""
        resp = _call_claude(
            system=_SUPERVISOR_SYSTEM, user=user_msg,
            model="claude-sonnet-4-6", max_tokens=300
        )
        try:
            import re
            json_match = re.search(r"\{.*\}", resp, re.DOTALL)
            if json_match:
                supervisor_data = json.loads(json_match.group())
                notes = supervisor_data.get("strategy", "")
                # Supervisor が推薦した馬のみ上位にソート
                top_picks = set(supervisor_data.get("top_picks", []))
                if top_picks:
                    state["predictions"] = sorted(
                        preds,
                        key=lambda x: (x["bamei"] in top_picks, x["confidence"]),
                        reverse=True
                    )
                log.append(f"{tag} Claude 判断完了: {notes}")
            else:
                notes = "自動判断"
        except Exception:
            notes = "自動判断（JSON解析失敗）"
    else:
        # API 未設定時: 確信度上位3頭を自動選定
        top3 = [p["bamei"] for p in preds[:3]]
        notes = f"自動選定: {', '.join(top3)}"
        log.append(f"{tag} APIキー未設定 → 自動判断")

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
# エージェント 8: CommentaryAgent（Claude Haiku）
# ─────────────────────────────────────────────────────────────

_PERSONA = (
    "あなたは競馬予想AI「うまなり地蔵」です。"
    "閻魔大王の目で穴馬の魅力を簡潔に語ります（60文字以内）。"
)


def commentary_agent(state: AgentState) -> AgentState:
    tag = "[Commentary]"
    log = [f"{tag} 起動 {_ts()}"]

    approved = state.get("approved_bets", [])
    if not approved:
        return {**state, "comments": {}, "log": log}

    comments: Dict[str, str] = {}

    for bet in approved:
        bamei = bet["bamei"]
        odds  = bet["odds"]
        ev    = bet["expected_value"] * 100
        conf  = bet["confidence"] * 100
        blood = bet["blood_score"]

        if _ANTHROPIC_KEY:
            user_msg = (
                f"馬名:{bamei} オッズ:{odds:.1f}倍 EV:{ev:.0f}% "
                f"確信度:{conf:.0f}% 血統相性:{blood:.2f}"
            )
            comment = _call_claude(
                system=_PERSONA, user=user_msg,
                model="claude-haiku-4-5-20251001", max_tokens=80
            )
        else:
            # テンプレートフォールバック
            if blood >= 2.0:
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
        lines = [
            f"🙏【うまなり地蔵AI {now.strftime('%m/%d')}】",
            f"💰 本日投入: {risk.get('total_allocated', 0):,.0f}円"
            f" ({risk.get('day_ratio', 0)*100:.1f}%)",
            "",
        ]
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
    out_path = f"{BASE_DIR}\\agent_picks_{now.strftime('%Y%m%d')}.json"
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
    """blood_agent と pace_agent を Python スレッドで並列実行する。"""
    import threading

    blood_result: list = [state]
    pace_result:  list = [state]

    def run_blood():
        blood_result[0] = blood_agent(state)

    def run_pace():
        pace_result[0] = pace_agent(state)

    t1 = threading.Thread(target=run_blood)
    t2 = threading.Thread(target=run_pace)
    t1.start(); t2.start()
    t1.join();  t2.join()

    merged = {
        **state,
        "blood_results": blood_result[0].get("blood_results", []),
        "pace_results":  pace_result[0].get("pace_results", []),
        "log": (blood_result[0].get("log", []) + pace_result[0].get("log", [])),
        "errors": (blood_result[0].get("errors", []) + pace_result[0].get("errors", [])),
    }
    return merged


# ─────────────────────────────────────────────────────────────
# メイン実行（並列版）
# ─────────────────────────────────────────────────────────────

def run_multi_agent_v2(year: Optional[int] = None) -> AgentState:
    year = year or datetime.now().year
    now  = datetime.now()

    print(f"\n{'='*60}")
    print(f"🤖 うまなり地蔵AI マルチエージェント v2")
    print(f"   9エージェント並列・階層型アーキテクチャ")
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
        "ev_candidates":    [],
        "predictions":      [],
        "approved_bets":    [],
        "risk_summary":     {},
        "comments":         {},
        "post_text":        "",
        "supervisor_notes": "",
        "errors":           [],
        "log":              [],
    }

    # ── フェーズ1: データ取得 ──
    print("\n  📦 Phase 1: データ取得")
    state = data_agent(state)
    if not state["data_ready"]:
        print("  ⚠️ データ取得失敗 → 中断")
        return state

    # ── フェーズ2: 並列分析（血統・ペース） ──
    print("  🔀 Phase 2: 並列分析（血統 × ペース）")
    state = _run_parallel_analysis(state)
    print(f"    blood={len(state['blood_results'])} pace={len(state['pace_results'])}")

    # ── フェーズ3: ML アンサンブル ──
    print("  🤖 Phase 3: ML アンサンブル")
    state = ml_ensemble_agent(state)
    print(f"    EV候補: {len(state['ev_candidates'])}R")

    if not state["ev_candidates"]:
        print("  ⚠️ 候補なし → Publisher へ")
        state = publisher_agent(state)
        return state

    # ── フェーズ4: EV フィルタ ──
    print("  📊 Phase 4: EV フィルタ")
    state = ev_agent(state)

    # ── フェーズ5: Supervisor 判断 ──
    print("  🧠 Phase 5: Supervisor 判断")
    state = supervisor_agent(state)
    if state.get("supervisor_notes"):
        print(f"    判断: {state['supervisor_notes']}")

    # ── フェーズ6: リスク管理 ──
    print("  🛡️ Phase 6: リスク管理")
    state = risk_agent(state)

    # ── フェーズ7: コメント生成 ──
    print("  💬 Phase 7: コメント生成")
    state = commentary_agent(state)

    # ── フェーズ8: 発信 ──
    print("  📢 Phase 8: 発信")
    state = publisher_agent(state)

    # ─────── サマリー ───────
    elapsed = (datetime.now() - now).seconds
    rs = state.get("risk_summary", {})

    print(f"\n{'='*60}")
    print(f"📋 実行ログ")
    for entry in state.get("log", []):
        print(f"  {entry}")

    if state.get("errors"):
        print(f"\n⚠️ エラー ({len(state['errors'])}件)")
        for e in state["errors"][:5]:
            print(f"  {e}")

    approved = state.get("approved_bets", [])
    print(f"\n📊 最終サマリー")
    print(f"  承認レース   : {rs.get('approved_count', 0)}R")
    print(f"  総投入予定   : {rs.get('total_allocated', 0):,.0f}円")
    print(f"  資金消費率   : {rs.get('day_ratio', 0)*100:.1f}%")
    print(f"  DD乗数       : {rs.get('dd_multiplier', 1.0):.2f}x")
    print(f"  所要時間     : {elapsed}秒")
    if approved:
        top = max(approved, key=lambda x: x["confidence"])
        print(f"  イチ推し     : {top['bamei']} "
              f"{top['odds']:.1f}倍 確信度{top['confidence']*100:.0f}%")
    print(f"{'='*60}")

    return state


# ─────────────────────────────────────────────────────────────
# 旧 API 互換
# ─────────────────────────────────────────────────────────────

def run_multi_agent(year: Optional[int] = None) -> AgentState:
    """run_all.py との後方互換"""
    return run_multi_agent_v2(year)


if __name__ == "__main__":
    run_multi_agent_v2()
