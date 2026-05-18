---
name: warn-model-delete
enabled: true
event: bash
pattern: rm.*model_v8\.pkl|del.*model_v8\.pkl|Remove-Item.*model_v8
action: block
---

⚠️ **model_v8.pkl の削除を検出！**

現在の学習済みモデルを削除しようとしています。

削除前に必ずバックアップを作成してください：
```bash
cp D:/keiba_ai/model_v8.pkl D:/keiba_ai/model_v8_backup_$(date +%Y%m%d).pkl
```

バックアップが完了していれば、削除を再実行してください。
