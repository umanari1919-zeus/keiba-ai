# 統合テスト計画 — うまなり地蔵AI Dashboard v4

## フェーズ構成

- **Phase 1**: FastAPI サーバー起動 & ヘルスチェック
- **Phase 2**: REST API エンドポイント検証
- **Phase 3**: WebSocket エンドポイント検証
- **Phase 4**: Streamlit ダッシュボード検証
- **Phase 5**: エンドツーエンド統合テスト

---

## Phase 1: FastAPI サーバー起動 & ヘルスチェック

### 準備
```bash
# PowerShell or Bash から実行
cd D:\keiba_ai

# FastAPI サーバー起動
uvicorn api.main:app --reload --port 8000

# 別のターミナルで確認
curl http://localhost:8000/
curl http://localhost:8000/health
```

### 期待結果

✅ **API ルート情報**
```json
{
  "name": "うまなり地蔵AI Pipeline API",
  "version": "2.0.0",
  "docs": "/docs",
  "openapi": "/openapi.json"
}
```

✅ **ヘルスチェック**
```json
{"status": "ok"}
```

### 検証項目

- [ ] サーバーがポート 8000 で起動
- [ ] `/` エンドポイントが API 情報を返す
- [ ] `/health` エンドポイントが `ok` を返す
- [ ] Swagger UI に http://localhost:8000/docs でアクセス可能

---

## Phase 2: REST API エンドポイント検証

### 2-1. パイプライン実行 API

**テスト**: パイプラインを起動して trace_id を取得

```bash
# パイプライン実行（v2 DAG）
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"pattern":"v2"}'

# 期待結果
# {
#   "trace_id": "run_20260506_120000_abc12345",
#   "status": "running"
# }
```

**保存**: 返された trace_id を後続テストで使用

### 2-2. パイプライン状態確認 API

**テスト**: 実行中のパイプラインの状態を確認

```bash
# {TRACE_ID} を前のステップで取得した値に置き換え
curl http://localhost:8000/api/pipeline/status/{TRACE_ID}

# 期待結果（実行中）
# {
#   "trace_id": "run_20260506_120000_abc12345",
#   "status": "running",
#   "exit_code": null,
#   "elapsed_seconds": 45.2,
#   "pattern": "v2"
# }

# パイプライン完了後
# {
#   "status": "completed",
#   "exit_code": 0,
#   "elapsed_seconds": 180.5
# }
```

### 2-3. パイプラインログ API

**テスト**: 実行ログを取得

```bash
curl "http://localhost:8000/api/pipeline/log/{TRACE_ID}?tail=50"

# 期待結果
# {
#   "trace_id": "run_20260506_120000_abc12345",
#   "lines": [
#     "[2026-05-06 12:00:00] Starting pipeline: v2",
#     "[2026-05-06 12:00:05] Step 1: Ingest...",
#     ...
#   ],
#   "total_lines": 250
# }
```

### 2-4. パイプライン履歴 API

**テスト**: 過去の実行履歴を取得

```bash
curl http://localhost:8000/api/pipeline/history?limit=10

# 期待結果
# {
#   "history": [
#     {
#       "trace_id": "run_20260506_120000_abc12345",
#       "pattern": "v2",
#       "status": "completed",
#       "start_time": "2026-05-06T12:00:00",
#       "elapsed_seconds": 180.5,
#       "exit_code": 0
#     },
#     ...
#   ]
# }
```

### 2-5. データ API テスト

#### 2-5a. 今日の予想を取得

```bash
curl "http://localhost:8000/api/data/predictions?date=20260506"

# 期待結果: 予想馬データの JSON array
```

#### 2-5b. ROI サマリーを取得

```bash
curl "http://localhost:8000/api/data/roi?year=2026"

# 期待結果: 日次/週次/月次 ROI サマリー
```

#### 2-5c. 資金状態を取得

```bash
curl http://localhost:8000/api/data/bankroll

# 期待結果
# {
#   "current": 1150000,
#   "initial": 1000000,
#   "peak": 1200000,
#   "drawdown_percent": 4.17
# }
```

#### 2-5d. レースランキングを取得

```bash
curl "http://localhost:8000/api/data/race-ranking?year=2026&limit=20"

# 期待結果: TOP 20 レース（ROI 降順）
```

### 2-6. 設定 API テスト

#### 2-6a. 現在のパラメータを取得

```bash
curl http://localhost:8000/api/settings/parameters

# 期待結果
# {
#   "EV_THRESHOLD": 0.15,
#   "KELLY_FRACTION": 0.10,
#   "MIN_ODDS": 10.0,
#   "MIN_ODDS_BACKTEST": 300,
#   "updated_at": "2026-05-06T11:30:00"
# }
```

#### 2-6b. パラメータを更新

```bash
curl -X PUT http://localhost:8000/api/settings/parameters \
  -H "Content-Type: application/json" \
  -d '{"EV_THRESHOLD": 0.20}'

# 期待結果
# {
#   "message": "Parameters updated",
#   "EV_THRESHOLD": 0.20,
#   "updated_at": "2026-05-06T12:15:00"
# }

# ✅ config.py が書き換わったことを確認
# grep "EV_THRESHOLD = " pipeline/config.py
```

#### 2-6c. パラメータをリセット

```bash
curl -X POST http://localhost:8000/api/settings/reset

# 期待結果
# {
#   "message": "Parameters reset to defaults",
#   "EV_THRESHOLD": 0.15,
#   "KELLY_FRACTION": 0.10,
#   "MIN_ODDS": 10.0
# }
```

### 2-7. Admin API テスト

#### 2-7a. スケジューラジョブ一覧

```bash
curl http://localhost:8000/api/admin/jobs

# 期待結果
# {
#   "jobs": [
#     {
#       "name": "v2_daily",
#       "next_run": "2026-05-07T09:00:00",
#       "last_run": "2026-05-06T09:00:00",
#       "enabled": true
#     },
#     ...
#   ]
# }
```

#### 2-7b. ジョブを手動実行

```bash
curl -X POST http://localhost:8000/api/admin/jobs/v2_daily/run

# 期待結果
# {
#   "message": "Job triggered: v2_daily",
#   "trace_id": "run_20260506_121500_def67890"
# }
```

#### 2-7c. ログを検索

```bash
curl "http://localhost:8000/api/admin/logs?pattern=error&limit=20"

# 期待結果: エラーログ 20 件
```

### 2-8. エラーハンドリングテスト

#### 無効な trace_id

```bash
curl http://localhost:8000/api/pipeline/status/invalid_trace_id

# 期待結果: 404
# {
#   "detail": "Trace ID not found"
# }
```

#### 無効なパターン

```bash
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"pattern":"invalid"}'

# 期待結果: 400
# {
#   "detail": "Invalid pattern. Choose from: v2, v2-weekly, morning, results"
# }
```

---

## Phase 3: WebSocket エンドポイント検証

### 前提条件

FastAPI サーバーが起動している必要があります。

```bash
# wscat のインストール（Node.js）
npm install -g wscat

# または Python
pip install websocket-client
```

### 3-1. パイプラインログ配信

```bash
# Terminal 1: FastAPI サーバー起動
uvicorn api.main:app --reload --port 8000

# Terminal 2: パイプラインを起動して trace_id を取得
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"pattern":"v2"}'
# → trace_id: run_20260506_abc123

# Terminal 3: WebSocket でログを購読
wscat -c ws://localhost:8000/ws/pipeline/run_20260506_abc123

# 期待結果: リアルタイムログが配信される
# {"type":"log","trace_id":"run_20260506_abc123","line":"[2026-05-06 12:00:00] Starting...","timestamp":"2026-05-06T12:00:00Z"}
# {"type":"log","trace_id":"run_20260506_abc123","line":"[2026-05-06 12:00:05] Step 1...","timestamp":"2026-05-06T12:00:05Z"}
```

### 3-2. オッズ更新配信（シミュレーション）

```bash
# WebSocket でオッズを購読
wscat -c ws://localhost:8000/ws/odds/20260426010101

# 期待結果: 5秒ごとにオッズスナップショット更新を配信
# {"type":"odds","race_code":"20260426010101","timestamp":"2026-05-06T12:00:00Z",...}
```

### 3-3. 通知配信（シミュレーション）

```bash
# WebSocket で全体通知を購読
wscat -c ws://localhost:8000/ws/notifications

# 期待結果: 通知イベントが配信される
# {"type":"notification","notification_type":"alert","message":"Drawdown warning: 15%","timestamp":"2026-05-06T12:00:00Z"}
```

---

## Phase 4: Streamlit ダッシュボード検証

### 準備

```bash
# FastAPI サーバーが起動していることを確認（別ターミナル）
# uvicorn api.main:app --reload --port 8000

# Streamlit ダッシュボード起動
streamlit run pipeline/dashboard_v4/app.py
```

### テスト項目

#### 4-1. メインページ表示

- [ ] ウィンドウタイトルが「うまなり地蔵AI Dashboard v4」
- [ ] 現在の日付・時刻が表示
- [ ] ページ説明が表示

#### 4-2. ページナビゲーション

左側メニューのボタンをクリックして各ページに遷移できることを確認：

- [ ] 🏠 ホーム → ページ読み込み成功
- [ ] 📈 成績サマリー → ROI グラフ表示
- [ ] 💰 資金管理 → Kelly シミュレーター表示
- [ ] 🔬 詳細分析 → 特徴量グラフ表示
- [ ] 🧪 バックテスト → 検証結果テーブル表示
- [ ] ⚙️ 設定 → パラメータスライダー表示
- [ ] 👨‍💼 管理画面 → ジョブ制御パネル表示
- [ ] 🏇 出走表 → レース・馬データ表示

#### 4-3. ホームページ機能

- [ ] 4 つの KPI カード表示（Bankroll, EV Threshold, Kelly, Min Odds）
- [ ] 本日の買い目テーブル（5行以上）表示
- [ ] Pipeline Pattern ドロップダウン表示
- [ ] Run ボタンをクリック → パイプライン起動
- [ ] ステータス表示（Running/Completed）
- [ ] ライブログ表示（最後 30 行）

#### 4-4. 成績ページ機能

- [ ] 期間フィルタ（30日/3ヶ月/6ヶ月/全期間）が動作
- [ ] ROI トレンドグラフ表示
- [ ] 統計メトリクス表示（Current ROI, Max ROI, Avg ROI, Volatility）
- [ ] Hit Rate グラフ表示
- [ ] 月別集計テーブル表示

#### 4-5. 資金管理ページ機能

- [ ] 資金メトリクス表示（Current, Peak, Max DD, Total ROI）
- [ ] 月別資金推移グラフ表示
- [ ] Kelly シミュレーター動作
  - オッズと勝率を入力
  - Kelly % 計算表示
  - ベット額計算表示
- [ ] Kelly カーブ表示

#### 4-6. 設定ページ機能

- [ ] 現在のパラメータ表示
- [ ] EV_THRESHOLD スライダー変更 → API 呼び出し
- [ ] KELLY_FRACTION スライダー変更 → API 呼び出し
- [ ] MIN_ODDS スライダー変更 → API 呼び出し
- [ ] Apply Changes ボタンクリック → 「更新成功」メッセージ
- [ ] Reset to Defaults ボタン → パラメータをデフォルトに戻す

#### 4-7. 管理画面機能

- [ ] Pipeline Control タブ
  - Pattern ドロップダウン（v2, v2-weekly, morning, results）
  - Start ボタン → パイプライン起動
  - Cancel ボタン → パイプライン停止
- [ ] Jobs タブ
  - ジョブリスト表示（next_run, last_run）
  - Manual Trigger ボタン → ジョブ実行
- [ ] Logs タブ
  - ログ検索フィルタ
  - 検索結果テーブル表示
- [ ] Agent Stats タブ
  - エージェント統計表示

---

## Phase 5: エンドツーエンド統合テスト

### シナリオ 1: 朝の運用フロー

1. **7:00 — Streamlit ダッシュボード起動**
   - ホームページで本日の買い目確認
   - 4 つの KPI メトリクスが表示される

2. **7:15 — パイプライン実行**
   - ホームページ → "Run" ボタン → v2 pattern 選択
   - ライブログで進捗を監視
   - 完了後 ✅ メッセージ表示

3. **8:00 — 成績確認**
   - 成績サマリーページ → 本週の ROI 確認
   - 的中率グラフ確認

4. **8:30 — パラメータ調整**
   - 設定ページ → EV_THRESHOLD を 0.15 → 0.18 に変更
   - Apply Changes → API 呼び出し確認
   - config.py が書き換わったことを確認

5. **9:00 — ジョブ監視**
   - 管理画面 → Jobs タブ
   - 週次ジョブの次回実行時刻確認

### シナリオ 2: 夕方の結果確認フロー

1. **17:00 — 本日の成績確認**
   - 成績サマリーページ → 本日 ROI 確認
   - 赤字・黒字の確認

2. **17:30 — 資金状態確認**
   - 資金管理ページ → Bankroll Status タブ
   - ドローダウン警告確認（>10% なら対応）

3. **18:00 — バックテスト確認**
   - バックテストページ → Walk-Forward Results
   - 年別 ROI 推移確認

---

## 検証チェックリスト

### API テスト

- [ ] Pipeline API 全エンドポイント動作確認
- [ ] Data API 全エンドポイント動作確認
- [ ] Settings API 全エンドポイント動作確認
- [ ] Admin API 全エンドポイント動作確認
- [ ] エラーハンドリング（404, 400 など）確認

### WebSocket テスト

- [ ] パイプラインログ配信確認
- [ ] オッズ配信確認（シミュレーション）
- [ ] 通知配信確認（シミュレーション）

### Streamlit テスト

- [ ] 全 8 ページ表示確認
- [ ] ページナビゲーション確認
- [ ] データロード確認（TTL キャッシング）
- [ ] インタラクティブ要素確認（スライダー、ボタン）

### 統合テスト

- [ ] FastAPI ← → Streamlit API 連携確認
- [ ] パイプライン実行フロー（開始 → 進捗表示 → 完了）
- [ ] パラメータ変更 → 新規パイプライン実行で反映確認

---

## トラブルシューティング

### サーバー起動時エラー

```
Address already in use
```

→ ポート 8000 が既に使用されている。別のプロセスを終了するか、ポート番号を変更

```bash
# 別のポートで起動
uvicorn api.main:app --reload --port 8001
```

### API 接続エラー

```
ConnectionError: Failed to connect to localhost:8000
```

→ FastAPI サーバーが起動していない

```bash
# 確認
curl http://localhost:8000/health
```

### Streamlit データ読み込みエラー

```
FileNotFoundError: data/roi_tracker.csv
```

→ パイプラインを実行して CSV を生成

```bash
python run_all.py --v2
```

### WebSocket 接続失敗

```
WebSocket connection failed
```

→ FastAPI WebSocket エンドポイントが起動していない

```bash
# api/routers/ws.py が正しくマウントされているか確認
curl http://localhost:8000/docs
# → Swagger UI で /ws/* エンドポイントが表示されるか確認
```

---

## 期待される成果物

✅ すべてのテストが PASS した場合：

- FastAPI バックエンド完全動作
- Streamlit ダッシュボード完全動作
- 全 REST API エンドポイント正常
- WebSocket リアルタイム更新正常
- 朝夕の運用フロー確認済み

→ **本番運用可能レベル**

---

## 次のステップ

1. **本番デプロイ**
   - FastAPI を `gunicorn + uvicorn` でデプロイ
   - Streamlit をプロダクション モードで起動

2. **監視・運用**
   - ログ監視（`logs/` ディレクトリ）
   - ドローダウン監視（>20% でアラート）
   - パイプライン失敗監視

3. **拡張機能**
   - Phase 4: エージェント監視ダッシュボード
   - リアルタイム通知（Slack/Discord）
   - パフォーマンスプロファイリング

---

**テスト実施日**: \_\_\_\_年\_\_\_月\_\_\_日
**実施者**: \_\_\_\_\_\_\_\_\_\_\_\_
**結果**: ✅ PASS / ❌ FAIL

テスト中に問題が発生した場合は、上記トラブルシューティングを参照するか、ログファイルを確認してください。
