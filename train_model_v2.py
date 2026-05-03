import psycopg2, pandas as pd, numpy as np, lightgbm as lgb, pathlib, warnings
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore")

DB=dict(host="localhost",port=5433,dbname="mykeibadb",user="postgres",password="")
MODEL_PATH=r"D:\keiba_ai\pipeline_v2\model_lgbm_v2.txt"
pathlib.Path(r"D:\keiba_ai\pipeline_v2\logs").mkdir(exist_ok=True)

print("="*60)
print("うまなり地蔵AI v2 - 血統・調教込みモデル学習")
print("="*60)

conn=psycopg2.connect(**DB)

print("\n[1/6] メインデータ取得中（1986-2025）...")
sql_main="""
SELECT u.race_code,u.kaisai_nen,u.kaisai_gappi,u.keibajo_code,u.race_bango,u.umaban,
    u.ketto_toroku_bango,u.barei,u.seibetsu_code,u.hinshu_code,u.kishu_code,
    u.kishu_minarai_code,u.chokyoshi_code,u.futan_juryo,u.bataiju,u.zogen_fugo,u.zogen_sa,
    u.tansho_odds,u.tansho_ninkijun,u.kakutei_chakujun,u.soha_time,u.kohan_3f,u.kohan_4f,
    u.corner4_juni,u.blinker_shiyo_kubun,u.ijo_kubun_code,
    r.kyori,r.track_code,r.tenko_code,r.shiba_babajotai_code,r.dirt_babajotai_code,r.toroku_tosu
FROM umagoto_race_joho u
JOIN race_shosai r ON u.race_code=r.race_code
WHERE u.data_kubun='7' AND u.kaisai_nen>='1986'
  AND u.kakutei_chakujun!='00' AND u.soha_time!='0000'
"""
df=pd.read_sql(sql_main,conn)
print(f"  取得: {len(df):,}行")

print("\n[2/6] 血統データ結合中...")
sql_blood="""
SELECT k.ketto_toroku_bango,
    k.ketto1_hanshoku_toroku_bango AS chichi_id,
    k.ketto2_hanshoku_toroku_bango AS haha_id,
    k.ketto3_hanshoku_toroku_bango AS bms_id
FROM kyosoba_master2 k
"""
blood=pd.read_sql(sql_blood,conn)
df=df.merge(blood,on="ketto_toroku_bango",how="left")
for col in ["chichi_id","haha_id","bms_id"]:
    df[col]=df[col].fillna("000000").str.strip()
    df[col+"_n"]=pd.Categorical(df[col]).codes
print(f"  血統結合後: {len(df):,}行 父:{df['chichi_id'].nunique():,}種 母父:{df['bms_id'].nunique():,}種")

print("\n[3/6] 調教データ集計中（坂路）...")
sql_hanro="""
SELECT ketto_toroku_bango,
    CASE WHEN time_gokei_4furlong~'^[0-9]+$' THEN CAST(time_gokei_4furlong AS INTEGER) ELSE NULL END AS f4,
    CASE WHEN lap_time_3furlong~'^[0-9]+$'   THEN CAST(lap_time_3furlong   AS INTEGER) ELSE NULL END AS lap3f,
    CASE WHEN lap_time_1furlong~'^[0-9]+$'   THEN CAST(lap_time_1furlong   AS INTEGER) ELSE NULL END AS lap1f
FROM hanro_chokyo WHERE data_kubun IN ('1','2') AND time_gokei_4furlong!='0000'
"""
hanro=pd.read_sql(sql_hanro,conn)
print(f"  坂路件数: {len(hanro):,}")
hanro_agg=hanro.groupby("ketto_toroku_bango").agg(
    hanro_f4_avg=("f4","mean"),hanro_f4_min=("f4","min"),
    hanro_lap3f_avg=("lap3f","mean"),hanro_lap1f_avg=("lap1f","mean"),
    hanro_count=("f4","count")).reset_index()
df=df.merge(hanro_agg,on="ketto_toroku_bango",how="left")

print("\n[3b/6] 調教データ集計中（ウッドチップ）...")
sql_wood="""
SELECT ketto_toroku_bango,
    CASE WHEN time_gokei_4furlong~'^[0-9]+$' THEN CAST(time_gokei_4furlong AS INTEGER) ELSE NULL END AS wood_f4,
    CASE WHEN laptime_3furlong~'^[0-9]+$'    THEN CAST(laptime_3furlong    AS INTEGER) ELSE NULL END AS wood_lap3f
FROM woodchip_chokyo WHERE data_kubun IN ('1','2') AND time_gokei_4furlong!='0000'
"""
wood=pd.read_sql(sql_wood,conn)
wood_agg=wood.groupby("ketto_toroku_bango").agg(
    wood_f4_avg=("wood_f4","mean"),wood_f4_min=("wood_f4","min"),
    wood_lap3f_avg=("wood_lap3f","mean"),wood_count=("wood_f4","count")).reset_index()
df=df.merge(wood_agg,on="ketto_toroku_bango",how="left")
conn.close()

print("\n[4/6] 特徴量生成中...")
def si(s,d=0):
    try: return int(str(s).strip()) if str(s).strip() not in ('','None','nan') else d
    except: return d

df["barei_n"]      =df["barei"].apply(si)
df["futan_n"]      =df["futan_juryo"].apply(lambda x:si(x)/10)
df["bataiju_n"]    =df["bataiju"].apply(si)
df["zogen_sa_n"]   =df["zogen_sa"].apply(si)
df["zogen_fugo_n"] =df["zogen_fugo"].apply(lambda x:-1 if str(x).strip()=="-" else 1)
df["bataiju_diff"] =df["zogen_sa_n"]*df["zogen_fugo_n"]
df["odds_n"]       =df["tansho_odds"].apply(lambda x:si(x)/10)
df["ninki_n"]      =df["tansho_ninkijun"].apply(si)
df["kyori_n"]      =df["kyori"].apply(si)
df["toroku_n"]     =df["toroku_tosu"].apply(si)
df["umaban_n"]     =df["umaban"].apply(si)
df["kohan3f_n"]    =df["kohan_3f"].apply(si)
df["kohan4f_n"]    =df["kohan_4f"].apply(si)
df["corner4_n"]    =df["corner4_juni"].apply(si)
df["minarai_n"]    =df["kishu_minarai_code"].apply(si)
df["blinker_n"]    =df["blinker_shiyo_kubun"].apply(si)
df["ijo_n"]        =df["ijo_kubun_code"].apply(si)
df["track_n"]      =df["track_code"].apply(si)
df["tenko_n"]      =df["tenko_code"].apply(si)
df["baba_shiba_n"] =df["shiba_babajotai_code"].apply(si)
df["baba_dirt_n"]  =df["dirt_babajotai_code"].apply(si)
df["keibajo_n"]    =df["keibajo_code"].apply(si)
df["race_bango_n"] =df["race_bango"].apply(si)
df["seibetsu_n"]   =df["seibetsu_code"].apply(si)
df["hinshu_n"]     =df["hinshu_code"].apply(si)
df["month"]        =df["kaisai_gappi"].apply(lambda x:si(str(x)[:2]))
df["year_int"]     =df["kaisai_nen"].apply(si)
df["win_flag"]     =(df["kakutei_chakujun"]=="01").astype(int)

for col in ["hanro_f4_avg","hanro_f4_min","hanro_lap3f_avg","hanro_lap1f_avg","hanro_count",
            "wood_f4_avg","wood_f4_min","wood_lap3f_avg","wood_count"]:
    df[col]=df[col].fillna(-1)

df=df.sort_values(["year_int","kaisai_gappi","race_code","umaban_n"])
df["win_flag"]=df["win_flag"].astype(int)
df["kishu_wins"] =df.groupby("kishu_code")["win_flag"].cumsum()-df["win_flag"]
df["kishu_rides"]=df.groupby("kishu_code").cumcount()
df["kishu_winrate"]=(df["kishu_wins"]/(df["kishu_rides"]+1)).fillna(0)
df["trainer_wins"] =df.groupby("chokyoshi_code")["win_flag"].cumsum()-df["win_flag"]
df["trainer_rides"]=df.groupby("chokyoshi_code").cumcount()
df["trainer_winrate"]=(df["trainer_wins"]/(df["trainer_rides"]+1)).fillna(0)
df["odds_rank"] =df.groupby("race_code")["odds_n"].rank()
df["futan_rank"]=df.groupby("race_code")["futan_n"].rank()

print("\n[5/6] 学習・検証分割...")
FEATURES=[
    "barei_n","seibetsu_n","hinshu_n","futan_n","bataiju_n","bataiju_diff",
    "minarai_n","blinker_n","ijo_n","odds_n","ninki_n","odds_rank",
    "kyori_n","track_n","tenko_n","baba_shiba_n","baba_dirt_n",
    "keibajo_n","race_bango_n","toroku_n","umaban_n","month",
    "kohan3f_n","kohan4f_n","corner4_n",
    "kishu_winrate","trainer_winrate","futan_rank",
    "chichi_id_n","haha_id_n","bms_id_n",
    "hanro_f4_avg","hanro_f4_min","hanro_lap3f_avg","hanro_lap1f_avg","hanro_count",
    "wood_f4_avg","wood_f4_min","wood_lap3f_avg","wood_count",
]
train=df[df["year_int"]<=2022].copy()
valid=df[(df["year_int"]>=2023)&(df["year_int"]<=2025)].copy()
test =df[df["year_int"]==2026].copy()
print(f"  学習: {len(train):,}行")
print(f"  検証: {len(valid):,}行")
print(f"  テスト(2026): {len(test):,}行")

params=dict(objective="binary",metric="auc",learning_rate=0.05,num_leaves=127,
    min_child_samples=50,feature_fraction=0.8,bagging_fraction=0.8,bagging_freq=5,
    verbose=-1,n_jobs=-1)
dtrain=lgb.Dataset(train[FEATURES],label=train["win_flag"])
dvalid=lgb.Dataset(valid[FEATURES],label=valid["win_flag"],reference=dtrain)
model=lgb.train(params,dtrain,num_boost_round=2000,valid_sets=[dvalid],
    callbacks=[lgb.early_stopping(100,verbose=False),lgb.log_evaluation(200)])
print(f"  最適ラウンド: {model.best_iteration}")

print("\n[6/6] 評価...")
valid["pred"]=model.predict(valid[FEATURES])
test["pred"] =model.predict(test[FEATURES])
auc=roc_auc_score(valid["win_flag"],valid["pred"])
print(f"  AUC(2023-2025): {auc:.4f}")

def simulate(df_s,label):
    res=[]
    for rc,g in df_s.groupby("race_code"):
        if len(g)<2: continue
        top=g.loc[g["pred"].idxmax()]
        odds=top["odds_n"]
        win=int(top["win_flag"]==1)
        res.append({"win":win,"ret":odds*100 if win else 0})
    r=pd.DataFrame(res)
    races=len(r); wins=int(r["win"].sum())
    roi=r["ret"].sum()/races
    print(f"  [{label}] {races:,}R 的中:{wins:,}({wins/races*100:.1f}%) 回収率:{roi:.1f}%")

simulate(valid,"検証2023-25")
simulate(test, "テスト2026")
lastweek=valid[valid["kaisai_gappi"].between("0425","0501")]
if len(lastweek)>0:
    simulate(lastweek,"先週4/25-5/1")

imp=pd.DataFrame({"feature":FEATURES,"importance":model.feature_importance("gain")})
imp=imp.sort_values("importance",ascending=False).head(15)
print("\n  特徴量重要度TOP15:")
for _,row in imp.iterrows():
    print(f"    {row['feature']:30s}: {int(row['importance']):>10,}")

model.save_model(MODEL_PATH)
print(f"\n  モデル保存: {MODEL_PATH}")
print("完了")
