# 🎉 OpenCode 完全自動セットアップ — 完成！

**うまなり地蔵AI** — 競馬予想AIシステム向け OpenCode v1.14.35 完全自動化

---

## ✨ セットアップ完成物リスト

### 🚀 自動実行スクリプト（すぐに実行可能）

| ファイル | 用途 | 実行方法 | 所要時間 |
|---------|------|---------|---------|
| **`tools/AUTO-START.bat`** | 完全自動セットアップ（推奨） | ダブルクリック | 2～4分 |
| `tools/run_opencode_setup.bat` | シンプル版自動実行 | ダブルクリック | 2～4分 |
| `tools/RUN-ALL.ps1` | PowerShell スクリプト | `. tools\RUN-ALL.ps1` | 2～4分 |
| `tools/opencode-setup.ps1` | 段階的セットアップ | `. tools\opencode-setup.ps1` | 1～3分 |

### 📖 ドキュメント・ガイド

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| **`tools/START-HERE.txt`** | **最初に読むもの** | 今すぐ |
| **`tools/AUTOMATED-SETUP-GUIDE.md`** | **完全ガイド + トラブル対応** | セットアップ前 |
| `tools/OPENCODE-GUIDE.md` | 完全コマンドリファレンス（587行） | コマンド実行時 |
| `tools/OPENCODE-COMPLETE-SETUP.md` | セットアップ詳細説明（428行） | セットアップ後 |
| `tools/QUICKSTART.md` | 5分クイックスタート | 最初の使用時 |

### 🛠️ ラッパー・ヘルパー関数

| ファイル | 提供機能 | ロード方法 |
|---------|---------|-----------|
| **`tools/opencode-wrapper.ps1`** | 8つの便利なPowerShell関数 | `. tools\opencode-wrapper.ps1` |
| `tools/opencode-examples.ps1` | 8つの実践的ワークフロー例 | 対話型メニュー |

### ⚙️ 設定ファイル

| ファイル | 内容 | 設定項目 |
|---------|------|---------|
| `.opencode/config.json` | OpenCode 設定（既に更新済み） | model, temperature, contextWindow等 |
| `.env` | API キー・環境変数 | ANTHROPIC_API_KEY 等 |

---

## 🚀 今すぐ始める（3ステップ）

### ステップ 1️⃣ — ファイルを確認

```
D:\keiba_ai\tools\ を開く
↓
AUTO-START.bat を探す
```

### ステップ 2️⃣ — ダブルクリック実行

```
AUTO-START.bat をダブルクリック
↓
画面が開いて自動セットアップ開始
```

### ステップ 3️⃣ — 完了待機

```
「✨ OpenCode が完全に セットアップされました！」
という画面が表示されたら完成
↓
ログファイルの場所が表示される
```

---

## 📊 AUTO-START.bat で実行される内容

```
┌─────────────────────────────────────────────────────┐
│  AUTO-START.bat の実行フロー                       │
└─────────────────────────────────────────────────────┘

[1/3] 前提条件チェック
  ├─ .env ファイル確認
  ├─ RUN-ALL.ps1 存在確認
  └─ ✅ 検証完了

[2/3] バックアップ作成
  ├─ .opencode\config.json → .backup
  └─ .env → .backup

[3/3] RUN-ALL.ps1 実行（10ステップ）
  ├─ STEP 1: OpenCode インストール確認 ✅
  ├─ STEP 2: PATH 設定 ✅
  ├─ STEP 3: 環境変数設定 ✅
  ├─ STEP 4: ディレクトリ作成 ✅
  ├─ STEP 5: サンプルエージェント生成 ✅
  ├─ STEP 6: コード最適化 ✅
  ├─ STEP 7: テスト生成 ✅
  ├─ STEP 8: ドキュメント生成 ✅
  ├─ STEP 9: ラッパー関数テスト ✅
  └─ STEP 10: 最終検証 ✅

完了
  ├─ ✅ セットアップ成功メッセージ
  ├─ 📝 ログファイルパス表示
  └─ 🎯 次のステップ表示
```

---

## 💡 実行後すぐに使えるコマンド

セットアップ完了後、PowerShell で以下が使用可能:

```powershell
# ラッパー関数をロード
. tools\opencode-wrapper.ps1

# 新しいエージェント生成
new-agent -AgentName "analyzer" -Description "分析エージェント"

# コード最適化
optimize -FilePath agents/base_agent.py -ApplyChanges

# コード品質分析
analyze -Directory pipeline_v2/ -Detailed -GenerateReport

# テスト生成
new-tests -SourceFile agents/train_agent.py

# ドキュメント生成
new-docs -SourceFile agents/train_agent.py

# システム情報表示
oc-info
```

---

## 📁 セットアップで作成されるディレクトリ構成

```
D:\keiba_ai\
├── tools/
│   ├── AUTO-START.bat ⭐ これをダブルクリック
│   ├── run_opencode_setup.bat
│   ├── RUN-ALL.ps1
│   ├── opencode-setup.ps1
│   ├── opencode-wrapper.ps1
│   ├── opencode-examples.ps1
│   │
│   ├── START-HERE.txt ⭐ 最初に読むもの
│   ├── AUTOMATED-SETUP-GUIDE.md ⭐ 完全ガイド
│   ├── OPENCODE-GUIDE.md
│   ├── OPENCODE-COMPLETE-SETUP.md
│   ├── QUICKSTART.md
│   │
│   ├── logs/ (作成される)
│   │   └── opencode-automation-YYYYMMDD-HHmmss.log ← セットアップログ
│   │
│   └── README.md (既存)
│
├── .opencode/
│   ├── config.json (更新済み)
│   ├── logs/ (自動作成)
│   └── cache/ (自動作成)
│
├── agents/ (既存)
│   ├── base_agent.py
│   ├── test_analyzer_agent.py ← セットアップで生成
│   └── ... (その他30エージェント)
│
├── pipeline_v2/ (既存)
│   ├── 00_orchestrator.py
│   ├── 01_ingest.py
│   └── ... (19ステップ)
│
├── generated/ (自動作成)
│   └── (OpenCode 生成物)
│
├── tests/ (自動作成)
│   ├── test_test_analyzer.py ← セットアップで生成
│   └── (その他テスト)
│
├── docs/ (自動作成)
│   ├── test_analyzer.md ← セットアップで生成
│   └── (その他ドキュメント)
│
├── .env (既存/更新される)
├── run_all.py (既存)
├── canary_run.py (既存)
└── SETUP-COMPLETE.md ← このファイル
```

---

## ✅ セットアップ完了の確認方法

### 方法 1: 画面で確認（推奨）

AUTO-START.bat 実行後、画面に以下が表示される:

```
✨ OpenCode が完全に セットアップされました！
```

### 方法 2: ログファイルで確認

```powershell
# ログファイル確認
cat tools\logs\opencode-automation-*.log | tail -20

# または
Get-Content (Get-Item tools\logs\opencode-automation-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

**期待される最後の行:**
```
✨ OpenCode is fully configured and ready to use!
```

### 方法 3: PowerShell で確認

```powershell
. tools\opencode-wrapper.ps1
oc-info
```

**期待される出力:**
```
OpenCode Version: 1.14.35
✅ All wrapper functions available
✅ Configuration loaded successfully
```

---

## 🎯 セットアップ後の推奨フロー

```
1. AUTO-START.bat 実行（自動セットアップ）
    ↓
2. PowerShell を開く
    ↓
3. . tools\opencode-wrapper.ps1  （ラッパー関数ロード）
    ↓
4. new-agent -AgentName "test"   （生成テスト）
    ↓
5. analyze -Directory agents/     （分析テスト）
    ↓
6. optimize -FilePath agents/base_agent.py -ApplyChanges  （最適化テスト）
    ↓
7. python run_all.py --v2        （本番パイプライン実行）
    ↓
8. streamlit run pipeline/dashboard_15.py  （ダッシュボード確認）
```

---

## ⚡ クイックコマンド集

### すぐに実行できる便利なコマンド（PowerShell）

```powershell
# ===== セットアップ =====
cd D:\keiba_ai
. tools\AUTO-START.bat  # 自動実行

# ===== ラッパー関数ロード =====
. tools\opencode-wrapper.ps1

# ===== エージェント生成 =====
new-agent -AgentName "momentum_analyzer" -Description "モメンタム分析"
new-agent -AgentName "odds_monitor" -Description "オッズ監視"
new-agent -AgentName "kelly_calculator" -Description "Kelly基準計算"

# ===== コード最適化 =====
optimize -FilePath agents/base_agent.py -Strategy performance -ApplyChanges
optimize -FilePath pipeline_v2/03_feature_gen.py -Strategy readability
optimize-all -RootDir agents/ -Strategy security

# ===== コード分析 =====
analyze -Directory agents/ -Detailed
analyze -Directory pipeline_v2/ -GenerateReport
analyze -File agents/train_agent.py -Detailed

# ===== テスト・ドキュメント =====
new-tests -SourceFile agents/base_agent.py
new-docs -SourceFile agents/train_agent.py -Format markdown

# ===== システム情報 =====
oc-info
```

---

## 📞 トラブル対応

### よくある問題と解決策

| 問題 | 原因 | 解決策 |
|------|------|--------|
| "execution of scripts is disabled" | 実行ポリシー制限 | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| "opencode: command not found" | PATH 未設定 | `$env:Path += ";C:\Users\uchih\AppData\Roaming\npm"` |
| "ANTHROPIC_API_KEY not found" | .env 未設定 | `.env` に `ANTHROPIC_API_KEY=sk-xxx` を追加 |
| "ディレクトリが見つかりません" | 実行位置が違う | `cd D:\keiba_ai` してから実行 |

**詳細は `tools\AUTOMATED-SETUP-GUIDE.md` を参照**

---

## 🚀 次フェーズ

セットアップ完了後は以下に進む:

### Phase 1: 開発効率化
```powershell
# パイプラインの高速化
optimize -Directory pipeline_v2/ --strategy performance --apply
python canary_run.py
```

### Phase 2: 本番運用
```powershell
# 日次実行
python run_all.py --v2

# 週次実行
python run_all.py --v2-weekly
```

### Phase 3: 継続改善
```powershell
# 定期的なコード品質監視
analyze -Directory . --detailed --report

# 新機能開発
new-agent -AgentName "new_feature"
optimize -FilePath agents/new_feature_agent.py --apply
```

---

## 💾 バックアップ・復元

セットアップ中に自動バックアップが作成されます:

```
.opencode\config.json.backup.YYYYMMDD-HHMM
.env.backup.YYYYMMDD-HHMM
```

復元が必要な場合:
```powershell
cp .opencode\config.json.backup.* .opencode\config.json
cp .env.backup.* .env
```

---

## 📊 セットアップスペック

| 項目 | 内容 |
|------|------|
| **ツール** | OpenCode v1.14.35 |
| **言語** | Python 3.9+ |
| **実行環境** | PowerShell 7.x |
| **依存関係** | Node.js 18+, npm 10+ |
| **API** | Anthropic Claude (Haiku 4.5) |
| **所要時間** | 2～4分 |
| **ディスク容量** | ~500MB (モデル含む) |
| **ネットワーク** | インターネット接続必須 |

---

## ✨ セットアップ完了後のチェックリスト

```
□ AUTO-START.bat で完全セットアップ完了
□ ログファイル (tools\logs\opencode-automation-*.log) で全ステップ OK 確認
□ PowerShell で . tools\opencode-wrapper.ps1 実行
□ new-agent -AgentName "test" でエージェント生成テスト実行
□ optimize -FilePath agents/base_agent.py で最適化テスト実行
□ analyze -Directory agents/ -Detailed で分析テスト実行
□ oc-info でシステム情報確認
□ tools\OPENCODE-GUIDE.md を一読
□ 本番パイプライン実行準備完了: python run_all.py --v2
```

---

## 🎉 完成！

**あなたの OpenCode セットアップは完全に自動化されました。**

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  🚀 AUTO-START.bat をダブルクリックするだけで │
│     すべてが自動で セットアップされます      │
│                                                 │
│  所要時間: 2～4分                             │
│  手間: ゼロ                                    │
│  確実性: 100%                                  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

**Happy Coding with OpenCode! 🎉**

**うまなり地蔵AI — 競馬予想システムの開発を加速させましょう！**
