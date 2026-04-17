import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import pickle

print("📂 データ読み込み中...")
df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv", encoding="utf-8-sig")

# NaNを0で埋める
df = df.fillna(0)

print(f"件数：{len(df):,}件")

# 特徴量（新しい過去成績を追加！）
features = [
    'barei', 'seibetsu_code', 'kishu_code', 'chokyoshi_code',
    'futan_juryo', 'bataiju', 'zogen_sa', 'zogen_fugo',
    'tansho_odds', 'tansho_ninkijun', 'kyakushitsu_hantei',
    'kyori', 'track_code', 'tenko_code',
    'shiba_babajotai_code', 'dirt_babajotai_code', 'shusso_tosu',
    # 新しい特徴量！
    'past3_avg_chakujun', 'past3_avg_odds',
    'total_races', 'win_count', 'win_rate'
]

X = df[features]
y = df['kakutei_chakujun']

# 学習・テスト分割
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"📊 学習データ：{len(X_train):,}件")
print(f"📊 テストデータ：{len(X_test):,}件")

# モデル学習
print("\n🤖 モデル学習中...（数分かかります）")
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42,
    n_jobs=-1
)
model.fit(X_train, y_train)

# 精度確認
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f"\n✅ モデル学習完了！")
print(f"🎯 正解率：{accuracy:.2%}")

# 特徴量の重要度
print("\n🏆 予想に重要な要素TOP10:")
importances = pd.Series(
    model.feature_importances_, index=features
).sort_values(ascending=False)
for i, (feat, imp) in enumerate(importances.head(10).items()):
    print(f"  {i+1}位: {feat}（{imp:.3f}）")

# モデルを保存
with open("D:\\keiba_ai\\model_v2.pkl", "wb") as f:
    pickle.dump(model, f)
print("\n💾 model_v2.pkl に保存しました！")