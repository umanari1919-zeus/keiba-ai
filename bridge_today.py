"""
bridge_today.py
今日のDBデータをexplainに流すブリッジスクリプト
predictions テーブルがない場合でも直接LLMに投げて結果を保存します
"""
import psycopg2, json, uuid, logging, sys, pathlib, urllib.request
from datetime import datetime

BASE=pathlib.Path(r"D:\keiba_ai\pipeline_v2")
(BASE/"logs").mkdir(exist_ok=True)
today=datetime.now().strftime("%Y%m%d")
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(BASE/f"logs/bridge_{today}.log",encoding="utf-8"),logging.StreamHandler(sys.stdout)])
log=logging.getLogger(__name__)

DB_CONFIG={"host":"localhost","port":5433,"dbname":"mykeibadb","user":"postgres","password":""}
OLLAMA_URL="http://localhost:11434/api/chat"
MODEL="qwen2.5:3b"
TRACE_ID=str(uuid.uuid4())
RUN_TAG=f"run_{today}_{uuid.uuid4().hex[:8]}"

KEIBAJO={
    "01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京",
    "06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉"
}
TRACK={
    "10":"芝","11":"芝","12":"芝","17":"ダ","18":"ダ","23":"芝","24":"ダ","56":"障"
}
TENKO={"1":"晴","2":"曇","3":"雨","4":"小雨","5":"雪","6":"小雪"}
BABA={"1":"良","2":"稍重","3":"重","4":"不良"}

SYSTEM_PROMPT="あなたは競馬予測AIの解説エージェントです。与えられたデータから競馬ファン向けの解説を日本語で生成します。必ずJSONのみ出力してください。"

def build_prompt(entry):
    return f"""以下のデータからJSONで解説を生成してください。

レース: {entry['race_code']} {entry['keibajo']} {entry['race_bango']}R
距離: {entry['kyori']}m {entry['track_type']} 天気:{entry['tenko']} 馬場:{entry['baba']}
馬番: {entry['umaban']} 馬名: {entry['bamei']}
騎手: {entry['kishu']} 斤量: {int(entry['futan_juryo'])/10:.1f}kg
単勝オッズ: {entry['odds']:.1f}倍 人気: {entry['ninki']}番人気

出力JSON:
{{
  "entry_id": "{entry['entry_id']}",
  "race_id": "{entry['race_code']}",
  "explanation_short": "X投稿用50文字以内の解説",
  "explanation_long": "note用150文字以上の詳細解説（根拠・展開・リスク・買い目）",
  "bet_recommendation": {{
    "type": "単勝 or 複勝 or ワイド",
    "selection": "{entry['umaban']}番",
    "stake_min": 最小額(整数),
    "stake_max": 最大額(整数),
    "rationale": "推奨理由"
  }},
  "confidence": 0.0から1.0,
  "requires_human_review": trueまたはfalse
}}"""

def call_ollama(prompt):
    payload=json.dumps({
        "model":MODEL,
        "messages":[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":prompt}
        ],
        "stream":False,
        "options":{"temperature":0.3,"num_predict":512}
    }).encode("utf-8")
    req=urllib.request.Request(OLLAMA_URL,data=payload,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]

def parse_json(text):
    text=text.strip()
    if "```" in text:
        lines=text.split("\n")
        cleaned,in_b=[],False
        for l in lines:
            if l.startswith("```"):
                in_b=not in_b
                continue
            cleaned.append(l)
        text="\n".join(cleaned).strip()
    return json.loads(text)

CREATE_EXPLANATIONS="""
CREATE TABLE IF NOT EXISTS explanations (
    id SERIAL PRIMARY KEY,
    entry_id TEXT,
    race_id TEXT,
    explanation_short TEXT,
    explanation_long TEXT,
    bet_type TEXT,
    bet_selection TEXT,
    stake_min INTEGER,
    stake_max INTEGER,
    bet_rationale TEXT,
    confidence FLOAT,
    uncertainty FLOAT DEFAULT 0.5,
    requires_human_review BOOLEAN DEFAULT TRUE,
    prompt_id TEXT,
    model_name TEXT,
    run_tag TEXT,
    trace_id TEXT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(entry_id, race_id, run_tag)
)
"""

def main():
    log.info("="*60)
    log.info("bridge_today.py 実行開始")
    log.info(f"  MODEL   : {MODEL}")
    log.info(f"  RUN_TAG : {RUN_TAG}")
    log.info("="*60)

    conn=psycopg2.connect(**DB_CONFIG)
    cur=conn.cursor()

    # explanationsテーブル作成
    cur.execute(CREATE_EXPLANATIONS)
    conn.commit()

    # 本日の出走馬を取得（人気上位3頭のみ：テスト用）
    cur.execute("""
        SELECT
            u.race_code,
            u.race_bango,
            u.umaban,
            u.bamei,
            u.kishumei_ryakusho,
            u.futan_juryo,
            u.keibajo_code,
            r.kyori,
            r.track_code,
            r.tenko_code,
            r.shiba_babajotai_code,
            COALESCE(CAST(o.odds AS FLOAT)/10, 0) AS odds,
            COALESCE(CAST(o.ninki AS INTEGER), 99) AS ninki
        FROM umagoto_race_joho u
        JOIN race_shosai r ON u.race_code=r.race_code
        LEFT JOIN odds1_tansho o ON u.race_code=o.race_code AND u.umaban=o.umaban
        WHERE u.kaisai_gappi='0502' AND u.kaisai_nen='2026'
          AND u.keibajo_code='05'
          AND u.race_bango IN ('01','11')
          AND COALESCE(CAST(o.ninki AS INTEGER),99) <= 3
        ORDER BY u.race_bango, CAST(o.ninki AS INTEGER)
    """)
    rows=cur.fetchall()
    log.info(f"処理対象: {len(rows)} 頭")

    ok=0
    ng=0
    for row in rows:
        race_code,race_bango,umaban,bamei,kishu,futan,kcode,kyori,track,tenko,baba,odds,ninki=row
        entry={
            "entry_id": f"{race_code}_{umaban}",
            "race_code": race_code,
            "race_bango": race_bango,
            "umaban": umaban,
            "bamei": bamei,
            "kishu": kishu,
            "futan_juryo": futan,
            "keibajo": KEIBAJO.get(kcode,"?"),
            "kyori": kyori,
            "track_type": TRACK.get(track,"?"),
            "tenko": TENKO.get(tenko,"?"),
            "baba": BABA.get(baba,"?"),
            "odds": odds,
            "ninki": ninki,
        }
        log.info(f"  処理中: {bamei}（{umaban}番）{odds:.1f}倍 {ninki}人気")

        try:
            prompt=build_prompt(entry)
            raw=call_ollama(prompt)
            parsed=parse_json(raw)
            bet=parsed.get("bet_recommendation",{})
            cur.execute("""
                INSERT INTO explanations
                    (entry_id,race_id,explanation_short,explanation_long,
                     bet_type,bet_selection,stake_min,stake_max,bet_rationale,
                     confidence,requires_human_review,model_name,run_tag,trace_id,raw_json)
                VALUES
                    (%(entry_id)s,%(race_id)s,%(short)s,%(long)s,
                     %(bt)s,%(bs)s,%(smin)s,%(smax)s,%(rat)s,
                     %(cf)s,%(rev)s,%(model)s,%(run)s,%(trace)s,%(raw)s)
                ON CONFLICT(entry_id,race_id,run_tag) DO UPDATE
                SET explanation_short=EXCLUDED.explanation_short,
                    confidence=EXCLUDED.confidence
            """,{
                "entry_id": entry["entry_id"],
                "race_id":  race_code,
                "short":    parsed.get("explanation_short",""),
                "long":     parsed.get("explanation_long",""),
                "bt":       bet.get("type",""),
                "bs":       bet.get("selection",""),
                "smin":     bet.get("stake_min",0),
                "smax":     bet.get("stake_max",0),
                "rat":      bet.get("rationale",""),
                "cf":       parsed.get("confidence",0.5),
                "rev":      parsed.get("requires_human_review",True),
                "model":    MODEL,
                "run":      RUN_TAG,
                "trace":    TRACE_ID,
                "raw":      json.dumps(parsed,ensure_ascii=False),
            })
            conn.commit()
            log.info(f"    ✅ 保存完了: {parsed.get('explanation_short','')[:40]}")
            ok+=1
        except Exception as e:
            log.error(f"    ❌ エラー: {e}")
            conn.rollback()
            ng+=1

    log.info("="*60)
    log.info(f"完了: 成功={ok} 失敗={ng}")
    log.info(f"ログ: {BASE}/logs/bridge_{today}.log")
    log.info("="*60)
    cur.close()
    conn.close()

if __name__=="__main__":
    main()
