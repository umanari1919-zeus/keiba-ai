"""
当日出馬表フェッチャー
- netkeiba から当日の出馬表をスクレイピング
- DB（kyosoba_master2, umagoto_race_joho, hanro_chokyo 等）と JOIN して特徴量を構築
- keiba_data_features.csv と同じカラム構造で today_entries_YYYYMMDD.csv を出力

依存: httpx, beautifulsoup4
"""
from __future__ import annotations

import argparse
import re
import os
import json
import time
import pathlib
import sys
from datetime import datetime
from typing import Optional, List, Dict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None
try:
    import pandas as pd
except ImportError:
    pd = None

from pipeline.config import BASE_DIR, DATA_DIR, DB_CONFIG


def check_runtime() -> list[str]:
    issues = []
    if psycopg2 is None:
        issues.append("psycopg2 が未インストールです")
    if pd is None:
        issues.append("pandas が未インストールです")
    try:
        import httpx  # noqa: F401
    except ImportError:
        issues.append("httpx が未インストールです")
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        issues.append("beautifulsoup4 が未インストールです")
    nicks_path = os.path.join(BASE_DIR, "pedigree_output", "nicks_feature.csv")
    if not os.path.exists(nicks_path):
        issues.append(f"nicks特徴量なし: {nicks_path}")
    return issues

KEIBAJO_JV = {
    "01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京",
    "06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉",
    "30":"門別","31":"盛岡","32":"水沢","33":"上山","34":"福島",
    "35":"新潟","36":"足利","37":"宇都宮","38":"高崎","39":"浦和",
    "40":"船橋","41":"大井","42":"川崎","43":"金沢","44":"笠松",
    "45":"名古屋","46":"中京","47":"園田","48":"姫路","49":"福山",
    "50":"高知","51":"佐賀","52":"荒尾","53":"中津","58":"帯広",
}

# netkeiba 競馬場名 → JV コード
KEIBAJO_NAME2CODE = {v: k for k, v in KEIBAJO_JV.items()}
# 追加マッピング（略称）
KEIBAJO_NAME2CODE.update({
    "福島": "03", "新潟": "04", "東京": "05", "中山": "06",
    "中京": "07", "京都": "08", "阪神": "09", "小倉": "10",
    "札幌": "01", "函館": "02",
})

def _db_query(sql: str, params=None) -> List[Dict]:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 が未インストールのため DB 問い合わせできません")
    last_err = None
    for attempt in range(1, 4):
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params or [])
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise last_err


def _get_http(url: str) -> str:
    import httpx
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://race.netkeiba.com/",
    }
    r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
    return r.content.decode("euc-jp", errors="replace")


def fetch_race_ids(date_str: str) -> List[str]:
    """netkeiba から指定日のレース ID 一覧を取得"""
    try:
        from pipeline.odds_scraper_36 import fetch_today_race_ids
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from pipeline.odds_scraper_36 import fetch_today_race_ids
    return fetch_today_race_ids(date_str)


def parse_shutsuba_page(race_id: str) -> Dict:
    """
    netkeiba 出馬表ページをパースして馬ごとの dict リストを返す。
    返値: {
        "race_id": str,         # netkeiba 12桁
        "keibajo": str,         # 競馬場名
        "kyori": int,
        "track": str,           # 芝/ダート
        "tenko": str,           # 天候
        "baba": str,            # 馬場状態
        "horses": [...]
    }
    """
    from bs4 import BeautifulSoup

    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    html = _get_http(url)
    soup = BeautifulSoup(html, "html.parser")

    # ── レース情報 ────────────────────────────
    rd1 = soup.find("div", class_="RaceData01")
    rd1_text = rd1.get_text(" ", strip=True) if rd1 else ""

    # 距離・馬場種別
    kyori = 0
    track = ""
    m = re.search(r"[ダ芝障](\d{3,4})m", rd1_text.replace(" ", ""))
    if m:
        # 文字の前が track
        idx = rd1_text.find(m.group(0))
        ch = rd1_text[idx] if idx >= 0 else ""
        track = {"ダ": "dirt", "芝": "turf", "障": "jump"}.get(ch, "")
        kyori = int(m.group(1))

    # 天候・馬場
    tenko = ""
    baba  = ""
    m2 = re.search(r"天候[:：]\s*(\S+)", rd1_text)
    if m2: tenko = m2.group(1)
    m3 = re.search(r"馬場[:：]\s*(\S+)", rd1_text)
    if m3: baba = m3.group(1)

    # 競馬場名（タイトルから）
    title_el = soup.find("title")
    title    = title_el.get_text() if title_el else ""
    keibajo  = ""
    for name in ["札幌","函館","福島","新潟","東京","中山","中京","京都","阪神","小倉"]:
        if name in title:
            keibajo = name
            break

    # ── 馬一覧 ───────────────────────────────
    horses = []
    for row in soup.find_all("tr", class_="HorseList"):
        tds = row.find_all("td")
        if len(tds) < 10:
            continue

        # 馬名・血統番号
        horse_link = row.find("a", href=re.compile(r"/horse/"))
        ketto = re.search(r"/horse/(\d+)", horse_link["href"]).group(1) if horse_link else ""
        bamei = tds[3].get_text(strip=True)

        # 性齢: 牡3 → seibetsu=牡, barei=3
        barei_raw = tds[4].get_text(strip=True)
        seibetsu  = barei_raw[0] if barei_raw else ""
        barei     = int(re.sub(r"\D", "", barei_raw) or "0")

        # 馬体重
        weight_raw = tds[8].get_text(strip=True)  # e.g. "424(-2)"
        bataiju, zogen_sa, zogen_fugo = 0, 0, ""
        wm = re.match(r"(\d+)\(([+-]?\d+)\)", weight_raw)
        if wm:
            bataiju  = int(wm.group(1))
            diff     = int(wm.group(2))
            zogen_sa = abs(diff)
            zogen_fugo = "+" if diff >= 0 else "-"

        # オッズ（まだ確定していない場合は 0）
        odds_raw = tds[9].get_text(strip=True).replace(",", "").replace("---.-", "0")
        odds = float(odds_raw) if odds_raw.replace(".", "").isdigit() else 0.0

        horses.append({
            "umaban":     int(tds[1].get_text(strip=True) or "0"),
            "wakuban":    int(tds[0].get_text(strip=True) or "0"),
            "bamei":      bamei,
            "ketto_toroku_bango": ketto,
            "seibetsu":   seibetsu,
            "barei":      barei,
            "futan_juryo": float(tds[5].get_text(strip=True) or "0"),
            "kishumei_ryakusho":    tds[6].get_text(strip=True),
            "chokyoshimei_ryakusho": tds[7].get_text(strip=True),
            "bataiju":    bataiju,
            "zogen_sa":   zogen_sa,
            "zogen_fugo": zogen_fugo,
            "tansho_odds": odds * 10,  # JV 形式（10倍スケール）
        })

    return {
        "race_id":  race_id,
        "keibajo":  keibajo,
        "kyori":    kyori,
        "track":    track,
        "tenko":    tenko,
        "baba":     baba,
        "horses":   horses,
    }


def _build_horse_history() -> pd.DataFrame:
    """umagoto_race_joho から馬ごとの集計＋直近特徴量を取得"""
    sql = """
        WITH base AS (
            SELECT
                ketto_toroku_bango,
                race_code,
                kakutei_chakujun::int AS chakujun,
                kyakushitsu_hantei,
                kaisai_nen,
                kaisai_gappi,
                ROW_NUMBER() OVER (PARTITION BY ketto_toroku_bango ORDER BY race_code DESC) AS rn
            FROM umagoto_race_joho
            WHERE kakutei_chakujun ~ '^[0-9]+$'
              AND kakutei_chakujun::int > 0
        )
        SELECT
            ketto_toroku_bango,
            COUNT(*) AS total_races,
            SUM(CASE WHEN chakujun=1 THEN 1 ELSE 0 END) AS win_count,
            SUM(CASE WHEN chakujun=1 THEN 1 ELSE 0 END)::float / COUNT(*) AS win_rate,
            SUM(CASE WHEN chakujun=1 THEN 1 ELSE 0 END) AS sogo_1chaku,
            SUM(CASE WHEN chakujun<=2 THEN 1 ELSE 0 END) AS sogo_2chaku,
            SUM(CASE WHEN chakujun<=3 THEN 1 ELSE 0 END) AS sogo_3chaku,
            SUM(CASE WHEN chakujun=1 THEN 1 ELSE 0 END)::float / COUNT(*) AS sogo_win_rate,
            COUNT(*) AS sogo_total,
            -- 直近3走平均
            AVG(CASE WHEN rn<=3 THEN chakujun END) AS past3_avg_chakujun,
            -- 直近1走
            MAX(CASE WHEN rn=1 THEN chakujun END) AS prev_chakujun,
            -- 脚質
            AVG(CASE WHEN kyakushitsu_hantei='逃' THEN 1 ELSE 0 END) AS kyakushitsu_keiko_nige,
            AVG(CASE WHEN kyakushitsu_hantei='先' THEN 1 ELSE 0 END) AS kyakushitsu_keiko_senko,
            AVG(CASE WHEN kyakushitsu_hantei='差' THEN 1 ELSE 0 END) AS kyakushitsu_keiko_sashi,
            AVG(CASE WHEN kyakushitsu_hantei='追' THEN 1 ELSE 0 END) AS kyakushitsu_keiko_oikomi,
            (ARRAY_AGG(kyakushitsu_hantei ORDER BY race_code DESC))[1] AS kyakushitsu_hantei,
            -- 最終出走日
            MAX(kaisai_nen || kaisai_gappi) AS last_race_date
        FROM base
        GROUP BY ketto_toroku_bango
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ketto_toroku_bango")
    # 最終出走からの週数を計算
    from datetime import datetime
    today = datetime.now()
    def _weeks(d):
        try:
            dt = datetime.strptime(str(d), "%Y%m%d")
            return max(0, (today - dt).days // 7)
        except:
            return 0
    df["weeks_since_last_race"] = df["last_race_date"].apply(_weeks)
    return df


def _build_prev_race_features() -> pd.DataFrame:
    """
    前走情報: 各馬の直近1走の着順・競馬場・距離・グレード・騎手変更フラグを取得。
    data_fetch_01.py と同じ派生特徴量を再現する。
    """
    sql = """
        WITH ordered AS (
            SELECT
                u.ketto_toroku_bango,
                u.kishu_code,
                u.kakutei_chakujun::int AS chakujun,
                u.keibajo_code,
                r.kyori,
                r.grade_code,
                u.kaisai_nen || u.kaisai_gappi AS race_date,
                ROW_NUMBER() OVER (
                    PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code DESC
                ) AS rn,
                LAG(u.kishu_code) OVER (
                    PARTITION BY u.ketto_toroku_bango ORDER BY u.race_code DESC
                ) AS next_kishu_code
            FROM umagoto_race_joho u
            JOIN race_shosai r ON u.race_code = r.race_code
            WHERE u.kakutei_chakujun ~ '^[0-9]+'
        )
        SELECT
            ketto_toroku_bango,
            MAX(CASE WHEN rn=1 THEN chakujun END) AS prev_chakujun,
            MAX(CASE WHEN rn=1 THEN keibajo_code END) AS prev_keibajo,
            MAX(CASE WHEN rn=1 THEN kyori END)::int   AS prev_kyori,
            MAX(CASE WHEN rn=1 THEN grade_code END)   AS prev_grade,
            -- 騎手変更: 直近1走の騎手 ≠ 直近2走の騎手
            MAX(CASE WHEN rn=1 AND kishu_code IS DISTINCT FROM next_kishu_code
                     THEN 1 ELSE 0 END) AS kishu_change
        FROM ordered
        WHERE rn <= 2
        GROUP BY ketto_toroku_bango
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ketto_toroku_bango")
    # グレードスコア（JV-Data grade_code 数値コード対応）
    GRADE_SCORE = {
        # JV-Data 数値コード
        "11": 10, "12": 8, "13": 6, "14": 4, "15": 4,
        "16": 3, "17": 3, "18": 2, "19": 1, "20": 1, "21": 1,
        # 旧テキストコード互換
        "G1": 10, "GI": 10, "G2": 8, "GII": 8, "G3": 6, "GIII": 6,
        "OP": 4, "L": 4, "3勝": 3, "2勝": 2, "1勝": 1, "新馬": 1, "未勝利": 1, "障害": 5,
    }
    def _gs(g):
        g = str(g).strip() if g else ""
        return GRADE_SCORE.get(g, 1)
    df["prev_grade_score"] = df["prev_grade"].apply(_gs)
    return df


def _build_master_features() -> pd.DataFrame:
    """kyosoba_master2 から血統・成績特徴量を取得"""
    sql = """
        SELECT
            ketto_toroku_bango,
            ketto1_bamei AS chichi,
            ketto2_bamei AS haha,
            ketto3_bamei AS chichi_chichi,
            ketto5_bamei AS haha_chichi,
            -- 血統コード（繁殖登録番号を数値として使用、クロス特徴量用）
            COALESCE(ketto1_hanshoku_toroku_bango::bigint, 0) AS chichi_code,
            COALESCE(ketto2_hanshoku_toroku_bango::bigint, 0) AS haha_code,
            COALESCE(ketto3_hanshoku_toroku_bango::bigint, 0) AS chichi_chichi_code,
            shiba_ryo_1chaku, shiba_ryo_2chaku, shiba_ryo_3chaku,
            dirt_ryo_1chaku,  dirt_ryo_2chaku,  dirt_ryo_3chaku,
            shiba_short_1chaku, shiba_middle_1chaku, shiba_long_1chaku,
            dirt_short_1chaku,  dirt_middle_1chaku,  dirt_long_1chaku,
            kyakushitsu_keiko_nige, kyakushitsu_keiko_senko,
            kyakushitsu_keiko_sashi, kyakushitsu_keiko_oikomi
        FROM kyosoba_master2
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ketto_toroku_bango")
    # DBから文字列で返るカラムを数値に変換
    num_cols = [
        "shiba_ryo_1chaku", "shiba_ryo_2chaku", "shiba_ryo_3chaku",
        "dirt_ryo_1chaku", "dirt_ryo_2chaku", "dirt_ryo_3chaku",
        "shiba_short_1chaku", "shiba_middle_1chaku", "shiba_long_1chaku",
        "dirt_short_1chaku", "dirt_middle_1chaku", "dirt_long_1chaku",
        "kyakushitsu_keiko_nige", "kyakushitsu_keiko_senko",
        "kyakushitsu_keiko_sashi", "kyakushitsu_keiko_oikomi",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    # 馬場適性勝率を計算（feature_eng_02.py と同じ式）
    df["shiba_win_rate"] = df["shiba_ryo_1chaku"] / (
        df["shiba_ryo_1chaku"] + df["shiba_ryo_2chaku"] + df["shiba_ryo_3chaku"] + 1
    )
    df["dirt_win_rate"] = df["dirt_ryo_1chaku"] / (
        df["dirt_ryo_1chaku"] + df["dirt_ryo_2chaku"] + df["dirt_ryo_3chaku"] + 1
    )
    df["short_win_rate"]  = df["shiba_short_1chaku"] + df["dirt_short_1chaku"]
    df["middle_win_rate"] = df["shiba_middle_1chaku"] + df["dirt_middle_1chaku"]
    df["long_win_rate"]   = df["shiba_long_1chaku"] + df["dirt_long_1chaku"]
    return df


def _build_kishu_features() -> pd.DataFrame:
    """
    騎手コード・勝率を kanji 名でインデックス化。
    kishu_master.kishumei（漢字）→ kishu_code → umagoto_race_joho で勝率計算。
    netkeiba スクレイパーは漢字名を取得するのでこれが最も正確にマッチする。
    スペース・全角スペースを除去してノーマライズする。
    """
    sql = """
        SELECT
            km.kishu_code,
            km.kishumei,
            COUNT(u.*) AS kishu_total,
            SUM(CASE WHEN u.kakutei_chakujun='1' THEN 1 ELSE 0 END)::float
              / NULLIF(COUNT(u.*), 0) AS kishu_win_rate
        FROM kishu_master km
        JOIN umagoto_race_joho u ON u.kishu_code = km.kishu_code
        WHERE u.kakutei_chakujun ~ '^[0-9]+$'
          AND u.kakutei_chakujun::int > 0
          AND km.kishumei IS NOT NULL
          AND km.kishumei != ''
          AND km.kishu_code ~ '^[0-9]+$'
        GROUP BY km.kishu_code, km.kishumei
        HAVING COUNT(u.*) >= 10
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["kishu_code"] = pd.to_numeric(df["kishu_code"], errors="coerce").fillna(0).astype(int)
    # スペース除去でノーマライズ（JV は「姓　名」形式でスペースが入ることがある）
    # PyArrow \u306e RE2 \u306f \u \u30a8\u30b9\u30b1\u30fc\u30d7\u975e\u5bfe\u5fdc\u306e\u305f\u3081 re.sub \u3067\u51e6\u7406
    df["kishumei_norm"] = df["kishumei"].apply(
        lambda x: re.sub(r"[\s\u3000]+", "", x) if isinstance(x, str) else ""
    )
    df = df.drop_duplicates("kishumei_norm")
    return df.set_index("kishumei_norm")


def _build_kishu_keibajo_features() -> pd.DataFrame:
    """騎手×競馬場別勝率を (kishu_code, keibajo_code) でインデックス化"""
    sql = """
        SELECT
            kishu_code,
            keibajo_code,
            SUM(CASE WHEN kakutei_chakujun='1' THEN 1 ELSE 0 END)::float
              / NULLIF(COUNT(*), 0) AS kishu_keibajo_win_rate
        FROM umagoto_race_joho
        WHERE kakutei_chakujun ~ '^[0-9]+$'
          AND kakutei_chakujun::int > 0
          AND kishu_code IS NOT NULL
          AND kishu_code ~ '^[0-9]+$'
        GROUP BY kishu_code, keibajo_code
        HAVING COUNT(*) >= 5
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["key"] = df["kishu_code"].astype(str) + "_" + df["keibajo_code"].astype(str)
    return df.set_index("key")["kishu_keibajo_win_rate"]


def _build_chokyoshi_features() -> pd.DataFrame:
    """調教師コード・勝率を chokyoshimei でインデックス化"""
    sql = """
        SELECT
            chokyoshi_code,
            chokyoshimei_ryakusho,
            COUNT(*) AS cho_total,
            SUM(CASE WHEN kakutei_chakujun='1' THEN 1 ELSE 0 END)::float
              / COUNT(*) AS chokyoshi_win_rate
        FROM umagoto_race_joho
        WHERE kakutei_chakujun ~ '^[0-9]+$'
          AND kakutei_chakujun::int > 0
          AND chokyoshimei_ryakusho IS NOT NULL
          AND chokyoshimei_ryakusho != ''
          AND chokyoshi_code IS NOT NULL
          AND chokyoshi_code ~ '^[0-9]+$'
        GROUP BY chokyoshi_code, chokyoshimei_ryakusho
        HAVING COUNT(*) >= 5
    """
    rows = _db_query(sql)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values("cho_total", ascending=False).drop_duplicates("chokyoshimei_ryakusho")
    df["chokyoshi_code"] = pd.to_numeric(df["chokyoshi_code"], errors="coerce").fillna(0).astype(int)
    return df.set_index("chokyoshimei_ryakusho")


def _build_chokyo_features() -> pd.DataFrame:
    """hanro_chokyo から直近調教タイムを取得"""
    sql = """
        SELECT DISTINCT ON (ketto_toroku_bango)
            ketto_toroku_bango,
            time_gokei_3furlong AS chokyo_3f,
            lap_time_3furlong   AS chokyo_lap_3f,
            lap_time_1furlong   AS chokyo_lap_1f,
            time_gokei_4furlong AS chokyo_4f
        FROM hanro_chokyo
        WHERE time_gokei_3furlong > '0'
        ORDER BY ketto_toroku_bango, chokyo_nengappi DESC
    """
    rows = _db_query(sql)
    return pd.DataFrame(rows).set_index("ketto_toroku_bango") if rows else pd.DataFrame()


def net12_to_jv16(race_id: str, date_str: str) -> str:
    """
    netkeiba 12桁 → JV 16桁
    race_id: YYYYKKAANNRR
    date_str: YYYYMMDD
    → YYYYMMDDKKAANNRR
    """
    return date_str + race_id[4:]


def build_today_entries(date_str: Optional[str] = None) -> pd.DataFrame:
    """
    当日の全出馬表を取得して特徴量付き DataFrame を返す。
    date_str: 'YYYYMMDD'（省略時は今日）
    """
    if pd is None:
        raise RuntimeError("pandas が未インストールのため shutsuba_fetch を実行できません")
    if psycopg2 is None:
        raise RuntimeError("psycopg2 が未インストールのため shutsuba_fetch を実行できません")

    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    print(f"[shutsuba_fetch] {date_str} 出馬表取得開始...")

    race_ids = fetch_race_ids(date_str)
    if not race_ids:
        print("[shutsuba_fetch] レースIDが取得できませんでした")
        return pd.DataFrame()

    print(f"[shutsuba_fetch] {len(race_ids)}R 取得")

    # DB から特徴量マスタを事前ロード
    print("[shutsuba_fetch] DB 特徴量ロード中...")
    master_df        = _build_master_features()
    hist_df          = _build_horse_history()
    chokyo_df        = _build_chokyo_features()
    kishu_df         = _build_kishu_features()
    kishu_keibajo_sr = _build_kishu_keibajo_features()
    chokyoshi_df     = _build_chokyoshi_features()
    prev_df          = _build_prev_race_features()  # 前走情報（新規追加）

    # ニックス特徴量
    nicks_path = os.path.join(BASE_DIR, "pedigree_output", "nicks_feature.csv")
    try:
        nicks_df = pd.read_csv(nicks_path, encoding="utf-8-sig")
        nick_cols = ["chichi", "haha_chichi", "nick_index", "nick_roi", "nick_win_rate", "nick_place_rate"]
        nicks_df = nicks_df[nick_cols].drop_duplicates(subset=["chichi", "haha_chichi"])
        nicks_map = {(r["chichi"], r["haha_chichi"]): r for _, r in nicks_df.iterrows()}
    except Exception:
        nicks_map = {}

    all_rows = []
    for i, race_id in enumerate(race_ids, 1):
        try:
            race = parse_shutsuba_page(race_id)
            jv16 = net12_to_jv16(race_id, date_str)

            keibajo_code = KEIBAJO_NAME2CODE.get(race["keibajo"], "00")
            kyori  = race["kyori"]
            track  = race["track"]
            # jv16 = YYYYMMDD KK AA NN RR  (8+2+2+2+2=16)
            kaisai_kai     = int(jv16[10:12]) if len(jv16) == 16 else 1
            kaisai_nichime = int(jv16[12:14]) if len(jv16) == 16 else 1
            track_code_int = 10 if track == "dirt" else 11 if track == "turf" else 51

            for h in race["horses"]:
                ketto = h["ketto_toroku_bango"]
                row = {
                    # レース識別
                    "race_code":      jv16,
                    "kaisai_nen":     int(date_str[:4]),
                    "kaisai_gappi":   date_str[4:],
                    "kaisai_kai":     kaisai_kai,
                    "kaisai_nichime": kaisai_nichime,
                    "keibajo_code":   keibajo_code,
                    # 馬基本情報
                    "umaban":         h["umaban"],
                    "wakuban":        h["wakuban"],
                    "bamei":          h["bamei"],
                    "ketto_toroku_bango": ketto,
                    "barei":          h["barei"],
                    "seibetsu_code":  h["seibetsu"],
                    "kishumei_ryakusho": h["kishumei_ryakusho"],
                    "futan_juryo":    h["futan_juryo"],
                    "futan_henka":    0,  # 前走斤量不明なので 0
                    "bataiju":        h["bataiju"],
                    "zogen_sa":       h["zogen_sa"],
                    "zogen_fugo":     h["zogen_fugo"],
                    "tansho_odds":    h["tansho_odds"],
                    "tansho_ninkijun": 0,  # 確定前
                    # レース条件
                    "kyori":          kyori,
                    "track_code":     track_code_int,
                    "tenko_code":     1 if race["tenko"] in ["晴","薄曇"] else 2,
                    "shiba_babajotai_code": int(_baba_code(race["baba"])) if track == "turf" else 0,
                    "dirt_babajotai_code":  int(_baba_code(race["baba"])) if track == "dirt" else 0,
                    "shusso_tosu":    len(race["horses"]),
                    # 結果は未確定
                    "kakutei_chakujun": 0,
                    "kyakushitsu_hantei": "",
                    # デフォルト
                    "kishu_code": 0, "chokyoshi_code": 0,
                    "kishu_win_rate": 0.0, "kishu_keibajo_win_rate": 0.0,
                    "chokyoshi_win_rate": 0.0,
                    "chichi_code": 0, "haha_code": 0, "chichi_chichi_code": 0,
                    "nick_index": 1.0, "nick_roi": 1.0,
                    "nick_win_rate": 0.0, "nick_place_rate": 0.0,
                }

                # 血統・マスタ特徴量
                if ketto in master_df.index:
                    m = master_df.loc[ketto]
                    for col in master_df.columns:
                        row[col] = m[col]

                # 過去成績集計（全カラム一括マージ）
                if ketto in hist_df.index:
                    hh = hist_df.loc[ketto]
                    for col in hist_df.columns:
                        row[col] = hh[col]

                # 調教タイム
                if ketto in chokyo_df.index:
                    cc = chokyo_df.loc[ketto]
                    for col in chokyo_df.columns:
                        row[col] = cc[col]

                # 前走情報（新規追加）
                if not prev_df.empty and ketto in prev_df.index:
                    pv = prev_df.loc[ketto]
                    row["prev_chakujun"]    = int(pv.get("prev_chakujun", 0) or 0)
                    row["prev_keibajo"]     = str(pv.get("prev_keibajo", "") or "")
                    row["prev_kyori"]       = int(pv.get("prev_kyori", 0) or 0)
                    row["prev_grade_score"] = int(pv.get("prev_grade_score", 1) or 1)
                    row["kishu_change"]     = int(pv.get("kishu_change", 0) or 0)
                else:
                    row.setdefault("prev_chakujun", 0)
                    row.setdefault("prev_keibajo", "")
                    row.setdefault("prev_kyori", 0)
                    row.setdefault("prev_grade_score", 1)
                    row.setdefault("kishu_change", 0)

                # 騎手: kanji名をスペース除去してDBとマッチ
                kishu_raw  = h["kishumei_ryakusho"]
                kishu_norm = re.sub(r"[\s\u3000]+", "", kishu_raw)
                if kishu_norm in kishu_df.index:
                    row["kishu_win_rate"] = float(kishu_df.loc[kishu_norm, "kishu_win_rate"] or 0)
                    row["kishu_code"]     = int(kishu_df.loc[kishu_norm, "kishu_code"] or 0)
                kj_key = f"{row['kishu_code']}_{keibajo_code}"
                if not kishu_keibajo_sr.empty and kj_key in kishu_keibajo_sr.index:
                    row["kishu_keibajo_win_rate"] = float(kishu_keibajo_sr[kj_key] or 0)

                # 調教師: コード・勝率（scraper が chokyoshimei_ryakusho として格納）
                cho = h.get("chokyoshimei_ryakusho", "") or h.get("chokyoshimei", "")
                if cho and cho in chokyoshi_df.index:
                    row["chokyoshi_win_rate"] = float(chokyoshi_df.loc[cho, "chokyoshi_win_rate"] or 0)
                    row["chokyoshi_code"]     = int(chokyoshi_df.loc[cho, "chokyoshi_code"] or 0)

                # ニックス
                chichi_name = row.get("chichi", "")
                haha_chichi = row.get("haha_chichi", "")
                nick = nicks_map.get((chichi_name, haha_chichi))
                if nick is not None:
                    row["nick_index"]      = float(nick.get("nick_index", 1.0) or 1.0)
                    row["nick_roi"]        = float(nick.get("nick_roi", 1.0) or 1.0)
                    row["nick_win_rate"]   = float(nick.get("nick_win_rate", 0.0) or 0.0)
                    row["nick_place_rate"] = float(nick.get("nick_place_rate", 0.0) or 0.0)

                # 相互作用特徴量
                _ck  = int(row.get("chichi_code", 0) or 0)
                _hk  = int(row.get("haha_code", 0) or 0)
                _jk  = int(row.get("kishu_code", 0) or 0)
                _age = int(row.get("barei", 0) or 0)
                _wt  = int(row.get("bataiju", 0) or 0)
                _fl  = float(row.get("futan_juryo", 0) or 0)
                _ws  = float(row.get("weeks_since_last_race", 0) or 0)
                _kn  = float(row.get("kyakushitsu_keiko_nige", 0) or 0)
                _ks  = float(row.get("kyakushitsu_keiko_senko", 0) or 0)
                row["chichi_kyori"]  = _ck * kyori
                row["haha_kyori"]    = _hk * kyori
                row["chichi_track"]  = _ck * track_code_int
                row["haha_track"]    = _hk * track_code_int
                row["kishu_kyori"]   = _jk * kyori
                row["kishu_track"]   = _jk * track_code_int
                row["barei_kyori"]   = _age * kyori
                row["bataiju_kyori"] = _wt  * kyori
                row["weeks_barei"]   = _ws  * _age
                row["kaishi_nige"]   = kaisai_nichime * _kn
                row["kaishi_senko"]  = kaisai_nichime * _ks
                row["futan_barei"]   = _fl  * _age

                all_rows.append(row)

            time.sleep(0.3)
        except Exception as e:
            print(f"[shutsuba_fetch] {race_id} エラー: {e}")

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).fillna(0)
    print(f"[shutsuba_fetch] 完了: {len(df)}頭, {df['race_code'].nunique()}R")
    return df


def _baba_code(baba_str: str) -> str:
    return {"良": "1", "稍重": "2", "重": "3", "不良": "4"}.get(baba_str, "1")


def save_today_entries(date_str=None) -> str:
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    df = build_today_entries(date_str)
    if df.empty:
        print("[shutsuba_fetch] データなし、保存スキップ")
        return ""
    out = os.path.join(DATA_DIR, f"today_entries_{date_str}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    try:
        from pipeline.db_sync_42 import add_ingest_meta, write_snapshot
        snapshot = add_ingest_meta(df.assign(trade_date=date_str), source_name=f"shutsuba_fetch:{date_str}")
        ok = write_snapshot(
            snapshot,
            "today_entries_snapshot",
            if_exists="replace",
            source_name=f"shutsuba_fetch:{date_str}",
        )
        if ok:
            print(f"[shutsuba_fetch] DB同期: today_entries_snapshot ({date_str})")
    except Exception as e:
        print(f"[shutsuba_fetch] DB同期スキップ: {e}")
    print(f"[shutsuba_fetch] 保存: {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="当日出馬表フェッチャー")
    parser.add_argument("date", nargs="?", default=None, help="対象日 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="依存関係と補助ファイルだけ確認する")
    args, _ = parser.parse_known_args()

    if args.dry_run:
        issues = check_runtime()
        if issues:
            print("[shutsuba_fetch] dry-run: 要確認")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("[shutsuba_fetch] dry-run: 実行要件は概ね満たしています")
        raise SystemExit(0)

    save_today_entries(args.date)
