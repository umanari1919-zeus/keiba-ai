# うまなり地蔵AI — OpenCode エージェント設定

## プロジェクト概要
高オッズ穴馬（30倍以上）をアンサンブルMLで予測し、X・note.comへ自動投稿する競馬予想システム。

## 重要なルール
- **EV_THRESHOLD = 0.15**（期待値15%以上が推奨買い目）
- **KELLY_FRACTION = 0.10**（資金の10%を上限にベット）
- **MIN_ODDS = 10.0**（10倍未満は対象外）
- **ANABA_ODDS = 30.0**（30倍以上が穴馬定義）
- オッズ・人気は特徴量に使用禁止（データリーク防止）

## ディレクトリ構成
```
D:\keiba_ai\
├── pipeline/          # メインパイプライン（40+スクリプト）
│   ├── config.py      # 全定数の定義元（必ずここから import）
│   ├── claude_comment_06.py   # コメント生成
│   └── ...
├── pipeline_v2/       # v2パイプライン（推奨）
│   └── 00_orchestrator.py    # DAG実行エンジン
├── agents/            # 30エージェント（BaseAgent継承）
├── data/              # JSON・バックテスト結果
├── nvidia_comment.py  # NVIDIA APIコメント生成ツール
└── .env               # APIキー管理
```

## よく使うコマンド
```bash
# 日次パイプライン（毎朝）
python run_all.py --v2

# 週次学習（毎週日曜）
python run_all.py --v2-weekly

# 今日の買い目
python pipeline/morning_report.py

# コメント生成（NVIDIA API）
python nvidia_comment.py --bamei 馬名 --odds 25.5 --kishu 武豊

# パイプライン検証
python canary_run.py
```

## DB接続
```
postgresql://postgres:trust@localhost:5433/mykeibadb
主テーブル: race_results, horse_info, jockey_stats
```

## コーディング規則
- 新しい定数は必ず `pipeline/config.py` に追加する
- CSV読み込みは `on_bad_lines='skip'` を使用（339766行目が破損）
- 新エージェントは `agents/base_agent.py` の `BaseAgent` を継承
- Ollama → NVIDIA API → Claude Haiku → テンプレートの優先順位でLLMを使う

## 注意事項
- CatBoostのshap.TreeExplainerはセグフォルトする → get_feature_importance()を使う
- advanced features は並列化不可（CSV書き込み競合）
- `python-dotenv` で `.env` を読み込む
