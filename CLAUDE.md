# CLAUDE.md

**うまなり地蔵AI** — 高オッズ穴馬（30倍以上）をアンサンブルMLで予測し、X・note.comへ自動投稿する競馬予想システム。

## 実行

```bash
python run_all.py        # 全9ステップ自動実行
python scheduler.py      # 土日08:00自動スケジューラ
streamlit run pipeline/dashboard_15.py  # ダッシュボード
```

## パイプライン構成（pipeline/）

| ファイル | 役割 |
|----------|------|
| data_fetch_01.py | PostgreSQL → keiba_data.csv |
| feature_eng_02.py | 60+特徴量 → keiba_data_features.csv |
| model_train_03.py | アンサンブル学習 → model_v8.pkl |
| predict_04.py | 予想生成 → simulation_2025.csv |
| claude_comment_06.py | Haiku API + prompt caching でコメント生成 |
| kelly_bankroll_09.py | ケリー基準資金管理 |
| ev_engine_10.py | 期待値計算・レース選別 |
| portfolio_opt_11.py | 馬券ポートフォリオ最適化 |
| roi_tracker_12.py | 日次/週次/月次 回収率追跡 |
| auto_learn_13.py | 精度低下時の自動再学習 |
| multi_agent_14.py | LangGraph 5エージェント協調 |
| dashboard_15.py | Streamlit UI（http://localhost:8501） |
| anomaly_detect_16.py | 異常検知（精度劣化・八百長兆候） |

## モデル (model_v8.pkl)

LightGBM 50% + XGBoost 30% + CatBoost 20%。オッズ・人気は**特徴量から除外**（データリーク防止）、予測後フィルタとしてのみ使用。DB: `postgresql://postgres:trust@localhost:5433/mykeibadb`

## 注意

- DB詳細・環境変数一覧は memory/ を参照
- `requirements.txt` なし（手動インストール要）
- 廃止: model_v2〜v7.pkl, feature_engineering.py
