# Codex Tooling Plan 2026-05-09

## 目的

X上で目立つCodex活用の流れである `AGENTS.md`、Agent Skills、MCP、レビュー自動化を、うまなり地蔵AIの毎日運用に寄せて導入する。狙いは、日次パイプラインの失敗を減らし、データリークを防ぎ、X・note.com発信を安全に育てること。

## 今回入れる最小セット

1. `keiba-daily-pipeline` Skill
   - 日次実行、preflight、doctor、morning report、発信前チェックの手順を固定する。
   - ライブ投稿はユーザー明示時のみ行う。

2. `keiba-leakage-audit` Skill
   - オッズ、人気、払戻、確定着順、未来情報がモデル特徴量に入らないよう監査する。
   - オッズ利用を「予測後のEV・Kelly・レポート」に限定して整理する。

3. `pipeline/AGENTS.md`
   - pipeline配下で作業するCodexに、最重要ルールと確認コマンドを近い場所で読ませる。

## 追加で取り込むもの

公式以外のコミュニティSkill、MCP、awesome系カタログも候補に入れる。採用候補は `docs/external-tools/codex_mcp_skill_candidates_2026-05-09.md` に整理し、導入前に権限、更新状況、秘密情報の扱いを確認する。

### 特徴量強化

特徴量強化は最優先テーマにする。方向性は、オッズ・人気ではなく、レース前に確定している血統、調教、馬場、コース、ローテーション、騎手調教師、展開推定、枠順バイアスを厚くすること。

追加したSkill:

- `keiba-feature-engineering`

### PostgreSQL強化

PostgreSQLは単なる保存先ではなく、特徴量生成のエンジンとして強化する。読み取り専用診断、index、materialized view、`pg_stat_statements`、年単位分割を検討する。

追加したSkill:

- `keiba-db-ops`

MCPを使う場合は、PostgreSQL MCPを最初に検討する。ただし、最初は読み取り専用ユーザーで接続し、破壊的SQLを使わない。

## 次に検討するもの

### X MCP

X公式のMCPは、最初は読み取り専用で検討する。

- 競馬AI、JRA、穴馬、Codex関連投稿の収集
- 投稿反応の確認
- 競合・参考アカウントの分析

自動投稿は誤投稿リスクが高いため、当面は既存の `pipeline/post_x_05.py` と `social_bot_27.py` を優先し、MCPからの投稿権限は保留する。

### 追加Skill候補

- `keiba-backtest-review`: 追加済み。ROI、回収率、的中率、EV閾値、Kelly上限をまとめて読む。
- `keiba-publisher-review`: 追加済み。X・note.comの文章を、過度な断定なしで整える。
- `keiba-db-ops`: 追加済み。PostgreSQL、mykeibadb、CSV seed、index、readinessを安全に扱う。
- `keiba-feature-engineering`: 追加済み。レース前に使える特徴量だけを安全に増やす。

## 導入順

1. 日次運用とリーク監査のSkillを作る。
2. `pipeline/AGENTS.md` でローカル規約を補強する。
3. 実際の変更や日次実行時にSkillを使い、足りない手順だけ追記する。
4. X MCPは認証・権限・投稿安全策を整理してから接続する。

## 成功条件

- Codexが日次確認コマンドを迷わず選べる。
- モデル入力にオッズ・人気・結果情報が入る変更を早期に止められる。
- 発信系の作業で、ライブ投稿前に確認が入る。
- ユーザーが「何を実行したか」「どこが危ないか」を短く把握できる。
