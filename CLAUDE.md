# CLAUDE.md

**うまなり地蔵AI** — 高オッズ穴馬（30倍以上）をアンサンブルMLで予測し、X・note.com へ自動投稿する競馬予想システム。

## クイックスタート

```bash
python run_all.py --morning               # 朝の予想モード v2（並列実行・約3分）← 毎朝これ
python run_all.py --morning --skip-social # 朝の予想モード（SNS投稿なし）
python run_all.py --results               # 夕方モード: 確定結果取得 → roi_tracker 更新
python run_all.py --skip-fetch --skip-train   # 既存モデルで予想のみ
python run_all.py                              # 全ステップ（DB取得 → 学習 → 投稿）
python scheduler.py                            # 土日 08:00 自動実行（--morning 使用）
streamlit run pipeline/dashboard_15.py        # ダッシュボード http://localhost:8501
```

`run_all.py` のフラグ: `--morning` `--results` `--evening` `--skip-fetch` `--skip-train` `--skip-adv` `--skip-nn` `--skip-rl` `--skip-social` `--full-optuna`

### 買い目シート
```bash
python pipeline/morning_report.py              # 今日の買い目シート表示・保存
python pipeline/morning_report.py 20260426     # 指定日
python pipeline/morning_report.py --no-ollama  # Ollama解説スキップ
```
出力先: `reports/morning_{date}.txt`

## パイプライン構成（pipeline/）

### PHASE 1 — データ・特徴量
| ファイル | 役割 | 出力 |
|----------|------|------|
| data_fetch_01.py | PostgreSQL → CSV | keiba_data.csv |
| feature_eng_02.py | 97特徴量生成 | keiba_data_features.csv |
| feature_advanced_19.py | 高度特徴量（ペース・展開） | keiba_data_features.csv に追記 |
| pace_training_analysis_20.py | ペース・調教分析 | — |
| jockey_trainer_analysis_21.py | 騎手・調教師・3代ニックス | — |
| statistical_tools_23.py | 統計分析・クラスタリング | — |
| training_analysis_37.py | 調教マルチセッション集計（60日・速度Zスコア・トレンド） | keiba_data_features.csv に追記 |
| trainer_analysis_38.py | 調教師特性（会場×距離別勝率・好調度スコア） | keiba_data_features.csv に追記 |
| debut_analysis_39.py | **新馬戦強化**（騎手/調教師/父馬の新馬戦勝率・debut_score） | keiba_data_features.csv に追記 |
| shogai_analysis_40.py | **障害戦強化**（騎手/調教師障害勝率・馬の経験数・shogai_score） | keiba_data_features.csv に追記 |

### PHASE 2 — 異常検知・自動学習
| ファイル | 役割 |
|----------|------|
| anomaly_detect_16.py | 精度劣化・八百長兆候検知 |
| bankroll_advanced_24.py | ドローダウン管理・Kelly最適化 |
| auto_learn_13.py | 精度低下時の自動再学習トリガ |

### PHASE 3 — モデル学習
| ファイル | 役割 | 出力 |
|----------|------|------|
| model_train_03.py | LGB+XGB+CB アンサンブル | model_v8.pkl |
| optuna_advanced_25.py | Optunaハイパーパラメータ最適化 | — |
| nn_stacking_22.py | Neural Network + Stacking | — |
| rl_strategy_26.py | 強化学習ベットサイジング | rl_model.zip |
| shap_analysis.py | SHAP可視化 11種（LGB/XGB） | shap_output/*.png |

### PHASE 4 — 予想・資金管理・馬券戦略
| ファイル | 役割 | 出力 |
|----------|------|------|
| predict_04.py | 予想生成（穴馬: >=30倍・MIN_ODDS_RAW=300） | simulation_{year}.csv |
| ev_engine_10.py | 期待値計算（race_type別閾値・knowledge_base boost） | ev_analysis_{year}.csv |
| portfolio_opt_11.py | 馬券ポートフォリオ最適化 | portfolio_{year}.csv |
| kelly_bankroll_09.py | Kelly基準資金管理 | data/bankroll.json |
| race_selector_31.py | レース価値スコアリング Grade S〜C | data/race_ranking_{year}.csv |
| ticket_optimizer_30.py | Harville確率推定・馬券種自動選択 | data/ticket_recommendations_{year}.json |
| bet_portfolio_29.py | 期待対数成長最適化 多点買い | data/bet_portfolio_{year}.json |
| backtest_engine_32.py | EVグリッドサーチ バックテスト | data/backtest_summary_{year}.json |
| backtest_walkforward_35.py | 時系列OOS検証（パージ幅2週） | data/walkforward_result.json |
| condition_adjuster_34.py | 競馬場×距離×季節 ベット係数 | data/condition_coefficients.json |
| odds_monitor_33.py | SHARP/STEAM/DRIFT 変動検知（過去データ分析） | data/odds_monitor_config.json |
| odds_scraper_36.py | **Playwright リアルタイムオッズ取得**（セッション不要） | data/odds_snapshot_YYYYMMDD.json |
| roi_tracker_12.py | 日次/週次/月次 回収率追跡 | — |
| knowledge_curator_41.py | **知識ベース自動進化**（Ollama/Haiku抽出→EV boost/特徴量反映） | data/knowledge_base/ |

### PHASE 5 — 発信
| ファイル | 役割 |
|----------|------|
| claude_comment_06.py | Ollama優先 + Haiku prompt caching コメント生成 |
| note_07.py | Ollama全文生成 note.com 記事 |
| notify_08.py | パイプラインレポート通知 |
| multi_agent_v2_28.py | **v3: 14エージェント協調**（7並列分析 → Supervisor(json) → Risk → Commentary(japanese) → Publisher） |
| social_bot_27.py | X / Discord / Telegram / LINE 一括配信 |
| dashboard_15.py | Streamlit 8タブ UI |

## モデル (model_v8.pkl)

```
LightGBM 50% + XGBoost 30% + CatBoost 20%
特徴量: 97列（オッズ・人気は除外 — データリーク防止）
予測後フィルタ: EV≥15% かつ オッズ≥10倍
```

## 重要定数（変更時は全ファイル統一）

| 定数 | 値 | 定義ファイル |
|------|-----|-------------|
| EV_THRESHOLD | **0.15** | ev_engine_10, multi_agent_v2_28, condition_adjuster_34, odds_monitor_33 |
| EV_THRESHOLDS_BY_TYPE | debut/shogai: 0.10, handicap: 0.20, default: 0.15 | ev_engine_10 |
| KELLY_FRACTION | **0.10** | kelly_bankroll_09, bet_portfolio_29, ticket_optimizer_30, backtest_engine_32, backtest_walkforward_35 |
| MIN_ODDS | 10.0 | ev_engine_10, multi_agent_v2_28 |
| MIN_ODDS_RAW | 100 (=10倍×10) | predict_04 (tansho_odds x10格納形式) |
| ANABA_ODDS_RAW | 300 (=30倍×10) | predict_04 穴馬定義 |

## EV boost（knowledge_base）

`data/knowledge_base/ev_boost_map.json` に race_code または `{chichi}_{jyo}` キーで boost 係数が格納される。
knowledge_curator_41.py が自動生成・更新。ev_engine_10.py が予測後に乗算適用。

## データベース

```
postgresql://postgres:trust@localhost:5433/mykeibadb
主テーブル: race_results, horse_info, jockey_stats
```

詳細は `memory/project_db.md` を参照。

## --morning v2 並列化マップ

```
P1 (serial) : DB同期 → shutsuba → data_fetch → feature_eng → adv_features(×7)
P2 (parallel): anomaly ‖ bankroll   → auto_learn
P4a (serial) : predict
P4b (parallel x4): ev ‖ race_sel ‖ backtest ‖ walkfwd ‖ cond_adj ‖ odds_mon ‖ odds_scraper
P4c (parallel x3): portfolio ‖ ticket_opt ‖ bet_portfolio
P4d (serial) : multi_agent → knowledge_curator
P5  (parallel x4): comment ‖ note ‖ morning_report ‖ roi_report
                  + ollama_analyst ‖ llm_predictor
```

## Ollama ローカルLLM

コメント生成・予想解説を Claude API 不要でローカル実行できる。

```bash
ollama serve                               # 起動（常駐させておく）
python pipeline/ollama_comment.py           # コメント生成テスト
python pipeline/ollama_comment.py --models  # インストール済みモデル一覧
python pipeline/ollama_analyst.py           # 解説記事生成テスト
```

### RAM別推奨モデル

| 空きRAM | コマンド | 用途 |
|---------|---------|------|
| ~1GB | `ollama pull qwen2.5:1.5b` | fast（バッチ最速） |
| ~1GB | `ollama pull deepseek-r1:1.5b` | json（推論最軽量） |
| ~2GB | `ollama pull qwen2.5:3b` | japanese（バランス型）★推奨 |
| ~5GB | `ollama pull qwen2.5:7b` | japanese（高品質） |
| ~5GB | `ollama pull aya-expanse:8b` | japanese（多言語特化） |
| ~5GB | `ollama pull deepseek-r1:7b` | json（構造出力最強） |

### タスク別モデルプロファイル

| タスク | alias | 用途 | 推奨モデル |
|--------|-------|------|-----------|
| `japanese` | `comment` | X投稿・note記事・morning_report解説 | qwen2.5:7b / aya-expanse:8b |
| `json` | `analysis` | Supervisor判断・知見抽出・knowledge_curator | deepseek-r1:7b / phi4-mini:3.8b |
| `fast` | `batch` | 並列バッチ処理 | qwen2.5:1.5b / deepseek-r1:1.5b |

### Ollama 統合箇所（全6ファイル）

| モジュール | 用途 | task= |
|----------|------|-------|
| claude_comment_06.py | 馬1頭のX投稿コメント | japanese |
| multi_agent_v2_28.py | SupervisorAgent 戦略判断 | json |
| multi_agent_v2_28.py | Commentary / Publisher 冒頭文 | japanese |
| note_07.py | note.com 記事（イントロ/解説/締め） | japanese |
| llm_predictor.py | SHAP解説付き予想コメント | japanese |
| knowledge_curator_41.py | 知見抽出・重複判定・歴史的知見抽出 | json |
| morning_report.py | 1行ピック解説 | japanese |
| ollama_analyst.py | note.com 草稿生成 | japanese |

**優先順位**: Ollama（無料・ローカル） → Claude Haiku API（有料） → テンプレート

## 共通設定

`pipeline/config.py` に全定数を集約（DB_URL・パス・EV_THRESHOLD・KELLY_FRACTION など）。
新しいモジュールは必ず `from pipeline.config import ...` で参照すること。

## smoke test

```bash
python smoke_test.py   # 21項目チェック（DB・import・CSV・モデルファイル）
```

## 既知の問題・注意事項

- `keiba_data_features.csv` 339766行目が破損 → 全 `read_csv` に `on_bad_lines='skip'` 適用済み（`config.CSV_READ_OPTS` を使うと安全）
- CatBoost の `shap.TreeExplainer` はセグフォルト → `get_feature_importance()` で代替（04_cb_summary.png）
- `condition_adjuster_34.py` は `win_probability` 列が必要 → model_train_03 実行後に有効化
- `NETKEIBA_SESSION_ID` 不要 → `odds_scraper_36.py` が Playwright で直接取得（セッション不要）
- advanced features (steps 3-6e) は CSV書き込み競合のため並列化不可 → 順次実行
- `python-dotenv` / `playwright` / `anthropic` / `langgraph` / `stable-baselines3` は未インストール → オプション機能（`requirements.txt` を参照）
- PyArrow の RE2 は `　` 正規表現非対応 → `re.sub(r"[\s　]+", ...)` を使用（修正済み）
- `woodchip_chokyo` に `time_gokei_1furlong` 列なし → `laptime_1furlong` を使用（修正済み）
- `race_shosai` に `grade` 列なし → `grade_code` を使用（修正済み）
- `mykeibadb.exe` は `cwd=MYKEIBADB_DIR` と `stdin=DEVNULL` が必要（修正済み）

## データリーク注意

`feature_eng_02.py` の `kishu_win_rate`・`chokyoshi_win_rate`・`kishu_keibajo_win_rate` は
expanding window（shift+cumsum）で計算するよう修正済み。
全データ統計での計算は未来データの混入（リーク）になるため使用禁止。

## ウォークフォワード検証結果（最新）

| 年 | ROI | 的中率 | 最大DD |
|----|-----|--------|--------|
| 2025 | +570.7% | 12.6% | 32.2% |
| 2026 | +1,111.5% | 17.5% | 13.4% |
| 平均 | **+841.1%** | 15.1% | 22.8% |

判定: **汎化性能良好 ✅ 実運用可能レベル**

## 廃止ファイル

`model_v2~v7.pkl`（cleanup_old_models.bat で削除可） / `feature_engineering.py` / `multi_agent_14.py`（→ multi_agent_v2_28.py に移行）
