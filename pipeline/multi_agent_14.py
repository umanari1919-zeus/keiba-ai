"""
マルチエージェントシステム（LangGraph）
5つのエージェントが協調してレース予想〜発信を自動実行する。

依存: pip install langgraph langchain langchain-anthropic
"""
import os
import json
import pickle
import pandas as pd
import numpy as np
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

# LangGraph インポート（未インストール時は明示エラー）
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    raise ImportError(
        "LangGraphが必要です: pip install langgraph langchain langchain-anthropic"
    )

# ──────────────────────────────────────────────────────────────
# 共有ステート定義
# ──────────────────────────────────────────────────────────────

class RacePrediction(TypedDict):
    race_code: str
    bamei: str
    odds: float
    win_probability: float
    expected_value: float
    kelly_bet: int
    risk_approved: bool
    comment: str


class AgentState(TypedDict):
    # 各エージェントが書き込むフィールド
    year: int
    raw_data_path: str                              # DataCollector → 出力
    features_path: str                              # DataCollector → 出力
    model_loaded: bool                              # Analyzer → フラグ
    ev_analysis: List[Dict[str, Any]]               # Analyzer → 期待値リスト
    predictions: List[RacePrediction]               # Predictor → 予想リスト
    risk_summary: Dict[str, Any]                    # RiskManager → リスク評価
    approved_bets: List[RacePrediction]             # RiskManager → 承認済みベット
    post_text: str                                  # Publisher → SNS投稿文
    errors: Annotated[List[str], operator.add]      # エラー蓄積（append）
    log: Annotated[List[str], operator.add]         # 実行ログ（append）


# ──────────────────────────────────────────────────────────────
# エージェント実装
# ──────────────────────────────────────────────────────────────

def data_collector_agent(state: AgentState) -> AgentState:
    """
    【エージェント1: データ収集】
    PostgreSQL からデータを取得し、特徴量を計算する。
    既存ファイルが新しければスキップしてキャッシュを使用。
    """
    tag = "[DataCollector]"
    log = [f"{tag} 起動 {datetime.now().strftime('%H:%M:%S')}"]

    year = state.get('year', datetime.now().year)
    raw_path  = "D:\\keiba_ai\\keiba_data.csv"
    feat_path = "D:\\keiba_ai\\keiba_data_features.csv"

    try:
        # ファイル存在確認（当日更新済みならスキップ）
        raw_exists  = os.path.exists(raw_path)
        feat_exists = os.path.exists(feat_path)

        if raw_exists and feat_exists:
            mtime = os.path.getmtime(feat_path)
            age_hours = (datetime.now().timestamp() - mtime) / 3600
            if age_hours < 6:
                log.append(f"{tag} キャッシュ使用（{age_hours:.1f}時間前に更新済み）")
                return {**state,
                        'raw_data_path': raw_path,
                        'features_path': feat_path,
                        'log': log}

        log.append(f"{tag} データ取得中...")
        from pipeline.data_fetch_01 import fetch_data
        fetch_data()
        log.append(f"{tag} 特徴量計算中...")
        from pipeline.feature_eng_02 import feature_engineering
        feature_engineering()
        log.append(f"{tag} 完了")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        log.append(err)
        return {**state,
                'raw_data_path': raw_path if os.path.exists(raw_path) else '',
                'features_path': feat_path if os.path.exists(feat_path) else '',
                'errors': [err],
                'log': log}

    return {**state,
            'raw_data_path': raw_path,
            'features_path': feat_path,
            'log': log}


def analyzer_agent(state: AgentState) -> AgentState:
    """
    【エージェント2: 分析】
    モデルを使って期待値計算・上位候補を選出する。
    """
    tag = "[Analyzer]"
    log = [f"{tag} 起動 {datetime.now().strftime('%H:%M:%S')}"]

    year = state.get('year', datetime.now().year)
    feat_path = state.get('features_path', '')

    if not feat_path or not os.path.exists(feat_path):
        err = f"{tag} 特徴量ファイルなし: {feat_path}"
        log.append(err)
        return {**state, 'model_loaded': False,
                'ev_analysis': [], 'errors': [err], 'log': log}

    try:
        with open("D:\\keiba_ai\\model_v8.pkl", "rb") as f:
            saved = pickle.load(f)

        lgb_model = saved['lgb_model']
        xgb_model = saved['xgb_model']
        cb_model  = saved['cb_model']
        le        = saved['le']
        features  = saved['features']
        log.append(f"{tag} モデル読込完了")

        df = pd.read_csv(feat_path, encoding="utf-8-sig", low_memory=False)
        df = df.fillna(0)
        test_df = df[df['kaisai_nen'] == year].copy()

        if len(test_df) == 0:
            log.append(f"{tag} {year}年データなし")
            return {**state, 'model_loaded': True,
                    'ev_analysis': [], 'log': log}

        X = test_df[features]
        ensemble_proba = (
            0.5 * lgb_model.predict_proba(X) +
            0.3 * xgb_model.predict_proba(X) +
            0.2 * cb_model.predict_proba(X)
        )

        # 1着確率を抽出
        classes = list(le.classes_)
        win_idx = classes.index(1) if 1 in classes else 0
        win_probs = ensemble_proba[:, win_idx]

        test_df = test_df.copy()
        test_df['win_probability'] = win_probs
        test_df['odds_decimal'] = pd.to_numeric(
            test_df['tansho_odds'], errors='coerce').fillna(0) / 10
        test_df['expected_value'] = (
            test_df['win_probability'] * test_df['odds_decimal'] - 1.0
        )

        # 期待値5%以上・オッズ10倍以上でフィルタ
        top = test_df[
            (test_df['expected_value'] >= 0.05) &
            (test_df['odds_decimal'] >= 10.0)
        ].sort_values('expected_value', ascending=False)

        ev_list = []
        for race_code, race in top.groupby('race_code'):
            best = race.iloc[0]
            ev_list.append({
                'race_code':      str(race_code),
                'bamei':          str(best.get('bamei', '')),
                'odds':           float(best['odds_decimal']),
                'win_probability': float(best['win_probability']),
                'expected_value': float(best['expected_value']),
                'kishumei_ryakusho': str(best.get('kishumei_ryakusho', '')),
                'barei':          int(best.get('barei', 0)),
                'bataiju':        int(best.get('bataiju', 0)),
                'zogen_sa':       int(best.get('zogen_sa', 0)),
                'zogen_fugo':     int(best.get('zogen_fugo', 0)),
            })

        log.append(f"{tag} 期待値候補: {len(ev_list)}R")

    except Exception as e:
        err = f"{tag} エラー: {e}"
        log.append(err)
        return {**state, 'model_loaded': False,
                'ev_analysis': [], 'errors': [err], 'log': log}

    return {**state, 'model_loaded': True,
            'ev_analysis': ev_list, 'log': log}


def predictor_agent(state: AgentState) -> AgentState:
    """
    【エージェント3: 予想】
    期待値リストをもとに、ケリー基準で賭け金を付加した予想を生成する。
    """
    tag = "[Predictor]"
    log = [f"{tag} 起動 {datetime.now().strftime('%H:%M:%S')}"]

    ev_list = state.get('ev_analysis', [])
    if not ev_list:
        log.append(f"{tag} 分析候補なし")
        return {**state, 'predictions': [], 'log': log}

    try:
        from pipeline.kelly_bankroll_09 import load_bankroll, calculate_kelly_bet
        bk = load_bankroll()
        bankroll = bk['current']
        log.append(f"{tag} 現在資金: {bankroll:,.0f}円")
    except Exception as e:
        bankroll = 100000
        log.append(f"{tag} 資金読込エラー（デフォルト使用）: {e}")

    predictions: List[RacePrediction] = []
    for item in ev_list:
        p    = item['win_probability']
        odds = item['odds']
        bet  = calculate_kelly_bet(bankroll, p, odds)

        predictions.append({
            'race_code':      item['race_code'],
            'bamei':          item['bamei'],
            'odds':           odds,
            'win_probability': p,
            'expected_value': item['expected_value'],
            'kelly_bet':      bet,
            'risk_approved':  False,
            'comment':        '',
        })

    log.append(f"{tag} 予想生成: {len(predictions)}頭")
    return {**state, 'predictions': predictions, 'log': log}


def risk_manager_agent(state: AgentState) -> AgentState:
    """
    【エージェント4: リスク管理】
    各予想のリスクを評価し、投入上限・破産防止チェックを行う。
    承認済み予想のみ approved_bets に格納する。
    """
    tag = "[RiskManager]"
    log = [f"{tag} 起動 {datetime.now().strftime('%H:%M:%S')}"]

    preds = state.get('predictions', [])
    if not preds:
        return {**state, 'approved_bets': [],
                'risk_summary': {}, 'log': log}

    try:
        from pipeline.kelly_bankroll_09 import load_bankroll
        bk = load_bankroll()
        bankroll = bk['current']
    except Exception:
        bankroll = 100000

    MAX_DAY_RATIO  = 0.20   # 1日最大20%まで
    MAX_BET_RATIO  = 0.05   # 1レース最大5%
    MIN_BANKROLL   = 10000  # 最低保持残高

    total_allocated = 0
    approved = []
    rejected = []

    for pred in sorted(preds, key=lambda x: x['expected_value'], reverse=True):
        bet = pred['kelly_bet']

        # 残高チェック
        if bankroll - total_allocated - bet < MIN_BANKROLL:
            rejected.append({'race_code': pred['race_code'],
                             'reason': '最低残高割れ'})
            continue

        # 1日上限チェック
        if (total_allocated + bet) / bankroll > MAX_DAY_RATIO:
            rejected.append({'race_code': pred['race_code'],
                             'reason': '1日上限超過'})
            continue

        # 1レース上限チェック
        if bet / bankroll > MAX_BET_RATIO:
            bet = int(bankroll * MAX_BET_RATIO / 100) * 100

        approved_pred = {**pred, 'kelly_bet': bet, 'risk_approved': True}
        approved.append(approved_pred)
        total_allocated += bet

    risk_summary = {
        'bankroll':        bankroll,
        'total_allocated': total_allocated,
        'approved_count':  len(approved),
        'rejected_count':  len(rejected),
        'day_ratio':       total_allocated / bankroll if bankroll > 0 else 0,
        'rejected_detail': rejected,
    }

    log.append(f"{tag} 承認: {len(approved)}R / "
               f"却下: {len(rejected)}R "
               f"(総投入予定: {total_allocated:,}円)")

    return {**state, 'approved_bets': approved,
            'risk_summary': risk_summary, 'log': log}


def publisher_agent(state: AgentState) -> AgentState:
    """
    【エージェント5: 発信】
    承認済み予想をもとにSNS投稿文を生成し、通知・保存を行う。
    """
    tag = "[Publisher]"
    log = [f"{tag} 起動 {datetime.now().strftime('%H:%M:%S')}"]

    approved = state.get('approved_bets', [])
    risk     = state.get('risk_summary', {})

    if not approved:
        post_text = "🙏 本日は条件を満たすレースがありません。地蔵はお休みです。"
        log.append(f"{tag} 発信候補なし")
        return {**state, 'post_text': post_text, 'log': log}

    now  = datetime.now()
    lines = [
        f"🙏 うまなり地蔵AIの本日予想 ({now.strftime('%m/%d')})",
        f"💰 本日投入予定: {risk.get('total_allocated', 0):,}円",
        "",
    ]

    for i, bet in enumerate(approved[:5], 1):   # 最大5頭
        ev_pct = bet['expected_value'] * 100
        lines.append(
            f"{'🔥' if ev_pct > 30 else '🎯'} "
            f"#{i} {bet['bamei']} "
            f"({bet['odds']:.1f}倍 / EV{ev_pct:+.0f}% / "
            f"推奨{bet['kelly_bet']:,}円)"
        )

    lines += [
        "",
        f"📊 承認レース: {len(approved)}R",
        "閻魔帳が示す穴馬に賽を投げよ👹",
        "#競馬 #穴馬予想 #うまなり地蔵AI",
    ]

    post_text = "\n".join(lines)

    # 結果を保存
    out_path = f"D:\\keiba_ai\\agent_picks_{now.strftime('%Y%m%d')}.json"
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': now.isoformat(),
                'approved_bets': approved,
                'risk_summary':  risk,
                'post_text':     post_text,
            }, f, ensure_ascii=False, indent=2)
        log.append(f"{tag} 保存完了: {out_path}")
    except Exception as e:
        log.append(f"{tag} 保存エラー: {e}")

    log.append(f"{tag} 投稿文生成完了 ({len(post_text)}文字)")
    print(f"\n{'='*55}")
    print(post_text)
    print(f"{'='*55}\n")

    return {**state, 'post_text': post_text, 'log': log}


# ──────────────────────────────────────────────────────────────
# ルーティング関数
# ──────────────────────────────────────────────────────────────

def should_analyze(state: AgentState) -> str:
    """データ取得成功時のみ分析へ進む。"""
    if state.get('features_path') and os.path.exists(state['features_path']):
        return "analyzer"
    return END


def should_predict(state: AgentState) -> str:
    """分析結果があれば予想へ進む。"""
    return "predictor" if state.get('ev_analysis') else "publisher"


# ──────────────────────────────────────────────────────────────
# グラフ構築
# ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("data_collector", data_collector_agent)
    graph.add_node("analyzer",       analyzer_agent)
    graph.add_node("predictor",      predictor_agent)
    graph.add_node("risk_manager",   risk_manager_agent)
    graph.add_node("publisher",      publisher_agent)

    graph.set_entry_point("data_collector")

    graph.add_conditional_edges(
        "data_collector",
        should_analyze,
        {"analyzer": "analyzer", END: END}
    )
    graph.add_conditional_edges(
        "analyzer",
        should_predict,
        {"predictor": "predictor", "publisher": "publisher"}
    )
    graph.add_edge("predictor",    "risk_manager")
    graph.add_edge("risk_manager", "publisher")
    graph.add_edge("publisher",    END)

    return graph.compile()


# ──────────────────────────────────────────────────────────────
# 実行エントリポイント
# ──────────────────────────────────────────────────────────────

def run_multi_agent(year: Optional[int] = None) -> AgentState:
    year = year or datetime.now().year

    print(f"\n{'='*55}")
    print(f"🤖 マルチエージェントシステム起動")
    print(f"   対象年: {year}  開始: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    app = build_graph()
    initial_state: AgentState = {
        'year':         year,
        'raw_data_path': '',
        'features_path': '',
        'model_loaded':  False,
        'ev_analysis':   [],
        'predictions':   [],
        'risk_summary':  {},
        'approved_bets': [],
        'post_text':     '',
        'errors':        [],
        'log':           [],
    }

    final_state = app.invoke(initial_state)

    print(f"\n{'='*55}")
    print(f"📋 実行ログ")
    for entry in final_state.get('log', []):
        print(f"  {entry}")

    if final_state.get('errors'):
        print(f"\n⚠️ エラー")
        for err in final_state['errors']:
            print(f"  {err}")

    rs = final_state.get('risk_summary', {})
    print(f"\n📊 最終サマリー")
    print(f"  承認レース: {rs.get('approved_count', 0)}R")
    print(f"  総投入予定: {rs.get('total_allocated', 0):,}円")
    print(f"  資金消費率: {rs.get('day_ratio', 0)*100:.1f}%")
    print(f"{'='*55}")

    return final_state


if __name__ == "__main__":
    run_multi_agent()
