# 🎯 OpenCode 完全自動セットアップ ガイド

**うまなり地蔵AI** — ワンクリック自動セットアップ完全ガイド

---

## ⚡ クイックスタート（推奨）

### 方法 1: ワンクリック自動実行（最も簡単）

**`AUTO-START.bat` をダブルクリック**

```
D:\keiba_ai\tools\AUTO-START.bat
```

**これだけで全て自動実行されます:**
- ✅ 前提条件の確認
- ✅ 既存ファイルのバックアップ
- ✅ 10ステップ完全セットアップ
- ✅ ログ自動保存
- ✅ 完了レポート表示

**所要時間:** 2～4分

---

## 📋 前提条件チェック

AUTO-START.bat を実行する前に、以下が完了していることを確認:

| 項目 | 確認コマンド | 期待値 |
|------|-----------|--------|
| PowerShell | `pwsh -v` または `$PSVersionTable.PSVersion` | 7.x |
| npm | `npm --version` | 10.x 以上 |
| OpenCode | `opencode --version` | 1.14.35 |
| Node.js | `node --version` | 18.x 以上 |

**確認できない場合:**
```powershell
# PowerShell 7 をインストール
choco install powershell-core

# または Microsoft Store から PowerShell をインストール

# npm / Node.js をインストール
choco install nodejs
```

---

## 🚀 実行方法 3パターン

### パターン A: ワンクリック実行（推奨）
```
D:\keiba_ai\tools\AUTO-START.bat をダブルクリック
```
- 最も簡単
- すべてのチェックと確認が自動
- ログが自動保存される

### パターン B: PowerShell で直接実行
```powershell
cd D:\keiba_ai
. tools\RUN-ALL.ps1
```
- より詳細な制御が可能
- リアルタイムで出力を見られる
- トラブル時のデバッグが容易

### パターン C: 段階的実行（カスタマイズ向け）
```powershell
cd D:\keiba_ai
. tools\opencode-setup.ps1
```
- 各ステップで確認しながら進行
- ステップをスキップできる
- 既存設定を保持したい場合に最適

---

## 📊 実行フロー（AUTO-START.bat）

```
START
  │
  ├─ [1/3] 前提条件チェック
  │         ├─ .env 存在確認
  │         ├─ tools\RUN-ALL.ps1 存在確認
  │         └─ ✅ OK → 続行
  │
  ├─ [2/3] バックアップ作成
  │         ├─ .opencode\config.json → .json.backup
  │         └─ .env → .env.backup
  │
  ├─ [3/3] 10ステップ実行（RUN-ALL.ps1）
  │         ├─ OpenCode 確認
  │         ├─ PATH 設定
  │         ├─ API キー確認
  │         ├─ ディレクトリ作成
  │         ├─ サンプルエージェント生成
  │         ├─ コード最適化
  │         ├─ テスト生成
  │         ├─ ドキュメント生成
  │         ├─ ラッパー関数テスト
  │         └─ 最終検証
  │
  ├─ SUCCESS: 完了レポート表示
  │           ├─ ログファイルパス
  │           └─ 次のステップ表示
  │
  └─ END
```

---

## ✅ 実行結果の確認

### 成功時の画面

```
████████████████████████████████████████████████████
█                                                  █
█  ✨ OpenCode が完全に セットアップされました！  █
█                                                  █
████████████████████████████████████████████████████

📝 実行ログ:
   D:\keiba_ai\tools\logs\opencode-automation-YYYYMMDD-HHmmss.log

🎯 次のステップ (PowerShell で):

1️⃣  ラッパー関数をロード:
    . tools\opencode-wrapper.ps1

2️⃣  新しいエージェント生成:
    new-agent -AgentName "my_analyzer"

3️⃣  パイプライン分析:
    analyze -Directory pipeline_v2/ -Detailed

4️⃣  コード最適化:
    optimize -FilePath agents/train_agent.py -ApplyChanges

5️⃣  システム情報:
    oc-info
```

### ログファイルの確認

セットアップ後、以下でログを確認:
```powershell
# 最新ログを表示
Get-Content (Get-Item tools\logs\opencode-automation-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# または
cat tools\logs\opencode-automation-*.log | tail -50
```

---

## 🎯 次のステップ（セットアップ後）

### 1. ラッパー関数をロード

```powershell
cd D:\keiba_ai
. tools\opencode-wrapper.ps1
```

**確認:**
```powershell
Get-Command new-agent
Get-Command optimize
Get-Command analyze
```

### 2. 新しいエージェント生成テスト

```powershell
new-agent -AgentName "test_agent" -Description "テストエージェント"
```

**確認:**
```powershell
ls agents\test_agent_agent.py
```

### 3. パイプライン全体の分析

```powershell
analyze -Directory pipeline_v2/ -Detailed -GenerateReport
```

### 4. コード最適化テスト

```powershell
optimize -FilePath agents/base_agent.py -Strategy readability -Preview
```

### 5. 本番パイプラインの実行準備

```powershell
python run_all.py --v2
```

---

## ⚠️ トラブルシューティング

### エラー: "execution of scripts is disabled"

**原因:** PowerShell のスクリプト実行ポリシーが制限されている

**解決策:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

その後、AUTO-START.bat を再実行

### エラー: "opencode: command not found"

**原因:** npm の PATH が設定されていない

**解決策:**
```powershell
$env:Path += ";C:\Users\uchih\AppData\Roaming\npm"
[Environment]::SetEnvironmentVariable("Path", $env:Path, "User")
```

PowerShell を再起動して再実行

### エラー: "ANTHROPIC_API_KEY not found"

**原因:** .env ファイルに API キーが設定されていない

**解決策:**
```powershell
# .env ファイルを編集
notepad .env

# または追加
Add-Content .env "ANTHROPIC_API_KEY=sk-your-key-here"
```

### エラー: "ディレクトリが見つかりません"

**原因:** バッチファイルが D:\keiba_ai\ 以外から実行された

**解決策:**
```cmd
cd /d D:\keiba_ai
tools\AUTO-START.bat
```

---

## 📚 ドキュメント参照

セットアップ完了後、以下を参照:

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| `tools\OPENCODE-GUIDE.md` | 完全コマンドリファレンス | コマンド実行時 |
| `tools\QUICKSTART.md` | 5分クイックスタート | 最初の使用時 |
| `tools\OPENCODE-COMPLETE-SETUP.md` | セットアップ完全ガイド | セットアップ後 |
| `.opencode\config.json` | 詳細設定 | 設定変更時 |

---

## 🔄 再実行（設定リセット）

セットアップを再実行する場合:

```bash
# バックアップされた設定が自動保存されます
AUTO-START.bat をダブルクリック
```

古い設定が必要な場合:
```powershell
# バックアップから復元
cp .opencode\config.json.backup.* .opencode\config.json
cp .env.backup.* .env
```

---

## ✨ セットアップ完了後の確認リスト

```
□ AUTO-START.bat で完全セットアップ実行済み
□ ログファイルで 10/10 ステップ成功を確認
□ PowerShell で . tools\opencode-wrapper.ps1 実行済み
□ new-agent -AgentName "test" でエージェント生成テスト完了
□ oc-info でシステム情報確認済み
□ analyze -Directory agents/ で既存コード分析完了
□ tools\OPENCODE-GUIDE.md を読了
□ pipeline_v2 で本番実行準備完了
```

---

## 🚀 最後に

これで OpenCode による自動開発が全て準備できました。

```powershell
# 次は本番パイプラインを実行
python run_all.py --v2

# または週次実行
python run_all.py --v2-weekly
```

**Happy Coding! 🎉**
