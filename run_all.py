import sys
from datetime import datetime

sys.path.append("D:\\keiba_ai")

from pipeline.data_fetch_01 import fetch_data
from pipeline.feature_eng_02 import feature_engineering
from pipeline.model_train_03 import train_model
from pipeline.predict_04 import simulate_recovery
from pipeline.claude_comment_06 import generate_todays_post
from pipeline.note_07 import generate_note_article
from pipeline.notify_08 import send_pipeline_report

def run_all():
    print("="*50)
    print(f"🙏 うまなり地蔵AI 全自動実行開始")
    print(f"⏰ {datetime.now()}")
    print("="*50)

    # STEP1: データ取得
    print("\n【STEP 1/6】データ取得")
    fetch_data()

    # STEP2: 特徴量計算
    print("\n【STEP 2/6】特徴量計算")
    feature_engineering()

    # STEP3: モデル学習
    print("\n【STEP 3/6】モデル学習")
    train_model()

    # STEP4: 予想生成
    print("\n【STEP 4/6】予想生成")
    year = datetime.now().year
    result = simulate_recovery(year)
    
    # STEP5: コメント生成
    print("\n【STEP 5/6】うまなり地蔵コメント生成")
    post_text = generate_todays_post()

    # STEP6: note記事生成
    print("\n【STEP 6/6】note記事生成")
    generate_note_article()

    # Gmail通知
    print("\n📧 Gmail通知送信中...")
    if result:
        notify_result = {
            'hit_rate': result.get('hit_rate', 0),
            'recovery_rate': result.get('recovery_rate', 0),
            'profit': result.get('profit', 0),
            'total_races': result.get('races', 0),
            'total_profit': result.get('profit', 0),
            'honmei': post_text[:100] if post_text else '取得中...'
        }
        send_pipeline_report(notify_result)

    print("\n" + "="*50)
    print(f"✅ 全自動実行完了！")
    print(f"⏰ {datetime.now()}")
    print("="*50)

if __name__ == "__main__":
    run_all()