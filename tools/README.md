# 🛠️ NPM Tools Integration — うまなり地蔵AI

全ツール（opencode, claude, openclaw, codex）を統合セットアップ。

## 📦 インストール済みツール

| ツール | バージョン | 用途 |
|--------|-----------|------|
| **opencode** | 1.14.35 | パイプラインコード生成・改善 |
| **claude** (Claude Code) | 2.1.126 | エージェント開発・テスト・デバッグ |
| **openclaw** | 2026.4.26 | ドキュメント生成 |
| **codex** | 0.125.0 | コード補完・スニペット生成 |

---

## 🚀 クイックスタート

### 1️⃣ PATH 確認（グローバルコマンド有効化）

```powershell
# Windows
$env:Path -split ";" | Select-String "npm"

# 出力確認
opencode --version
claude --version
```

### 2️⃣ ツール別使用方法

#### A. **opencode** — コード生成・最適化

```powershell
cd D:\keiba_ai

# パイプラインコード生成例
opencode --help

# 特定機能のコード生成
opencode generate --type "anomaly_detection" --output "pipeline/anomaly_new.py"
```

#### B. **claude** — エージェント開発

```powershell
cd D:\keiba_ai

# Claude Code CLI 起動
claude --version

# エージェント開発用ワークスペース作成
claude init agents/new_agent/
claude dev agents/train_agent.py
```

#### C. **openclaw** — ドキュメント自動生成

```powershell
cd D:\keiba_ai

openclaw --help

# モジュール説明の自動生成
openclaw generate --input "agents/base_agent.py" --output "docs/base_agent.md"
```

#### D. **codex** — コード補完

```powershell
codex --help

# スニペット検索
codex search "kelly fraction"
codex search "horse racing model"
```

---

## 🔧 設定ファイル

### `.opencode/config.json`
opencode の設定（生成スタイル・出力形式）

### `.claude/settings.local.json`
Claude Code の設定（モデル・API キー）

### `tools/config.json`
全ツール統合設定（パス・キー・環境変数）

---

## 📋 推奨ワークフロー

### 新機能開発
```powershell
# 1. opencode でコード骨組み生成
opencode generate --type "feature" --name "new_indicator"

# 2. claude で開発・テスト
claude dev agents/new_agent.py

# 3. openclaw で自動ドキュメント化
openclaw generate --input "agents/new_agent.py" --output "docs/"

# 4. codex で不足部分補完
codex search "similar pattern"
```

### エージェント改善
```powershell
# 改善コードを opencode で生成
opencode optimize --input "agents/train_agent.py"

# claude で動作確認
claude test agents/train_agent.py

# ドキュメント更新
openclaw update --file "agents/train_agent.py"
```

### パイプライン最適化
```powershell
# 全パイプラインコード分析
opencode analyze --dir "pipeline_v2/"

# 改善提案適用
opencode apply-suggestions --auto

# テスト実行
claude test pipeline_v2/00_orchestrator.py
```

---

## ⚙️ 環境変数設定

`.env` に以下を追加：

```bash
# OpenCode API設定
OPENCODE_API_KEY=xxx          # 必要な場合
OPENCODE_MODEL=gpt4           # デフォルト: gpt4

# Claude Code設定
CLAUDE_API_KEY=sk-xxxxx       # Anthropic API Key
CLAUDE_MODEL=claude-opus-4.6

# OpenClaw設定
OPENCLAW_STYLE=japanese       # ドキュメント言語

# Codex設定
CODEX_API_KEY=sk-xxxxx        # OpenAI API Key
```

---

## 📊 ツール統計

```powershell
# 全ツールのバージョン・状態確認
.\tools\status.ps1

# ツール使用履歴確認
.\tools\usage-log.ps1
```

---

## 🔗 統合例

### pipeline_v2 + opencode

```python
# pipeline_v2/00_orchestrator.py

from tools.opencode_integration import CodeGenerator

gen = CodeGenerator()

# DAG の各ステップをAI生成
for step_id in dag_spec['steps']:
    code = gen.generate(step_id, template="agent_pattern")
    save_to_file(f"agents/{step_id}_agent.py", code)
```

### agents + claude

```python
# agents/base_agent.py

# Claude Code で自動テスト生成
def test_agent(agent_class):
    # claude test --auto agents/base_agent.py
    pass
```

---

## 🐛 トラブルシューティング

### ツールが見つからない
```powershell
# PATH 再設定
$env:Path += ";C:\Users\uchih\AppData\Roaming\npm"

# PowerShell 再起動
exit
```

### API キーエラー
```powershell
# .env 確認
cat .env | Select-String "API_KEY"

# 設定リセット
opencode config --reset
```

### 権限エラー
```powershell
# 管理者権限で実行
# または
npm uninstall -g opencode-ai
npm install -g opencode-ai
```

---

## 📚 参照

- [opencode ドキュメント](https://opencode-ai.dev/)
- [Claude Code CLI](https://docs.anthropic.com/claude-code)
- [openclaw](https://github.com/openclaw/)
- [codex](https://platform.openai.com/docs/guides/gpt/)

---

## 🎯 次のステップ

- [ ] `tools/config.json` に API キー設定
- [ ] `.\tools\init.ps1` で環境セットアップ
- [ ] `.\tools\status.ps1` で動作確認
- [ ] パイプラインとの統合テスト
- [ ] エージェント自動生成パイプライン構築

