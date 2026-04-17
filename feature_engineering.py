import pandas as pd
import numpy as np
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://postgres:trust@localhost:5433/mykeibadb"
)

print("📂 データ読み込み中...")
df = pd.read_csv("D:\\keiba_ai\\keiba_data.csv", encoding="utf-8-sig")

# クレンジング
df['bataiju'] = pd.to_numeric(df['bataiju'], errors='coerce')
df['zogen_sa'] = pd.to_numeric(df['zogen_sa'], errors='coerce')
df['zogen_fugo'] = df['zogen_fugo'].map({'+': 1, '-': -1}).fillna(0)
df['kakutei_chakujun'] = pd.to_numeric(df['kakutei_chakujun'], errors='coerce')
df = df.fillna(0)

# 日付でソート（過去→未来の順番に並べる）
df = df.sort_values(['ketto_toroku_bango', 'kaisai_nen', 'race_code'])
df = df.reset_index(drop=True)

print("⚙️ 過去成績の特徴量を計算中...（少し時間がかかります）")

# 馬ごとの過去3走の平均着順
df['past3_avg_chakujun'] = (
    df.groupby('ketto_toroku_bango')['kakutei_chakujun']
    .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
)

# 馬ごとの過去3走の平均オッズ
df['past3_avg_odds'] = (
    df.groupby('ketto_toroku_bango')['tansho_odds']
    .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
)

# 馬ごとの通算出走回数
df['total_races'] = (
    df.groupby('ketto_toroku_bango').cumcount()
)

# 馬ごとの通算1着回数
df['win_count'] = (
    df.groupby('ketto_toroku_bango')['kakutei_chakujun']
    .transform(lambda x: (x.shift(1) == 1).cumsum())
)

# 勝率
df['win_rate'] = df['win_count'] / (df['total_races'] + 1)

print("✅ 特徴量計算完了！")
print(f"件数：{len(df):,}件")

# 保存
df.to_csv("D:\\keiba_ai\\keiba_data_features.csv", 
          index=False, encoding="utf-8-sig")
print("💾 keiba_data_features.csv に保存しました！")

# 確認
print("\n📋 新しい特徴量の確認:")
print(df[['bamei', 'kakutei_chakujun', 'past3_avg_chakujun', 
          'total_races', 'win_rate']].head(10).to_string())