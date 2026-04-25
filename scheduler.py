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
        print(f"  ⚠️ 開催日チェック失敗（DB接続エラー）: {e}")
        # DB接続失敗時は土日なら実行
        return date.weekday() in (5, 6)

PYTHON = r"C:\Users\uchih\AppData\Local\Programs\Python\Python313\python.exe"

def run_pipeline():
    """開催日のみ: mykeibadb同期 → 予想パイプライン → 推奨ベットメール"""
    now = now_jst()
    print(f"\n⏰ [{now}] 定時チェック開始")

    if not is_jra_race_day(now):
        print(f"  📭 本日（{now.strftime('%m/%d')}）はJRA開催なし → スキップ")
        return

    print(f"  🏇 本日（{now.strftime('%m/%d')}）はJRA開催日 → パイプライン実行")
    subprocess.run([PYTHON, "-X", "utf8", r"D:\keiba_ai\run_all.py", "--skip-train"])
    print(f"✅ [{datetime.now()}] 実行完了")


def run_weekday_mail():
    """月〜金: 曜日別の情報メールを送信"""
    now = now_jst()
    dow = now.weekday()  # 0=月 … 4=金
    if dow > 4:
        return  # 土日は run_pipeline 側で対応
    labels = {0:"月曜:成績振り返り", 1:"火曜:特別登録馬",
              2:"水曜:注目調教馬",   3:"木曜:週末プレビュー", 4:"金曜:オッズ動向"}
    print(f"\n📧 [{now}] {labels.get(dow,'')} メール送信")
    subprocess.run([PYTHON, "-X", "utf8", "-c",
        "import sys; sys.path.insert(0,r'D:\\keiba_ai'); "
        "from pipeline.notify_08 import send_daily_report; send_daily_report()"])


# 開催日のみ: パイプライン（予想→メール）
schedule.every().day.at("08:00").do(run_pipeline)

# 月〜金: 曜日別情報メール
schedule.every().day.at("08:30").do(run_weekday_mail)

print("=" * 50)
print("🙏 うまなり地蔵AI スケジューラー起動")
print("📅 毎朝08:00 → JRA開催日のみ予想実行")
print("📧 毎朝08:30 → 月〜金は曜日別情報メール")
print("=" * 50)
print(f"  本日({now_jst().strftime('%m/%d')} JST)の開催: {'あり🏇' if is_jra_race_day() else 'なし📭'}")

while True:
    schedule.run_pending()
    time.sleep(60)
