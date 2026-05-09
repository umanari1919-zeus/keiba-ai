import smtplib
import os
import glob
import json
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from dotenv import load_dotenv
    load_dotenv("D:\\keiba_ai\\.env")
except ImportError:
    pass  # python-dotenv 未インストール時は .env を無視
from datetime import datetime, timedelta

from pipeline.config import BASE_DIR as BASE, DB_CONFIG
import logging

log = logging.getLogger(__name__)

_JYO = {
    '01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',
    '06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉',
    '30':'門別','35':'盛岡','36':'水沢','42':'浦和','43':'船橋',
    '44':'大井','45':'川崎','46':'金沢','47':'笠松','48':'名古屋',
    '50':'園田','51':'姫路','54':'高知','55':'佐賀','58':'帯広',
}

def _db():
    return psycopg2.connect(**DB_CONFIG)


def send_daily_report():
    """曜日に応じたメールを送信するエントリーポイント"""
    dow = datetime.now().weekday()  # 0=月, 1=火, ..., 6=日
    handlers = {
        0: _send_monday_results,
        1: _send_tuesday_tokubetsu,
        2: _send_wednesday_chokyo,
        3: _send_thursday_preview,
        4: _send_friday_odds,
    }
    if dow in handlers:
        return handlers[dow]()
    # 土日祝は send_pipeline_report で対応（scheduler側で制御）
    return send_pipeline_report({})

def send_notify(subject, body):
    """Gmail通知を送る"""
    
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    notify_to = os.getenv("NOTIFY_TO")
    
    if not all([gmail_address, gmail_password, notify_to]):
        log.warning(".envファイルを確認してください")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_address
        msg['To'] = notify_to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(gmail_address, gmail_password)
            smtp.send_message(msg)
        
        log.info("Gmail通知送信完了")
        return True

    except Exception as e:
        log.warning("送信失敗：%s", e)
        return False

# ─────────────────────────────────────────────
# 月曜: 先週末の成績振り返り
# ─────────────────────────────────────────────
def _send_monday_results():
    now  = datetime.now()
    last_sat = now - timedelta(days=(now.weekday() + 2) % 7 or 7)
    last_sun = last_sat + timedelta(days=1)
    sat_str  = last_sat.strftime("%Y%m%d")
    sun_str  = last_sun.strftime("%Y%m%d")

    # agent_picksから先週土日の実績を集計
    lines = []
    total_bet = total_return = hits = races = 0
    for d in (sat_str, sun_str):
        f = os.path.join(BASE, f"agent_picks_{d}.json")
        if not os.path.exists(f):
            continue
        picks = json.load(open(f, encoding="utf-8"))
        for b in picks.get("approved_bets", []):
            races += 1
            total_bet += b.get("kelly_bet", 100)
        label = f"{int(d[4:6])}/{int(d[6:8])}"
        n = len(picks.get("approved_bets", []))
        lines.append(f"  {label}: {n}件推奨")

    import pandas as pd
    try:
        sim = pd.read_csv(os.path.join(BASE, f"simulation_{now.year}.csv"),
                          on_bad_lines="skip")
        sim["mmdd"] = sim["race_code"].astype(str).str[4:8]
        weekend = sim[sim["mmdd"].isin([sat_str[4:], sun_str[4:]])]
        if not weekend.empty:
            hr  = weekend["hit"].mean() * 100
            roi = (weekend[weekend["hit"]==1]["odds"].sum() * 100
                   / max(len(weekend) * 100, 1))
            lines.append(f"\n  的中率: {hr:.1f}%  回収率: {roi:.1f}%")
    except Exception:
        pass

    body_picks = "\n".join(lines) if lines else "  データなし"
    now_str = now.strftime("%Y年%m月%d日")
    subject = f"🙏 うまなり地蔵AI 先週末の成績 {last_sat.strftime('%m/%d')}〜{last_sun.strftime('%m/%d')}"
    body = f"""
🙏 うまなり地蔵AI 週明けレポート
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}（月曜）

📊 先週末({last_sat.strftime('%m/%d')}〜{last_sun.strftime('%m/%d')})の成績
{body_picks}

━━━━━━━━━━━━━━━━━━━━━━
今週末も閻魔帳に刻まれた穴馬を追え🔥
うまなり地蔵AI研究所
"""
    return send_notify(subject, body)


# ─────────────────────────────────────────────
# 火曜: 特別登録馬（重賞候補）
# ─────────────────────────────────────────────
def _send_tuesday_tokubetsu():
    now     = datetime.now()
    # 今週土日のMMDD
    days_to_sat = (5 - now.weekday()) % 7 or 7
    this_sat = now + timedelta(days=days_to_sat)
    this_sun = this_sat + timedelta(days=1)
    sat_gappi = this_sat.strftime("%m%d")
    sun_gappi = this_sun.strftime("%m%d")

    lines = []
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT keibajo_code, kyosomei_hondai, kaisai_gappi
            FROM tokubetsu_torokuba
            WHERE kaisai_nen = %s
              AND kaisai_gappi IN (%s, %s)
            ORDER BY kaisai_gappi, keibajo_code
        """, (str(now.year), sat_gappi, sun_gappi))
        for keibajo, name, gappi in cur.fetchall():
            venue = _JYO.get(str(keibajo).zfill(2), keibajo)
            day   = f"{int(gappi[0:2])}/{int(gappi[2:4])}"
            lines.append(f"  {day} {venue} 「{name}」")
        conn.close()
    except Exception as e:
        lines.append(f"  DB取得エラー: {e}")

    body_races = "\n".join(lines) if lines else "  特別登録馬データなし（mykeibadb同期が必要かもしれません）"
    now_str = now.strftime("%Y年%m月%d日")
    subject = f"🙏 うまなり地蔵AI 今週末の重賞・特別戦 {this_sat.strftime('%m/%d')}〜{this_sun.strftime('%m/%d')}"
    body = f"""
🙏 うまなり地蔵AI 今週末レース情報
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}（火曜）

🏆 今週末({this_sat.strftime('%m/%d')}〜{this_sun.strftime('%m/%d')})の特別戦・重賞
{body_races}

━━━━━━━━━━━━━━━━━━━━━━
木曜以降にオッズ動向をお知らせします🔥
うまなり地蔵AI研究所
"""
    return send_notify(subject, body)


# ─────────────────────────────────────────────
# 水曜: 注目調教馬（坂路タイム上位）
# ─────────────────────────────────────────────
def _send_wednesday_chokyo():
    now  = datetime.now()
    week_ago = (now - timedelta(days=7)).strftime("%Y%m%d")

    lines = []
    try:
        conn = _db()
        cur  = conn.cursor()
        # 直近1週間の坂路調教上位馬（4F総合タイム良好順）
        cur.execute("""
            SELECT h.ketto_toroku_bango, m.bamei,
                   h.time_gokei_4furlong, h.lap_time_1furlong
            FROM hanro_chokyo h
            JOIN kyosoba_master2 m ON h.ketto_toroku_bango = m.ketto_toroku_bango
            WHERE h.chokyo_nengappi >= %s
              AND h.time_gokei_4furlong > 0
            ORDER BY h.time_gokei_4furlong ASC
            LIMIT 10
        """, (week_ago,))
        for bango, bamei, t4f, lap1 in cur.fetchall():
            lines.append(f"  {bamei}  4F:{t4f/10:.1f}秒  上がり1F:{lap1/10:.1f}秒")
        conn.close()
    except Exception as e:
        lines.append(f"  DB取得エラー: {e}")

    body_chokyo = "\n".join(lines) if lines else "  調教データなし"
    now_str = now.strftime("%Y年%m月%d日")
    subject = f"🙏 うまなり地蔵AI 今週の注目調教馬 {now.strftime('%m/%d')}"
    body = f"""
🙏 うまなり地蔵AI 調教注目馬レポート
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}（水曜）

🏋️ 坂路調教 今週タイム上位10頭
{body_chokyo}

━━━━━━━━━━━━━━━━━━━━━━
動ける状態の馬が本番でも走る🔥
うまなり地蔵AI研究所
"""
    return send_notify(subject, body)


# ─────────────────────────────────────────────
# 木曜: 今週末レース＋AI予告
# ─────────────────────────────────────────────
def _send_thursday_preview():
    now      = datetime.now()
    days_to_sat = (5 - now.weekday()) % 7 or 7
    this_sat = now + timedelta(days=days_to_sat)
    this_sun = this_sat + timedelta(days=1)
    sat_gappi = this_sat.strftime("%m%d")
    sun_gappi = this_sun.strftime("%m%d")

    lines = []
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT keibajo_code, COUNT(*) as race_cnt
            FROM race_shosai
            WHERE kaisai_nen = %s AND kaisai_gappi IN (%s, %s)
            GROUP BY keibajo_code, kaisai_gappi
            ORDER BY kaisai_gappi, keibajo_code
        """, (str(now.year), sat_gappi, sun_gappi))
        for keibajo, cnt in cur.fetchall():
            venue = _JYO.get(str(keibajo).zfill(2), keibajo)
            lines.append(f"  {venue}: {cnt}R")
        conn.close()
    except Exception as e:
        lines.append(f"  DB取得エラー: {e}")

    body_races = "\n".join(lines) if lines else "  出走データなし（金曜以降に確定）"
    now_str = now.strftime("%Y年%m月%d日")
    subject = f"🙏 うまなり地蔵AI 今週末プレビュー {this_sat.strftime('%m/%d')}〜{this_sun.strftime('%m/%d')}"
    body = f"""
🙏 うまなり地蔵AI 週末プレビュー
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}（木曜）

🏇 今週末({this_sat.strftime('%m/%d')}〜{this_sun.strftime('%m/%d')})の開催場・レース数
{body_races}

📌 明日（金曜）にオッズ動向をお知らせ
📌 当日朝（土日）に推奨ベットをお知らせ

━━━━━━━━━━━━━━━━━━━━━━
閻魔帳の解析は進んでいる🔥
うまなり地蔵AI研究所
"""
    return send_notify(subject, body)


# ─────────────────────────────────────────────
# 金曜: オッズ初期動向（1倍台・荒れ候補）
# ─────────────────────────────────────────────
def _send_friday_odds():
    now      = datetime.now()
    days_to_sat = (5 - now.weekday()) % 7 or 7
    this_sat = now + timedelta(days=days_to_sat)
    this_sun = this_sat + timedelta(days=1)
    sat_gappi = this_sat.strftime("%m%d")
    sun_gappi = this_sun.strftime("%m%d")

    tanban_lines = []   # 断然人気（1倍台）
    upset_lines  = []   # 荒れ候補（最低人気30倍超）
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT o.race_code, o.umaban, o.odds, o.ninki,
                   m.bamei, o.keibajo_code
            FROM odds1_tansho o
            LEFT JOIN kyosoba_master2 m ON o.ketto_toroku_bango = m.ketto_toroku_bango
            WHERE o.kaisai_nen = %s AND o.kaisai_gappi IN (%s, %s)
              AND o.ninki = 1
            ORDER BY o.odds ASC
            LIMIT 20
        """, (str(now.year), sat_gappi, sun_gappi))
        for rc, umaban, odds, ninki, bamei, keibajo in cur.fetchall():
            venue = _JYO.get(str(keibajo).zfill(2), keibajo)
            race  = f"{int(rc[4:6])}/{int(rc[6:8])} {venue}{rc[14:16].lstrip('0')}R"
            o_real = odds / 10
            if o_real < 2.0:
                tanban_lines.append(f"  {race} {umaban}番 {bamei or '?'} {o_real:.1f}倍（断然）")
        conn.close()
    except Exception as e:
        tanban_lines.append(f"  DB取得エラー: {e}")

    body_odds = "\n".join(tanban_lines) if tanban_lines else "  断然人気馬なし / データ未反映"
    now_str = now.strftime("%Y年%m月%d日")
    subject = f"🙏 うまなり地蔵AI 週末オッズ動向 {this_sat.strftime('%m/%d')}〜{this_sun.strftime('%m/%d')}"
    body = f"""
🙏 うまなり地蔵AI 週末オッズ動向
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}（金曜）

⚠️ 断然人気馬（AIが嫌う候補）
{body_odds}

📌 明日朝8時に推奨ベットをお知らせします

━━━━━━━━━━━━━━━━━━━━━━
人気馬を嫌って穴を狙え🔥
うまなり地蔵AI研究所
"""
    return send_notify(subject, body)


def _fmt_race(code: str) -> str:
    """race_code → '4/19 中山6R' 形式"""
    _JYO = {
        '01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',
        '06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉',
        '30':'門別','35':'盛岡','36':'水沢','42':'浦和','43':'船橋',
        '44':'大井','45':'川崎','46':'金沢','47':'笠松','48':'名古屋',
        '50':'園田','51':'姫路','54':'高知','55':'佐賀','58':'帯広',
    }
    s = str(code).strip()
    if len(s) != 16:
        return s
    mm, dd = s[4:6], s[6:8]
    jyo = _JYO.get(s[8:10], s[8:10])
    rno = s[14:16].lstrip('0') or '1'
    return f"{int(mm)}/{int(dd)} {jyo}{rno}R"


def send_pipeline_report(result):
    """本日のagent_picksから推奨ベットをメール通知"""
    import glob, json

    now      = datetime.now()
    now_str  = now.strftime('%Y年%m月%d日 %H:%M')
    date_str = now.strftime('%Y%m%d')
    subject  = f"🙏 うまなり地蔵AI 本日の推奨ベット {now.strftime('%m/%d')}"

    # 本日のagent_picksを読む（なければ最新）
    base    = "D:\\keiba_ai"
    pattern = os.path.join(base, f"agent_picks_{date_str}.json")
    files   = glob.glob(pattern) or sorted(
                  glob.glob(os.path.join(base, "agent_picks_*.json")), reverse=True
              )

    picks_date = date_str
    bets       = []
    rs         = {}
    if files:
        try:
            with open(files[0], encoding="utf-8") as f:
                picks = json.load(f)
            fname = os.path.basename(files[0])
            picks_date = fname.replace("agent_picks_", "").replace(".json", "")
            bets = picks.get("approved_bets", [])
            rs   = picks.get("risk_summary", {})
        except Exception:
            pass

    # ベット一覧テキスト
    if bets:
        bet_lines = []
        for i, b in enumerate(bets, 1):
            race  = _fmt_race(b.get("race_code", ""))
            uma   = f"{b['umaban']}番" if b.get("umaban") else ""
            bamei = b.get("bamei", "")
            odds  = b.get("odds", 0)
            ev    = b.get("expected_value", 0) * 100
            conf  = b.get("confidence", 0) * 100
            kelly = b.get("kelly_bet", 0)
            ticket= b.get("ticket_type", "単勝")
            bet_lines.append(
                f"  {i}. {race} {uma} {bamei}\n"
                f"     {ticket} {odds:.1f}倍  EV:{ev:+.0f}%  確信度:{conf:.0f}%  投入:{kelly:,}円"
            )
        bets_text = "\n".join(bet_lines)
    else:
        bets_text = "  本日の推奨ベットはありません"

    picks_label = f"※最新ファイル ({picks_date[:4]}/{picks_date[4:6]}/{picks_date[6:]})" \
                  if picks_date != date_str else ""

    body = f"""
🙏 うまなり地蔵AI 本日の推奨ベット
━━━━━━━━━━━━━━━━━━━━━━
📅 {now_str}  {picks_label}

🔥 推奨ベット（{len(bets)}件 / 総投入:{rs.get('total_allocated',0):,}円）
{bets_text}

📊 リスク状態
  DD乗数　：{rs.get('dd_multiplier', 1):.2f}x
  資金消費率：{rs.get('day_ratio', 0)*100:.1f}%

━━━━━━━━━━━━━━━━━━━━━━
データと閻魔大王の御加護を信じよ🔥
うまなり地蔵AI研究所
"""

    return send_notify(subject, body)

def send_test():
    """テスト通知"""
    subject = "🙏 うまなり地蔵AI テスト通知"
    body = """
うまなり地蔵AIからテスト通知です！

Gmail通知の設定が完了しました🎉

毎週土日の朝6時に
自動で予想レポートが届きます！

データと閻魔大王の御加護を信じよ🔥
"""
    return send_notify(subject, body)

if __name__ == "__main__":
    log.info("テスト通知を送信します...")
    send_test()