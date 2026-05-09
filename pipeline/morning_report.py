"""
morning_report.py -- 朝の買い目シート自動生成 v2
=========================================================
agent_picks_{date}.json を読み込み、見やすい買い目シートを
ターミナルに表示し reports/morning_{date}.txt に保存する。

新機能 (v2):
  - レース種別（新馬/障害/ハンデ）表示
  - EV boost ソース表示（knowledge_base 反映済みかどうか）
  - Ollama による1行解説生成（起動中の場合）
  - ev_analysis CSV からのフォールバック読み込み
  - Kelly 配分率と残高推移を追加表示

使い方:
    python pipeline/morning_report.py              # 今日
    python pipeline/morning_report.py 20260426     # 指定日
    python pipeline/morning_report.py --no-ollama  # Ollama解説スキップ
"""

import os
import json
import glob
import sys
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from pipeline.config import BASE_DIR, DATA_DIR

JST      = ZoneInfo("Asia/Tokyo")
RPT_DIR  = os.path.join(BASE_DIR, "reports")

KEIBAJO = {
    "01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京",
    "06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉",
    "30":"門別","31":"盛岡","32":"水沢","39":"浦和","40":"船橋",
    "41":"大井","42":"川崎","43":"金沢","44":"笠松","45":"名古屋",
    "47":"園田","48":"姫路","50":"高知","51":"佐賀","58":"帯広",
}

RACE_TYPE_LABEL = {
    "debut":    "【新馬】",
    "shogai":   "【障害】",
    "handicap": "【ハンデ】",
    "default":  "",
}

RACE_TYPE_EV = {
    "debut":    0.10,
    "shogai":   0.10,
    "handicap": 0.20,
    "default":  0.15,
}


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────

def _fmt_race(code: str) -> str:
    s = str(code).strip()
    if len(s) < 16:
        return s
    mm  = str(int(s[4:6]))
    dd  = str(int(s[6:8]))
    jyo = KEIBAJO.get(s[8:10], s[8:10])
    rno = s[14:16].lstrip("0") or "1"
    return f"{mm}/{dd} {jyo}{rno}R"


def _ev_bar(ev_pct: float, width: int = 20) -> str:
    filled = min(max(int(ev_pct / 5), 0), width)
    return "█" * filled + "░" * (width - filled)


def _load_picks(date_str: str = None) -> dict:
    if date_str:
        path = os.path.join(BASE_DIR, f"agent_picks_{date_str}.json")
        if not os.path.exists(path):
            path = os.path.join(DATA_DIR, f"agent_picks_{date_str}.json")
    else:
        candidates = sorted(
            glob.glob(os.path.join(BASE_DIR, "agent_picks_*.json")), reverse=True
        )
        if not candidates:
            candidates = sorted(
                glob.glob(os.path.join(DATA_DIR, "agent_picks_*.json")), reverse=True
            )
        path = candidates[0] if candidates else None

    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_predictions_csv(date_str: str) -> list:
    """predictions_{date}.csv からレースごとの本命馬を読み込む。"""
    path = os.path.join(DATA_DIR, f"predictions_{date_str}.csv")
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        if 'win_prob' not in df.columns:
            return []
        top = (df.sort_values('win_prob', ascending=False)
                 .drop_duplicates('race_code')
                 .sort_values('win_prob', ascending=False)
                 .head(20))
        records = []
        for _, row in top.iterrows():
            odds = float(row.get("odds", 0))
            wp = float(row.get("win_prob", 0)) / 100.0  # win_prob is in % (e.g. 13.2 = 13.2%)
            ev = wp * odds - 1.0 if odds > 0 else 0
            records.append({
                "race_code":       str(row.get("race_code", "")),
                "bamei":           str(row.get("bamei", "")),
                "umaban":          row.get("umaban", ""),
                "kishumei":        str(row.get("kishumei_ryakusho", "")),
                "odds":            odds,
                "odds_estimated":  bool(row.get("odds_estimated", False)),
                "ninki":           int(row.get("ninki", 0)),
                "win_probability": wp,
                "expected_value":  ev,
                "race_type":       "default",
                "kelly_bet":       0,
                "ticket_type":     "単勝",
                "comment":         f"推定{int(row.get('ninki',0))}人気" if row.get("odds_estimated") else "",
            })
        return records
    except Exception as e:
        print(f"  [morning] predictions load error: {e}")
        return []


def _load_ev_csv(year: int = None) -> list:
    """ev_analysis_{year}.csv から正EV馬を読み込む（agent_picks がない場合のフォールバック）。"""
    if year is None:
        year = datetime.now(tz=JST).year
    path = os.path.join(BASE_DIR, f"ev_analysis_{year}.csv")
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        records = []
        for _, row in df.head(20).iterrows():
            records.append({
                "race_code":       row.get("race_code", ""),
                "bamei":           row.get("bamei", ""),
                "umaban":          row.get("umaban", ""),
                "kishumei":        row.get("kishumei_ryakusho", ""),
                "odds":            float(row.get("odds_decimal", 0)),
                "win_probability": float(row.get("win_probability", 0)),
                "expected_value":  float(row.get("expected_value", 0)),
                "race_type":       row.get("race_type", "default"),
                "kelly_bet":       0,
                "ticket_type":     "単勝",
                "comment":         "(EV CSV フォールバック)",
            })
        return records
    except Exception as e:
        print(f"  [morning] ev_csv load error: {e}")
        return []


def _load_bankroll() -> dict:
    path = os.path.join(DATA_DIR, "bankroll.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"current": 10000, "initial": 10000}


def _load_roi_summary() -> dict:
    path = os.path.join(DATA_DIR, "roi_tracker.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        valid = df[df["hit"] != -1]
        if len(valid) == 0:
            return {}
        hits = (valid["hit"] == 1).sum()
        invested = valid["bet_amount"].sum()
        returned = valid["return_amount"].sum()
        roi = returned / invested * 100 if invested > 0 else 0
        return {
            "total": len(valid),
            "hits": int(hits),
            "hit_rate": hits / len(valid) * 100,
            "roi": roi,
        }
    except Exception:
        return {}


def _try_ollama_explain(bet: dict) -> str:
    """Ollama で1行予想解説を生成する。失敗時は空文字を返す。"""
    try:
        from pipeline.ollama_comment import is_ollama_running, get_model_for_task, _generate
        if not is_ollama_running():
            return ""
        model = get_model_for_task("japanese")
        if not model:
            return ""
        bamei   = bet.get("bamei", "")
        odds    = bet.get("odds", 0)
        ev_pct  = bet.get("expected_value", 0) * 100
        kelly   = bet.get("kelly_bet", 0)
        rtype   = RACE_TYPE_LABEL.get(bet.get("race_type", "default"), "")
        factors = bet.get("ev_factors", [])
        factors_str = "・".join(factors[:3]) if factors else "AI分析による高期待値"
        prompt = (
            "\u7af6\u99ac\u4e88\u60f3AI\u306e\u5206\u6790\u7d50\u679c\u3092" "40\u6587\u5b57\u4ee5\u5185\u306e\u65e5\u672c\u8a9e\u30671\u884c\u89e3\u8aac\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n"
            f"\u99ac\u540d: {bamei}{rtype}\u3001\u30aa\u30c3\u30ba: {odds:.1f}\u500d\u3001EV: {ev_pct:.0f}%\u3001\u6295\u8cc7: {kelly:,}\u5186\n"
            f"\u6839\u62e0: {factors_str}\n"
            "\u5730\u8535\u7684\u306a\u8a9e\u611f\u3067\u3002\u4f59\u5206\u306a\u524d\u7f6e\u304d\u4e0d\u8981\u3002"
        )
        result = _generate(prompt, system="あなたは競馬予想AIの解説者です。簡潔に日本語で答えてください。",
                           model=model, temperature=0.75, stream=False, task="japanese")
        if result:
            # 改行除去・先頭空白除去
            result = result.strip().replace("\n", " ")[:80]
        return result or ""
    except Exception as e:
        print(f"  [morning] ollama explain skip: {e}")
        return ""


# ─────────────────────────────────────────────────────────────
# メイン生成
# ─────────────────────────────────────────────────────────────

def generate_report(date_str: str = None, save: bool = True,
                    print_report: bool = True, use_ollama: bool = True) -> str:
    if date_str is None:
        date_str = datetime.now(tz=JST).strftime("%Y%m%d")

    picks   = _load_picks(date_str)
    bkroll  = _load_bankroll()
    current = bkroll.get("current", 10000)
    initial = bkroll.get("initial", current)
    roi_s   = _load_roi_summary()

    now_str   = datetime.now(tz=JST).strftime("%Y-%m-%d %H:%M")
    date_disp = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"

    lines = []
    sep  = "=" * 62
    sep2 = "-" * 62

    # ── ヘッダー ──────────────────────────────────────────────
    lines += [
        sep,
        f"  🙏 うまなり地蔵AI  買い目シート  {date_disp}",
        f"  生成: {now_str}",
        sep,
    ]

    approved   = picks.get("approved_bets", []) if picks else []
    ev_cands   = picks.get("ev_candidates", []) if picks else []
    rs         = picks.get("risk_summary", {}) if picks else {}
    from_csv   = False

    if not approved:
        # フォールバック1: 当日 predictions CSV
        approved = _load_predictions_csv(date_str)
        from_csv = True
        if approved:
            has_est = any(b.get("odds_estimated") for b in approved)
            tag = " (推定オッズ)" if has_est else ""
            lines.append(f"  📊 predictions_{date_str}.csv から生成{tag}")
        else:
            # フォールバック2: ev_analysis CSV
            year = int(date_str[:4])
            approved = _load_ev_csv(year)
            if approved:
                lines.append(f"  ⚠️  agent_picks_{date_str}.json なし → ev_analysis_{year}.csv を使用")
            else:
                lines.append("  ⚠️  予想データがありません。")
                lines.append("  python run_all.py --morning  を実行してください。")
                lines.append(sep)
            report = "\n".join(lines)
            if print_report:
                print(report)
            return report

    # ── バンクロール情報 ──────────────────────────────────────
    total_bet   = sum(b.get("kelly_bet", 0) for b in approved)
    exp_return  = sum(
        b.get("kelly_bet", 0) * b.get("odds", 0) * b.get("win_probability", 0)
        for b in approved
    )
    alloc_pct   = total_bet / current * 100 if current > 0 else 0
    pl_all      = current - initial
    pl_pct      = pl_all / initial * 100 if initial > 0 else 0
    pl_sign     = "+" if pl_all >= 0 else ""

    lines += [
        f"  💰 現在バンクロール : {current:>12,.0f} 円  ({pl_sign}{pl_pct:.1f}% vs 初期)",
        f"  📥 本日投入予定     : {total_bet:>12,.0f} 円  ({alloc_pct:.1f}%)",
        f"  📈 期待回収額       : {exp_return:>12,.0f} 円",
        f"  🎯 推奨レース数     : {rs.get('approved_count', len(approved))} R",
    ]
    if roi_s:
        lines.append(
            f"  📊 累計実績         : 的中率{roi_s['hit_rate']:.1f}%  "
            f"回収率{roi_s['roi']:.1f}%  ({roi_s['total']}R)"
        )
    lines.append(sep2)

    # ── 買い目一覧 ────────────────────────────────────────────
    lines.append("  【 推奨買い目 】")
    lines.append(sep2)

    for i, bet in enumerate(approved, 1):
        race_lbl  = _fmt_race(str(bet.get("race_code", "")))
        bamei     = bet.get("bamei", "")
        umaban    = bet.get("umaban", "")
        kishu     = bet.get("kishumei", bet.get("kishumei_ryakusho", ""))
        odds      = bet.get("odds", 0)
        kelly     = bet.get("kelly_bet", 0)
        ev_raw    = bet.get("expected_value", 0)
        win_p     = bet.get("win_probability", 0) * 100
        ticket    = bet.get("ticket_type", "単勝")
        grade     = bet.get("condition_grade", "B")
        comment   = bet.get("comment", "")
        rtype     = bet.get("race_type", "default")
        ev_pct    = ev_raw * 100
        ev_thresh = RACE_TYPE_EV.get(rtype, 0.15) * 100
        rtype_lbl = RACE_TYPE_LABEL.get(rtype, "")

        grade_mark = "★★" if grade == "S" else "★ " if grade == "A" else "  "

        # Kelly 配分率
        kelly_pct = kelly / current * 100 if current > 0 else 0

        lines += [
            f"  {i:>2}. {grade_mark} {race_lbl}  {rtype_lbl}",
            f"       馬番: {umaban}番  馬名: {bamei}  騎手: {kishu}",
            f"       馬券: {ticket}  オッズ: {odds:.1f}倍  勝率推定: {win_p:.1f}%",
            f"       投資: {kelly:,}円 ({kelly_pct:.1f}%)  EV閾値: {ev_thresh:.0f}%",
            f"       EV : {ev_pct:+.0f}%  {_ev_bar(ev_pct)}",
        ]

        if comment:
            lines.append(f"       備考: {comment}")

        # Ollama 解説
        if use_ollama and not from_csv:
            explanation = _try_ollama_explain(bet)
            if explanation:
                lines.append(f"       🤖 {explanation}")

        lines.append(sep2)

    # ── EV候補（承認外・参考）────────────────────────────────
    extra = [c for c in ev_cands if not any(
        b.get("race_code") == c.get("race_code") and b.get("umaban") == c.get("umaban")
        for b in approved
    )]
    if extra:
        lines += [
            "  【 EV候補（リスク未承認 / 参考）】",
            sep2,
        ]
        for c in extra[:5]:
            race_lbl = _fmt_race(str(c.get("race_code", "")))
            ev_pct   = c.get("expected_value", 0) * 100
            odds     = c.get("odds", 0)
            rtype    = c.get("race_type", "default")
            rtype_lbl = RACE_TYPE_LABEL.get(rtype, "")
            lines.append(
                f"    {race_lbl}  {c.get('bamei','')}  {odds:.1f}倍  "
                f"EV:{ev_pct:+.0f}%  {rtype_lbl}"
            )
        lines.append(sep2)

    # ── フッター ──────────────────────────────────────────────
    lines += [
        "  ⚠️  投資は余裕資金で。損失は自己責任です。",
        "  📊 ダッシュボード: streamlit run pipeline/dashboard_15.py",
        sep,
    ]

    report = "\n".join(line for line in lines if line is not None)

    if print_report:
        print(report)

    if save:
        os.makedirs(RPT_DIR, exist_ok=True)
        out_path = os.path.join(RPT_DIR, f"morning_{date_str}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n  💾 保存: {out_path}")

    return report


def run_morning_report(date_str: str = None, use_ollama: bool = True):
    """run_all.py から呼び出されるエントリーポイント"""
    if date_str is None:
        date_str = datetime.now(tz=JST).strftime("%Y%m%d")
    return generate_report(date_str=date_str, save=True,
                           print_report=True, use_ollama=use_ollama)


if __name__ == "__main__":
    args = sys.argv[1:]
    no_ollama = "--no-ollama" in args
    args = [a for a in args if not a.startswith("--")]
    date_arg = args[0] if args else None
    generate_report(date_str=date_arg, save=True,
                    print_report=True, use_ollama=not no_ollama)
