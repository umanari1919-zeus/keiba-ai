import schedule
import time
import subprocess
from datetime import datetime

def run_pipeline():
    print(f"⏰ [{datetime.now()}] 自動実行開始！")
    subprocess.run(["python", "D:\\keiba_ai\\run_all.py"])
    print(f"✅ [{datetime.now()}] 自動実行完了！")

def run_post():
    print(f"📱 [{datetime.now()}] X投稿開始！")
    subprocess.run(["python", "D:\\keiba_ai\\pipeline\\post_x_05.py"])
    print(f"✅ [{datetime.now()}] X投稿完了！")

# 毎週土曜日・日曜日の朝8時にパイプライン実行
schedule.every().saturday.at("08:00").do(run_pipeline)
schedule.every().sunday.at("08:00").do(run_pipeline)

# 毎週土曜日・日曜日の朝9時にX投稿
schedule.every().saturday.at("09:00").do(run_post)
schedule.every().sunday.at("09:00").do(run_post)

print("="*50)
print("🙏 うまなり地蔵AI スケジューラー起動！")
print("📅 毎週土日 08:00 自動実行")
print("📱 毎週土日 09:00 X自動投稿")
print("="*50)

# ずっと動き続ける
while True:
    schedule.run_pending()
    time.sleep(60)