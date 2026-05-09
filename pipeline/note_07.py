import logging
import os
import json
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

JST      = ZoneInfo("Asia/Tokyo")
BASE_DIR = "D:\\keiba_ai"
DATA_DIR = os.path.join(BASE_DIR, "data")

# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────

def _load_picks(date_str: str) -> list:
    path = os.path.join(BASE_DIR, f"agent_picks_{date_str}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("approved_bets", [])


def _load_roi_stats() -> dict:
    path = os.path.join(DATA_DIR, "roi_tracker.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, encoding="utf-8-sig")
    valid = df[df["hit"] != -1]
    total = len(valid)
    if total == 0:
        return {}
    hits = (valid["hit"] == 1).sum()
    invested = valid["bet_amount"].sum()
    returned = valid["return_amount"].sum()
    roi = returned / invested * 100 if invested > 0 else 0
    top_hits = (
        valid[valid["hit"] == 1]
        .sort_values("odds", ascending=False)
        .head(5)[["bamei", "odds", "return_amount"]]
        .to_dict("records")
    )
    return {
        "total": total,
        "hits": int(hits),
        "hit_rate": hits / total * 100,
        "roi": roi,
        "invested": invested,
        "returned": returned,
        "top_hits": top_hits,
    }


def _load_bankroll() -> int:
    path = os.path.join(DATA_DIR, "bankroll.json")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return int(json.load(f).get("current", 0))


def _try_ollama(prompt: str, system: str = "", temperature: float = 0.75) -> str:
    """Ollama 呼び出し。失敗時は空文字を返す。"""
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return ""
        model = get_model_for_task("japanese")  # note記事は日本語プロファイル
        if not model:
            return ""
        result = _generate(prompt, system=system, model=model,
                           temperature=temperature, stream=True, task="japanese")
        return result or ""
    except Exception as e:
        log.warning("[note_07] ollama skip: %s", e)
        return ""


SYSTEM_NOTE = (
    "You are the content writer for a Japanese horse racing AI prediction service called "
    "umanari-jizo AI. Write compelling Japanese content for note.com readers. "
    "Use a mix of Buddhist/Jizo references and data-driven analysis. "
    "Tone: warm, expert, slightly mystical. Always write in Japanese."
)

# ─────────────────────────────────────────────────────────────
# Section generators
# ─────────────────────────────────────────────────────────────

def _gen_intro(date_fmt: str, n_picks: int, bankroll: int) -> str:
    prompt = (
        f"Write a compelling intro paragraph (150 chars) for a note.com article.\n"
        f"Date: {date_fmt}, picks: {n_picks} horses, bankroll: {bankroll:,}yen.\n"
        "Include Jizo/Buddhist imagery. Japanese only."
    )
    result = _try_ollama(prompt, system=SYSTEM_NOTE, temperature=0.8)
    if result:
        return result
    return f"{date_fmt}、うまなり地蔵AIが今日も閻魔帳を開き、{n_picks}頭の穴馬を炙り出しました。"


def _gen_pick_analysis(bet: dict) -> str:
    bamei   = bet.get("bamei", "")
    odds    = bet.get("odds", 0)
    ev      = bet.get("ev", 0)
    kelly   = bet.get("kelly_bet", 0)
    factors = bet.get("ev_factors", [])
    factors_str = ", ".join(factors[:4]) if factors else "statistical edge"
    prompt = (
        f"Write a 200-char Japanese analysis for this pick:\n"
        f"Horse: {bamei}, odds: {odds:.1f}x, EV: {ev*100:.0f}%, bet: {kelly:,}yen\n"
        f"Reasons: {factors_str}\n"
        "Why is this horse worth betting? Include Jizo style. Japanese only."
    )
    result = _try_ollama(prompt, system=SYSTEM_NOTE, temperature=0.72)
    if result:
        return result
    return f"{bamei}は{odds:.1f}倍と人気薄ながらEV{ev*100:.0f}%の高期待値。データが示す穴馬候補。"


def _gen_stats_commentary(stats: dict) -> str:
    prompt = (
        f"Write a 200-char Japanese commentary on these AI stats:\n"
        f"Total bets: {stats['total']}, hit rate: {stats['hit_rate']:.1f}%, "
        f"ROI: {stats['roi']:.1f}%\n"
        "Celebrate good performance or encourage if mediocre. Jizo style. Japanese only."
    )
    result = _try_ollama(prompt, system=SYSTEM_NOTE, temperature=0.7)
    if result:
        return result
    return (
        f"累計{stats['total']:,}レースで的中率{stats['hit_rate']:.1f}%・"
        f"回収率{stats['roi']:.1f}%を達成。地蔵の修行は続く。"
    )


def _gen_closing(bankroll: int) -> str:
    prompt = (
        f"Write a 150-char closing message for a note.com article.\n"
        f"Current bankroll: {bankroll:,}yen. Encourage readers to follow AI picks.\n"
        "Mystical Jizo tone. End with hashtags: #keiba #anauma #AI. Japanese only."
    )
    result = _try_ollama(prompt, system=SYSTEM_NOTE, temperature=0.85)
    if result:
        return result
    return (
        f"現在の軍資金 {bankroll:,}円。地蔵の炎は消えない。\n"
        "#競馬予想 #穴馬 #AIyoso #うまなり地蔵"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def generate_note_article(date_str: str = None) -> str:
    log.info("[note_07] note.com article generation start...")
    if date_str is None:
        date_str = datetime.now(tz=JST).strftime("%Y%m%d")

    date_fmt = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    picks    = _load_picks(date_str)
    stats    = _load_roi_stats()
    bankroll = _load_bankroll()

    log.info("  picks: %d, bankroll: %syen", len(picks), f"{bankroll:,}")

    sections = [
        f"# {date_fmt} umanari-jizo AI anauma picks report",
        "",
        "---",
        "",
    ]

    # intro
    log.info("  (1) intro...")
    sections.append(_gen_intro(date_fmt, len(picks), bankroll))
    sections.append("")

    # today's picks
    if picks:
        sections.append("## Today picks")
        sections.append("")
        for i, bet in enumerate(picks, 1):
            bamei = bet.get("bamei", f"horse{i}")
            odds  = bet.get("odds", 0)
            ev    = bet.get("ev", 0)
            kelly = bet.get("kelly_bet", 0)
            sections.append(f"### {i}. {bamei}  {odds:.1f}x  EV{ev*100:.0f}%")
            sections.append("")
            log.info("  (%d) %s analysis...", i + 1, bamei)
            sections.append(_gen_pick_analysis(bet))
            sections.append(f"\n> bet: {kelly:,}yen (Kelly criteria)")
            sections.append("")

    # stats
    if stats:
        sections.append("## Cumulative performance")
        sections.append("")
        sections.append(
            f"| item | value |\n"
            f"|------|-------|\n"
            f"| total bets | {stats['total']:,} |\n"
            f"| hit rate | {stats['hit_rate']:.1f}% |\n"
            f"| ROI | {stats['roi']:.1f}% |\n"
            f"| invested | {stats['invested']:,.0f}yen |\n"
            f"| returned | {stats['returned']:,.0f}yen |"
        )
        sections.append("")
        log.info("  stats commentary...")
        sections.append(_gen_stats_commentary(stats))
        sections.append("")

        if stats.get("top_hits"):
            sections.append("### Top wins")
            sections.append("")
            for h in stats["top_hits"]:
                sections.append(
                    f"- {h['bamei']}  {h['odds']:.1f}x  "
                    f"return {h['return_amount']:,.0f}yen"
                )
            sections.append("")

    # system info (template)
    sections.extend([
        "## AI system info",
        "",
        "- Data: JRA-VAN DataLab (1954~)",
        "- Model: LightGBM 50% + XGBoost 30% + CatBoost 20%",
        "- Features: 97 columns (odds excluded to prevent leakage)",
        "- Filter: EV >= 15% AND odds >= 10x",
        "",
    ])

    # closing
    log.info("  closing...")
    sections.append("---")
    sections.append("")
    sections.append(_gen_closing(bankroll))
    sections.append("")
    sections.append("---")
    sections.append("*This article is for research purposes. Bet at your own risk.*")

    article = "\n".join(sections)

    # save
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
    filename = os.path.join(BASE_DIR, "reports", f"note_{date_str}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(article)

    log.info("  saved: %s  (%d chars)", filename, len(article))
    return article


if __name__ == "__main__":
    generate_note_article()
