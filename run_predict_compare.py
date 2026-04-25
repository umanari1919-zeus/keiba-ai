"""ニックス特徴量追加前後の回収率比較"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pipeline.predict_04 import simulate_recovery

BASELINE = {
    2025: {'recovery_rate': 478.2, 'hit_rate': 38.8, 'races': 3455}
}

print("=" * 55)
print("ニックス特徴量追加後 - 年別回収率シミュレーション")
print("=" * 55)

total_profit = 0
new_results = {}
for year in [2020, 2021, 2022, 2023, 2024, 2025]:
    result = simulate_recovery(year)
    if result:
        emoji = "🎉" if result['recovery_rate'] >= 100 else "📉"
        print(f"{emoji} {result['year']}年")
        print(f"   レース数：{result['races']:,}")
        print(f"   的中率　：{result['hit_rate']:.1f}%")
        print(f"   回収率　：{result['recovery_rate']:.1f}%")
        print(f"   損　益　：{result['profit']:+,.0f}円")
        print(f"   {'─'*30}")
        total_profit += result['profit']
        new_results[year] = result

print(f"\n💰 6年間の総損益：{total_profit:+,.0f}円")

print("\n" + "=" * 55)
print("【2025年】ニックス追加前後比較")
print("=" * 55)
if 2025 in new_results:
    new = new_results[2025]
    old_roi = BASELINE[2025]['recovery_rate']
    new_roi = new['recovery_rate']
    diff = new_roi - old_roi
    emoji = "↑" if diff > 0 else "↓"
    print(f"  回収率  ：{old_roi:.1f}% → {new_roi:.1f}%  {emoji}{abs(diff):.1f}pt")
    print(f"  的中率  ：{BASELINE[2025]['hit_rate']:.1f}% → {new['hit_rate']:.1f}%")
    print(f"  レース数：{BASELINE[2025]['races']:,} → {new['races']:,}")
