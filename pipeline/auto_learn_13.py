"""
自動学習・自己改善システム
レース結果を自動フィードバックし、パフォーマンスが閾値を下回ったら
モデルを自動再学習する。
"""
import pandas as pd
import numpy as np
import pickle
import json
import os
import shutil
from datetime import datetime

from sqlalchemy import create_engine, text

PERF_FILE    = "D:\\keiba_ai\\data\\model_performance.json"
MODEL_FILE   = "D:\\keiba_ai\\model_v8.pkl"
DB_URL       = "postgresql://postgres:trust@localhost:5433/mykeibadb"

RETRAIN_THRESHOLD    = 0.80   # 回収率80%未満で再学習検討
RETRAIN_WINDOW       = 3      # 直近N回の平均で判定
MIN_EVAL_SAMPLES     = 20     # 評価に必要な最低サンプル数
BACKUP_KEEP          = 5      # バックアップを何世代保持するか


# ──────────────────────────────────────────────
# DB からの結果取得
# ──────────────────────────────────────────────

def fetch_recent_results(days=30):
    """
    直近N日の確定レース結果をDBから取得する。
    Returns DataFrame or empty DataFrame on error.
    """
    engine = create_engine(DB_URL)
    year = datetime.now().year

    query = text("""
        SELECT
            race_code,
            umaban,
            bamei,
            kakutei_chakujun,
            tansho_odds,
            kaisai_nen,
            kaisai_gappi
        FROM umagoto_race_joho
        WHERE kaisai_nen = :year
          AND kakutei_chakujun IS NOT NULL
          AND kakutei_chakujun != ''
        ORDER BY race_code
    """)

    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'year': str(year)})
        df['kakutei_chakujun'] = pd.to_numeric(
            df['kakutei_chakujun'], errors='coerce')
        return df.dropna(subset=['kakutei_chakujun'])
    except Exception as e:
        print(f"  ⚠️ DB接続エラー：{e}")
        return pd.DataFrame()


# ──────────────────────────────────────────────
# パフォーマンス評価
# ──────────────────────────────────────────────

def evaluate_predictions(actual_df, predictions_df):
    """
    予測結果と実際の着順を照合してパフォーマンス指標を返す。

    actual_df      : race_code, bamei, kakutei_chakujun, tansho_odds
    predictions_df : race_code, bamei, pred_chakujun
    """
    merged = predictions_df.merge(
        actual_df[['race_code', 'bamei', 'kakutei_chakujun', 'tansho_odds']],
        on=['race_code', 'bamei'],
        how='inner'
    )

    if len(merged) < MIN_EVAL_SAMPLES:
        return None

    hits         = (merged['kakutei_chakujun'] == 1).sum()
    total        = len(merged)
    total_return = (merged[merged['kakutei_chakujun'] == 1]
                    ['tansho_odds'].astype(float) / 10 * 100).sum()
    total_bet    = total * 100

    return {
        'evaluated_at':  datetime.now().isoformat(),
        'total':         int(total),
        'hits':          int(hits),
        'hit_rate':      float(hits / total),
        'recovery_rate': float(total_return / total_bet) if total_bet > 0 else 0.0,
    }


# ──────────────────────────────────────────────
# パフォーマンス履歴の保存・読込
# ──────────────────────────────────────────────

def save_performance(perf):
    os.makedirs(os.path.dirname(PERF_FILE), exist_ok=True)
    history = load_performance_history()
    history.append(perf)
    history = history[-50:]  # 最大50件保持
    with open(PERF_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_performance_history():
    if not os.path.exists(PERF_FILE):
        return []
    with open(PERF_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ──────────────────────────────────────────────
# 再学習判定
# ──────────────────────────────────────────────

def should_retrain():
    """
    再学習が必要か判定する。

    Returns
    -------
    (bool, str) : (再学習要否, 理由メッセージ)
    """
    history = load_performance_history()

    if len(history) < RETRAIN_WINDOW:
        return False, f"評価履歴が{len(history)}件（最低{RETRAIN_WINDOW}件必要）"

    recent     = history[-RETRAIN_WINDOW:]
    avg_roi    = np.mean([h['recovery_rate'] for h in recent])
    trend_rois = [h['recovery_rate'] for h in history[-6:]]

    # トレンド（直近6回で下降傾向）
    if len(trend_rois) >= 4:
        first_half  = np.mean(trend_rois[:len(trend_rois)//2])
        second_half = np.mean(trend_rois[len(trend_rois)//2:])
        declining   = second_half < first_half * 0.9
    else:
        declining = False

    if avg_roi < RETRAIN_THRESHOLD:
        reason = (f"直近{RETRAIN_WINDOW}回の平均回収率 "
                  f"{avg_roi*100:.1f}% < 閾値{RETRAIN_THRESHOLD*100:.0f}%")
        return True, reason

    if declining and avg_roi < 1.0:
        reason = (f"回収率が下降トレンド（{first_half*100:.1f}% → "
                  f"{second_half*100:.1f}%）かつ100%未満")
        return True, reason

    return False, (f"直近{RETRAIN_WINDOW}回の平均回収率 "
                   f"{avg_roi*100:.1f}%（正常）")


# ──────────────────────────────────────────────
# 自動再学習
# ──────────────────────────────────────────────

def _cleanup_old_backups():
    """古いバックアップファイルを削除して最新N世代のみ保持する。"""
    import glob
    pattern = MODEL_FILE.replace('.pkl', '_backup_*.pkl')
    backups = sorted(glob.glob(pattern))
    while len(backups) > BACKUP_KEEP:
        old = backups.pop(0)
        os.remove(old)
        print(f"  🗑️ 古いバックアップを削除：{os.path.basename(old)}")


def auto_retrain():
    """モデルをバックアップしてから再学習する。"""
    print(f"\n⚡ [{datetime.now()}] 自動再学習を開始します...")

    backup = MODEL_FILE.replace(
        '.pkl', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pkl')
    shutil.copy2(MODEL_FILE, backup)
    print(f"  💾 バックアップ保存：{os.path.basename(backup)}")
    _cleanup_old_backups()

    from pipeline.model_train_03 import train_model
    train_model()

    print(f"  ✅ 再学習完了：{datetime.now()}")


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def run_auto_learn(simulation_csv="D:\\keiba_ai\\simulation_2025.csv"):
    """
    自動学習サイクルを1回実行する。

    1. DBから最新レース結果を取得
    2. simulation_2025.csv の予測と照合して精度評価
    3. パフォーマンス履歴を保存
    4. 閾値を下回れば自動再学習
    """
    print(f"\n{'='*55}")
    print(f"🤖 自動学習・自己改善システム")
    print(f"{'='*55}")

    # Step 1: 実績取得
    print("\n📥 直近レース結果を取得中...")
    actual_df = fetch_recent_results(days=30)
    if len(actual_df) == 0:
        print("  データを取得できませんでした（DB未接続の場合はスキップ）")
        needs_retrain, reason = should_retrain()
        print(f"\n🔍 再学習判定：{reason}")
        if needs_retrain:
            auto_retrain()
        return needs_retrain

    print(f"  取得件数：{len(actual_df):,}件")

    # Step 2: 予測との照合
    try:
        pred_df = pd.read_csv(simulation_csv, encoding="utf-8-sig",
                              dtype={'race_code': str}, on_bad_lines="skip")
        perf = evaluate_predictions(actual_df, pred_df)
    except FileNotFoundError:
        print(f"  ⚠️ {simulation_csv} が見つかりません")
        perf = None

    if perf:
        save_performance(perf)
        roi_emoji = "🎉" if perf['recovery_rate'] >= 1.0 else "📉"
        print(f"\n{roi_emoji} 直近パフォーマンス評価（{perf['total']}件）")
        print(f"  的中率  ：{perf['hit_rate']*100:.1f}%")
        print(f"  回収率  ：{perf['recovery_rate']*100:.1f}%")
    else:
        print("  評価サンプル不足のため今回はスキップ")

    # Step 3: 再学習判定
    needs_retrain, reason = should_retrain()
    print(f"\n🔍 再学習判定：{reason}")

    if needs_retrain:
        auto_retrain()
        return True

    print("✅ 再学習不要（モデル良好）")
    return False


def show_performance_trend():
    """パフォーマンストレンドをコンソールに表示する。"""
    history = load_performance_history()

    if not history:
        print("パフォーマンス履歴がありません")
        return

    print(f"\n{'='*55}")
    print(f"📈 モデルパフォーマンストレンド（直近{min(len(history),15)}回）")
    print(f"{'='*55}")

    for h in history[-15:]:
        date   = h['evaluated_at'][:10]
        roi    = h['recovery_rate'] * 100
        hr     = h['hit_rate'] * 100
        n      = h['total']
        emoji  = "🎉" if roi >= 100 else ("⚠️" if roi >= 80 else "🚨")
        bar    = "█" * int(roi / 10) + "░" * max(0, 10 - int(roi / 10))
        print(f"  {emoji} {date}  [{bar}]  "
              f"回収率{roi:>6.1f}%  的中率{hr:>5.1f}%  ({n}件)")

    # 平均
    rois = [h['recovery_rate'] for h in history]
    print(f"\n  全期間平均回収率：{np.mean(rois)*100:.1f}%")
    print(f"  直近3回平均回収率：{np.mean(rois[-3:])*100:.1f}%")
    print(f"{'='*55}")


if __name__ == "__main__":
    show_performance_trend()
    retrained = run_auto_learn()
    if retrained:
        print("\n🔄 モデルが更新されました。次回予測から新モデルが使用されます。")
