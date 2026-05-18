---
name: block-data-leakage
enabled: true
event: file
pattern: FEATURES.*tansho_odds|FEATURES.*tansho_ninkijun
action: block
---

🚨 **データリーケージ検出！**

`tansho_odds`（オッズ）や `tansho_ninkijun`（人気）を FEATURES リストに含めようとしています。

これらはレース結果が確定する前に変動する情報で、モデルに含めると**データリーケージ**が発生し、実運用で性能が大幅に劣化します。

**対処法**: オッズ・人気は予測後のフィルタ（`tansho_odds >= 30` など）としてのみ使用してください。
