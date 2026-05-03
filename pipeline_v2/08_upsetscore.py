"""
08_upsetscore.py — レース別アップセットスコア算出
===================================================
当日の予測データ（ev_analysis_YYYY.csv）からレースごとに
荒れ度スコア（upset_score）を算出し、public.race_metrics テーブルへ書き込む。

算出指標:
  avg_gap    — 最低オッズ馬と他馬の平均オッズ差（荒れ幅）
  odds_std   — レース内オッズ標準偏差
  top3_prob  — 上位3頭の推定勝率合計（= 正規化 1/odds の上位3合計）
  shock_score — 高オッズ馬の相対的支持率（upset 候補の EV 平均）
  upset_score — 総合荒れ度 (0〜1)

実行方法:
  python pipeline_v2/08_upsetscore.py
  python pipeline_v2/08_upsetscore.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd

# ─── パス設定 ────────────────────────────────────────────────
BASE_DIR = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
DATA_DIR = BASE_DIR / "data"

LOG_DIR = pathlib.Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%Y%m%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"upsetscore_{today}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

DB_URL = os.getenv("KEIBA_DB_URL", "postgresql://postgres:trust@localhost:5433/mykeibadb")

# upset_score の重み
W_AVG_GAP    = 0.30
W_ODDS_STD   = 0.25
W_TOP3_PROB  = 0.25  # inverted (低いほど荒れる)
W_SHOCK      = 0.20


# ─────────────────────────────────────────────────────────────
# データ読み込み
# ─────────────────────────────────────────────────────────────

def load_ev_data() -> pd.DataFrame:
    """ev_analysis_{year}.csv を読み込む（当年 → 前年の順）。"""
    year = datetime.now().year
    # BASE_DIR 直下と DATA_DIR の両方を検索
    for y in [year, year - 1]:
        for search_dir in [BASE_DIR, DATA_DIR]:
            path = search_dir / f"ev_analysis_{y}.csv"
            if path.exists():
                df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
                log.info("EV データ読み込み: %s (%d 行)", path, len(df))
                return df
    log.warning("ev_analysis CSV が見つかりません。空 DataFrame を返します。")
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# 指標算出
# ─────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_race_metrics(group: pd.DataFrame) -> dict:
    """1 レース分の DataFrame → 指標 dict を返す。"""
    # オッズ列を探す
    odds_col = next(
        (c for c in ["tansho_odds", "odds_decimal", "odds", "min_odds"] if c in group.columns),
        None,
    )
    odds_vals: list[float] = []
    if odds_col:
        raw = [_safe_float(v) for v in group[odds_col] if _safe_float(v) > 1.0]
        # tansho_odds は JRA 形式（実オッズ × 100）→ 100 で割って実オッズに変換
        # odds_decimal は既に実オッズ形式
        if odds_col == "tansho_odds" and raw and max(raw) > 100:
            raw = [v / 100.0 for v in raw]
        odds_vals = raw

    if not odds_vals:
        return {
            "avg_gap":    0.0,
            "odds_std":   0.0,
            "top3_prob":  0.33,
            "shock_score": 0.0,
            "upset_score": 0.5,
        }

    min_odds  = min(odds_vals)
    avg_gap   = (sum(odds_vals) / len(odds_vals)) - min_odds
    n         = len(odds_vals)
    mean      = sum(odds_vals) / n
    odds_std  = math.sqrt(sum((o - mean) ** 2 for o in odds_vals) / max(n, 1))

    # 推定勝率 = 1/odds（正規化）
    inv_odds  = [1.0 / max(o, 0.1) for o in odds_vals]
    total_inv = sum(inv_odds)
    probs     = sorted([v / total_inv for v in inv_odds], reverse=True)
    top3_prob = sum(probs[:3])  # 上位3頭の勝率合計

    # shock_score: 高 EV（穴馬候補）エントリーの EV 平均
    ev_col = next((c for c in ["expected_value", "ev", "expected_return"] if c in group.columns), None)
    if ev_col:
        ev_vals = [_safe_float(v) for v in group[ev_col] if _safe_float(v) > 0]
        shock_score = sum(v for v in ev_vals if v > 1.15) / max(len(ev_vals), 1)
    else:
        shock_score = 0.0

    # upset_score (0〜1)
    # avg_gap を正規化（20以上で満点）
    norm_gap   = min(1.0, avg_gap / 20.0)
    # odds_std を正規化（15以上で満点）
    norm_std   = min(1.0, odds_std / 15.0)
    # top3_prob は低いほど荒れる → 反転
    inv_top3   = max(0.0, 1.0 - top3_prob)
    # shock_score 正規化（0.5以上で満点）
    norm_shock = min(1.0, shock_score / 0.5)

    upset_score = (
        W_AVG_GAP   * norm_gap
        + W_ODDS_STD  * norm_std
        + W_TOP3_PROB * inv_top3
        + W_SHOCK     * norm_shock
    )

    return {
        "avg_gap":     round(avg_gap, 4),
        "odds_std":    round(odds_std, 4),
        "top3_prob":   round(top3_prob, 4),
        "shock_score": round(shock_score, 4),
        "upset_score": round(upset_score, 4),
    }


# ─────────────────────────────────────────────────────────────
# DB 書き込み
# ─────────────────────────────────────────────────────────────

def upsert_race_metrics(rows: list[tuple], run_tag: str) -> int:
    """
    public.race_metrics に UPSERT する。
    rows: [(race_id, metric_name, metric_value), ...]
    Returns: 書き込み行数
    """
    try:
        import psycopg2
    except ImportError:
        log.warning("psycopg2 未インストール。DB 書き込みをスキップします。")
        return 0

    sql = """
        INSERT INTO race_metrics (race_id, metric_name, metric_value, computed_at, run_tag)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (race_id, metric_name)
        DO UPDATE SET
            metric_value = EXCLUDED.metric_value,
            computed_at  = EXCLUDED.computed_at,
            run_tag      = EXCLUDED.run_tag
    """
    computed_at = datetime.now(timezone.utc)
    written = 0
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            for race_id, metric_name, metric_value in rows:
                cur.execute(sql, (race_id, metric_name, metric_value, computed_at, run_tag))
                written += 1
        conn.commit()
        conn.close()
        log.info("race_metrics UPSERT: %d 行", written)
    except Exception as exc:
        log.warning("DB 書き込みエラー: %s", exc)
    return written


# ─────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────

def run_upsetscore(dry_run: bool = False, run_tag: str = "") -> dict:
    """
    EV データを読み込み → レース別指標算出 → DB 書き込み。

    Returns
    -------
    dict: {races_computed, metrics_written, top_upsets: [...]}
    """
    df = load_ev_data()
    if df.empty:
        return {"races_computed": 0, "metrics_written": 0, "top_upsets": []}

    # race_id 列を特定
    # race_code は JRA 16桁形式（末尾2桁が umaban）→ 先頭14桁でレース単位に集約
    if "race_code" in df.columns and "race_id" not in df.columns:
        df = df.copy()  # フラグメント警告回避
        df["_race_key"] = df["race_code"].astype(str).str[:14]
        race_id_col = "_race_key"
    else:
        race_id_col = next(
            (c for c in ["race_id", "race_code", "レースID", "race_key"] if c in df.columns),
            None,
        )
    if race_id_col is None:
        log.warning("race_id 列が見つかりません。処理をスキップします。")
        return {"races_computed": 0, "metrics_written": 0, "top_upsets": []}

    db_rows: list[tuple] = []
    race_summaries: list[dict] = []

    for race_id, group in df.groupby(race_id_col):
        metrics = compute_race_metrics(group)
        race_summaries.append({"race_id": str(race_id), **metrics})

        for metric_name, metric_value in metrics.items():
            db_rows.append((str(race_id), metric_name, metric_value))

    races_computed = len(race_summaries)
    log.info("レース数: %d / 指標行数: %d", races_computed, len(db_rows))

    # 上位3レース（upset_score 順）
    top_upsets = sorted(race_summaries, key=lambda r: r["upset_score"], reverse=True)[:3]
    for r in top_upsets:
        log.info(
            "  [upset] race_id=%s score=%.3f avg_gap=%.1f odds_std=%.1f",
            r["race_id"], r["upset_score"], r["avg_gap"], r["odds_std"],
        )

    metrics_written = 0
    if not dry_run:
        metrics_written = upsert_race_metrics(db_rows, run_tag)
    else:
        log.info("[DRY-RUN] DB 書き込みをスキップ (%d 行)", len(db_rows))
        metrics_written = 0

    return {
        "races_computed":  races_computed,
        "metrics_written": metrics_written,
        "top_upsets":      top_upsets,
    }


# ─────────────────────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="レース別アップセットスコア算出")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace_id", default=str(uuid.uuid4()))
    parser.add_argument("--run_tag",  default=f"run_{today}_{uuid.uuid4().hex[:8]}")
    args = parser.parse_args()

    result = run_upsetscore(dry_run=args.dry_run, run_tag=args.run_tag)
    log.info("完了: %s", result)
    sys.exit(0)
