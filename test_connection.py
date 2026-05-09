import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import numpy as np
from pipeline.config import CSV_FEATURES, CSV_READ_OPTS, LEAKY_DERIVED_FEATURE_COLUMNS

# データ読み込み
print("📂 データ読み込み中...")
df = pd.read_csv(CSV_FEATURES, **CSV_READ_OPTS)
df = df.drop(columns=[c for c in LEAKY_DERIVED_FEATURE_COLUMNS if c in df.columns])

# データクレンジング
print("🧹 データクレンジング中...")

# 馬体重を数字に変換（変換できないものはNaNに）
df['bataiju'] = pd.to_numeric(df['bataiju'], errors='coerce')
df['zogen_sa'] = pd.to_numeric(df['zogen_sa'], errors='coerce')

# 増減符号を数字に変換（+→1、-→-1、それ以外→0）
df['zogen_fugo'] = df['zogen_fugo'].map({'+': 1, '-': -1}).fillna(0)

# NaNを0で埋める
df = df.fillna(0)

# 着順を数字に変換
df['kakutei_chakujun'] = pd.to_numeric(df['kakutei_chakujun'], errors='coerce')
df = df.dropna(subset=['kakutei_chakujun'])

print(f"✅ クレンジング完了！件数：{len(df):,}件")

# 特徴量と目的変数を設定
features = [
    'barei', 'seibetsu_code', 'kishu_code', 'chokyoshi_code',
    'futan_juryo', 'bataiju', 'zogen_sa', 'zogen_fugo',
    'kyakushitsu_hantei',
    'kyori', 'track_code', 'tenko_code',
    'shiba_babajotai_code', 'dirt_babajotai_code', 'shusso_tosu'
]
features = [feature for feature in features if feature in df.columns]

X = df[features]
y = df['kakutei_chakujun']

# 学習データとテストデータに分割（80%学習、20%テスト）
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"\n📊 学習データ：{len(X_train):,}件")
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
print("📈 精度確認中...")
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f"\n✅ モデル学習完了！")
print(f"🎯 正解率：{accuracy:.2%}")

# 特徴量の重要度
print("\n🏆 予想に重要な要素TOP5:")
importances = pd.Series(
    model.feature_importances_, index=features
).sort_values(ascending=False)
for i, (feat, imp) in enumerate(importances.head(5).items()):
    print(f"  {i+1}位: {feat}（{imp:.3f}）")
