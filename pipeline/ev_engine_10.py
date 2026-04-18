import pandas as pd
import numpy as np
import pickle
from datetime import datetime

EV_THRESHOLD = 0.15   # 最低期待値 15%（グリッドサーチ最適化結果）
MIN_ODDS = 10.0       # 最低オッズ（低オッズ馬は除外）


def _get_win_prob_index(le):
    """LabelEncoderのクラス一覧から「1着」に対応するインデックスを取得。"""
    classes = list(le.classes_)
    if 1 in classes:
        return classes.index(1)
    # 文字列 '1' でフォールバック
    if '1' in classes:
        return classes.index('1')
    return 0


def extract_win_probabilities(ensemble_proba, le):
    """アンサンブル確率行列から各馬の1着確率を抽出する。"""
    idx = _get_win_prob_index(le)
    return ensemble_proba[:, idx]


def calculate_ev(p_win, odds):
    """期待値 EV = p × odds − 1 (プラスなら収益見込みあり)"""
    return p_win * odds - 1.0


def build_ev_dataframe(test_df, ensemble_proba, le):
    """全馬の期待値を計算してDataFrameに追加する。"""
    win_probs = extract_win_probabilities(ensemble_proba, le)

    result = test_df.copy()
    result['win_probability'] = win_probs
    result['odds_decimal'] = pd.to_numeric(
        result['tansho_odds'], errors='coerce').fillna(0) / 10
    result['expected_value'] = (
        result['win_probability'] * result['odds_decimal'] - 1.0
    )
    return result


def filter_positive_ev(df, threshold=EV_THRESHOLD, min_odds=MIN_ODDS):
    """
    期待値プラスかつ最低オッズ条件を満たす馬を抽出する。
    レースごとに期待値最大の1頭を返す。
    """
    filtered = df[
        (df['expected_value'] >= threshold) &
        (df['odds_decimal'] >= min_odds)
    ].copy()

    # レースごとに期待値最大の馬を選ぶ
    best = (filtered
            .sort_values('expected_value', ascending=False)
            .groupby('race_code', as_index=False)
            .first())
    return best.sort_values('expected_value', ascending=False)


def run_ev_analysis(year=2025, threshold=EV_THRESHOLD):
    print(f"📊 [{datetime.now()}] 期待値計算エンジン起動...")

    with open("D:\\keiba_ai\\model_v8.pkl", "rb") as f:
        saved = pickle.load(f)

    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model  = saved['cb_model']
    le        = saved['le']
    features  = saved['features']

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    test_df = df[df['kaisai_nen'] == year].copy()

    if len(test_df) == 0:
        print(f"⚠️ {year}年のデータがありません")
        return pd.DataFrame()

    X_test = test_df[features]
    ensemble_proba = (
        0.5 * lgb_model.predict_proba(X_test) +
        0.3 * xgb_model.predict_proba(X_test) +
        0.2 * cb_model.predict_proba(X_test)
    )

    ev_df = build_ev_dataframe(test_df, ensemble_proba, le)
    positive_ev = filter_positive_ev(ev_df, threshold)

    print(f"\n{'='*55}")
    print(f"🎯 {year}年 期待値分析結果")
    print(f"{'='*55}")
    print(f"全馬数                ：{len(ev_df):,}頭")
    print(f"期待値{threshold*100:.0f}%以上・選抜レース：{len(positive_ev):,}R")

    # 期待値帯別実績
    bins   = [-float('inf'), -0.1, 0, 0.1, 0.3, float('inf')]
    labels = ['EV<-10%', '-10〜0%', '0〜10%', '10〜30%', 'EV>30%']
    ev_df['ev_band'] = pd.cut(ev_df['expected_value'], bins=bins, labels=labels)

    print(f"\n【期待値帯別実績】")
    for band, g in ev_df.groupby('ev_band', observed=True):
        total = len(g)
        hits  = (g['kakutei_chakujun'] == 1).sum()
        ret   = (g[g['kakutei_chakujun'] == 1]['odds_decimal'] * 100).sum()
        bet   = total * 100
        roi   = ret / bet * 100 if bet > 0 else 0
        print(f"  {band:<12}：{total:>6,}頭  "
              f"的中率{hits/total*100:>5.1f}%  "
              f"回収率{roi:>6.1f}%")

    out_path = f"D:\\keiba_ai\\ev_analysis_{year}.csv"
    positive_ev.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n💾 {out_path} に保存しました")

    return positive_ev


if __name__ == "__main__":
    result = run_ev_analysis(2025)
    if len(result) > 0:
        print(f"\n【期待値TOP10】")
        cols = ['race_code', 'bamei', 'win_probability',
                'odds_decimal', 'expected_value']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head(10).to_string(index=False))
