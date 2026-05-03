"""
result_fetcher.py  —  レース確定結果の自動取得 & roi_tracker 更新
=================================================================
レース終了後（当日夕方〜夜）に実行することで、agent_picks の予想と
確定着順を照合し roi_tracker.csv に自動追記・bankroll.json を更新する。

使い方:
    python pipeline/result_fetcher.py              # 今日の結果を取得
    python pipeline/result_fetcher.py 20260426     # 指定日
    python pipeline/result_fetcher.py --dry-run    # 確認のみ（CSV更新なし）

依存: httpx, beautifulsoup4
"""
import os
import re
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Optional, List, Dict

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

JST      = ZoneInfo("Asia/Tokyo")
BASE_DIR = "D:\\keiba_ai"
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://race.netkeiba.com/",
}


# ─────────────────────────────────────────────────────────────
# 結果スクレイピング
# ─────────────────────────────────────────────────────────────

def _get_html(url: str) -> str:
    r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    try:
        return r.content.decode("euc-jp", errors="replace")
    except Exception:
        return r.text


def fetch_race_result(race_id: str) -> List[Dict]:
    """
    netkeiba のレース結果ページから確定着順・確定単勝オッズを取得する。
    race_id: 12桁（例: 202605020206）または 16桁 JV 形式

    Returns:
        [{"umaban": int, "bamei": str, "chakujun": int, "tansho_odds": float}, ...]
    """
    # JV 16桁 → netkeiba 12桁
    rid = str(race_id).strip()
    if len(rid) == 16:
        rid = rid[:4] + rid[8:]   # YYYY + KKAARR

    url = f"https://race.netkeiba.com/race/result.html?race_id={rid}"
    html = _get_html(url)
    soup = BeautifulSoup(html, "html.parser")

    results = []
    # 着順テーブル: id="All_Result_Table" or class="ResultTable"
    table = (soup.find("table", id="All_Result_Table")
             or soup.find("table", class_="RaceTable01"))
    if not table:
        return results

    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 5:
            continue
        try:
            chakujun_raw = tds[0].get_text(strip=True)
            if not chakujun_raw.isdigit():
                continue
            chakujun = int(chakujun_raw)
            umaban   = int(re.sub(r"\D", "", tds[2].get_text(strip=True)) or "0")
            bamei    = tds[3].get_text(strip=True)

            # 単勝オッズ（列番号はページによって異なる）
            odds = 0.0
            for td in reversed(tds):
                txt = td.get_text(strip=True).replace(",", "")
                if re.match(r"^\d+\.\d+$", txt):
                    odds = float(txt)
                    break

            results.append({
                "umaban":       umaban,
                "bamei":        bamei,
                "chakujun":     chakujun,
                "tansho_odds":  odds,
            })
        except Exception:
            continue

    return results


def fetch_all_results(date_str: str) -> Dict[str, List[Dict]]:
    """
    指定日の全レース結果を取得する。
    agent_picks_{date}.json の race_code 一覧を使用。

    Returns: {race_code: [result, ...], ...}
    """
    picks_path = os.path.join(BASE_DIR, f"agent_picks_{date_str}.json")
    if not os.path.exists(picks_path):
        print(f"  ⚠️ picks ファイルなし: {picks_path}")
        return {}

    with open(picks_path, encoding="utf-8") as f:
        picks = json.load(f)

    race_codes = list({b["race_code"] for b in picks.get("approved_bets", [])})
    print(f"  📋 対象レース: {len(race_codes)}R")

    all_results = {}
    for i, rc in enumerate(race_codes, 1):
        try:
            res = fetch_race_result(rc)
            all_results[rc] = res
            hit_count = sum(1 for r in res if r["chakujun"] == 1)
            print(f"  [{i:2d}/{len(race_codes)}] {rc}  "
                  f"{len(res)}頭 ({'結果あり' if res else '取得失敗'})")
            time.sleep(0.5)
        except Exception as e:
            print(f"  [{i:2d}/{len(race_codes)}] {rc}  ⚠️ {e}")
            all_results[rc] = []

    return all_results


# ─────────────────────────────────────────────────────────────
# 的中判定 & roi_tracker 更新
# ─────────────────────────────────────────────────────────────

def evaluate_picks(date_str: str, results: Dict[str, List[Dict]],
                   dry_run: bool = False) -> Dict:
    """
    agent_picks_{date}.json の予想と確定結果を照合し、
    roi_tracker.csv に追記する。

    Returns: サマリー dict
    """
    picks_path = os.path.join(BASE_DIR, f"agent_picks_{date_str}.json")
    if not os.path.exists(picks_path):
        return {}

    with open(picks_path, encoding="utf-8") as f:
        picks = json.load(f)

    approved = picks.get("approved_bets", [])
    if not approved:
        print("  承認ベットなし")
        return {}

    # 既存 roi_tracker を読み込む
    tracker_path = os.path.join(DATA_DIR, "roi_tracker.csv")
    if os.path.exists(tracker_path):
        tracker_df = pd.read_csv(tracker_path, encoding="utf-8-sig")
    else:
        tracker_df = pd.DataFrame(columns=[
            "date", "race_code", "bamei", "bet_type",
            "bet_amount", "odds", "hit", "return_amount", "profit"
        ])

    # 日付フォーマット
    date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    # すでに同日のデータが入っていれば重複追記を防ぐ
    existing = tracker_df[tracker_df["date"] == date_fmt]
    if len(existing) > 0 and not dry_run:
        print(f"  ⚠️ {date_fmt} のデータは既に {len(existing)}件 登録済み。スキップ。")
        print(f"     強制上書きする場合は roi_tracker.csv から該当行を削除後に再実行。")
        return {}

    new_rows = []
    summary  = {
        "date":         date_fmt,
        "total_bets":   len(approved),
        "hits":         0,
        "total_invested": 0,
        "total_return": 0.0,
    }

    for bet in approved:
        rc        = bet["race_code"]
        bamei     = bet.get("bamei", "")
        umaban    = bet.get("umaban", 0)
        kelly_bet = bet.get("kelly_bet", 100)
        ticket    = bet.get("ticket_type", "単勝")

        race_results = results.get(rc, [])

        # 単勝の場合: 馬番または馬名で照合
        hit       = 0
        ret_amount = 0.0
        actual_odds = bet.get("odds", 0)

        if race_results:
            # 馬番または馬名でマッチ
            matched = next(
                (r for r in race_results
                 if r["umaban"] == umaban or r["bamei"] == bamei),
                None
            )
            if matched:
                hit = 1 if matched["chakujun"] == 1 else 0
                if matched["tansho_odds"] > 0:
                    actual_odds = matched["tansho_odds"]
                if hit:
                    ret_amount = kelly_bet * actual_odds
        else:
            hit = -1  # 結果取得失敗

        profit = ret_amount - kelly_bet if hit != -1 else 0

        if hit != -1:  # 結果が取得できたものだけ記録
            new_rows.append({
                "date":          date_fmt,
                "race_code":     rc,
                "bamei":         bamei,
                "bet_type":      ticket,
                "bet_amount":    kelly_bet,
                "odds":          actual_odds,
                "hit":           hit,
                "return_amount": ret_amount,
                "profit":        profit,
            })
            summary["total_invested"] += kelly_bet
            summary["total_return"]   += ret_amount
            if hit == 1:
                summary["hits"] += 1

    summary["roi"] = (
        summary["total_return"] / summary["total_invested"] * 100
        if summary["total_invested"] > 0 else 0
    )

    # ── 結果表示 ──────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f"  📊 {date_fmt} 結果集計")
    print(f"{'─'*55}")
    for row in new_rows:
        mark = "🎯" if row["hit"] == 1 else "✗ "
        print(f"  {mark} {row['race_code'][-6:]}  {row['bamei']:<12}  "
              f"{row['odds']:.1f}倍  "
              f"投資:{row['bet_amount']:,}円  "
              f"回収:{row['return_amount']:,.0f}円")
    print(f"{'─'*55}")
    print(f"  的中: {summary['hits']}/{summary['total_bets']}R"
          f"  投資: {summary['total_invested']:,}円"
          f"  回収: {summary['total_return']:,.0f}円"
          f"  ROI: {summary['roi']:.1f}%")
    print(f"{'─'*55}\n")

    # ── CSV 更新 ──────────────────────────────────────────
    if not dry_run and new_rows:
        new_df     = pd.DataFrame(new_rows)
        tracker_df = pd.concat([tracker_df, new_df], ignore_index=True)
        tracker_df.to_csv(tracker_path, index=False, encoding="utf-8-sig")
        print(f"  💾 roi_tracker.csv 更新: +{len(new_rows)}件")

        # bankroll.json も更新
        try:
            from pipeline.roi_tracker_12 import _sync_bankroll
            _sync_bankroll(tracker_df)
            bk_path = os.path.join(DATA_DIR, "bankroll.json")
            with open(bk_path, encoding="utf-8") as f:
                bk = json.load(f)
            print(f"  💰 バンクロール更新: {bk['current']:,.0f}円")
        except Exception as e:
            print(f"  ⚠️ bankroll 更新エラー: {e}")
    elif dry_run:
        print("  ℹ️ --dry-run モード: CSV は更新しません")

    return summary


# ─────────────────────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────────────────────

def run_result_fetcher(date_str: str = None, dry_run: bool = False) -> Dict:
    """run_all.py から呼び出されるエントリーポイント"""
    if date_str is None:
        date_str = datetime.now(tz=JST).strftime("%Y%m%d")

    print(f"\n[result_fetcher] {date_str} の結果取得開始...")
    results = fetch_all_results(date_str)
    if not results:
        print("[result_fetcher] 結果データなし")
        return {}
    summary = evaluate_picks(date_str, results, dry_run=dry_run)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="レース結果自動取得 & roi_tracker 更新")
    parser.add_argument("date", nargs="?", help="対象日 YYYYMMDD（省略時は今日）")
    parser.add_argument("--dry-run", action="store_true", help="CSV を更新しない確認モード")
    args = parser.parse_args()

    date_str = args.date or datetime.now(tz=JST).strftime("%Y%m%d")
    run_result_fetcher(date_str=date_str, dry_run=args.dry_run)
