"""
Playwright オッズスクレイパー
- NETKEIBA_SESSION_ID 不要・ヘッドレスブラウザで直接取得
- 今日の全レース一覧取得 → 単勝/複勝オッズ一括スクレイピング
- OddsSnapshot に格納 → odds_monitor_33.py の SHARP/STEAM 検知と連携
- run_all.py から呼び出し可能（Step 15g 代替）

依存: pip install playwright && python -m playwright install chromium
"""
import re
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR = "D:\\keiba_ai"


# ─────────────────────────────────────────────────────────────
# レースID一覧取得
# ─────────────────────────────────────────────────────────────

def fetch_today_race_ids(date_str: Optional[str] = None) -> List[str]:
    """
    netkeiba のレース一覧ページから今日の全レース ID を取得。
    date_str: 'YYYYMMDD' 形式（省略時は今日）
    """
    import httpx
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={date_str}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://race.netkeiba.com/',
    }
    try:
        r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        ids = list(dict.fromkeys(re.findall(r'race_id=(\d{12})', r.text)))
        return ids
    except Exception as e:
        print(f"  ⚠️ レース一覧取得失敗: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Playwright 単一レースのオッズ取得
# ─────────────────────────────────────────────────────────────

def _parse_odds_page(page) -> Dict[str, Dict]:
    """
    odds/index.html から単勝・複勝オッズを解析して返す。
    Returns: {馬名: {'tansho': float, 'fukusho_min': float, 'fukusho_max': float,
                     'ninki': int, 'umaban': int}}
    """
    result = {}
    try:
        rows = page.query_selector_all('table.RaceOdds_HorseList_Table tr')
        for row in rows:
            cells = row.query_selector_all('td')
            if len(cells) < 6:
                continue
            try:
                ninki   = int(cells[0].inner_text().strip())
                umaban  = int(cells[2].inner_text().strip())
                bamei   = cells[4].inner_text().strip().replace('\n', '')
                tansho  = float(cells[5].inner_text().strip())
                fuku_txt = cells[6].inner_text().strip()
                fuku_parts = re.findall(r'[\d.]+', fuku_txt)
                f_min = float(fuku_parts[0]) if fuku_parts else 0.0
                f_max = float(fuku_parts[1]) if len(fuku_parts) > 1 else f_min
                if bamei:
                    result[bamei] = {
                        'tansho':      tansho,
                        'fukusho_min': f_min,
                        'fukusho_max': f_max,
                        'ninki':       ninki,
                        'umaban':      umaban,
                    }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        pass
    return result


def scrape_race_odds(race_id: str, page, max_retries: int = 2) -> Dict:
    """
    1レースのオッズを Playwright で取得して返す。
    page: 呼び出し元で生成済みの playwright Page オブジェクト
    - wait_until='domcontentloaded' で networkidle タイムアウトを回避
    - タイムアウト 45秒 + 最大2回リトライ
    """
    url = f"https://race.netkeiba.com/odds/index.html?race_id={race_id}"
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            # オッズテーブルが描画されるまで最大5秒待機
            try:
                page.wait_for_selector('table.Odds', timeout=5000)
            except Exception:
                pass  # テーブルなしでも続行
            odds = _parse_odds_page(page)
            title = page.title()
            return {
                'race_id':   race_id,
                'title':     title,
                'timestamp': datetime.now().isoformat(),
                'horses':    odds,
                'n_horses':  len(odds),
            }
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2)  # リトライ前に2秒待機
    return {'race_id': race_id, 'error': str(last_err), 'horses': {}}


# ─────────────────────────────────────────────────────────────
# 全レース一括スクレイピング
# ─────────────────────────────────────────────────────────────

def scrape_all_races(date_str: Optional[str] = None,
                     max_races: int = 36,
                     interval_sec: float = 1.0,
                     headless: bool = True) -> List[Dict]:
    """
    今日の全レースのオッズを一括取得する。
    Returns: [{'race_id', 'title', 'horses': {馬名: {...}}, ...}, ...]
    """
    from playwright.sync_api import sync_playwright

    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    print(f"  📅 対象日: {date_str}")
    race_ids = fetch_today_race_ids(date_str)
    if not race_ids:
        print("  ⚠️ レースなし")
        return []
    race_ids = race_ids[:max_races]
    print(f"  🏇 {len(race_ids)}R 取得開始...")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for i, race_id in enumerate(race_ids, 1):
            data = scrape_race_odds(race_id, page)
            results.append(data)
            n = data['n_horses'] if 'n_horses' in data else 0
            err = f" ⚠️ {data['error']}" if 'error' in data else f" ({n}頭)"
            print(f"  [{i:2d}/{len(race_ids)}] {race_id}{err}")
            if interval_sec > 0:
                time.sleep(interval_sec)

        browser.close()

    return results


# ─────────────────────────────────────────────────────────────
# SHARP/STEAM 検知（2回取得の差分）
# ─────────────────────────────────────────────────────────────

def detect_movements(snapshot1: List[Dict], snapshot2: List[Dict]) -> List[Dict]:
    """
    2つのスナップショットを比較して SHARP/STEAM シグナルを返す。
    odds_monitor_33.py の classify_movement と同じ基準を使用。
    """
    from pipeline.odds_monitor_33 import classify_movement, OddsMovement

    s1 = {r['race_id']: r['horses'] for r in snapshot1}
    s2 = {r['race_id']: r['horses'] for r in snapshot2}
    signals = []

    for race_id, horses2 in s2.items():
        horses1 = s1.get(race_id, {})
        for bamei, h2 in horses2.items():
            h1 = horses1.get(bamei)
            if not h1:
                continue
            od1 = h1['tansho']
            od2 = h2['tansho']
            if od1 <= 0:
                continue
            movement = classify_movement(od1, od2)
            pct = (od2 - od1) / od1 * 100
            if movement in (OddsMovement.SHARP, OddsMovement.STEAM):
                signals.append({
                    'race_id':  race_id,
                    'bamei':    bamei,
                    'umaban':   h2.get('umaban', 0),
                    'opening':  od1,
                    'current':  od2,
                    'pct':      round(pct, 1),
                    'movement': movement.value,
                })

    return sorted(signals, key=lambda x: abs(x['pct']), reverse=True)


# ─────────────────────────────────────────────────────────────
# リアルタイム監視ループ
# ─────────────────────────────────────────────────────────────

def realtime_monitor(date_str: Optional[str] = None,
                     cycles: int = 6,
                     interval_min: float = 10.0,
                     headless: bool = True) -> List[Dict]:
    """
    指定間隔でオッズを繰り返し取得し、SHARP/STEAM シグナルを表示。
    cycles: 繰り返し回数
    interval_min: 取得間隔（分）
    """
    print(f"\n  🔄 リアルタイム監視開始 ({cycles}回 × {interval_min}分間隔)")
    all_signals = []
    snapshot_prev = None

    for cycle in range(1, cycles + 1):
        print(f"\n  ── Cycle {cycle}/{cycles} [{datetime.now():%H:%M:%S}] ──")
        snapshot = scrape_all_races(date_str, headless=headless)

        if snapshot_prev is not None:
            signals = detect_movements(snapshot_prev, snapshot)
            if signals:
                print(f"  🚨 シグナル {len(signals)}件:")
                for s in signals:
                    icon = '🔥' if s['movement'] == 'SHARP' else '💨'
                    print(f"    {icon} [{s['race_id']}] {s['bamei']} "
                          f"{s['opening']:.1f}→{s['current']:.1f}倍 "
                          f"({s['pct']:+.1f}%) {s['movement']}")
                    all_signals.append(s)
            else:
                print("  ✅ シグナルなし")
        else:
            print(f"  📸 初回スナップショット取得完了 ({len(snapshot)}R)")

        snapshot_prev = snapshot

        if cycle < cycles:
            print(f"  ⏳ {interval_min}分後に再取得...")
            time.sleep(interval_min * 60)

    return all_signals


# ─────────────────────────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────────────────────────

def run_odds_scraper(date_str: Optional[str] = None,
                     monitor: bool = False) -> dict:
    print("\n" + "="*55)
    print("🕷️ Playwright オッズスクレイパー")
    print("="*55)

    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    if monitor:
        # リアルタイム監視モード
        signals = realtime_monitor(date_str, cycles=3, interval_min=10)
    else:
        # 一括取得モード
        results = scrape_all_races(date_str)

        if not results:
            return {}

        # 集計
        total = len(results)
        ok    = sum(1 for r in results if r.get('n_horses', 0) > 0)
        total_horses = sum(r.get('n_horses', 0) for r in results)

        print(f"\n  ✅ 取得完了: {ok}/{total}R  計{total_horses}頭")

        # 単勝1倍台の馬（断然人気）
        heavy_favs = [
            (r['race_id'], bamei, h['tansho'])
            for r in results
            for bamei, h in r.get('horses', {}).items()
            if h['tansho'] < 2.0 and h['ninki'] == 1
        ]
        if heavy_favs:
            print(f"\n  🎯 断然人気（1倍台）:")
            for rid, bamei, od in heavy_favs:
                print(f"    {rid} {bamei} {od:.1f}倍")

        # 穴馬候補（30倍以上 複勝圏内可能性）
        anabas = [
            (r['race_id'], bamei, h['tansho'], h['fukusho_min'])
            for r in results
            for bamei, h in r.get('horses', {}).items()
            if h['tansho'] >= 30.0
        ]
        print(f"\n  🕳️ 穴馬候補（単勝30倍以上）: {len(anabas)}頭")
        for rid, bamei, od, fmin in sorted(anabas, key=lambda x: -x[2])[:10]:
            print(f"    {rid} {bamei} 単勝{od:.0f}倍 複勝{fmin:.1f}〜倍")

        # 保存
        os.makedirs(f"{BASE_DIR}\\data", exist_ok=True)
        out_path = f"{BASE_DIR}\\data\\odds_snapshot_{date_str}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  💾 保存: {out_path}")

        signals = []

    return {
        'date':    date_str,
        'n_races': len(results) if not monitor else 0,
        'signals': signals,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date',    default=None, help='YYYYMMDD (default: today)')
    parser.add_argument('--monitor', action='store_true', help='リアルタイム監視モード')
    parser.add_argument('--show',    action='store_true', help='ブラウザを表示する')
    args = parser.parse_args()
    run_odds_scraper(args.date, monitor=args.monitor)
