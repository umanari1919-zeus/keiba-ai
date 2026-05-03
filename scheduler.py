import schedule
import time
import subprocess
import psycopg2
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(tz=JST)

DB_CONFIG = dict(host="127.0.0.1", port=5433, dbname="mykeibadb",
                 user="postgres", password="zeus")

def is_jra_race_day(date: datetime = None) -> bool:
    """kaisaibiテーブルで今日がJRA開催日か確認"""
    if date is None:
        date = now_jst()
    yyyymmdd = date.strftime("%Y%m%d")
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
        print(f"  開催日チェック失敗 (DB接続エラー): {e}")
        return date.weekday() in (5, 6)

PYTHON      = r"C:\Users\uchih\AppData\Local\Programs\Python\Python313\python.exe"
PIPELINE_V2 = r"D:\keiba_ai\pipeline_v2"
BASE_DIR    = r"D:\keiba_ai"


def _run(args: list[str], cwd: str = BASE_DIR) -> None:
    subprocess.run([PYTHON, "-X", "utf8"] + args, cwd=cwd)


# ─────────────────────────────────────────────────────────────────────
# 日次ジョブ
# ─────────────────────────────────────────────────────────────────────

def run_pipeline():
    """開催日のみ: 日次 DAG（ingest→…→monitor）を実行"""
    now = now_jst()
    if not is_jra_race_day(now):
        print(f"  本日 ({now.strftime('%m/%d')}) はJRA開催なし → スキップ")
        return
    print(f"  JRA開催日 ({now.strftime('%m/%d')}) → 日次パイプライン実行")
    _run([f"{PIPELINE_V2}/00_orchestrator.py"])


def run_weekday_mail():
    """月〜金: 曜日別の情報メールを送信"""
    now = now_jst()
    dow = now.weekday()
    if dow > 4:
        return
    labels = {0: "月曜:成績振り返り", 1: "火曜:特別登録馬",
              2: "水曜:注目調教馬",   3: "木曜:週末プレビュー", 4: "金曜:オッズ動向"}
    print(f"  {labels.get(dow, '')} メール送信")
    _run(["-c",
          "import sys; sys.path.insert(0,r'D:\\keiba_ai'); "
          "from pipeline.notify_08 import send_daily_report; send_daily_report()"])


def run_paper_trading():
    """30日間ペーパートレード（TradingAgent paper_trading モード）"""
    print(f"  ペーパートレード実行")
    _run([f"{PIPELINE_V2}/07_trade.py", "--paper"])


def run_odds_snapshot():
    """JRA開催日 07〜17時: リアルタイムオッズ取得"""
    now = now_jst()
    if not is_jra_race_day(now) or not (7 <= now.hour <= 17):
        return
    print(f"  オッズスナップショット取得 ({now.strftime('%H:%M')})")
    _run([f"{PIPELINE_V2}/../pipeline/odds_scraper_36.py"])


def run_roi_tracking():
    """日次 07:00: 前日レース結果確定後に回収率を精算"""
    print(f"  回収率精算実行")
    _run([f"{PIPELINE_V2}/15_roi_track.py"])


# ─────────────────────────────────────────────────────────────────────
# 週次ジョブ（月曜早朝）
# ─────────────────────────────────────────────────────────────────────

def run_rag_index_rebuild():
    """毎週月曜 03:00: RAG インデックス全件再構築"""
    print(f"  RAGインデックス再構築開始")
    _run([f"{PIPELINE_V2}/10_rag_index.py"])


def run_upsetscore_weekly():
    """毎週月曜 03:30: UpsetScore 再算出"""
    print(f"  UpsetScore週次再算出開始")
    _run([f"{PIPELINE_V2}/08_upsetscore.py"])


def run_knowledge_update():
    """毎週月曜 04:00: 知識ベース更新（KnowledgeAgent days=7）"""
    print(f"  知識ベース更新開始")
    _run([f"{PIPELINE_V2}/12_knowledge_update.py"])


def run_model_training():
    """毎週日曜 02:00: 週次 DAG（train→backtest→…→monitor）を実行"""
    print(f"  週次モデル再学習パイプライン開始")
    _run([f"{PIPELINE_V2}/00_orchestrator_weekly.py"])


# ─────────────────────────────────────────────────────────────────────
# スケジュール登録
# ─────────────────────────────────────────────────────────────────────

# 日次
schedule.every().day.at("08:00").do(run_pipeline)
schedule.every().day.at("08:30").do(run_weekday_mail)
schedule.every().day.at("09:00").do(run_paper_trading)
schedule.every().hour.at(":02").do(run_odds_snapshot)
schedule.every().day.at("07:00").do(run_roi_tracking)

# 週次（月曜早朝）
schedule.every().monday.at("03:00").do(run_rag_index_rebuild)
schedule.every().monday.at("03:30").do(run_upsetscore_weekly)
schedule.every().monday.at("04:00").do(run_knowledge_update)

# 週次（日曜早朝）
schedule.every().sunday.at("02:00").do(run_model_training)

print("=" * 55)
print("  うまなり地蔵AI スケジューラー起動")
print("=" * 55)
print("  日次 08:00  JRA開催日のみ 日次パイプライン")
print("  日次 08:30  月-金 曜日別情報メール")
print("  日次 09:00  ペーパートレード")
print("  毎時 :02   JRA開催日 07-17時 オッズ取得")
print("  日次 07:00  回収率精算")
print("  月曜 03:00  RAGインデックス再構築")
print("  月曜 03:30  UpsetScore週次再算出")
print("  月曜 04:00  知識ベース更新")
print("  日曜 02:00  週次モデル再学習")
print("=" * 55)
print(f"  本日({now_jst().strftime('%m/%d')} JST) 開催: {'あり' if is_jra_race_day() else 'なし'}")

while True:
    schedule.run_pending()
    time.sleep(60)
