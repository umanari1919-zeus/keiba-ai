# 🎯 OpenCode 完全ガイド — うまなり地蔵AI

**OpenCode v1.14.35 で競馬AI開発を加速させる**

---

## 📋 目次

1. [セットアップ確認](#セットアップ確認)
2. [基本コマンド](#基本コマンド)
3. [機能別ガイド](#機能別ガイド)
4. [実践例](#実践例)
5. [PowerShell ラッパー関数](#powershell-ラッパー関数)
6. [設定・カスタマイズ](#設定カスタマイズ)
7. [トラブルシューティング](#トラブルシューティング)

---

## ✅ セットアップ確認

### 1. バージョン確認

```powershell
opencode --version
# 出力例: opencode 1.14.35
```

### 2. 設定確認

```powershell
# 設定ファイルの場所
.opencode/config.json

# 設定内容確認
cat .opencode/config.json | jq .model
# "anthropic/claude-haiku-4-5-20251001"
```

### 3. API キー確認

```powershell
# .env ファイルに設定
cat .env | Select-String "API_KEY"
```

### 4. 使用可能なモデル確認

```powershell
opencode config --list-models

# 出力例:
# Anthropic Claude:
#  - claude-opus-4-6 (200k tokens)
#  - claude-sonnet-4-6 (200k tokens)
#  - claude-haiku-4-5-20251001 (200k tokens) ← デフォルト
```

---

## 🚀 基本コマンド

### ヘルプ表示

```powershell
opencode --help
opencode <command> --help
```

### バージョン・情報表示

```powershell
opencode --version
opencode --info
opencode status
```

### 設定操作

```powershell
opencode config --get <key>           # 値取得
opencode config --set <key> <value>   # 値設定
opencode config --list                # 全設定表示
opencode config --reset               # リセット
```

### キャッシュ・ログ

```powershell
opencode cache --clear
opencode logs --show
opencode logs --follow     # リアルタイム表示
```

---

## 🔧 機能別ガイド

### A. コード生成

#### エージェント生成

```powershell
# 基本形
opencode generate --type agent --name "new_analyzer"

# テンプレート指定
opencode generate --type agent --name "new_analyzer" --template agent_pattern_v2

# 説明付き
opencode generate --type agent --name "new_analyzer" --description "特徴量分析エージェント"

# 出力先指定
opencode generate --type agent --name "new_analyzer" --output agents/analyzer_agent.py
```

#### パイプラインステップ生成

```powershell
# 基本形
opencode generate --type pipeline_step --name "feature_extraction"

# フェーズ指定
opencode generate --type pipeline_step --name "feature_extraction" --phase "data_processing"
```

#### テストコード生成

```powershell
# pytest 形式
opencode generate --type tests --input agents/train_agent.py --framework pytest

# unittest 形式
opencode generate --type tests --input agents/train_agent.py --framework unittest
```

#### ドキュメント生成

```powershell
# Markdown
opencode generate --type documentation --input agents/train_agent.py --format markdown

# RST (Sphinx)
opencode generate --type documentation --input agents/train_agent.py --format rst

# HTML
opencode generate --type documentation --input agents/train_agent.py --format html
```

### B. コード最適化

#### パフォーマンス最適化

```powershell
# 提案を表示
opencode optimize --input pipeline_v2/04_batch_inference.py --strategy performance

# 自動適用
opencode optimize --input pipeline_v2/04_batch_inference.py --strategy performance --apply
```

#### 可読性向上

```powershell
opencode optimize --input agents/base_agent.py --strategy readability

# 結果を確認してから適用
opencode optimize --input agents/base_agent.py --strategy readability --preview
opencode optimize --input agents/base_agent.py --strategy readability --apply
```

#### 保守性改善

```powershell
opencode optimize --input pipeline/model_train_03.py --strategy maintainability --detailed
```

#### セキュリティ改善

```powershell
opencode optimize --input agents/ --strategy security --recursive
```

### C. コード分析

#### ディレクトリ全体分析

```powershell
# 基本分析
opencode analyze --dir pipeline_v2/

# 詳細分析
opencode analyze --dir pipeline_v2/ --detailed

# レポート生成
opencode analyze --dir pipeline_v2/ --report
```

#### 単一ファイル分析

```powershell
opencode analyze --file agents/base_agent.py --detailed
```

#### 品質メトリクス

```powershell
# コード品質スコア
opencode analyze --dir agents/ --metrics

# 出力例:
# Maintainability Index: 85/100
# Cyclomatic Complexity: 3.2 (average)
# Lines of Code: 12,500
```

### D. 検索・パターンマッチング

#### コード検索

```powershell
# Kelly 基準の実装を検索
opencode search --pattern "kelly"

# 特定ディレクトリ内で検索
opencode search --pattern "odds" --dir pipeline/

# 複雑検索
opencode search --pattern "def.*kelly|kelly_fraction" --regex
```

#### パターンマッチング

```powershell
# よく使われるパターン一覧
opencode list --patterns

# 特定パターンの詳細
opencode show --pattern "feature_engineering"
```

---

## 💡 実践例

### 例 1: 新しいエージェント開発フロー

```powershell
# STEP 1: ニーズ分析
opencode analyze --dir agents/ --metrics

# STEP 2: 骨組み生成
opencode generate --type agent --name "momentum_analyzer" `
    --description "価格モメンタム分析エージェント"

# STEP 3: テストコード生成
opencode generate --type tests `
    --input agents/momentum_analyzer_agent.py `
    --framework pytest

# STEP 4: 最適化提案確認
opencode optimize --input agents/momentum_analyzer_agent.py --strategy performance

# STEP 5: ドキュメント生成
opencode generate --type documentation `
    --input agents/momentum_analyzer_agent.py `
    --format markdown

# 完成！
```

### 例 2: パイプライン全体の改善

```powershell
# STEP 1: 全体分析
opencode analyze --dir pipeline_v2/ --detailed --report

# STEP 2: ボトルネック特定
opencode analyze --dir pipeline_v2/04_batch_inference.py --metrics

# STEP 3: 改善提案取得
opencode optimize --dir pipeline_v2/ --strategy performance --preview

# STEP 4: 段階的適用
opencode optimize --file pipeline_v2/01_ingest.py --apply
opencode optimize --file pipeline_v2/02_normalize.py --apply
opencode optimize --file pipeline_v2/03_feature_gen.py --apply
# ... 以下同様

# STEP 5: 動作確認
python canary_run.py
```

### 例 3: 学習スクリプト最適化

```powershell
# Kelly 基準ロジックを最適化
opencode optimize --input pipeline/kelly_bankroll_09.py `
    --strategy performance `
    --detailed

# 提案を確認
# "Use vectorized operations instead of loops"
# "Cache computed values"
# など

# 適用
opencode optimize --input pipeline/kelly_bankroll_09.py --apply

# テスト実行
python pipeline/kelly_bankroll_09.py --test
```

### 例 4: バッチドキュメント生成

```powershell
# agents/ 全体のドキュメント生成
opencode generate --type documentation `
    --dir agents/ `
    --format markdown `
    --output docs/agents/

# 出力: docs/agents/base_agent.md
#      docs/agents/train_agent.md
#      docs/agents/inference_agent.md
#      ...
```

---

## 🎛️ PowerShell ラッパー関数

便利なショートカット関数を設定済み。以下で読み込み:

```powershell
. tools\opencode-wrapper.ps1
```

### 利用可能な関数

#### 1. New-Agent (エージェント生成)

```powershell
New-Agent -AgentName "market_analyzer" `
    -Description "マーケット分析エージェント" `
    -Template agent_pattern_v2 `
    -OutputDir agents

# またはエイリアス
new-agent -AgentName "market_analyzer"
```

#### 2. Optimize-Code (コード最適化)

```powershell
Optimize-Code -FilePath "agents/train_agent.py" `
    -Strategy performance `
    -ApplyChanges

# またはエイリアス
optimize -FilePath agents/train_agent.py -ApplyChanges
```

#### 3. Analyze-Codebase (分析)

```powershell
Analyze-Codebase -Directory pipeline_v2 `
    -Detailed `
    -GenerateReport

# またはエイリアス
analyze -Directory pipeline_v2 -Detailed -GenerateReport
```

#### 4. New-Tests (テスト生成)

```powershell
New-Tests -SourceFile "agents/base_agent.py" `
    -TestDir tests `
    -Framework pytest

# またはエイリアス
new-tests -SourceFile agents/base_agent.py
```

#### 5. New-Documentation (ドキュメント生成)

```powershell
New-Documentation -SourceFile "agents/train_agent.py" `
    -OutputDir docs `
    -Format markdown

# またはエイリアス
new-docs -SourceFile agents/train_agent.py
```

#### 6. Optimize-All (全体最適化)

```powershell
Optimize-All -RootDir . `
    -Strategy performance `
    -Apply

# またはエイリアス
optimize-all -Apply
```

#### 7. Show-OpenCodeInfo (情報表示)

```powershell
Show-OpenCodeInfo

# またはエイリアス
oc-info
```

---

## ⚙️ 設定・カスタマイズ

### 設定ファイル: `.opencode/config.json`

```json
{
  "preferredProvider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "project": {
    "name": "うまなり地蔵AI",
    "language": "python"
  },
  "advanced": {
    "contextWindow": 100000,
    "temperature": 0.5,
    "maxTokens": 8000
  }
}
```

### モデル切り替え

```powershell
# Opus (高精度・高コスト)
opencode config --set model "anthropic/claude-opus-4-6"

# Sonnet (バランス型)
opencode config --set model "anthropic/claude-sonnet-4-6"

# Haiku (高速・低コスト)← デフォルト
opencode config --set model "anthropic/claude-haiku-4-5-20251001"
```

### 温度 (Creativity) 調整

```powershell
# 確定的 (0.0 = 確定的, 1.0 = ランダム)
opencode config --set temperature 0.3  # コード生成向け

# クリエイティブ
opencode config --set temperature 0.7  # ドキュメント向け
```

### コンテキストウィンドウ調整

```powershell
# 大規模コード分析向け (max 200k)
opencode config --set contextWindow 150000

# 標準
opencode config --set contextWindow 100000
```

---

## 🐛 トラブルシューティング

### OpenCode が見つからない

```powershell
# PATH 確認
$env:Path -split ";" | Select-String "npm"

# PATH 追加
$env:Path += ";C:\Users\uchih\AppData\Roaming\npm"

# PowerShell 再起動
exit
```

### API キーエラー

```powershell
# .env ファイルを確認
cat .env | Select-String "API_KEY"

# 環境変数設定
$env:ANTHROPIC_API_KEY = "sk-xxxxx"

# 設定確認
opencode config --get preferredProvider
```

### レート制限エラー

```powershell
# リトライポリシー設定
opencode config --set retryPolicy.maxRetries 5

# 遅延設定
opencode config --set retryPolicy.initialDelay 2
```

### メモリ不足

```powershell
# コンテキストウィンドウ縮小
opencode config --set contextWindow 50000

# バッチサイズ縮小
opencode config --set maxTokens 4000
```

### キャッシュクリア

```powershell
opencode cache --clear
opencode config --reset
```

---

## 📊 ベストプラクティス

### 1. 段階的最適化

```powershell
# ❌ 一気にやる
opencode optimize --dir . --apply

# ✅ 段階的にやる
opencode optimize --file agents/base_agent.py --preview
# ... 確認して適用 ...
opencode optimize --file agents/base_agent.py --apply
```

### 2. テスト駆動開発

```powershell
# コード生成 → テスト生成 → 実装 → 最適化
opencode generate --type agent --name "new_agent"
opencode generate --type tests --input agents/new_agent_agent.py
# ... 実装 ...
opencode optimize --input agents/new_agent_agent.py --apply
```

### 3. ドキュメント優先

```powershell
# 生成時点でドキュメント作成
opencode generate --type agent --name "new_agent"
opencode generate --type documentation --input agents/new_agent_agent.py
```

### 4. 定期的な分析

```powershell
# 日次: コード品質スコア
opencode analyze --dir agents/ --metrics

# 週次: 全体分析
opencode analyze --dir . --detailed --report

# 月次: 改善機会特定
opencode analyze --dir . --optimization-candidates
```

---

## 🎓 さらに詳しく

- `opencode --help` — 全コマンド参照
- `.opencode/config.json` — 詳細設定
- `tools/opencode-wrapper.ps1` — ラッパー関数定義
- `tools/README.md` — 統合ガイド

---

**OpenCode で 開発生産性を 3 倍に！🚀**
