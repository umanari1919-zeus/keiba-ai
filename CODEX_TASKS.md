# Codex 作業指示書 — うまなり地蔵AI Tier 1+2 完成

## 前提

- **ブランチ**: `claude/gifted-kirch-a032d5`（worktree: `D:\keiba_ai\.claude\worktrees\gifted-kirch-a032d5`）
- **連携方式**: Claude Code と並列作業。**互いに同じファイルを触らない**
- **目標**: Tier 1（安全運用）+ Tier 2（本格運用）= 残り46h を Codex 担当
- **Claude Code 担当分は完了済**（5コミット、36テスト全パス）

## ⚠️ 絶対遵守ルール

### Codex が **触ってはいけない** ファイル（Claude Code 専有）

```
scheduler.py                    # 1.9 完了済 → 1.11 のログ統一のみ Codex 担当
setup_pipeline_v2.py            # 1.5+1.6 完了
pipeline_v2/00_orchestrator.py  # 1.6 完了
tests/conftest.py               # 2.2 完了 — Codex は import するだけ
tests/__init__.py               # 完了
tests/test_base_agent.py        # サンプル — 上書き禁止
tests/test_integration.py       # 2.6 完了 — 上書き禁止
tests/test_mlflow_register.py   # 完了
mlflow_register.py              # 2.10 完了
pipeline/model_train_03.py      # 2.11 完了
pipeline/dashboard_v4/app.py    # 2.12 完了
pipeline/dashboard_v4/pages/08_model_comparison.py  # 2.12 完了
nvidia_test.py                  # 1.1 完了
.env.template                   # 完了
```

### Codex 専有ファイル（Claude Code は触らない）

```
.pre-commit-config.yaml         # 新規作成
requirements.txt                # 1.4 バージョン固定
api/routers/admin.py            # 1.7 Admin 実装
api/main.py                     # 1.10 CORS
pipeline/dashboard_v4/pages/*.py（08_model_comparison.py 以外）  # 1.8 bare except
pyproject.toml                  # 新規作成
tests/test_agents_*.py          # 新規 ×15
tests/test_pipeline_*.py        # 新規 ×8
tests/test_api_*.py             # 新規 ×4
.github/workflows/ci.yml        # 新規
pipeline/social_bot_27.py       # 2.15
pipeline/*.py（model_train_03.py, dashboard_15.py 除く）  # 2.14 print→logging
```

---

## Tier 1 残タスク（Codex 担当 9.5h）

### 1.3 pre-commit + detect-secrets 導入（1h）

**新規作成: `.pre-commit-config.yaml`**

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
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=120', '--ignore=E203,W503,E501']
```

**完了基準**:
```bash
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
pre-commit install
pre-commit run --all-files  # ゼロ違反
```

---

### 1.4 requirements.txt バージョン固定（0.5h）

**現状**: `pandas>=2.0`（範囲指定）→ **目標**: `pandas==2.2.3`（厳密固定）

```bash
pip freeze | grep -iE "psycopg2|pandas|numpy|lightgbm|xgboost|catboost|sklearn|fastapi|streamlit|plotly|httpx|playwright|anthropic|mlflow|optuna|shap|pyarrow|sqlalchemy|pydantic|uvicorn|schedule|python-dotenv" > requirements.lock
```

`requirements.txt` の `>=` を `==` に置換（コメント・オプションパッケージは現状維持）。

---

### 1.7 API Admin エンドポイント実装（3.5h）

**対象**: `api/routers/admin.py:97-107` および `:122-130`

現状は `TODO` で空リスト返却。`agents/audit_logger.py` の監査ログから集計する。

**実装方針**:
1. `audit_logger.py` のログ保存先（DB または `data/audit_logs/*.jsonl`）を確認
2. `get_agent_stats()`: 全エージェントの total_runs / success / error / avg_duration を集計
3. `get_agent_detail_stats(agent_name)`: 特定エージェントの最新50件履歴

**完了基準**:
```bash
curl http://localhost:8000/api/admin/agents | jq '.[0]'
# {"agent_name": "ingest-agent", "total_runs": 42, "success_count": 41, ...}
```

---

### 1.8 bare except 修正（2h）

**対象**: `pipeline/dashboard_v4/pages/*.py` 等の19箇所

```bash
grep -rn "except:" pipeline/dashboard_v4/pages/ pipeline/dashboard_15.py
```

各 `except:` を `except Exception as e:` に変換し、必要に応じて `logger.warning(e)` を追加。
**注意**: `dashboard_v4/pages/08_model_comparison.py` は Claude Code 専有。触らない。

---

### 1.10 CORS 制限（0.5h）

**対象**: `api/main.py:21`

```python
# 変更前
allow_origins=["*"],

# 変更後
allow_origins=[
    "http://localhost:8501",  # Streamlit
    "http://localhost:3000",  # 開発用フロント
    "http://127.0.0.1:8501",
    "http://127.0.0.1:3000",
],
```

---

### 1.11 scheduler.py ログ構造化（1.5h）

**⚠️ Claude Code 1.9 完了後に着手**（既に完了済 → すぐ着手可能）

**対象**: `scheduler.py` の `print()` → `logging` 統一

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")
```

`print(...)` を `log.info(...)` / `log.warning(...)` / `log.error(...)` に置換。

---

## Tier 2 残タスク（Codex 担当 36.5h）

### 2.1 pyproject.toml + pytest 設定（0.5h）

**新規作成**:

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
addopts = "-v --strict-markers"

[tool.coverage.run]
source = ["agents", "api", "pipeline"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 60
show_missing = true
```

---

### 2.3 agents/ ユニットテスト ×15（12h）

**前提**: `tests/conftest.py` に共通フィクスチャ完備済（Claude Code 担当）

**利用可能 fixture**:
- `mock_psycopg2`: psycopg2.connect をモック → DB 接続不要
- `agent_meta`: 再現可能な AgentMeta（trace_id 固定）
- `agent_meta_factory`: 呼ぶたびに新 AgentMeta
- `DummyAgent`: BaseAgent 継承の最小エージェント
- `sample_predictions`: 3件のサンプル予測リスト
- `sample_csv_path` / `sample_ev_csv_path`: テスト用 CSV
- `sample_bankroll_json`: bankroll.json
- `sample_model_pkl`: ダミー model_v8.pkl

**サンプル参照**: `tests/test_base_agent.py`, `tests/test_integration.py`

**作成対象（15ファイル）**:

| # | ファイル | テスト対象 |
|---|---------|-----------|
| 1 | tests/test_agents_ingest.py | IngestAgent: 正常系・dry_run・エラー時 |
| 2 | tests/test_agents_normalizer.py | NormalizerAgent: mismatch_rate計算 |
| 3 | tests/test_agents_feature.py | FeatureAgent: feature_set_id生成 |
| 4 | tests/test_agents_batch_inference.py | BatchInferenceAgent: predictions出力 |
| 5 | tests/test_agents_trading.py | TradingAgent: paper_trading・候補生成 |
| 6 | tests/test_agents_market.py | MarketAgent: estimate_slippage 境界値 |
| 7 | tests/test_agents_portfolio.py | PortfolioAgent: 空候補・summary集計 |
| 8 | tests/test_agents_bankroll.py | BankrollAgent: drawdown・stop_betting |
| 9 | tests/test_agents_anomaly.py | AnomalyAgent: critical検出・auto_stop |
| 10 | tests/test_agents_monitor.py | MonitorAgent: 閾値超過時のauto_stop |
| 11 | tests/test_agents_roi_tracker.py | RoiTrackerAgent: daily_roi算出 |
| 12 | tests/test_agents_race_selector.py | RaceSelectorAgent: grade S~C分類 |
| 13 | tests/test_agents_condition.py | ConditionAdjusterAgent: 係数適用 |
| 14 | tests/test_agents_knowledge.py | KnowledgeAgent: active_count |
| 15 | tests/test_agents_auto_learn.py | AutoLearnAgent: retrain_triggered判定 |

**雛形**:
```python
import pytest

@pytest.mark.unit
class TestIngestAgent:
    def test_execute_success(self, mock_psycopg2, agent_meta, sample_csv_path):
        from agents.ingest_agent import IngestAgent
        agent = IngestAgent(dry_run=True)
        result = agent.execute(agent_meta, {"source": "test"})
        assert result.ok is True
```

---

### 2.4 pipeline/ ユニットテスト ×8（8h）

| # | ファイル | テスト対象 |
|---|---------|-----------|
| 1 | tests/test_pipeline_ev_engine.py | ev_engine_10: 閾値・boost適用 |
| 2 | tests/test_pipeline_kelly.py | kelly_bankroll_09: Kelly計算 |
| 3 | tests/test_pipeline_predict.py | predict_04: MIN_ODDS_RAWフィルタ |
| 4 | tests/test_pipeline_portfolio_opt.py | portfolio_opt_11: 最適化 |
| 5 | tests/test_pipeline_roi_tracker.py | roi_tracker_12: 集計 |
| 6 | tests/test_pipeline_race_selector.py | race_selector_31: スコアリング |
| 7 | tests/test_pipeline_ticket_optimizer.py | ticket_optimizer_30: Harville確率 |
| 8 | tests/test_pipeline_bet_portfolio.py | bet_portfolio_29: 期待対数成長 |

---

### 2.5 API ユニットテスト ×4（4h）

**fixture**: `api_client`（conftest.py に完備、TestClient + DBモック）

| # | ファイル | エンドポイント |
|---|---------|---------------|
| 1 | tests/test_api_pipeline.py | /api/pipeline/* |
| 2 | tests/test_api_data.py | /api/data/* |
| 3 | tests/test_api_settings.py | /api/settings/* |
| 4 | tests/test_api_admin.py | /api/admin/* |

**雛形**:
```python
def test_get_agent_stats(api_client):
    resp = api_client.get("/api/admin/agents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

---

### 2.7 カバレッジ60%ゲート（0.5h）

`pyproject.toml` の `[tool.coverage.report]` に `fail_under = 60` を設定（2.1 で実施済み）。

**実行**:
```bash
pytest --cov=agents --cov=api --cov=pipeline --cov-report=term --cov-fail-under=60
```

---

### 2.8 + 2.9 GitHub Actions CI（3h）

**新規**: `.github/workflows/ci.yml`

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
      - run: pip install -r requirements.txt pytest pytest-cov
      - run: pytest --cov=agents --cov=api --cov-fail-under=60

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install detect-secrets bandit
      - run: detect-secrets scan --baseline .secrets.baseline
      - run: bandit -r agents/ api/ pipeline/ -ll

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install flake8
      - run: flake8 --max-line-length=120 --ignore=E203,W503,E501 agents/ api/
```

---

### 2.13 tenacity リトライ（3h）

**対象**: ネットワーク呼び出し（HTTP・DB・LLM API）

```bash
pip install tenacity
```

**対象ファイル**:
- `agents/odds_scraper_agent.py`（Playwright失敗時）
- `pipeline/social_bot_27.py`（X/Discord/Telegram投稿）
- `pipeline/claude_comment_06.py`（Anthropic API）
- `pipeline/note_07.py`（note.com）

**雛形**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def post_to_x(message: str) -> bool:
    # 既存実装
    ...
```

---

### 2.14 print → logging 統一（3h）

**対象**: `pipeline/*.py`, `run_all.py` の `print()` を `logging` に置換。

**除外**: `model_train_03.py`（Claude Code 専有）, `dashboard_15.py`（巨大モノリス、別タスク）

**統一フォーマット**:
```python
import logging
log = logging.getLogger(__name__)
log.info(...)
```

---

### 2.15 SNS dead-letter（1h）

**対象**: `pipeline/social_bot_27.py`

投稿失敗時に `data/sns_dead_letter.jsonl` に追記:

```python
import json
from datetime import datetime

def _save_dead_letter(channel: str, message: str, error: str) -> None:
    record = {
        "channel": channel,
        "message": message,
        "error": str(error),
        "timestamp": datetime.now().isoformat(),
    }
    with open("data/sns_dead_letter.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

各SNS投稿関数の `except` ブロックで呼び出す。

---

### 2.16 dashboard v4 サイレント失敗修正（1.5h）

**対象**: `pipeline/dashboard_v4/pages/*.py`（08_model_comparison.py を除く）

bare except 修正（1.8 と一部重複）+ ユーザーに見える `st.warning(...)` を追加。

---

## 進捗確認方法

```bash
# テスト実行
cd D:\keiba_ai\.claude\worktrees\gifted-kirch-a032d5
pytest tests/ -v

# カバレッジ
pytest --cov=agents --cov=api --cov-fail-under=60

# シークレットスキャン
detect-secrets scan --baseline .secrets.baseline

# CI ローカル実行（要 act）
act -j test
```

## Claude Code との連携

- **質問・衝突相談**: ブランチ上に `CODEX_NOTES.md` を新規作成して記入 → Claude Code が次回起動時に確認
- **完了通知**: 各タスク完了時にコミットメッセージ先頭に `[Codex]` を付与
- **テスト追加時**: 必ず `tests/conftest.py` のフィクスチャを再利用すること（重複定義禁止）

## 参考資料

- 全体計画: `C:\Users\uchih\.claude\plans\purring-tinkering-music.md`
- アーキテクチャ: `CLAUDE.md`
- 完了済 Claude Code コミット: `git log --oneline | head -5`
