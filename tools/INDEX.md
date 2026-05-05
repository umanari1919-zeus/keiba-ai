# 📋 OpenCode セットアップ — ファイルインデックス

**うまなり地蔵AI** — OpenCode v1.14.35 完全自動化パッケージ

---

## 🚀 すぐに実行する

### ワンクリック実行（最も推奨）
```
🎯 AUTO-START.bat をダブルクリック
   → 全て自動で実行される（2～4分）
```

### 最初に読むもの
```
📖 START-HERE.txt
   → 実行方法が書いてある
   
📖 AUTOMATED-SETUP-GUIDE.md
   → 詳細ガイド + 全トラブル対応
```

---

## 📁 ファイル構成

### 🔴 優先度「高」— 今すぐ見るべき

```
D:\keiba_ai\
├── SETUP-COMPLETE.md ⭐⭐⭐
│   └─ 全体のまとめドキュメント
│      セットアップ内容、確認方法、次のステップ
│
└── tools/
    ├── START-HERE.txt ⭐⭐⭐
    │   └─ 最初に読むもの（実行方法3ステップ）
    │
    ├── AUTO-START.bat ⭐⭐⭐
    │   └─ これをダブルクリック → 全自動実行
    │
    └── AUTOMATED-SETUP-GUIDE.md ⭐⭐⭐
        └─ 完全ガイド + トラブル対応の全て
```

### 🟠 優先度「中」— セットアップ後に読む

```
tools/
├── OPENCODE-GUIDE.md
│   └─ OpenCode コマンド完全リファレンス（587行）
│      コマンド実行時に参照
│
├── OPENCODE-COMPLETE-SETUP.md
│   └─ セットアップ詳細説明（428行）
│      概要・使い方パターン・実践例
│
├── QUICKSTART.md
│   └─ 5分クイックスタート
│      最初の使用時に参照
│
└── INDEX.md（このファイル）
    └─ ファイル全体のガイド
```

### 🟡 優先度「低」— 参考用

```
tools/
├── RUN-ALL.ps1
│   └─ PowerShell 自動実行スクリプト（310行）
│      AUTO-START.bat が内部で呼び出す
│      直接実行: . tools\RUN-ALL.ps1
│
├── run_opencode_setup.bat
│   └─ シンプル版自動実行（バッチ）
│      AUTO-START.bat よりもシンプル
│
├── opencode-setup.ps1
│   └─ 段階的セットアップ（250行）
│      ステップバイステップで進行
│      . tools\opencode-setup.ps1
│
├── opencode-wrapper.ps1
│   └─ ラッパー関数定義（PowerShell）
│      セットアップ後に . tools\opencode-wrapper.ps1
│      で以下が使用可能:
│      - new-agent
│      - optimize
│      - analyze
│      - new-tests
│      - new-docs
│      - optimize-all
│      - oc-info
│
└── opencode-examples.ps1
    └─ 8つの実践例（19KB）
       実装例やワークフロー参照用
```

---

## 🎯 読むべき順序

### 初回セットアップ

```
1️⃣  START-HERE.txt
    └─ 実行方法の確認

2️⃣  AUTO-START.bat をダブルクリック
    └─ 自動セットアップ実行（2～4分）

3️⃣  AUTOMATED-SETUP-GUIDE.md（トラブル時）
    └─ セットアップ詳細説明

4️⃣  SETUP-COMPLETE.md
    └─ セットアップ完了確認
```

### セットアップ後

```
5️⃣  OPENCODE-GUIDE.md
    └─ コマンドの詳細説明

6️⃣  QUICKSTART.md
    └─ 最初の5つのコマンド

7️⃣  opencode-examples.ps1
    └─ 実装例確認
```

---

## 📖 各ファイルの詳細

### START-HERE.txt
**何:** 最初に読むべきファイル
**内容:** 
- 実行手順（3ステップ）
- 前提条件
- 次のステップ

**開く:** テキストエディタで開く（notepad など）

---

### AUTO-START.bat
**何:** 完全自動セットアップスクリプト
**内容:**
- [1/3] 前提条件チェック
- [2/3] バックアップ作成
- [3/3] RUN-ALL.ps1 実行

**実行方法:** ダブルクリック

**所要時間:** 2～4分

**出力:** ログファイル → tools\logs\opencode-automation-*.log

---

### AUTOMATED-SETUP-GUIDE.md
**何:** 完全なセットアップガイド
**内容:**
- 実行方法（3パターン）
- 実行フロー図
- 次のステップ
- 全トラブルシューティング
- よくある質問

**開く:** Markdown ビューアまたは GitHub で表示

**長さ:** 約400行

---

### SETUP-COMPLETE.md
**何:** セットアップ完成のまとめドキュメント
**内容:**
- セットアップで作成されたもの一覧
- 実行後の確認方法
- ディレクトリ構成
- 次フェーズへの進み方
- バックアップ・復元方法

**開く:** Markdown ビューア

**長さ:** 約600行

---

### OPENCODE-GUIDE.md
**何:** OpenCode 完全コマンドリファレンス
**内容:**
- セットアップ確認
- 基本コマンド
- 機能別ガイド
- 実践例
- PowerShell ラッパー関数
- 設定・カスタマイズ
- トラブルシューティング

**開く:** Markdown ビューア

**長さ:** 587行

**参照時:** コマンド実行時の辞書として使用

---

### OPENCODE-COMPLETE-SETUP.md
**何:** セットアップ詳細説明
**内容:**
- クイックスタート
- ファイル構成
- 使い方パターン（A・B・C）
- 実践ワークフロー
- よく使うコマンド
- ラッパー関数リファレンス
- 設定ファイル詳細

**開く:** Markdown ビューア

**長さ:** 428行

---

### QUICKSTART.md
**何:** 5分で始めるクイックスタート
**内容:**
- 最初の5つのコマンド
- パターン別実行例
- チェックリスト

**開く:** テキストエディタまたは Markdown ビューア

**長さ:** 約200行

---

### RUN-ALL.ps1
**何:** 10ステップ自動実行スクリプト
**内容:**
- STEP 1: OpenCode 確認
- STEP 2: PATH 設定
- STEP 3: 環境変数設定
- STEP 4: ディレクトリ作成
- STEP 5-10: 各種生成・最適化・テスト

**実行方法:**
```powershell
. tools\RUN-ALL.ps1
```

**所要時間:** 2～4分

**長さ:** 310行

---

### opencode-wrapper.ps1
**何:** PowerShell ラッパー関数集
**内容:**
```
new-agent           エージェント生成
optimize            コード最適化
analyze             コード分析
new-tests           テスト生成
new-docs            ドキュメント生成
optimize-all        全体最適化
oc-info             システム情報表示
```

**読み込み方法:**
```powershell
. tools\opencode-wrapper.ps1
```

**その後、以下で使用可能:**
```powershell
new-agent -AgentName "my_agent"
optimize -FilePath agents/base_agent.py
```

---

### opencode-examples.ps1
**何:** 8つの実践例とワークフロー
**内容:**
1. 新しい指標エージェント開発
2. パイプラインステップ追加
3. 既存パイプライン改善
4. バッチドキュメント生成
5. Kelly 基準ロジック最適化
6. エージェント品質向上
7. ラッパー関数ワークフロー
8. コード品質監視

**実行方法:** 対話型メニュー
```powershell
. tools\opencode-examples.ps1
```

---

## 🎯 タスク別ファイル参照

### 「セットアップしたい」
```
START-HERE.txt
    ↓
AUTO-START.bat（実行）
    ↓
AUTOMATED-SETUP-GUIDE.md（トラブル時）
```

### 「セットアップ後、次は？」
```
SETUP-COMPLETE.md
    ↓
QUICKSTART.md
    ↓
opencode-wrapper.ps1（ロード）
    ↓
opencode-examples.ps1（例を見る）
```

### 「コマンドを知りたい」
```
OPENCODE-GUIDE.md
    ↓
OPENCODE-COMPLETE-SETUP.md
    ↓
opencode-examples.ps1
```

### 「トラブルが発生した」
```
AUTOMATED-SETUP-GUIDE.md（トラブルシューティング）
    ↓
tools\logs\opencode-automation-*.log（ログ確認）
```

### 「設定をカスタマイズしたい」
```
OPENCODE-GUIDE.md（設定・カスタマイズ）
    ↓
.opencode\config.json（編集）
```

---

## 📊 ファイル一覧表

| ファイル | 行数 | 用途 | 優先度 |
|---------|------|------|--------|
| START-HERE.txt | 65 | 最初に読むもの | ⭐⭐⭐ |
| SETUP-COMPLETE.md | 600 | 全体のまとめ | ⭐⭐⭐ |
| AUTOMATED-SETUP-GUIDE.md | 400 | 完全ガイド | ⭐⭐⭐ |
| AUTO-START.bat | 85 | 自動実行 | ⭐⭐⭐ |
| OPENCODE-GUIDE.md | 587 | コマンド辞書 | ⭐⭐ |
| QUICKSTART.md | 200 | 5分ガイド | ⭐⭐ |
| OPENCODE-COMPLETE-SETUP.md | 428 | 詳細説明 | ⭐⭐ |
| RUN-ALL.ps1 | 310 | PowerShell スクリプト | ⭐ |
| opencode-setup.ps1 | 250 | 段階実行 | ⭐ |
| opencode-wrapper.ps1 | 関数集 | ラッパー関数 | ⭐ |
| opencode-examples.ps1 | 600+ | 実践例 | ⭐ |
| run_opencode_setup.bat | 50 | シンプル自動実行 | ⭐ |

---

## 🚀 最短ルート（初回のみ）

```
1. START-HERE.txt を読む
       ↓
2. AUTO-START.bat をダブルクリック
       ↓
3. セットアップ完了
       ↓
4. QUICKSTART.md で最初のコマンドを実行
```

**所要時間: 約 10 分**

---

## 💾 保存場所の確認

全ファイルが保存されている場所:

```
D:\keiba_ai\
├── SETUP-COMPLETE.md ← ここ
├── tools/
│   ├── START-HERE.txt
│   ├── AUTO-START.bat
│   ├── AUTOMATED-SETUP-GUIDE.md
│   ├── OPENCODE-GUIDE.md
│   ├── OPENCODE-COMPLETE-SETUP.md
│   ├── QUICKSTART.md
│   ├── INDEX.md（このファイル）
│   ├── RUN-ALL.ps1
│   ├── opencode-setup.ps1
│   ├── opencode-wrapper.ps1
│   ├── opencode-examples.ps1
│   ├── run_opencode_setup.bat
│   └── logs/（セットアップ後作成される）
```

---

## ❓ よくある質問

### Q: どのファイルから始めれば？
**A:** `START-HERE.txt` → `AUTO-START.bat` の順

### Q: 今すぐ実行したい
**A:** `AUTO-START.bat` をダブルクリック

### Q: トラブルが発生した
**A:** `AUTOMATED-SETUP-GUIDE.md` の「トラブルシューティング」を見る

### Q: コマンドが分からない
**A:** `OPENCODE-GUIDE.md` を参照

### Q: 実装例を見たい
**A:** `opencode-examples.ps1` を実行

### Q: 設定を変更したい
**A:** `OPENCODE-GUIDE.md` → `.opencode/config.json` を編集

---

## 🎉 完成！

```
┌──────────────────────────────────────┐
│                                      │
│  🚀 全てが自動で セットアップされます  │
│                                      │
│  START-HERE.txt を読んで             │
│  AUTO-START.bat をダブルクリック     │
│                                      │
└──────────────────────────────────────┘
```

---

**Happy Coding! 🚀 OpenCode で競馬AI開発を加速させましょう！**
