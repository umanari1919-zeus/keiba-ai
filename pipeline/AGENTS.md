# pipeline/ AGENTS.md

このディレクトリは、うまなり地蔵AIのデータ取得、特徴量生成、学習、予測、期待値計算、資金管理、発信を担う中核です。変更時は、予想精度より先にデータリーク防止と再現性を守ってください。

## 最優先ルール

- オッズ・人気・払戻・確定着順・未来情報をモデル特徴量に入れない。
- オッズは `predict_proba` 後のEV計算、Kelly、買い目、レポート表示でのみ使用する。
- 新しい定数は `pipeline/config.py` に集約し、各スクリプトで直書きしない。
- CSV読み込みは `CSV_READ_OPTS` または `on_bad_lines='skip'` を使う。
- advanced features はCSV書き込み競合があるため並列化しない。
- CatBoostのSHAPは `shap.TreeExplainer` を使わず、`get_feature_importance()` を使う。

## 重要定数

- `EV_THRESHOLD = 0.15`
- `KELLY_FRACTION = 0.10`
- `MIN_ODDS = 10.0`
- `ANABA_ODDS = 30.0` または raw odds `300`

これらを変更する場合は、バックテストと運用意図を確認してから進めてください。

## 推奨確認コマンド

```bash
python3 run_all.py --source-sanity
python3 tools/verify_integrity.py
python3 run_all.py --runtime-check
python3 canary_run.py
```

日次運用前は軽い確認から始めます。

```bash
python3 run_all.py --v2 --preflight-only
python3 run_all.py --v2
python3 pipeline/morning_report.py
```

## 発信まわり

- Xやnote.comへの投稿は、ユーザーが明示した場合だけライブ投稿する。
- 投稿文は断定しすぎず、根拠、妙味、リスクを短く含める。
- LLMの優先順位は、Ollama、NVIDIA API、Claude Haiku、テンプレートの順に従う。

## 変更時の見方

- `feature_*`, `model_train_03.py`, `predict_04.py`, `validation.py`, `backtest_*` はリーク監査を必ず行う。
- `ev_engine_10.py`, `kelly_bankroll_09.py`, `ticket_optimizer_30.py`, `bet_portfolio_29.py` はオッズ利用が自然だが、モデル入力へ逆流させない。
- `morning_report.py`, `claude_comment_06.py`, `note_07.py`, `social_bot_27.py` は発信内容と投稿安全性を確認する。
