"""
llm_predictor.py  --  ML予測 + Ollama 自然言語解説
======================================================
predict_04.py が生成した予測結果（win_prob, features）に対して
Ollama (local LLM) が「なぜこの馬を選んだか」を日本語で解説する。

SHAP値 → 上位寄与特徴量 → Ollamaプロンプト → 解説テキスト

Usage:
    python pipeline/llm_predictor.py            # テストモード
    from pipeline.llm_predictor import explain_picks_batch
"""
import os
import json
import pickle
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from pipeline.config import BASE_DIR, DATA_DIR
from pipeline.native_runtime import ensure_native_runtime

ensure_native_runtime()

MODEL_PATH = os.path.join(BASE_DIR, "model_v8.pkl")

# ─────────────────────────────────────────────────────────────
# 特徴量名 → 日本語ラベル マッピング
# ─────────────────────────────────────────────────────────────

FEAT_JP = {
    "barei":               "馬齢",
    "bataiju":             "馬体重",
    "futan_juryo":         "斤量",
    "kyori":               "距離",
    "track_code":          "馬場種別",
    "win_rate":            "通算勝率",
    "sogo_win_rate":       "総合勝率",
    "past3_avg_chakujun":  "過去3走平均着順",
    "prev_chakujun":       "前走着順",
    "total_races":         "通算出走数",
    "win_count":           "通算勝利数",
    "shiba_win_rate":      "芝勝率",
    "dirt_win_rate":       "ダート勝率",
    "short_win_rate":      "短距離勝率",
    "middle_win_rate":     "中距離勝率",
    "long_win_rate":       "長距離勝率",
    "kishu_win_rate":      "騎手勝率",
    "kishu_keibajo_win_rate": "騎手×競馬場勝率",
    "chokyoshi_win_rate":  "調教師勝率",
    "chokyoshi_place_win_rate": "調教師複勝率",
    "chokyo_3f_avg3":      "調教3F平均タイム",
    "chokyo_3f_best":      "調教3F最速タイム",
    "chokyo_3f_std":       "調教タイム安定性",
    "chokyo_trend":        "調教トレンド",
    "chokyo_improving":    "調教タイム改善フラグ",
    "chokyo_quality":      "調教質スコア",
    "fresh_improving":     "休み明け調教好調",
    "grade_score":         "レースグレードスコア",
    "grade_up":            "グレードアップフラグ",
    "grade_up_fresh":      "格上げ×休み明けフラグ",
    "kishu_change":        "乗り替わりフラグ",
    "kishu_change_grade_up": "乗替×格上げフラグ",
    "keibajo_change":      "競馬場変更フラグ",
    "kyori_change":        "距離変化",
    "kyori_up":            "距離延長フラグ",
    "kyori_down":          "距離短縮フラグ",
    "weeks_since_last_race": "前走間隔(週)",
    "nick_index":          "ニックス指数",
    "nick_roi":            "ニックス回収率",
    "nick_win_rate":       "ニックス勝率",
    "debut_score":         "新馬戦スコア",
    "shogai_score":        "障害戦スコア",
    "pace_score":          "ペーススコア",
    "kyakushitsu_keiko_nige": "逃げ傾向",
    "kyakushitsu_keiko_senko": "先行傾向",
}

SYSTEM_EXPLAINER = (
    "あなたはプロの競馬予想家「うまなり地蔵」です。"
    "MLモデルが算出したデータをもとに、なぜその馬が穴馬として有力なのかを"
    "競馬ファンにわかりやすく日本語で解説してください。"
    "文体は簡潔・断定的・熱量があること。200文字以内。"
)


# ─────────────────────────────────────────────────────────────
# SHAP値計算
# ─────────────────────────────────────────────────────────────

def _compute_shap_top(model_dict: dict, X_row: pd.DataFrame, top_n: int = 5) -> List[Dict]:
    """LGBMモデルのSHAP値を1行分計算し、上位N特徴量を返す。"""
    try:
        import shap as shap_lib
        lgb_model = model_dict.get("lgb_model")
        features  = model_dict.get("features", [])
        if lgb_model is None or len(features) == 0:
            return []

        explainer = shap_lib.TreeExplainer(lgb_model)
        shap_vals = explainer.shap_values(X_row)

        win_idx = 0
        if isinstance(shap_vals, list) and len(shap_vals) > 0:
            sv = np.array(shap_vals[win_idx])[0]
        elif isinstance(shap_vals, np.ndarray) and shap_vals.ndim == 3:
            sv = shap_vals[0, :, win_idx]
        else:
            sv = np.array(shap_vals)[0] if hasattr(shap_vals, "__len__") else np.array([])

        if len(sv) == 0:
            return []

        feat_arr = np.array(features[:len(sv)])
        top_idx  = np.argsort(np.abs(sv))[::-1][:top_n]
        result = []
        for i in top_idx:
            fname = feat_arr[i] if i < len(feat_arr) else "feat_" + str(i)
            val = float(X_row.iloc[0].get(fname, 0))
            result.append({
                "feature": fname,
                "label":   FEAT_JP.get(fname, fname),
                "value":   val,
                "shap":    float(sv[i]),
            })
        return result

    except Exception as e:
        print("  [llm_predictor] SHAP skip: " + str(e))
        return []


# ─────────────────────────────────────────────────────────────
# テンプレート解説（Ollamaなし時のフォールバック）
# ─────────────────────────────────────────────────────────────

def _template_explain(horse: Dict, shap_feats: List[Dict]) -> str:
    bamei   = horse.get("bamei", "")
    odds    = horse.get("odds", 0)
    win_p   = horse.get("win_prob", 0)
    reasons = []
    for f in shap_feats[:3]:
        label = f["label"]
        shap  = f["shap"]
        direction = "好材料" if shap > 0 else "懸念材料"
        reasons.append(label + "(" + direction + ")")
    reason_str = "・".join(reasons) if reasons else "統計的優位性"
    return (
        "🙏 " + bamei + "（" + str(round(odds, 1)) + "倍）勝率" +
        str(round(win_p, 1)) + "%。地蔵の閻魔帳が示す根拠: " +
        reason_str + "。業火で炙り出した穴馬候補👹"
    )


# ─────────────────────────────────────────────────────────────
# Ollama 解説生成
# ─────────────────────────────────────────────────────────────

def _explain_via_ollama(horse: Dict, shap_feats: List[Dict]) -> str:
    """Ollama で1頭分の解説を生成（stream=False: 並列対応）。"""
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return ""
        _model = get_model_for_task("japanese")  # 予想解説は日本語プロファイル
        if not _model:
            return ""

        bamei  = horse.get("bamei", "")
        odds   = horse.get("odds", 0)
        win_p  = horse.get("win_prob", 0)
        race   = horse.get("race_info", "")
        ev     = horse.get("ev", 0)

        if shap_feats:
            shap_lines = []
            for f in shap_feats[:5]:
                label     = f["label"]
                val       = f["value"]
                shap_v    = f["shap"]
                direction = "プラス寄与" if shap_v > 0 else "マイナス寄与"
                sign      = "+" if shap_v >= 0 else ""
                shap_lines.append(
                    "  ・" + label + "=" + str(round(val, 3)) +
                    "  (" + direction + ": " + sign + str(round(shap_v, 3)) + ")"
                )
            shap_text = "\n".join(shap_lines)
        else:
            shap_text = "  ・SHAP情報なし"

        prompt = (
            "馬名: " + bamei + "\n" +
            "レース: " + str(race) + "\n" +
            "単勝オッズ: " + str(round(odds, 1)) + "倍\n" +
            "モデル勝率: " + str(round(win_p, 1)) + "%\n" +
            "期待値(EV): " + str(round(ev * 100, 0)) + "%\n" +
            "\nMLモデルが重視した特徴量（SHAP値）:\n" + shap_text + "\n" +
            "\n上記データをもとに、なぜこの穴馬を推奨するか200文字以内で解説してください。"
        )
        result = _generate(prompt, system=SYSTEM_EXPLAINER, model=_model,
                           temperature=0.7, stream=False, task="japanese")
        return result or ""
    except Exception as e:
        print("  [llm_predictor] ollama skip: " + str(e))
        return ""


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def explain_pick(horse: Dict, model_dict: dict = None,
                 feat_df: pd.DataFrame = None) -> str:
    """
    1頭分の解説を生成。

    Args:
        horse:      予測結果dict (bamei, odds, win_prob, race_info, ev, ...)
        model_dict: pickle から読んだモデル辞書（lgb_model, features等）
        feat_df:    当日の特徴量DataFrame（SHAP計算用）
    Returns:
        解説テキスト（Ollamaなし時はテンプレート）
    """
    shap_feats = []
    if model_dict is not None and feat_df is not None:
        bamei = horse.get("bamei", "")
        row = feat_df[feat_df["bamei"] == bamei]
        if len(row) > 0:
            features = model_dict.get("features", [])
            avail = [f for f in features if f in row.columns]
            if avail:
                X_row = row[avail].head(1).fillna(0)
                for f in features:
                    if f not in X_row.columns:
                        X_row[f] = 0
                X_row = X_row[features]
                shap_feats = _compute_shap_top(model_dict, X_row, top_n=5)

    explanation = _explain_via_ollama(horse, shap_feats)
    if not explanation:
        explanation = _template_explain(horse, shap_feats)
    return explanation


def explain_picks_batch(picks: List[Dict],
                        model_dict: dict = None,
                        feat_df: pd.DataFrame = None) -> List[str]:
    """
    承認済みベット一覧の解説を並列生成。

    Args:
        picks:      approved_bets リスト
        model_dict: モデル辞書（任意）
        feat_df:    特徴量DF（任意）
    Returns:
        解説テキストリスト（同順）
    """
    if not picks:
        return []

    shap_map: Dict[str, List[Dict]] = {}
    if model_dict is not None and feat_df is not None:
        features = model_dict.get("features", [])
        for horse in picks:
            bamei = horse.get("bamei", "")
            row = feat_df[feat_df["bamei"] == bamei]
            if len(row) > 0:
                avail = [f for f in features if f in row.columns]
                if avail:
                    X_row = row[avail].head(1).fillna(0)
                    for f in features:
                        if f not in X_row.columns:
                            X_row[f] = 0
                    X_row = X_row[features]
                    shap_map[bamei] = _compute_shap_top(model_dict, X_row, top_n=5)

    ollama_ok = False
    try:
        from pipeline.ollama_comment import is_ollama_running
        ollama_ok = is_ollama_running()
    except Exception:
        pass

    results: List[str] = [""] * len(picks)

    if not ollama_ok:
        for i, horse in enumerate(picks):
            bamei = horse.get("bamei", "")
            results[i] = _template_explain(horse, shap_map.get(bamei, []))
        return results

    def _one(idx: int, horse: Dict) -> tuple:
        bamei = horse.get("bamei", "")
        sf = shap_map.get(bamei, [])
        text = _explain_via_ollama(horse, sf)
        if not text:
            text = _template_explain(horse, sf)
        return idx, text

    max_workers = min(len(picks), 2)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, i, h): i for i, h in enumerate(picks)}
        done = 0
        for fut in as_completed(futures):
            idx, text = fut.result()
            results[idx] = text
            done += 1
            print("  [llm_predictor] 解説 " + str(done) + "/" + str(len(picks)) + " 完了")

    return results


def load_model_dict() -> Optional[dict]:
    """model_v8.pkl を読み込んで返す。失敗時はNone。"""
    if not os.path.exists(MODEL_PATH):
        print("  [llm_predictor] モデルなし: " + MODEL_PATH)
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        print("  [llm_predictor] モデル読み込み失敗: " + str(e))
        return None


def add_explanations_to_picks(picks_path: str,
                               feat_path: str = None) -> List[Dict]:
    """
    agent_picks_{date}.json を読み込み、LLM解説を追記して返す。

    Args:
        picks_path: agent_picks_{date}.json のパス
        feat_path:  keiba_data_features.csv のパス（任意、SHAP用）
    Returns:
        解説付きbetsリスト
    """
    if not os.path.exists(picks_path):
        print("  [llm_predictor] picks なし: " + picks_path)
        return []

    with open(picks_path, encoding="utf-8") as f:
        data = json.load(f)
    picks = data if isinstance(data, list) else data.get("bets", data.get("approved_bets", []))
    if not picks:
        return []

    model_dict = load_model_dict()
    feat_df = None
    if feat_path and os.path.exists(feat_path):
        try:
            feat_df = pd.read_csv(feat_path, encoding="utf-8-sig",
                                   low_memory=False, on_bad_lines="skip")
        except Exception as e:
            print("  [llm_predictor] 特徴量DF読み込みスキップ: " + str(e))

    explanations = explain_picks_batch(picks, model_dict=model_dict, feat_df=feat_df)

    for i, bet in enumerate(picks):
        bet["llm_explanation"] = explanations[i]

    print("  [llm_predictor] " + str(len(picks)) + "頭の解説を追加完了")
    return picks


# ─────────────────────────────────────────────────────────────
# テストモード
# ─────────────────────────────────────────────────────────────

def _run_test():
    print("\n[llm_predictor] テスト開始")

    dummy_picks = [
        {
            "bamei": "テストウマ",
            "race_info": "東京芝1600m G3",
            "odds": 28.4,
            "win_prob": 14.2,
            "ev": 0.38,
            "kelly_bet": 3200,
        },
        {
            "bamei": "サンプルホース",
            "race_info": "阪神ダート1400m",
            "odds": 45.0,
            "win_prob": 9.8,
            "ev": 0.31,
            "kelly_bet": 1800,
        },
    ]

    print("\n--- 単体解説テスト ---")
    text = explain_pick(dummy_picks[0])
    print(text)

    print("\n--- バッチ解説テスト（並列） ---")
    explanations = explain_picks_batch(dummy_picks)
    for i, (bet, exp) in enumerate(zip(dummy_picks, explanations)):
        preview = exp[:80] + "..." if len(exp) > 80 else exp
        print("  [" + str(i + 1) + "] " + bet["bamei"] + ": " + preview)

    print("\n[llm_predictor] テスト完了")


if __name__ == "__main__":
    _run_test()
