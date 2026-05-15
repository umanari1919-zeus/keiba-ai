# 🎯 うまなり地蔵AI 実運用化ロードマップ 2026

> **目的**: バックテスト ROI +841% を、本番運用で持続可能な真の Edge に変換する。
>
> **基本方針**: 「+841% は幻、+15% が真の最強」 — まずバックテストの嘘を暴き、リスクを絞り、CI と監視で運用を堅牢化し、advisory モードで実運用検証してから自律運用を検討する。
>
> **作成日**: 2026-05-10  /  **作成者**: Buffy (Codebuff/Claude Opus 4.7)

---

## ⚠️ 最重要の前提認識

WF 検証で ROI +841% は、ほぼ確実に**過大評価**である。

- 世界トップクラスのプロ競馬投資集団（Bill Benter 級）でも長期 ROI は +10〜30% が天井
- 日本の競馬は控除率 20〜30%
- +841% を恒常的に出すのは数学的に困難
- **この乖離を埋めずに実弾を投入すると、1ヶ月で資金の 50〜80% を失うのが典型シナリオ**

したがって本ロードマップは P0（出血を止める）→ P1（破産しないリスク管理）→ P2（運用安定性）→ P3（長期 Edge 維持）の4階層で順序立てる。

---

## 📋 アクション一覧（10項目）

### 🔴 P0 — 出血を止める

#### #1 バックテスト信頼性監査 ⭐ 最優先
- **失敗シナリオ**: ROI +841% の正体が「未来データ漏洩」「最終確定オッズ使用」「生存バイアス」のいずれか → 本番で即破産
- **実装**:
  - `tools/leak_audit.py` 新設 — pandas monkey-patch で「race_id 発走時刻以降のデータ参照」を全トレース
  - オッズリーク検証: バックテストでは「投票締切時点のスナップショット」のみ使用契約に
  - 生存バイアス監査: NaN ドロップ群と残存群で勝率差を年・距離・馬齢別に集計
- **検収条件**: Bill Benter ベンチマーク。全部直して再 WF 検証 → ROI が **+5〜30%** に着地
- **担当**: 未定
- **状態**: 設計済み（roadmap）／実装未着手

#### #2 壊れたパイプ 3 本の修復（mlflow / pedigree / DB スキーマ）
- **失敗シナリオ**:
  - mlflow 失敗 → 本番モデル lineage 不明 → 「いつから ROI 悪化したか」追跡不能
  - pedigree 80% 失敗 → 血統特徴量虫食い
  - chakujun カラム不存在 → CSV フォールバックで動いてはいるが静かに別データ使用の疑い
- **実装**:
  - `mlflow_register.py` ↔ `model_train_03.py` 間で `MLFLOW_RUN_ID` を `data/last_train_run.json` 経由で永続化
  - pedigree のエラーログを 3 種類に分類し原因別リトライ（馬名正規化、JBIS レート制限、全角スペース など定番）
  - `pipeline/schemas.py` 新設 — 主要テーブルの pydantic モデル + `column_aliases.yaml` でカラム揺れ集中管理
- **検収条件**: mlflow 登録成功、pedigree エラー率 < 5%、CSV フォールバック発動ゼロ
- **担当**: 未定
- **状態**: 設計済み／部分着手

#### #3 投票直前 dry-run ゲートの必須化
- **失敗シナリオ**: バグった日に止められず実弾が出る
- **実装**:
  - 投票実行前段に `canary_run.py` を必ず実行 → 30/30 PASS でない限り `trading_agent.py` は dry_run=True 強制
  - `bankroll_agent.py` に「直近30日 ROI < -20% で自動停止」のサーキットブレーカ
  - 投票 API は idempotency key（race_id + horse_id + ticket_type + date）で重複防止
- **検収条件**: canary FAIL / DD 超過時に投票が実行されないことをテストで確認
- **担当**: 未定
- **状態**: 未着手

---

### 🟠 P1 — 破産しないリスク管理

#### #4 Kelly の現実化と「同時露出制限」
- **失敗シナリオ**: KELLY_FRACTION=0.10 は確率推定が正確な前提。実運用では p の推定誤差 30〜50% → 理論 Kelly の 1/4 でも破産確率 10% 超
- **実装**:
  - `KELLY_FRACTION` 0.10 → **0.05**（quarter Kelly 相当、プロ保守派の水準）
  - レース単位: 1レース総ベット ≤ 資金の 2%
  - 日次上限: 1日総ベット ≤ 資金の 10%
  - 破産確率モニタ: P(ruin) = ((1-edge)/(1+edge))^bankroll_units を日次計算、5% 超で停止
- **検収条件**: 半年シミュレーションで最大 DD < 30%、破産確率 < 1%
- **担当**: 未定
- **状態**: 未着手

#### #5 控除率・プール縮小・スリッページのリアル化
- **失敗シナリオ**: 30倍に1万円張ると地方場で 28倍に瞬時に下落 + JRA 単勝控除 20%。実 ROI は半分以下
- **実装**:
  - `pipeline/market_impact.py` 新設 — `new_odds = old_odds × pool / (pool + bet × old_odds)` で市場インパクト推定
  - `pipeline/config.py` に `TAKEOUT_RATES` を明示（単勝0.20 / 馬連0.225 / 三連複0.275 / etc.）
  - オッズドリフト推定: 締切5分前と最終オッズの差を1年分集計、ドリフト係数表を予測オッズに乗算
- **検収条件**: 再 WF 検証で「真の ROI」が +5〜30% に着地
- **担当**: 未定
- **状態**: 設計済み／部分着手

---

### 🟡 P2 — インフラと運用安定性

#### #6 CI/CD + 最小監視スタック
- **失敗シナリオ**: コード変更で predict が破壊されても誰も気づかず本番で大量損失
- **実装**:
  - CI（CODEX_TASKS タスク 2.8）に「リーク検知 CI ジョブ」追加 — PR 毎に leak_audit を 10 race サンプルで自動実行
  - Prometheus メトリクス: bet_placement_total / prediction_latency_seconds / model_predict_proba_p99 / bankroll_balance_jpy / daily_roi_rolling7d
  - アラート: DD>10% / canary FAIL / mlflow 失敗 → LINE/Discord 即通知
  - Dead-letter を SNS だけでなく投票・データ取得失敗にも拡張
- **検収条件**: CI green、Prometheus メトリクス5種出力、アラート発火テスト pass
- **担当**: Codex（CODEX_TASKS と統合）
- **状態**: 部分着手

#### #7 決定論的特徴量計算 + データ品質ゲート
- **失敗シナリオ**: train-serve skew で ROI が静かに劣化（検知が一番難しい問題）
- **実装**:
  - 特徴量ハッシュ — 同じ race_id セットで2回実行して SHA-256 一致を CI 確認
  - `pd.options.mode.chained_assignment = "raise"` で警告→エラー化
  - NaN 率の日次推移ダッシュボード
  - `pipeline/data_contract.py` で値域チェック（tansho_odds∈[1.0, 9999.9]、barei∈[2,12] など）
- **検収条件**: 同一入力で2回実行して特徴量ハッシュが一致、NaN 率異常をダッシュボードで可視化
- **担当**: 未定
- **状態**: 未着手

---

### 🟢 P3 — エッジを長期維持する

#### #8 ローリング再学習 + Drift / OOD 検知
- **失敗シナリオ**: モデル鮮度低下で他参加者にキャッチアップされる（半年で edge 消失は珍しくない）
- **実装**:
  - `auto_learn_13.py` をチャンピオン/チャレンジャー型に — shadow モデルが本番に1ヶ月勝ったら昇格
  - Drift 検知: KS 検定で特徴量分布シフトを週次測定、p<0.01 が 5 列超で警告
  - OOD 検知: Isolation Forest で「学習分布外レース」を検出 → そのレースだけ EV 閾値を引き上げ
  - キャリブレーション監視: Brier スコア悪化で Platt / Isotonic 再フィット
- **検収条件**: 月次 drift レポートが自動生成、shadow モデルの evaluation が CI で動く
- **担当**: 未定
- **状態**: 未着手

#### #9 アンサンブル安定化 + SHAP 監査
- **失敗シナリオ**: 「LightGBM だけが効いていた」「SHAP 上位が突然変わって過学習」など静かな破綻
- **実装**:
  - 各モデル（LGB/XGB/CB）の単独 ROC-AUC・Brier・寄与を記録、劣化モデルは重み調整
  - SHAP 上位20特徴の月次 Jaccard 類似度 — 0.5 未満で警告
  - アンサンブル diversity: Pearson(predict_proba) > 0.95 で diversity 損失判定
- **検収条件**: 月次レポートで各モデルの寄与・SHAP 安定性が可視化
- **担当**: 未定
- **状態**: 未着手

#### #10 「決定支援モード」をデフォルト・「自律投票」をオプトイン
- **失敗シナリオ・法務**: JRA IPAT の自動投票は規約・法解釈で完全には白ではない + バグ時の被害が桁違い
- **実装**:
  - `MODE=advisory`（デフォルト）: 朝に買い目シートを LINE/Discord/morning_report.txt に出すだけ、人間が IPAT で投票
  - `MODE=autonomous`: 自動投票には `--i-understand-the-risks` フラグ + `AUTONOMOUS_MAX_DAILY_JPY` 上限 + 毎朝の 2FA 手動承認 必須
  - 月次累計損失 > 上限で自動的に advisory に格下げ
  - 全投票の意思決定ログ（予測根拠・SHAP 上位5特徴）を `data/audit/bet_decisions_{date}.jsonl` に保存
- **検収条件**: advisory モードで3ヶ月黒字を確認後、autonomous を検討
- **担当**: 未定
- **状態**: 未着手

---

## 📅 推奨スケジュール

| 週 | タスク | 検収条件 |
|---|---|---|
| **W1** | #1 リーク監査 + #2 mlflow/pedigree/schema 修復 | リーク監査ツール完成、mlflow 登録成功、pedigree エラー率 < 5% |
| **W2** | #5 控除率・スリッページのリアル化、再 WF 検証 | 真 ROI が +5〜30% で着地 |
| **W3** | #4 Kelly 0.05 化 + 露出キャップ、#3 dry-run ゲート | 半年シミュで最大 DD<30%、破産確率<1% |
| **W4** | #6 CI + 監視スタック、#7 データ契約 | CI green、Prometheus メトリクス5種出力 |
| **W5** | #10 advisory モード本番運用開始（少額・人間投票） | 1ヶ月で実 ROI と WF 予測の整合性確認 |
| **W6-8** | #8 drift 検知、#9 アンサンブル監査、調整 | 月次レポート自動生成 |
| **W9+** | autonomous モード検討（advisory で 3 ヶ月黒字が前提） | — |

---

## 🔗 関連ドキュメント

- `CLAUDE.md` — システム全体の技術仕様
- `AGENTS.md` — エージェント構成のルール
- `CODEX_TASKS.md` — Codex 担当タスク（Tier 1+2 の 44h 分）
- `AGENT_HANDOFF.md` — Claude Code ↔ Codex の作業ログ
- `INTEGRATION_TEST.md` — Dashboard v4 統合テスト計画

## 📝 改訂履歴

- 2026-05-10 [Buffy/Opus 4.7]: 初版作成
