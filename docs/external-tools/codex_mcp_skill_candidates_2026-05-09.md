# Codex / MCP / Skill Candidates 2026-05-09

## 方針

公式以外のツールも候補に入れる。ただし、競馬AIの資産を守るため、最初は読み取り専用、ローカル限定、投稿なし、秘密情報なしを原則にする。

## すぐ採用するローカルSkill

- `keiba-daily-pipeline`: 日次運用とpreflight。
- `keiba-leakage-audit`: オッズ・人気・結果・未来情報のリーク監査。
- `keiba-feature-engineering`: 血統、調教、馬場、ローテ、展開、コース適性の安全な特徴量強化。
- `keiba-backtest-review`: ROI、回収率、ドローダウン、EV閾値、Kellyの確認。
- `keiba-db-ops`: PostgreSQL診断、index、集計、materialized view候補。
- `keiba-publisher-review`: X・note.com発信の品質と安全確認。

## 外部カタログ

- OpenAI Skills catalog: Codex向けSkillの基準。まず構造と命名の参考にする。
- Codexlog: Codexのプロンプト、MCP、AGENTS.md、レビュー運用のコミュニティ知識ベース。
- Awesome Agent Skills / Awesome Codex CLI / Awesome MCP: 候補探索用。導入前にREADME、メンテ状況、権限、ライセンスを確認する。
- MCPpedia / FindMCP / mcp-awesome: MCP探索用。スコアやCVE、更新状況が見られるものを優先する。

## MCP候補

### 優先度A

- PostgreSQL MCP, read-only
  - 用途: スキーマ確認、EXPLAIN、集計確認、特徴量の元データ調査。
  - 条件: 読み取り専用ユーザー、接続先限定、DROP/UPDATE/INSERT不可。

- Playwright MCP
  - 用途: ダッシュボード確認、JRA/オッズ取得画面の検証、スクリーンショット。
  - 条件: 認証情報を保存しない。投稿や購入操作を禁止。

- GitHub MCP
  - 用途: issue/PR管理、レビューコメント対応、CI確認。
  - 条件: リポジトリ権限を最小化。tokenをログ出力しない。

### 優先度B

- Filesystem MCP
  - Codexは既にローカルファイルを扱えるため優先度は低い。導入するなら `D:\keiba_ai` のみに制限。

- Memory / Codebase-memory系
  - 用途: 大規模コードベースの構造記憶。
  - 条件: 秘密情報や馬券資金情報を取り込まない設定が必要。

- Sequential Thinking系
  - 用途: 複雑な特徴量設計やDB移行計画。
  - 条件: 既存の計画Skillで足りない場合だけ。

### 保留

- X MCPの投稿権限
  - 読み取りと分析は有望。投稿は誤投稿リスクがあるため、ユーザー確認フローが固まるまで保留。

- 汎用WebスクレイピングMCP
  - 競馬サイトの規約、robots、認証、負荷に注意。まず既存の `odds_scraper_36.py` を優先。

## 特徴量強化テーマ

- 父・母父の競馬場×距離×馬場状態適性。
- 騎手×調教師コンビの30/90/365日ローリング成績。
- 枠順バイアスを競馬場、距離、頭数、馬場状態で分解。
- 逃げ先行の数から作るペース圧指数。
- 調教時計の前走比、施設内z-score、2-3本トレンド。
- 休み明け、距離延長短縮、芝ダート替わり、昇級降級の組み合わせ。

## PostgreSQL強化テーマ

- `race_code`, `ketto_toroku_bango`, `kaisai_nen`, `kaisai_gappi` を中心にindexを確認。
- 重い履歴集計はmaterialized view化を検討。
- `pg_stat_statements` で遅い特徴量クエリを特定。
- 年単位のパーティション、または年別集計テーブルを検討。
- `EXPLAIN (ANALYZE, BUFFERS)` を使い、推測ではなく実測で改善する。

## 導入判断

外部ツールは、次の条件を満たしたものだけ使う。

- 最終更新が古すぎない。
- READMEに権限と設定例がある。
- ローカル限定または接続先限定にできる。
- 秘密情報をログに出さない。
- 読み取り専用で開始できる。
- 競馬AIの収益化に直結する。
