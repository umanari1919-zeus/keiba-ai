"""
うまなり地蔵AI Dashboard v4
Streamlit マルチページアプリケーション（8ページ）

起動: streamlit run pipeline/dashboard_v4/app.py
"""
import streamlit as st
from datetime import datetime

# ── ページ設定 ────────────────────────────────────────
st.set_page_config(
    page_title="うまなり地蔵AI Dashboard v4",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── テーマ適用 ────────────────────────────────────────
try:
    from utils.theme import apply_theme
    apply_theme()
except ImportError:
    pass

# ── ページ定義 ────────────────────────────────────────
PAGES = {
    "🏠 ホーム": "pages/00_home.py",
    "📈 成績サマリー": "pages/01_performance.py",
    "💰 資金管理": "pages/02_portfolio.py",
    "🔬 詳細分析": "pages/03_analysis.py",
    "🧪 バックテスト": "pages/04_backtest.py",
    "⚙️ 設定": "pages/05_settings.py",
    "👨‍💼 管理画面": "pages/06_admin.py",
    "🏇 出走表": "pages/07_race_entries.py",
}

# ── メイン画面 ────────────────────────────────────────
st.title("🏇 うまなり地蔵AI Dashboard v4")
st.markdown(f"📅 {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")

st.markdown("""
---
**ダッシュボード v4 へようこそ**

左側メニューからページを選択してください：
- 🏠 **ホーム** — 本日の買い目、リアルタイムログ、重要アラート
- 📈 **成績サマリー** — ROI 追跡、的中率、月別集計、レース別パフォーマンス
- 💰 **資金管理** — 資金推移、Kelly 基準、ドローダウン管理
- 🔬 **詳細分析** — SHAP 特徴量、血統分析、オッズシグナル
- 🧪 **バックテスト** — ウォークフォワード検証、パラメータグリッド
- ⚙️ **設定** — EV_THRESHOLD、KELLY_FRACTION 調整
- 👨‍💼 **管理画面** — パイプラインジョブ実行、ログ検索
- 🏇 **出走表** — 出走表、全頭評価、リスク分析

---

### 🚀 クイックスタート

**FastAPI バックエンド起動:**
```bash
uvicorn api.main:app --reload --port 8000
```

**API ドキュメント:** http://localhost:8000/docs

**ダッシュボード:** http://localhost:8501 (このページ)

### 📊 主な機能

| ページ | 目的 | 更新頻度 |
|--------|------|--------|
| ホーム | 本日の予想・パイプライン制御 | リアルタイム |
| 成績 | ROI・的中率追跡 | TTL 5分 |
| 資金管理 | Kelly 管理・ドローダウン | TTL 5分 |
| 分析 | 特徴量・オッズシグナル | TTL 10分 |
| バックテスト | 検証結果・パラメータ最適化 | TTL 30分 |
| 設定 | パラメータ動的調整 | 即時 |
| 管理 | パイプライン監視・ジョブ実行 | リアルタイム |
| 出走表 | 今日のレース・馬評価 | TTL 5分 |

---

### ⚠️ 注意事項

- **初回起動**: PostgreSQL (127.0.0.1:5433) が起動している必要があります
- **FastAPI**: 別ターミナルで `uvicorn api.main:app --reload` を実行してください
- **パイプライン実行**: ホームページから「Run」ボタンをクリックして開始
- **リアルタイム更新**: WebSocket エンドポイントが `/ws/pipeline/{trace_id}` で動作

---

💡 **トラブルシューティング**

1. **データが表示されない**
   - ホームページの「Refresh」ボタンをクリック
   - FastAPI サーバーが起動しているか確認
   - PostgreSQL が起動しているか確認

2. **パイプライン実行エラー**
   - 管理画面でログを確認
   - `logs/` ディレクトリを確認

3. **WebSocket 接続失敗**
   - FastAPI がポート 8000 で起動しているか確認
   - ファイアウォール設定を確認
""")

st.markdown("---")

st.info("""
🔧 **開発者向け情報**

- **構成**: Streamlit v1.30+ マルチページ + FastAPI バックエンド
- **データキャッシング**: `@st.cache_data(ttl=XXX)` 使用
- **非同期実行**: asyncio + `create_subprocess_exec()`
- **リアルタイム**: WebSocket (`/ws/*` エンドポイント)

詳細は [計画書](./PLAN.md) を参照。
""")
