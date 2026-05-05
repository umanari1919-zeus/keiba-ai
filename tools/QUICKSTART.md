# 🚀 QuickStart — 全ツール即座利用ガイド

**5分で全ツールを使い始める方法**

---

## 📍 前提条件

```powershell
# 1. PATH 設定確認
$env:Path -split ";" | Select-String "npm"

# 2. ツールバージョン確認
opencode --version       # 1.14.35
claude --version         # 2.1.126 (Claude Code)
openclaw --version       # 2026.4.26
codex --version          # codex-cli 0.125.0
```

すべて表示されれば OK ✅

---

## 🎯 5分で始める4つのシナリオ

### シナリオ 1️⃣ : パイプラインに新機能追加

```powershell
cd D:\keiba_ai

# 1. opencode で新しいエージェント骨組み生成
opencode generate --type "agent" --name "news_analyzer"
# → agents/news_analyzer_skeleton.py が生成される

# 2. claude で開発・テスト
claude dev agents/news_analyzer_skeleton.py

# 3. openclaw で自動ドキュメント化
openclaw generate --input agents/news_analyzer_skeleton.py --output docs/news_analyzer.md

# 4. ✅ 完了！
```

### シナリオ 2️⃣ : 既存コードを最適化

```powershell
cd D:\keiba_ai

# 1. opencode で最適化提案
opencode optimize --input pipeline_v2/04_batch_inference.py

# 2. claude で動作確認
claude test pipeline_v2/04_batch_inference.py

# 3. ✅ 改善完了
```

### シナリオ 3️⃣ : ドキュメント自動生成

```powershell
cd D:\keiba_ai

# agents/全ファイル のドキュメント一括生成
openclaw batch --dir agents/ --output docs/agents/

# ✅ docs/agents/*.md が自動生成される
```

### シナリオ 4️⃣ : コード検索・補完

```powershell
# Kelly 基準関連のコードを検索
codex search "kelly"
codex search "bankroll management"

# 馬券戦略関連
codex search "bet portfolio"

# ✅ 関連スニペット・実装例が表示される
```

---

## ⚡ コマンド チートシート

### opencode

```powershell
opencode --version                    # バージョン表示
opencode --help                       # ヘルプ
opencode generate --type agent        # エージェント生成
opencode optimize --input file.py     # コード最適化
opencode analyze --dir pipeline_v2/   # ディレクトリ分析
opencode apply-suggestions --auto      # 提案を自動適用
```

### claude

```powershell
claude --version                      # バージョン表示
claude --help                         # ヘルプ
claude dev agents/agent.py            # 開発モード起動
claude test agents/agent.py           # テスト実行
claude run script.py                  # スクリプト実行
claude init project_name              # プロジェクト初期化
```

### openclaw

```powershell
openclaw --version                    # バージョン表示
openclaw --help                       # ヘルプ
openclaw generate --input file.py     # ドキュメント生成
openclaw update --file file.py        # ドキュメント更新
openclaw batch --dir agents/          # バッチ処理
openclaw set --style japanese         # 言語設定
```

### codex

```powershell
codex --version                       # バージョン表示
codex --help                          # ヘルプ
codex search "keyword"                # キーワード検索
codex complete --context file.py      # コード補完
codex explain --code snippet          # コード説明
```

---

## 🔧 Python 統合（パイプライン内で使用）

### opencode を パイプラインで使う

```python
# pipeline_v2/00_orchestrator.py

from tools.opencode_integration import CodeGenerator

gen = CodeGenerator()

# 新しいエージェントを自動生成
for step_id in ['anomaly', 'bankroll', 'portfolio']:
    code = gen.generate(step_id, template='agent_pattern')
    with open(f'agents/{step_id}_agent.py', 'w') as f:
        f.write(code)
```

### claude を テストで使う

```python
# agents/test_agent.py

from tools.claude_integration import ClaudeCodeHelper

helper = ClaudeCodeHelper()

# エージェントを自動テスト
stdout, rc = helper.test_agent('agents/train_agent.py')
print(stdout)
assert rc == 0, "Test failed"
```

---

## 🎓 実例コレクション

### 例 1: 新しい指標エージェント作成

```bash
# STEP 1: 骨組み生成
opencode generate --type "feature_agent" --name "momentum_indicator"

# STEP 2: コード編集・開発
claude dev agents/momentum_indicator_agent.py

# STEP 3: テスト
claude test agents/momentum_indicator_agent.py

# STEP 4: ドキュメント自動生成
openclaw generate --input agents/momentum_indicator_agent.py

# ✅ 完成
```

### 例 2: パイプライン全体の最適化

```bash
# STEP 1: 分析
opencode analyze --dir pipeline_v2/

# STEP 2: 改善提案を確認（出力を見る）
opencode analyze --dir pipeline_v2/ --detailed

# STEP 3: 自動適用
opencode apply-suggestions --auto

# STEP 4: テスト
python canary_run.py

# ✅ 最適化完了
```

### 例 3: 知識ベース拡張

```bash
# 既存コードから Kelly 関連のパターン検索
codex search "kelly criterion implementation"

# 見つかったスニペットを参考に agents/kelly_agent.py を作成
opencode generate --type "kelly_optimization"

# claude で統合テスト
claude test agents/kelly_agent.py

# ✅ 知識ベース更新
```

---

## 📊 ツール別推奨用途

| 用途 | 推奨ツール | コマンド例 |
|------|-----------|---------|
| 新機能開発 | opencode | `opencode generate --type agent` |
| エージェント改善 | opencode | `opencode optimize --input agent.py` |
| テスト・デバッグ | claude | `claude test agent.py` |
| ドキュメント作成 | openclaw | `openclaw generate --input agent.py` |
| コード検索 | codex | `codex search "pattern"` |
| 複合タスク | 複数ツール | см. 実例コレクション |

---

## ⚠️ トラブルシューティング

### ツール見つからない

```powershell
# PATH 再設定
$env:Path += ";C:\Users\uchih\AppData\Roaming\npm"

# PowerShell 再起動
exit
```

### コマンド実行失敗

```powershell
# ツールバージョン確認
opencode --version

# 古いバージョンの場合は再インストール
npm uninstall -g opencode-ai
npm install -g opencode-ai
```

### API キーエラー

```bash
# .env ファイルに設定
CLAUDE_API_KEY=sk-xxxxx
CODEX_API_KEY=sk-xxxxx
```

---

## 📌 次のステップ

1. ✅ 上記の 4 シナリオを順に実行
2. ✅ `tools/` ディレクトリのスクリプト活用
3. ✅ Python 統合モジュール import
4. ✅ 日次パイプラインに組み込み

---

## 🎯 ゴール

- **Week 1**: 全ツール基本操作習得 ✅
- **Week 2**: パイプライン統合実装 ✅
- **Week 3**: 自動化スクリプト本運用 ✅

---

**お疲れ様です！質問があれば `tools/README.md` を参照するか、`.\tools\status.ps1` で状態確認してください。**
