# Runtime Operations

うまなり地蔵AI の日次・週次パイプラインを動かす前に見る、最短の運用メモです。

## Health Checks

```bash
python3 run_all.py --runtime-check
python3 run_all.py --source-sanity
python3 run_all.py --integrity-check
python3 tools/diagnose_external.py
python3 run_all.py --doctor --doctor-skip-canary
python3 run_all.py --v2 --preflight-only
python3 run_all.py --v2-weekly --preflight-only
python3 canary_run.py
python3 scheduler.py --list-jobs
python3 scheduler.py --check-now
```

期待値:

- `--runtime-check`: `FAIL 0` であれば実行可能です。`MYKEIBADB_EXE`、PostgreSQL クライアント、DB ポート疎通は外部依存なので、未準備の場合は `WARN` になります。
- `--source-sanity`: Python 構文、`git diff --check`、個人環境の固定パス混入を確認します。
- `--integrity-check`: 定数、CSV の派生オッズ列、保存済みモデル特徴量、RAG JSON ストアの件数・重複・検索IDを確認します。
- `tools/diagnose_external.py`: PostgreSQL と `mykeibadb.exe` に絞って候補パスや設定例を表示します。CIや本番起動前に外部依存を必須にしたい場合は `--strict` を使います。
- `--doctor`: 外部依存、source sanity、runtime、integrity、日次/週次 preflight、canary をまとめて実行します。短く済ませたい場合は `--doctor-skip-canary`、外部依存 WARN も失敗扱いにしたい本番前チェックでは `--doctor-strict-external` を使います。
- `--v2 --preflight-only`: 日次 DAG の全ステージが dry-run で `PASS` します。
- `--v2-weekly --preflight-only`: 週次 DAG の全ステージが dry-run で `PASS` します。
- `canary_run.py`: DB 未起動の警告が出ることはありますが、環境内では非致命扱いです。
- `scheduler.py --list-jobs`: 常駐せず、登録済みジョブと次回実行予定だけを表示します。
- `scheduler.py --check-now`: 常駐せず、現在の開催日判定とペーパートレード状態だけを表示します。

## Daily Run

```bash
python3 run_all.py --v2
```

`run_all.py --v2` は本実行前に `pipeline_v2/preflight_check.py` を自動で実行します。診断だけ確認したい場合は `--preflight-only`、緊急運用で事前診断を省略したい場合だけ `--skip-preflight` を使います。

発信ステージは安全のため既定ではドラフト生成のみです。実投稿する場合だけ、明示的に `pipeline_v2/06_publish.py --live` を使うか、`KEIBA_PUBLISH_LIVE=1` と `KEIBA_SOCIAL_LIVE=1` を設定します。レガシーの `pipeline/post_x_05.py` も既定は dry-run で、実投稿には同じく `--live` または `KEIBA_SOCIAL_LIVE=1` が必要です。

Gmail 通知も既定では dry-run です。実送信する場合だけ、`pipeline/notify_08.py --live` を使うか、`KEIBA_NOTIFY_LIVE=1` を設定します。

自動再学習も既定では判定のみです。実際にモデルを更新する場合だけ、`pipeline/auto_learn_13.py --live`、`pipeline_v2/19_auto_learn.py --live`、または `KEIBA_AUTO_RETRAIN_LIVE=1` を使います。

途中で止まった場合は、重い前半を再実行せずに指定ステージから再開できます。

```bash
python3 pipeline_v2/00_orchestrator.py --start-at anomaly
python3 pipeline_v2/00_orchestrator.py --start-at portfolio
```

## Weekly Run

```bash
python3 run_all.py --v2-weekly
```

週次 DAG は学習、RAG 再構築、穴馬スコア、バックテスト、統計更新を含みます。本実行前の確認は次で行います。

```bash
python3 run_all.py --v2-weekly --preflight-only
```

週次バッチ開始時の Ops ヘルスチェックは、DB 未起動なら警告を出しつつ縮退モードで継続します。DB 接続を必須にして止めたい本番運用では、次のどちらかを使います。

```bash
KEIBA_WEEKLY_STRICT_OPS=1 python3 run_all.py --v2-weekly
python3 pipeline_v2/00_orchestrator_weekly.py --strict-ops
```

## Model Training Leak Guard

学習特徴量にオッズ・人気を入れない方針です。`pipeline/model_train_03.py` と `train_model_v2.py` は、`odds`、`ninki`、`popular` 系の列を学習特徴量から除外します。評価・ROI シミュレーションにはオッズを使えますが、モデル入力には使いません。

派生オッズ特徴量（`prev_odds`、`past3_avg_odds`、`ema*_odds`）は raw/features CSV からも除去します。確認は次で行えます。

古い `pipeline_v2/model_lgbm_v2.txt` は生成物扱いです。存在する場合は integrity check が `feature_names` を読み、`odds`、`ninki`、`popular` 系特徴量の混入を失敗として検知します。

```bash
python3 run_all.py --integrity-check
```

## Native Runtime

LightGBM、XGBoost、CatBoost の import 前に `pipeline/native_runtime.py` が `libgomp.so.1` をプリロードします。標準位置で見つからない場合は、次の環境変数で場所を指定できます。

```bash
export KEIBA_NATIVE_LIB_DIR=/path/to/lib-directory
```

現在の WSL 環境では user-space に展開した `libgomp.so.1` を利用できます。

## RAG Limits

日次DAGの `rag_index` は `--limit 5000` で上限をかけています。週次バッチ側は `--limit 50000 --rebuild` で既存ストアをクリアしてから再構築します。JSONフォールバック検索も既定で先頭 `20000` 件までを検索します。RAG document ID は `doc_id` として保持し、説明用の `horse_id` には実馬IDを返します。

```bash
export KEIBA_RAG_DEFAULT_LIMIT=5000
export KEIBA_RAG_SEARCH_LIMIT=20000
export KEIBA_RAG_FULL=1  # 明示した場合だけ全件構築
python3 pipeline_v2/10_rag_index.py --limit 50000 --rebuild
```

## External Dependencies

- PostgreSQL は `KEIBA_DB_URL` 未指定時に `postgresql://postgres:trust@localhost:5433/mykeibadb` を想定します。`pipeline.config.DB_CONFIG` も同じ URL から生成されるため、接続先変更は `KEIBA_DB_URL` に集約できます。
- sudo なしの WSL 環境では、ユーザー領域の PostgreSQL を使えます。起動・停止・確認は次で行います。

```bash
python3 tools/local_postgres.py start
python3 tools/local_postgres.py status
python3 tools/local_postgres.py stop
```

- `run_all.py --runtime-check` は `psql` の有無、設定済み DB ポートへの TCP 疎通、JRA-VAN コアテーブルの存在と空でないことを確認します。現在の WSL 環境では PostgreSQL 本体・クライアントが未配置なら `WARN` になります。
- 詳細診断は `python3 tools/diagnose_external.py` を使います。JSON 連携は `--json`、WARN を終了コード 1 にしたい運用では `--strict` を付けます。
- 本番データ取得・DB 同期を実行する前に DB サーバーを起動してください。
- `mykeibadb` データベースが作成済みでも、JRA-VAN 由来のテーブル（例: `umagoto_race_joho`, `race_shosai`, `odds1_tansho`）は別途 `mykeibadb.exe` などで同期する必要があります。
- `MYKEIBADB_EXE` は `pipeline/config.py` の既定値、または環境変数 `MYKEIBADB_EXE` で指定します。
- Playwright を使うスクレイピング系処理では、`python3 -m playwright install chromium` が必要です。

### Local PostgreSQL 18 Restore

`mykeibadb.dump` / `mykeibadb_fast/` が PostgreSQL 18.3 で作成されている場合、PostgreSQL 16 の `pg_restore` では読めません。ユーザー領域では次の場所を既定で優先します。

```bash
/home/uchih/.keiba_ai/postgres18
/home/uchih/.keiba_ai/pgdata18
```

復元の基本手順:

```bash
python3 tools/local_postgres.py stop
KEIBA_PG_PREFIX=/home/uchih/.keiba_ai/postgres18 \
KEIBA_PGDATA=/home/uchih/.keiba_ai/pgdata18 \
python3 tools/local_postgres.py start

PGPASSWORD=trust /home/uchih/.keiba_ai/postgres18/bin/dropdb \
  -h 127.0.0.1 -p 5433 -U postgres --if-exists mykeibadb
PGPASSWORD=trust /home/uchih/.keiba_ai/postgres18/bin/createdb \
  -h 127.0.0.1 -p 5433 -U postgres mykeibadb
PGPASSWORD=trust /home/uchih/.keiba_ai/postgres18/bin/pg_restore \
  -h 127.0.0.1 -p 5433 -U postgres -d mykeibadb \
  --no-owner --no-acl --verbose /home/uchih/.keiba_ai/mykeibadb.dump
```

この環境で見つかった `mykeibadb.dump` は途中で `end of file` になり、`mykeibadb_fast/` は一部 `.dat` が欠けていました。その場合でも、既存の `keiba_data.csv` から日次パイプラインに必要な `race_shosai` と `umagoto_race_joho` を補完できます。

```bash
python3 tools/seed_core_tables_from_csv.py \
  --replace \
  --csv /mnt/d/keiba_ai/keiba_data.csv
```

このCSV補完は運用を前へ進めるための互換レイヤーです。`race_shosai` / `umagoto_race_joho` の全JRA-VAN列を完全再現するものではないため、完全同期には `mykeibadb.exe` か完全なdumpが必要です。

復元後は次でコアテーブルが使える状態か確認します。

```bash
python3 tools/diagnose_external.py
python3 run_all.py --runtime-check
```
