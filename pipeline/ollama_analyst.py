"""
ollama_analyst.py  --  Local LLM race analysis agent
=====================================================
agent_picks_{date}.json / simulation CSV from approved bets
to generate detailed per-race commentary and note.com article drafts.

Usage:
    python pipeline/ollama_analyst.py                 # today
    python pipeline/ollama_analyst.py 20260426        # specific date
    from pipeline.ollama_analyst import run_ollama_analyst
"""
import os
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

JST      = ZoneInfo("Asia/Tokyo")
BASE_DIR = "D:\\keiba_ai"
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

KEIBAJO_NAME = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

SYSTEM_ANALYST = (
    "あなたは「うまなり地蔵AI」の予想解説担当です。"
    "競馬データを分析し、note.com 読者向けの魅力的な日本語解説を書きます。"
    "仏教・地蔵・閻魔大王の世界観を随所に取り入れ、"
    "専門的でありながら親しみやすいトーンを保ってください。"
    "データの根拠を明確にし、なぜその馬を推すのかを論理的に説明してください。"
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _race_name(race_code: str) -> str:
    """race_code から競馬場名+レース番号を返す"""
    if len(race_code) >= 12:
        kj = race_code[4:6]
        rn = race_code[-2:]
        return f"{KEIBAJO_NAME.get(kj, '?')} {int(rn)}R"
    return race_code


def _load_picks(date_str: str) -> List[Dict]:
    path = os.path.join(BASE_DIR, f"agent_picks_{date_str}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("approved_bets", [])


def _load_bankroll() -> int:
    path = os.path.join(DATA_DIR, "bankroll.json")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return int(json.load(f).get("current", 0))


# ─────────────────────────────────────────────────────────────
# Analysis generators
# ─────────────────────────────────────────────────────────────

def _analyse_single_bet(bet: Dict, _generate) -> str:
    """1頭分の詳細解説を生成"""
    bamei   = bet.get("bamei", "")
    odds    = bet.get("odds", 0)
    ev      = bet.get("ev", 0)
    kelly   = bet.get("kelly_bet", 0)
    rc      = bet.get("race_code", "")
    ticket  = bet.get("ticket_type", "単勝")

    # EV要因がある場合は取り出す
    ev_factors = bet.get("ev_factors", [])
    factors_str = "、".join(ev_factors[:5]) if ev_factors else "統計的優位性"

    prompt = f"""
以下の穴馬予想データをもとに、note.com 記事用の解説を250〜350字で書いてください。

【予想馬】{bamei}
【レース】{_race_name(rc)}
【馬券種】{ticket}
【単勝オッズ】{odds:.1f}倍
【期待値】{ev*100:.0f}%（EV {ev:.3f}）
【投資額】{kelly:,}円
【選定根拠】{factors_str}

書き方のポイント:
- なぜこの馬が「穴」として価値があるのかを論じる
- オッズと期待値の関係を読者に分かりやすく説明する
- うまなり地蔵らしい仏教的表現を1〜2箇所に入れる
- 最後は「注目！」「見逃せない」などの締め言葉で終える
"""
    result = _generate(prompt, system=SYSTEM_ANALYST, temperature=0.72)
    return result or f"【{bamei}】{odds:.1f}倍の穴馬候補。EV {ev*100:.0f}%と統計的優位性あり。"


def _generate_intro(date_str: str, picks: List[Dict], bankroll: int,
                    _generate) -> str:
    """note.com 記事の冒頭部分を生成"""
    date_fmt = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日"
    total_investment = sum(b.get("kelly_bet", 0) for b in picks)
    avg_odds = sum(b.get("odds", 0) for b in picks) / max(len(picks), 1)

    prompt = f"""
note.com 記事の冒頭（リード文）を200字程度で書いてください。

【日付】{date_fmt}
【推奨馬数】{len(picks)}頭
【平均オッズ】{avg_odds:.1f}倍
【総投資予定額】{total_investment:,}円
【バンクロール】{bankroll:,}円

「うまなり地蔵AI」が今日もデータの海を泳ぎ、閻魔帳に記した穴馬たちを紹介する
という流れで書いてください。読者の期待感を高める書き出しにしてください。
"""
    result = _generate(prompt, system=SYSTEM_ANALYST, temperature=0.8)
    return result or f"本日{date_fmt}、うまなり地蔵AIが{len(picks)}頭の穴馬を厳選しました。"


def _generate_summary(picks: List[Dict], _generate) -> str:
    """記事末尾のまとめ文を生成"""
    total = sum(b.get("kelly_bet", 0) for b in picks)
    expected = sum(b.get("kelly_bet", 0) * b.get("ev", 0) for b in picks)

    prompt = f"""
note.com 記事の締めくくり（まとめ）を150字程度で書いてください。

【推奨馬数】{len(picks)}頭
【総投資予定】{total:,}円
【期待リターン（EV合計）】+{expected:,.0f}円相当

地蔵の慈悲と閻魔の審判という対比を使い、
「データを信じて賢く勝負せよ」というメッセージで締めてください。
"""
    result = _generate(prompt, system=SYSTEM_ANALYST, temperature=0.7)
    return result or f"本日の総投資予定 {total:,}円。データが示す優位性を信じ、賢く勝負しましょう。"


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def run_ollama_analyst(date_str: str = None) -> Optional[str]:
    """
    run_all.py から呼び出されるエントリーポイント。

    Returns:
        生成された記事テキスト（失敗時は None）
    """
    if date_str is None:
        date_str = datetime.now(tz=JST).strftime("%Y%m%d")

    print(f"\n[ollama_analyst] {date_str} 解説記事生成開始...")

    # Ollama 確認
    try:
        from pipeline.ollama_comment import (
            is_ollama_running, get_model_for_task, _generate
        )
    except ImportError:
        print("  [ollama_analyst] ollama_comment が見つかりません")
        return None

    if not is_ollama_running():
        print("  [ollama_analyst] Ollama が起動していません（スキップ）")
        print("  → 'ollama serve' を実行してから再試行してください")
        return None

    # note.com 日本語記事生成 → "japanese" プロファイル（qwen2.5/aya-expanse 優先）
    model = get_model_for_task("japanese")
    if not model:
        print("  [ollama_analyst] 利用可能なモデルがありません（スキップ）")
        return None
    print(f"  [ollama_analyst] モデル: {model}")

    # picks 読み込み
    picks = _load_picks(date_str)
    if not picks:
        print(f"  [ollama_analyst] agent_picks_{date_str}.json が見つからないか空です")
        return None

    bankroll = _load_bankroll()
    print(f"  対象ベット: {len(picks)}頭 | バンクロール: {bankroll:,}円")

    # 記事構築
    date_fmt = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日"
    sections = [
        f"# うまなり地蔵AI 穴馬予想レポート {date_fmt}",
        "",
    ]

    # 冒頭
    print("  (1/3) リード文生成中...")
    intro = _generate_intro(date_str, picks, bankroll, _generate)
    sections.append(intro)
    sections.append("")

    # 各馬解説
    print(f"  (2/3) {len(picks)}頭の個別解説生成中...")
    for i, bet in enumerate(picks, 1):
        bamei = bet.get("bamei", f"馬{i}")
        odds  = bet.get("odds", 0)
        rc    = bet.get("race_code", "")
        print(f"    [{i}/{len(picks)}] {bamei} ({odds:.1f}倍) {_race_name(rc)}")

        sections.append(f"## {_race_name(rc)}  {bamei}  {odds:.1f}倍")
        sections.append("")
        analysis = _analyse_single_bet(bet, _generate)
        sections.append(analysis)
        sections.append("")

    # まとめ
    print("  (3/3) まとめ生成中...")
    summary = _generate_summary(picks, _generate)
    sections.append("## まとめ")
    sections.append("")
    sections.append(summary)
    sections.append("")
    sections.append("---")
    sections.append("*うまなり地蔵AI — アンサンブルMLによる穴馬予想システム*")

    article = "\n".join(sections)

    # 保存
    os.makedirs(REPORTS_DIR, exist_ok=True)
    out_path = os.path.join(REPORTS_DIR, f"note_draft_{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(article)

    print(f"\n  [ollama_analyst] 記事生成完了!")
    print(f"  保存先: {out_path}")
    print(f"  文字数: {len(article):,}字")
    return article


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama \u4e88\u60f3\u89e3\u8aac\u8a18\u4e8b\u751f\u6210")
    parser.add_argument("date", nargs="?", help="YYYYMMDD (\u7701\u7565\u6642=\u4eca\u65e5)")
    args = parser.parse_args()
    result = run_ollama_analyst(args.date)
    if result:
        print(f"\n\u751f\u6210\u5b8c\u4e86: {result}")
    else:
        print("\n\u751f\u6210\u5931\u6557 (\u30e6\u30fc\u30b6\u30fc\u306b\u78ba\u8a8d\u3092)")
