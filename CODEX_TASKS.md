# Codex 作業指示書 — うまなり地蔵AI Tier 1+2 完成

## 0. 前提

- **Codex 作業ブランチ**: `claude/gifted-kirch-a032d5-codex`（このファイルが含まれた状態から切る）
- **Claude Code 作業ブランチ**: `claude/gifted-kirch-a032d5`
- **連携方式**: ブランチ分離・最後に PR マージ
- **コミット規約**: メッセージ先頭に `[Codex]` プレフィックスを付与
- **コミット粒度**: 小さく・CI を通しながら積む

## 1. 共通テスト方針（重要）

### mock する対象（I/O 境界）
- **DB**: `psycopg2.connect` → `tests/conftest.py` の `mock_psycopg2` を使用
- **HTTP**: `httpx`, `requests`, `urllib`（外部 API 全般）
- **SNS**: X / Discord / Telegram / LINE 投稿
- **LLM API**: `anthropic`, `ollama` クライアント
- **時刻**: `datetime.now()`, `time.time()`（再現性が必要なテストのみ）
- **ファイル I/O**: 大容量 CSV、`model_v8.pkl` など → fixture 経由で tmp_path
- **subprocess**: `subprocess.run`（パイプラインジョブ起動）

### mock しない対象（業務ロジック）
- EV 計算、Kelly 計算、確率変換、特徴量エンジニアリング
- アンサンブル重み計算、分類ロジック
- スキーマ検証、ハッシュ計算
- BaseAgent のライフサイクル（execute, dry_run 制御）

**理屈**: 「価値を生むコード」と「外部依存」を切り分ける。前者は実物で動かし、後者は隔離する。

## 2. 共通ファイル排他マップ

### Codex が **触ってはいけない** ファイル（Claude Code 専有）

```
scheduler.py
setup_pipeline_v2.py
pipeline_v2/00_orchestrator.py
tests/conftest.py                          # import するだけ
tests/__init__.py
tests/test_base_agent.py                   # 上書き禁止
tests/test_integration.py                  # 上書き禁止
tests/test_mlflow_register.py              # 上書き禁止
mlflow_register.py
pipeline/model_train_03.py
pipeline/dashboard_v4/app.py
pipeline/dashboard_v4/pages/08_model_comparison.py  # Claude Code 作成
nvidia_test.py
.env.template
CODEX_TASKS.md                             # この指示書を Codex は編集しない
```

### Codex 専有ファイル（Claude Code は触らない）

```
.pre-commit-config.yaml                    # 新規
requirements.txt
api/routers/admin.py
api/main.py
pipeline/dashboard_v4/pages/*.py
  ├─ ただし 08_model_comparison.py は除外
  └─ サイレント失敗修正（タスク 2.16）も除外（Claude Code 担当）
pyproject.toml                             # 新規
tests/test_agents_*.py                     # 新規 ×15
tests/test_pipeline_*.py                   # 新規 ×8
tests/test_api_*.py                        # 新規 ×4
.github/workflows/ci.yml                   # 新規
pipeline/social_bot_27.py
pipeline/*.py（model_train_03.py, dashboard_15.py を除く）
AGENT_HANDOFF.md                           # 双方が更新
```

### 1.8 と 2.16 の分担（重要）

- **1.8（bare except 修正）= Codex 担当**
  - 対象: `pipeline/dashboard_v4/pages/*.py`（08_model_comparison.py を除く）と `pipeline/dashboard_15.py`
  - 「except: → except Exception as e: + log」の機械的置換のみ
- **2.16（サイレント失敗の UX 改善）= Claude Code 担当**
  - 対象: 同じファイル群だが、`st.warning(...)` 等を追加するロジック判断を含む
  - Codex は **同じファイルを2回触る形になる**ので、1.8 完了後に Claude Code が引き継ぐ

---

## 3. タスク順序（CI 最優先）

| 順 | タスク | 工数 | 内容 |
|---|--------|------|------|
| 1 | **2.8 GitHub Actions CI** | 2h | ⭐ **最初に実施** |
| 2 | 2.9 セキュリティスキャン CI | 1h | 2.8 と同じ YAML に統合 |
| 3 | 1.4 requirements.txt 固定 | 0.5h | CI で検証可能になる |
| 4 | 1.3 pre-commit + detect-secrets | 1h | CI 連携 |
| 5 | 2.1 pyproject.toml | 0.5h | pytest 設定 |
| 6 | 1.10 CORS 制限 | 0.5h | 単純置換 |
| 7 | 1.11 scheduler logging | 1.5h | print→logging |
| 8 | 1.8 bare except 修正 | 2h | dashboard ファイル群 |
| 9 | 1.7 API Admin 実装 | 3.5h | 監査ログ集計 |
| 10 | 2.5 API テスト ×4 | 4h | 1.7 を検証 |
| 11 | 2.3 agents テスト ×15 | 12h | 大物 |
| 12 | 2.4 pipeline テスト ×8 | 8h | 大物 |
| 13 | 2.7 カバレッジゲート 60% | 0.5h | CI に追加 |
| 14 | 2.13 tenacity リトライ | 3h | ネットワーク系 |
| 15 | 2.14 print→logging 統一 | 3h | pipeline/*.py |
| 16 | 2.15 SNS dead-letter | 1h | social_bot_27 |

合計: 約 **44h**（Tier 1: 9.5h + Tier 2: 34.5h、2.16 は Claude Code に移譲）

---

## 4. タスク詳細

各タスクは以下 6 項目を必ず確認すること。

### Tier 0: CI 基盤

#### タスク 2.8 + 2.9: GitHub Actions CI（3h）⭐ 最初に実施

| 項目 | 内容 |
|---|---|
| **編集許可** | `.github/workflows/ci.yml`（新規） |
| **編集禁止** | 上記以外すべて |
| **完了条件** | `gh workflow run ci.yml` がグリーン。test/security/lint の3ジョブ全成功 |
| **実行テスト** | `pytest tests/` が CI 上で 36/36 PASS |
| **mock対象** | N/A（CI 設定のみ） |
| **仕様変更可否** | テストランナーは `pytest`、Python は `3.11` 固定。それ以外は自由 |

**雛形**:
```yaml
name: CI
on:
  push:
    branches: [main, "claude/**"]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt pytest pytest-cov mlflow
      - run: pytest tests/ -v
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install detect-secrets bandit
      - run: detect-secrets scan --baseline .secrets.baseline || true
      - run: bandit -r agents/ api/ pipeline/ -ll || true
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install flake8
      - run: flake8 --max-line-length=120 --ignore=E203,W503,E501 agents/ api/
```

**メモ**: 初回はカバレッジゲート無効。タスク 2.7 で `--cov-fail-under=60` を追加する。

---

### Tier 1: 安全運用

#### タスク 1.4: requirements.txt バージョン固定（0.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `requirements.txt` のみ |
| **編集禁止** | 全ソースコード |
| **完了条件** | `pip install -r requirements.txt --dry-run` がエラーなし。CI test ジョブが通る |
| **実行テスト** | `pytest tests/` 全パス（変わらず36個） |
| **mock対象** | N/A |
| **仕様変更可否** | コア依存（lightgbm, xgboost, pandas など）の **major バージョンは変えない**。minor までは可 |

**手順**:
```bash
pip freeze > /tmp/freeze.txt
# requirements.txt の各行を「>=」→「==」に置換し、freeze.txt の値を反映
```

オプション系（langgraph, stable-baselines3, torch）はコメントアウトのまま維持。

---

#### タスク 1.3: pre-commit + detect-secrets（1h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `.pre-commit-config.yaml`（新規）, `.secrets.baseline`（新規） |
| **編集禁止** | ソースコード |
| **完了条件** | `pre-commit run --all-files` がパス。`.secrets.baseline` がコミット済 |
| **実行テスト** | `detect-secrets scan` でゼロ違反 |
| **mock対象** | N/A |
| **仕様変更可否** | フック追加は自由。既存ルールの除外は要相談 |

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: '\.lock$|\.pkl$|\.csv$|\.json$|\.git/'
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=10000']
      - id: detect-private-key
```

---

#### タスク 2.1: pyproject.toml + pytest 設定（0.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `pyproject.toml`（新規） |
| **編集禁止** | `tests/conftest.py`, `tests/__init__.py` |
| **完了条件** | `pytest` が `pyproject.toml` の設定を読んで実行できる |
| **実行テスト** | `pytest tests/ -v` 36/36 PASS |
| **mock対象** | N/A |
| **仕様変更可否** | カバレッジ閾値は最終的に 60%。途中段階は緩めても可 |

```toml
[project]
name = "umanari-jizo-ai"
version = "2.0.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
markers = [
    "unit: unit tests (no DB, no network)",
    "integration: integration tests (may need DB)",
    "slow: slow tests (>10s)",
]
addopts = "--strict-markers"

[tool.coverage.run]
source = ["agents", "api", "pipeline"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 60
show_missing = true
```

---

#### タスク 1.10: CORS 制限（0.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `api/main.py` のみ |
| **編集禁止** | 他 API ルーター |
| **完了条件** | `allow_origins=["*"]` が消えて localhost に限定されている |
| **実行テスト** | `pytest tests/test_api_*.py`（タスク 2.5 で作成）<br>暫定: `python -c "from api.main import app; print('OK')"` |
| **mock対象** | N/A |
| **仕様変更可否** | 環境変数 `KEIBA_CORS_ORIGINS` で上書きできる設計に変えても可（推奨） |

```python
import os
allowed = os.getenv(
    "KEIBA_CORS_ORIGINS",
    "http://localhost:8501,http://localhost:3000,http://127.0.0.1:8501,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

#### タスク 1.11: scheduler.py logging（1.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `scheduler.py` のみ |
| **編集禁止** | `_run_with_retry` / `_notify_failure` の **ロジック変更禁止**（Claude Code 1.9 の成果物） |
| **完了条件** | 全 `print(...)` が `log.info/warning/error(...)` に置換 |
| **実行テスト** | `python -c "import scheduler"` でエラーなし。<br>`python scheduler.py --once`（もしあれば）で正常動作 |
| **mock対象** | N/A（実行検証のみ） |
| **仕様変更可否** | リトライ機構（`MAX_RETRIES`, `_run_with_retry`）には触らない |

```python
import logging
from pathlib import Path

LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")
```

---

#### タスク 1.8: bare except 修正（2h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `pipeline/dashboard_v4/pages/*.py`（**08_model_comparison.py を除く**）<br>`pipeline/dashboard_15.py` |
| **編集禁止** | 上記以外、特に `pipeline/dashboard_v4/pages/08_model_comparison.py` |
| **完了条件** | `grep -rn "except:" pipeline/dashboard_v4/ pipeline/dashboard_15.py` がゼロ |
| **実行テスト** | `python -c "import pipeline.dashboard_15"` でエラーなし<br>各ページの `streamlit run` 起動確認（任意） |
| **mock対象** | N/A |
| **仕様変更可否** | 機能変更は禁止。`except: → except Exception as e:` の機械的置換のみ。ログ出力追加は可 |

**注意**: 2.16（サイレント失敗の UX 改善）は Claude Code 担当。Codex は「ログを出すだけ」に留め、`st.warning` 追加は **しない**。

---

#### タスク 1.7: API Admin エンドポイント実装（3.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `api/routers/admin.py`<br>必要なら `agents/audit_logger.py` の **読み取り専用 helper 追加**は可 |
| **編集禁止** | `agents/base_agent.py`、その他エージェント本体 |
| **完了条件** | `GET /api/admin/agents` が監査ログから集計したリストを返す<br>`GET /api/admin/agents/{name}/stats` が詳細を返す |
| **実行テスト** | タスク 2.5 で作成する `tests/test_api_admin.py`<br>暫定: `curl http://localhost:8000/api/admin/agents \| jq` |
| **mock対象** | DB 接続、ファイル I/O（監査ログ読み込み） |
| **仕様変更可否** | レスポンス schema（`AgentStats` model）は維持。中身の集計ロジックは自由 |

**実装方針**:
1. `agents/audit_logger.py` のログ保存先（DB or `data/audit_logs/*.jsonl`）を確認
2. 全エージェントの `total_runs / success_count / error_count / avg_duration_seconds / last_run` を集計
3. fallback: 監査ログがない場合は空リストを返す（500エラーにしない）

---

### Tier 2: テスト整備

#### タスク 2.5: API テスト ×4（4h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `tests/test_api_pipeline.py` `tests/test_api_data.py` `tests/test_api_settings.py` `tests/test_api_admin.py`（全て新規） |
| **編集禁止** | `tests/conftest.py`, 既存テスト |
| **完了条件** | 各エンドポイントの正常系・異常系（404, 500）を1件以上カバー |
| **実行テスト** | `pytest tests/test_api_*.py -v` 全パス |
| **mock対象** | DB（`api_client` fixture が `mock_psycopg2` 内蔵）、外部 HTTP |
| **仕様変更可否** | API スキーマ変更を伴う場合は `CODEX_NOTES.md` に記載して相談 |

**fixture**: `api_client`（conftest.py 完備、TestClient + DBモック内蔵）

```python
@pytest.mark.unit
def test_get_agent_stats(api_client):
    resp = api_client.get("/api/admin/agents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

---

#### タスク 2.3: agents/ ユニットテスト ×15（12h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `tests/test_agents_*.py`（15ファイル新規） |
| **編集禁止** | `agents/*.py` 本体、`tests/conftest.py` |
| **完了条件** | 各エージェントの execute 正常系・dry_run・エラー系を最低3ケース<br>`pytest tests/test_agents_*.py -v` 全パス |
| **実行テスト** | `pytest tests/test_agents_*.py --cov=agents` |
| **mock対象** | DB、HTTP、ファイル I/O、subprocess（パイプライン起動） |
| **仕様変更可否** | エージェント本体の挙動変更は禁止。バグを見つけた場合は `CODEX_NOTES.md` に記載 |

**作成リスト**:

| # | ファイル | テスト対象 |
|---|---------|-----------|
| 1 | tests/test_agents_ingest.py | IngestAgent |
| 2 | tests/test_agents_normalizer.py | NormalizerAgent |
| 3 | tests/test_agents_feature.py | FeatureAgent |
| 4 | tests/test_agents_batch_inference.py | BatchInferenceAgent |
| 5 | tests/test_agents_trading.py | TradingAgent |
| 6 | tests/test_agents_market.py | MarketAgent.estimate_slippage |
| 7 | tests/test_agents_portfolio.py | PortfolioAgent |
| 8 | tests/test_agents_bankroll.py | BankrollAgent |
| 9 | tests/test_agents_anomaly.py | AnomalyAgent |
| 10 | tests/test_agents_monitor.py | MonitorAgent（auto_stop 閾値超え） |
| 11 | tests/test_agents_roi_tracker.py | RoiTrackerAgent |
| 12 | tests/test_agents_race_selector.py | RaceSelectorAgent |
| 13 | tests/test_agents_condition.py | ConditionAdjusterAgent |
| 14 | tests/test_agents_knowledge.py | KnowledgeAgent |
| 15 | tests/test_agents_auto_learn.py | AutoLearnAgent |

**雛形**:
```python
import pytest

@pytest.mark.unit
class TestIngestAgent:
    def test_dry_run(self, mock_psycopg2, agent_meta):
        from agents.ingest_agent import IngestAgent
        agent = IngestAgent(dry_run=True)
        result = agent.execute(agent_meta, {"source": "test"})
        assert result.ok is True

    def test_error_handling(self, mock_psycopg2, agent_meta, monkeypatch):
        from agents.ingest_agent import IngestAgent
        monkeypatch.setattr("psycopg2.connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DB down")))
        agent = IngestAgent(dry_run=False)
        result = agent.execute(agent_meta, {"source": "test"})
        assert result.ok is False
```

---

#### タスク 2.4: pipeline/ ユニットテスト ×8（8h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `tests/test_pipeline_*.py`（8ファイル新規） |
| **編集禁止** | `pipeline/*.py` 本体、`tests/conftest.py` |
| **完了条件** | `pytest tests/test_pipeline_*.py -v` 全パス |
| **実行テスト** | `pytest tests/test_pipeline_*.py --cov=pipeline` |
| **mock対象** | DB、ファイル I/O、subprocess、外部 API |
| **仕様変更可否** | パイプライン本体の挙動変更は禁止 |

| # | ファイル | テスト対象 |
|---|---------|-----------|
| 1 | tests/test_pipeline_ev_engine.py | ev_engine_10: EV閾値・boost適用 |
| 2 | tests/test_pipeline_kelly.py | kelly_bankroll_09: Kelly計算 |
| 3 | tests/test_pipeline_predict.py | predict_04: MIN_ODDS_RAWフィルタ |
| 4 | tests/test_pipeline_portfolio_opt.py | portfolio_opt_11: 最適化 |
| 5 | tests/test_pipeline_roi_tracker.py | roi_tracker_12: 集計 |
| 6 | tests/test_pipeline_race_selector.py | race_selector_31: スコアリング |
| 7 | tests/test_pipeline_ticket_optimizer.py | ticket_optimizer_30: Harville確率 |
| 8 | tests/test_pipeline_bet_portfolio.py | bet_portfolio_29: 期待対数成長 |

**重要**: EV計算・Kelly計算・確率変換は **mock しない**（業務ロジック本体）。

---

#### タスク 2.7: カバレッジ60%ゲート（0.5h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `.github/workflows/ci.yml`, `pyproject.toml` |
| **編集禁止** | テストコード |
| **完了条件** | CI で `pytest --cov-fail-under=60` がパス |
| **実行テスト** | `pytest --cov=agents --cov=api --cov=pipeline --cov-fail-under=60` |
| **mock対象** | N/A |
| **仕様変更可否** | 60% 閾値は固定。test 種類追加（cov.xml 出力など）は可 |

---

### Tier 2: 運用品質

#### タスク 2.13: tenacity リトライ（3h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `agents/odds_scraper_agent.py`, `pipeline/social_bot_27.py`, `pipeline/claude_comment_06.py`, `pipeline/note_07.py` |
| **編集禁止** | `agents/base_agent.py`, `scheduler.py` |
| **完了条件** | 各ネットワーク呼び出しに `@retry` デコレータ適用<br>失敗時に最大3回リトライ・指数バックオフ |
| **実行テスト** | 該当エージェント/モジュールの test_agents_*.py で「3回失敗→ok=False」を検証 |
| **mock対象** | HTTP, Playwright, Anthropic API |
| **仕様変更可否** | リトライ回数・wait は調整可（最大3回・最大30秒は守る） |

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def post_to_x(message: str) -> bool:
    ...
```

---

#### タスク 2.14: print → logging 統一（3h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `pipeline/*.py`（除外: `model_train_03.py`, `dashboard_15.py`, `dashboard_v4/`）<br>`run_all.py` |
| **編集禁止** | `pipeline/model_train_03.py`, `pipeline/dashboard_15.py`, `pipeline/dashboard_v4/`, `scheduler.py` |
| **完了条件** | `grep -rn "print(" pipeline/ \| grep -v dashboard \| grep -v model_train_03` がほぼゼロ（テンプレート出力など意図的な print は除外） |
| **実行テスト** | `python -c "import pipeline.<module>"` 各モジュールでエラーなし |
| **mock対象** | N/A |
| **仕様変更可否** | logger 名は `logging.getLogger(__name__)` 統一。出力フォーマットは統一しなくて可 |

---

#### タスク 2.15: SNS dead-letter（1h）

| 項目 | 内容 |
|---|---|
| **編集許可** | `pipeline/social_bot_27.py` のみ |
| **編集禁止** | 他 |
| **完了条件** | SNS 投稿失敗時に `data/sns_dead_letter.jsonl` に追記される<br>テストで失敗ケースを再現して JSONL が書かれることを検証 |
| **実行テスト** | `tests/test_pipeline_social_bot.py`（新規）または既存 `test_pipeline_*.py` 内 |
| **mock対象** | requests, X/Discord/Telegram/LINE クライアント |
| **仕様変更可否** | dead-letter のスキーマは下記を維持。追加フィールド可 |

```json
{
  "channel": "X",
  "message": "...",
  "error": "ConnectionError: ...",
  "timestamp": "2026-05-08T12:34:56"
}
```

---

## 5. AGENT_HANDOFF.md 運用

毎セッション開始時に `AGENT_HANDOFF.md` を読み、終了時に **必ず更新**する。
詳細は `AGENT_HANDOFF.md` 参照。

## 6. ブロック・相談先

`CODEX_NOTES.md` を新規作成して以下を記入:

- API スキーマ変更を伴う実装が必要になった
- エージェント本体のバグを発見した
- ファイル排他マップに記載のないファイルを触る必要が出た
- テストが既存ロジックの不整合を露呈した

Claude Code は次回起動時に確認します。

---

## 7. 完了チェックリスト

```bash
# 全タスク完了時に CI で全部通ることを確認
pytest tests/ -v --cov=agents --cov=api --cov=pipeline --cov-fail-under=60
detect-secrets scan --baseline .secrets.baseline
flake8 --max-line-length=120 --ignore=E203,W503,E501 agents/ api/
gh workflow run ci.yml
```

最終 PR タイトル: `[Codex] Tier 1+2 残タスク完了（44h 分）`
