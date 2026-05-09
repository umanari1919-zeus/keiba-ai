import time
import subprocess
import json
import sys
import pathlib
import os
import argparse
from datetime import datetime, date
from zoneinfo import ZoneInfo

try:
    import schedule
except ImportError:
    schedule = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import BASE_DIR as CONFIG_BASE_DIR, DATA_DIR as CONFIG_DATA_DIR, DB_CONFIG

BASE_DIR = pathlib.Path(CONFIG_BASE_DIR)
DATA_DIR = pathlib.Path(CONFIG_DATA_DIR)
PYTHON = os.getenv("KEIBA_PYTHON", sys.executable)

JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(tz=JST)

def is_jra_race_day(date: datetime = None) -> bool:
    """kaisaibiテーブルで今日がJRA開催日か確認"""
    if date is None:
        date = now_jst()
    yyyymmdd = date.strftime("%Y%m%d")
    if psycopg2 is None:
        print("  ⚠️ psycopg2 未インストール。開催日チェックは土日判定にフォールバック")
        return date.weekday() in (5, 6)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(
            "SELECT 1 FROM kaisaibi WHERE kaisaibi = %s LIMIT 1",
            (yyyymmdd,)
        )
        result = cur.fetchone() is not None
        conn.close()
        return result
    except Exception as e:
        print(f"  ⚠️ 開催日チェック失敗（DB接続エラー）: {e}")
        # DB接続失敗時は土日なら実行
        return date.weekday() in (5, 6)

MAX_RETRIES = 2
RETRY_WAIT  = 30  # 秒


def _run_with_retry(cmd: list, *, timeout: int = 600, label: str = "") -> subprocess.CompletedProcess:
    """subprocess実行をリトライ付きで行う。全リトライ失敗時はメール通知。"""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return result
            last_exc = RuntimeError(
                f"returncode={result.returncode}\n{result.stderr[-500:]}"
            )
        except subprocess.TimeoutExpired as e:
            last_exc = e
        except Exception as e:
            last_exc = e

        if attempt < MAX_RETRIES:
            print(f"  [{label}] リトライ {attempt}/{MAX_RETRIES} ({RETRY_WAIT}秒後)")
            time.sleep(RETRY_WAIT)

    _notify_failure(label, last_exc)
    raise last_exc


def _notify_failure(label: str, exc: Exception) -> None:
    """ジョブ失敗時にメール通知を試みる。通知自体が失敗してもクラッシュしない。"""
    try:
        from pipeline.notify_08 import send_notify
        now = now_jst().strftime("%Y-%m-%d %H:%M")
        send_notify(
            subject=f"[うまなり地蔵AI] ジョブ失敗: {label}",
            body=f"時刻: {now}\nジョブ: {label}\nリトライ{MAX_RETRIES}回失敗\n\nエラー:\n{exc}",
        )
    except Exception as notify_err:
        print(f"  [{label}] 通知送信失敗: {notify_err}")


def run_pipeline():
    """開催日のみ: mykeibadb同期 → 予想パイプライン → 推奨ベットメール"""
    now = now_jst()
    print(f"\n⏰ [{now}] 定時チェック開始")

    if not is_jra_race_day(now):
        print(f"  📭 本日（{now.strftime('%m/%d')}）はJRA開催なし → スキップ")
        return

    print(f"  🏇 本日（{now.strftime('%m/%d')}）はJRA開催日 → パイプライン実行")
    try:
        _run_with_retry(
            [
                PYTHON,
                "-X",
                "utf8",
                str(BASE_DIR / "run_all.py"),
                "--v2",
                "--sync-mykeibadb",
            ],
            timeout=1800, label="run_pipeline",
        )
        print(f"✅ [{datetime.now()}] 実行完了")
    except Exception as e:
        print(f"❌ [{datetime.now()}] パイプライン失敗: {e}")


PAPER_TRADE_STATE = DATA_DIR / "paper_trade_state.json"
PAPER_TRADE_DAYS  = 30  # 30日間ペーパートレード


def _load_paper_state() -> dict:
    if PAPER_TRADE_STATE.exists():
        try:
            return json.loads(PAPER_TRADE_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    state = {"start_date": date.today().isoformat(), "race_days": 0, "total_bets": 0, "active": True}
    PAPER_TRADE_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def _save_paper_state(state: dict) -> None:
    PAPER_TRADE_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_paper_trading():
    """
    JRA開催日のみ: 予想結果を読み込んでペーパートレードを実行。
    30日間の期間が終了したら自動停止してレポートを出力する。
    """
    now = now_jst()
    if not is_jra_race_day(now):
        return

    state = _load_paper_state()
    if not state.get("active", True):
        print(f"  [paper-trade] 30日間ペーパートレード期間終了済み (開始: {state.get('start_date')})")
        return

    start = date.fromisoformat(state["start_date"])
    elapsed_days = (date.today() - start).days
    if elapsed_days >= PAPER_TRADE_DAYS:
        state["active"] = False
        _save_paper_state(state)
        print(f"  [paper-trade] {PAPER_TRADE_DAYS}日間終了! 最終結果 -> {PAPER_TRADE_STATE}")
        _print_paper_summary(state)
        return

    print(f"\n  [paper-trade] ペーパートレード実行 ({elapsed_days+1}/{PAPER_TRADE_DAYS}日目)")

    try:
        from agents.base_agent import AgentMeta
        from agents.batch_inference_agent import BatchInferenceAgent
        from agents.trading_agent import TradingAgent

        meta = AgentMeta()

        # 今日の予測を読み込む
        infer_agent = BatchInferenceAgent(dry_run=True)  # 予測CSVは既存のものを使用
        today_str   = now.strftime("%Y%m%d")
        year        = now.strftime("%Y")

        # ev_analysis_{year}.csv から予測を読み込む
        import pandas as pd
        ev_path = DATA_DIR / f"ev_analysis_{year}.csv"
        if not ev_path.exists():
            ev_path = BASE_DIR / f"ev_analysis_{year}.csv"

        predictions = []
        if ev_path.exists():
            df = pd.read_csv(ev_path, on_bad_lines="skip")
            for _, row in df.iterrows():
                predictions.append({
                    "race_id":               str(row.get("race_id", row.get("race_code", ""))),
                    "entry_id":              str(row.get("entry_id", row.get("horse_num", ""))),
                    "win_prob":              float(row.get("win_prob", row.get("win_probability", 0))),
                    "place_prob":            float(row.get("place_prob", row.get("place_probability", 0))),
                    "expected_return":       float(row.get("expected_return", row.get("ev", 0))),
                    "uncertainty":           float(row.get("uncertainty", 0.30)),
                    "odds":                  float(row.get("odds", 10.0)),
                    "model_agreement_count": int(row.get("model_agreement_count", 2)),
                })

        # ペーパートレード実行
        trader = TradingAgent(paper_trading=True, dry_run=False)
        result = trader.execute(meta, {
            "predictions":     predictions,
            "quarantine_count": 0,
        })

        n_bets = len(result.output.get("candidate_bets", []))
        state["race_days"]  = state.get("race_days", 0) + 1
        state["total_bets"] = state.get("total_bets", 0) + n_bets
        _save_paper_state(state)

        print(f"  [paper-trade] 本日: {n_bets}件 | 累計: {state['total_bets']}件 | 残り{PAPER_TRADE_DAYS - elapsed_days - 1}日")

    except Exception as e:
        print(f"  [paper-trade] エラー: {e}")


def _print_paper_summary(state: dict) -> None:
    print("=" * 50)
    print("ペーパートレード 30日間 最終レポート")
    print(f"  開始日:     {state.get('start_date')}")
    print(f"  開催日数:   {state.get('race_days')}日")
    print(f"  累計ベット: {state.get('total_bets')}件")
    trade_log = DATA_DIR
    logs = sorted(trade_log.glob("trade_log_*.json"))
    print(f"  ログファイル: {len(logs)}件 -> {trade_log}")
    print("=" * 50)


def run_weekday_mail():
    """月〜金: 曜日別の情報メールを送信"""
    now = now_jst()
    dow = now.weekday()  # 0=月 … 4=金
    if dow > 4:
        return  # 土日は run_pipeline 側で対応
    labels = {0:"月曜:成績振り返り", 1:"火曜:特別登録馬",
              2:"水曜:注目調教馬",   3:"木曜:週末プレビュー", 4:"金曜:オッズ動向"}
    print(f"\n📧 [{now}] {labels.get(dow,'')} メール送信")
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(BASE_DIR)!r}); "
        "from pipeline.notify_08 import send_daily_report; "
        "send_daily_report()"
    )
    subprocess.run([PYTHON, "-X", "utf8", "-c",
        code])


# 開催日のみ: パイプライン（予想→メール）
if schedule is None:
    print("schedule が未インストールです。`pip install -r requirements.txt` 後に再実行してください。")
    sys.exit(1)

schedule.every().day.at("08:00").do(run_pipeline)

# 月〜金: 曜日別情報メール
schedule.every().day.at("08:30").do(run_weekday_mail)

# 開催日のみ: ペーパートレード（予想完了後09:00）
schedule.every().day.at("09:00").do(run_paper_trading)

# 毎時: オッズスナップショット収集（JRA開催日のみ、7:00〜17:00）
def run_odds_snapshot():
    now = now_jst()
    if not is_jra_race_day(now):
        return
    if not (7 <= now.hour <= 17):
        return
    print(f"\n  [odds-snapshot] {now.strftime('%H:%M')} オッズ取得")
    try:
        _run_with_retry(
            [PYTHON, "-X", "utf8", str(BASE_DIR / "pipeline" / "odds_scraper_36.py")],
            timeout=120, label="odds_snapshot",
        )
    except Exception as e:
        print(f"  [odds-snapshot] 最終失敗: {e}")

schedule.every().hour.at(":02").do(run_odds_snapshot)


# 週次: RAG インデックス再構築（毎週月曜 03:00）
def run_rag_index_rebuild():
    """keiba_data_features.csv の更新を RAGStore に反映する週次バッチ。"""
    now = now_jst()
    print(f"\n  [rag-index] {now.strftime('%Y-%m-%d %H:%M')} RAG インデックス再構築開始")
    rag_script = BASE_DIR / "pipeline_v2" / "10_rag_index.py"
    if not rag_script.exists():
        print("  [rag-index] 10_rag_index.py が見つかりません。スキップ。")
        return
    try:
        _run_with_retry(
            [PYTHON, "-X", "utf8", str(rag_script), "--limit", "50000", "--rebuild"],
            timeout=600, label="rag_index",
        )
        print(f"  [rag-index] 完了")
    except Exception as exc:
        print(f"  [rag-index] 最終失敗: {exc}")


schedule.every().monday.at("03:00").do(run_rag_index_rebuild)


# 週次: UpsetScore 再算出（毎週月曜 03:30）
def run_upsetscore_weekly():
    """ev_analysis CSV の更新を race_metrics テーブルに反映する週次バッチ。"""
    now = now_jst()
    print(f"\n  [upset-score] {now.strftime('%Y-%m-%d %H:%M')} UpsetScore 再算出")
    us_script = BASE_DIR / "pipeline_v2" / "08_upsetscore.py"
    run_tag   = f"weekly_{now.strftime('%Y%m%d')}"
    try:
        _run_with_retry(
            [PYTHON, "-X", "utf8", str(us_script), "--run_tag", run_tag],
            timeout=300, label="upsetscore",
        )
        print(f"  [upset-score] 完了")
    except Exception as exc:
        print(f"  [upset-score] 最終失敗: {exc}")


schedule.every().monday.at("03:30").do(run_upsetscore_weekly)


# 週次: モデル再学習（毎週日曜 02:00）
def run_model_training():
    """model_train_03.py を実行し、model_registry にバージョン登録する。"""
    now = now_jst()
    print(f"\n  [train] {now.strftime('%Y-%m-%d %H:%M')} モデル再学習開始")
    try:
        from agents.train_agent import TrainAgent
        from agents.base_agent import AgentMeta

        meta   = AgentMeta()
        agent  = TrainAgent(dry_run=False)
        result = agent.execute(meta, {})

        if result.ok:
            mid     = result.output.get("model_id", "")
            metrics = result.output.get("metrics", {})
            acc     = metrics.get("ensemble_acc", "N/A")
            print(f"  [train] 完了: model_id={mid} ensemble_acc={acc}")
        else:
            print(f"  [train] 失敗: {result.error}")
    except Exception as exc:
        print(f"  [train] 例外: {exc}")


schedule.every().sunday.at("02:00").do(run_model_training)


# 週次: 知識ベース更新（毎週月曜 04:00）
def run_knowledge_update():
    """knowledge_curator_41.py を KnowledgeAgent 経由で実行し、知識ベースを更新する。"""
    now = now_jst()
    print(f"\n  [knowledge] {now.strftime('%Y-%m-%d %H:%M')} 知識ベース更新開始")
    try:
        from agents.knowledge_agent import KnowledgeAgent
        from agents.base_agent import AgentMeta

        meta   = AgentMeta()
        agent  = KnowledgeAgent(dry_run=False)
        result = agent.execute(meta, {"days": 7, "force_snapshot": True})

        if result.ok:
            out = result.output
            print(
                f"  [knowledge] 完了: active={out.get('active_count',0)} "
                f"ev_boost={out.get('ev_boost_entries',0)} "
                f"version={out.get('version','')}"
            )
        else:
            print(f"  [knowledge] 失敗: {result.error}")
    except Exception as exc:
        print(f"  [knowledge] 例外: {exc}")


schedule.every().monday.at("04:00").do(run_knowledge_update)


# 日次: 回収率精算（翌朝 07:00 — レース結果確定後）
def run_roi_tracking():
    """roi_tracker.csv の日次損益を集計して MonitorAgent へのメトリクスを保存する。"""
    now = now_jst()
    print(f"\n  [roi-track] {now.strftime('%Y-%m-%d %H:%M')} 回収率精算開始")
    try:
        from agents.roi_tracker_agent import RoiTrackerAgent
        from agents.base_agent import AgentMeta

        meta   = AgentMeta()
        result = RoiTrackerAgent(dry_run=False).execute(meta, {})

        if result.ok:
            out = result.output
            print(
                f"  [roi-track] 完了: "
                f"daily={out.get('daily_roi', 0)*100:.1f}% "
                f"weekly={out.get('weekly_roi', 0)*100:.1f}% "
                f"losses={out.get('consecutive_losses', 0)}"
            )
            for a in out.get("alerts", []):
                print(f"  [roi-track] ALERT: {a.get('message', '')}")
        else:
            print(f"  [roi-track] 失敗: {result.error}")
    except Exception as exc:
        print(f"  [roi-track] 例外: {exc}")


schedule.every().day.at("07:00").do(run_roi_tracking)


def print_startup_summary() -> None:
    print("=" * 50)
    print("[SCHEDULER] Umanari Jizo AI Scheduler Started")
    print("[SCHEDULE] 08:00 - Run prediction (JRA race day only)")
    print("[SCHEDULE] 08:30 - Mail daily info (Mon-Fri)")
    print("=" * 50)
    _ps = _load_paper_state()
    print(f"  Today ({now_jst().strftime('%m/%d')} JST) JRA race: {'YES' if is_jra_race_day() else 'NO'}")
    print(f"  ペーパートレード: {'稼働中' if _ps.get('active') else '終了'} ({_ps.get('race_days',0)}開催日 / {PAPER_TRADE_DAYS}日間)")
    print("  オッズスナップショット: 毎時 :02 (JRA開催日 07:00-17:00)")


def list_jobs() -> None:
    print("=" * 50)
    print("[SCHEDULER] Registered jobs")
    print("=" * 50)
    for idx, job in enumerate(schedule.jobs, 1):
        next_run = job.next_run.isoformat(sep=" ") if job.next_run else "N/A"
        print(f"{idx:02d}. next={next_run}  {job}")


def main() -> int:
    parser = argparse.ArgumentParser(description="うまなり地蔵AI scheduler")
    parser.add_argument("--list-jobs", action="store_true", help="常駐せず登録ジョブ一覧だけ表示")
    parser.add_argument("--check-now", action="store_true", help="常駐せず現在の開催日・ペーパートレード状態だけ表示")
    args = parser.parse_args()

    if args.list_jobs:
        list_jobs()
        return 0
    if args.check_now:
        print_startup_summary()
        return 0

    print_startup_summary()
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
