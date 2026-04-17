import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from datetime import datetime

load_dotenv("D:\\keiba_ai\\.env")

def send_notify(subject, body):
    """Gmail通知を送る"""
    
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    notify_to = os.getenv("NOTIFY_TO")
    
    if not all([gmail_address, gmail_password, notify_to]):
        print("⚠️ .envファイルを確認してください")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_address
        msg['To'] = notify_to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(gmail_address, gmail_password)
            smtp.send_message(msg)
        
        print("✅ Gmail通知送信完了！")
        return True
        
    except Exception as e:
        print(f"❌ 送信失敗：{e}")
        return False

def send_pipeline_report(result):
    """パイプライン実行結果を通知"""
    
    now = datetime.now().strftime('%Y年%m月%d日 %H:%M')
    
    subject = f"🙏 うまなり地蔵AI 週次レポート {now}"
    
    body = f"""
🙏 うまなり地蔵AI 週次レポート
━━━━━━━━━━━━━━━━━━
📅 実行日時：{now}

📊 今週の成績
的中率　：{result.get('hit_rate', 0):.1f}%
回収率　：{result.get('recovery_rate', 0):.1f}%
損　益　：{result.get('profit', 0):+,.0f}円

🐴 本日の本命馬
{result.get('honmei', '取得中...')}

📈 累計成績
総レース：{result.get('total_races', 0):,}R
累計損益：{result.get('total_profit', 0):+,.0f}円

━━━━━━━━━━━━━━━━━━
データと閻魔大王の御加護を信じよ🔥
うまなり地蔵AI研究所
"""
    
    return send_notify(subject, body)

def send_test():
    """テスト通知"""
    subject = "🙏 うまなり地蔵AI テスト通知"
    body = """
うまなり地蔵AIからテスト通知です！

Gmail通知の設定が完了しました🎉

毎週土日の朝6時に
自動で予想レポートが届きます！

データと閻魔大王の御加護を信じよ🔥
"""
    return send_notify(subject, body)

if __name__ == "__main__":
    print("📧 テスト通知を送信します...")
    send_test()