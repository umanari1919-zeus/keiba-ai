"""
調教師特性分析
- shussobetsu_chokyoshi (638列) から会場×距離×芝ダート別成績を集計
- 本年勝率 / 累計勝率 / 好不調フラグ
- 得意条件（芝/ダート/距離/会場）スコア
- 調教師×開催場の相性係数
- 東西所属（美浦/栗東）

出力特徴量（keiba_data_features.csv に追記）:
  trainer_win_rate_honnen     本年勝率
  trainer_win_rate_ruikei     通算勝率
  trainer_form_ratio          本年/通算比（>1=好調, <1=不調）
  trainer_shiba_rate          芝得意スコア (win_rate_shiba / overall)
  trainer_dirt_rate           ダート得意スコア
  trainer_venue_rate          当該会場での勝率
  trainer_dist_rate           当該距離帯での勝率
  trainer_venue_dist_rate     会場×距離帯のピンポイント勝率
  trainer_tozai               東西所属 (1=東/美浦, 2=西/栗東)
  trainer_hot_cold            好調度スコア (0〜1)
  trainer_specialty_score     得意条件一致スコア (0〜1)
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import os
from pipeline.config import CSV_FEATURES, DB_URL

# 会場コード → 列名プレフィックスのマップ
VENUE_MAP = {
    '01': 'sapporo', '02': 'hakodate', '03': 'fukushima', '04': 'niigata',
    '05': 'tokyo',   '06': 'nakayama', '07': 'chukyo',    '08': 'kyoto',
    '09': 'hanshin', '10': 'kokura',
}

# 距離カテゴリ（DB列の距離帯キーに対応）
DIST_KEYS = ['1200_ika', '1201_1400', '1401_1600', '1601_1800', '1801_2000',
             '2001_2200', '2201_2400', '2401_2800', '2801_ijo']


def _to_int(val) -> int:
    """文字列整数をintに変換、失敗時は0"""
    try:
        return int(str(val).strip())
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────
# 調教師マスタ（東西所属）
# ─────────────────────────────────────────────────────────────

def _load_trainer_master(engine) -> pd.DataFrame:
    q = text("""
        SELECT chokyoshi_code,
               chokyoshimei_ryakusho AS trainer_name,
               tozai_shozoku_code    AS tozai
        FROM chokyoshi_master
        WHERE massho_kubun = '0'
    """)
    try:
        with engine.connect() as conn:
            return pd.read_sql(q, conn)
    except Exception as e:
        print(f"  ⚠️ chokyoshi_master取得エラー: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# 出走別調教師成績から特徴量を集計
# ─────────────────────────────────────────────────────────────

def _load_shussobetsu(engine, year_from: int = 2020) -> pd.DataFrame:
    """shussobetsu_chokyoshi から必要列のみ取得"""
    # 勝率計算に必要な列だけ取得（全638列は重すぎる）
    q = text(f"""
        SELECT
            race_code,
            ketto_toroku_bango,
            chokyoshi_code,
            kaisai_nen,
            keibajo_code,

            -- 本年成績（honnen）
            shiba_1chaku_honnen, shiba_2chaku_honnen, shiba_3chaku_honnen,
            shiba_4chaku_honnen, shiba_5chaku_honnen, shiba_chakugai_honnen,
            dirt_1chaku_honnen,  dirt_2chaku_honnen,  dirt_3chaku_honnen,
            dirt_4chaku_honnen,  dirt_5chaku_honnen,  dirt_chakugai_honnen,

            -- 通算成績（ruikei）
            shiba_1chaku_ruikei, shiba_chakugai_ruikei,
            dirt_1chaku_ruikei,  dirt_chakugai_ruikei,

            -- 当該会場（shiba/dirt）
            tokyo_shiba_1chaku_honnen,   tokyo_shiba_chakugai_honnen,
            tokyo_dirt_1chaku_honnen,    tokyo_dirt_chakugai_honnen,
            nakayama_shiba_1chaku_honnen, nakayama_shiba_chakugai_honnen,
            nakayama_dirt_1chaku_honnen,  nakayama_dirt_chakugai_honnen,
            hanshin_shiba_1chaku_honnen,  hanshin_shiba_chakugai_honnen,
            hanshin_dirt_1chaku_honnen,   hanshin_dirt_chakugai_honnen,
            kyoto_shiba_1chaku_honnen,    kyoto_shiba_chakugai_honnen,
            kyoto_dirt_1chaku_honnen,     kyoto_dirt_chakugai_honnen,
            chukyo_shiba_1chaku_honnen,   chukyo_shiba_chakugai_honnen,
            chukyo_dirt_1chaku_honnen,    chukyo_dirt_chakugai_honnen,
            niigata_shiba_1chaku_honnen,  niigata_shiba_chakugai_honnen,
            niigata_dirt_1chaku_honnen,   niigata_dirt_chakugai_honnen,
            fukushima_shiba_1chaku_honnen, fukushima_shiba_chakugai_honnen,
            fukushima_dirt_1chaku_honnen,  fukushima_dirt_chakugai_honnen,
            sapporo_shiba_1chaku_honnen,  sapporo_shiba_chakugai_honnen,
            sapporo_dirt_1chaku_honnen,   sapporo_dirt_chakugai_honnen,
            hakodate_shiba_1chaku_honnen, hakodate_shiba_chakugai_honnen,
            hakodate_dirt_1chaku_honnen,  hakodate_dirt_chakugai_honnen,
            kokura_shiba_1chaku_honnen,   kokura_shiba_chakugai_honnen,
            kokura_dirt_1chaku_honnen,    kokura_dirt_chakugai_honnen,

            -- 通算会場
            tokyo_shiba_1chaku_ruikei,   tokyo_shiba_chakugai_ruikei,
            tokyo_dirt_1chaku_ruikei,    tokyo_dirt_chakugai_ruikei,
            nakayama_shiba_1chaku_ruikei, nakayama_shiba_chakugai_ruikei,
            nakayama_dirt_1chaku_ruikei,  nakayama_dirt_chakugai_ruikei,
            hanshin_shiba_1chaku_ruikei,  hanshin_shiba_chakugai_ruikei,
            hanshin_dirt_1chaku_ruikei,   hanshin_dirt_chakugai_ruikei,
            kyoto_shiba_1chaku_ruikei,    kyoto_shiba_chakugai_ruikei,
            kyoto_dirt_1chaku_ruikei,     kyoto_dirt_chakugai_ruikei,
            sapporo_dirt_1chaku_ruikei,   sapporo_dirt_chakugai_ruikei,
            hakodate_dirt_1chaku_ruikei,  hakodate_dirt_chakugai_ruikei,

            -- 距離帯別（芝）
            shiba_1200_ika_1chaku_honnen,    shiba_1200_ika_chakugai_honnen,
            shiba_1201_1400_1chaku_honnen,   shiba_1201_1400_chakugai_honnen,
            shiba_1401_1600_1chaku_honnen,   shiba_1401_1600_chakugai_honnen,
            shiba_1601_1800_1chaku_honnen,   shiba_1601_1800_chakugai_honnen,
            shiba_1801_2000_1chaku_honnen,   shiba_1801_2000_chakugai_honnen,
            shiba_2001_2200_1chaku_honnen,   shiba_2001_2200_chakugai_honnen,
            shiba_2201_2400_1chaku_honnen,   shiba_2201_2400_chakugai_honnen,
            shiba_2401_2800_1chaku_honnen,   shiba_2401_2800_chakugai_honnen,
            shiba_2801_ijo_1chaku_honnen,    shiba_2801_ijo_chakugai_honnen,

            -- 距離帯別（ダート）
            dirt_1200_ika_1chaku_honnen,     dirt_1200_ika_chakugai_honnen,
            dirt_1201_1400_1chaku_honnen,    dirt_1201_1400_chakugai_honnen,
            dirt_1401_1600_1chaku_honnen,    dirt_1401_1600_chakugai_honnen,
            dirt_1601_1800_1chaku_honnen,    dirt_1601_1800_chakugai_honnen,
            dirt_1801_2000_1chaku_honnen,    dirt_1801_2000_chakugai_honnen,
            dirt_2001_2200_1chaku_honnen,    dirt_2001_2200_chakugai_honnen,
            dirt_2201_2400_1chaku_honnen,    dirt_2201_2400_chakugai_honnen,
            dirt_2401_2800_1chaku_honnen,    dirt_2401_2800_chakugai_honnen,
            dirt_2801_ijo_1chaku_honnen,     dirt_2801_ijo_chakugai_honnen

        FROM shussobetsu_chokyoshi
        WHERE kaisai_nen >= :year_from
    """)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn, params={'year_from': str(year_from)})
        print(f"    → {len(df):,}行 ({df['chokyoshi_code'].nunique():,}調教師)")
        return df
    except Exception as e:
        print(f"  ⚠️ shussobetsu取得エラー: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# 特徴量計算
# ─────────────────────────────────────────────────────────────

def _win_rate(wins, outer, min_races: int = 5) -> float:
    """勝率計算。レース数不足はNaN返し"""
    total = wins + outer
    if total < min_races:
        return np.nan
    return wins / total if total > 0 else 0.0


def compute_trainer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    shussobetsu_chokyoshi の各行に対して調教師特徴量を計算する。
    """
    def _i(col):
        return df[col].apply(_to_int) if col in df.columns else pd.Series(0, index=df.index)

    # ── 本年総合勝率 ──────────────────────────────────────
    shiba_w_h = _i('shiba_1chaku_honnen')
    shiba_o_h = _i('shiba_chakugai_honnen')
    dirt_w_h  = _i('dirt_1chaku_honnen')
    dirt_o_h  = _i('dirt_chakugai_honnen')

    total_w_h = shiba_w_h + dirt_w_h
    total_o_h = shiba_o_h + dirt_o_h
    total_h   = total_w_h + total_o_h

    df['trainer_win_rate_honnen'] = np.where(
        total_h >= 5, total_w_h / total_h.clip(1), np.nan
    )

    # ── 通算勝率 ──────────────────────────────────────────
    shiba_w_r = _i('shiba_1chaku_ruikei')
    shiba_o_r = _i('shiba_chakugai_ruikei')
    dirt_w_r  = _i('dirt_1chaku_ruikei')
    dirt_o_r  = _i('dirt_chakugai_ruikei')

    total_w_r = shiba_w_r + dirt_w_r
    total_o_r = shiba_o_r + dirt_o_r
    total_r   = total_w_r + total_o_r

    df['trainer_win_rate_ruikei'] = np.where(
        total_r >= 20, total_w_r / total_r.clip(1), np.nan
    )

    # ── 好不調フラグ（本年/通算比） ────────────────────────
    df['trainer_form_ratio'] = np.where(
        df['trainer_win_rate_ruikei'].notna() & (df['trainer_win_rate_ruikei'] > 0),
        df['trainer_win_rate_honnen'].fillna(0) / df['trainer_win_rate_ruikei'].clip(1e-6),
        1.0
    ).clip(0, 3)

    # ── 芝/ダート得意度（通算基準の相対値） ─────────────────
    shiba_total_r = shiba_w_r + shiba_o_r
    dirt_total_r  = dirt_w_r  + dirt_o_r

    shiba_wr = np.where(shiba_total_r >= 10, shiba_w_r / shiba_total_r.clip(1), np.nan)
    dirt_wr  = np.where(dirt_total_r  >= 10, dirt_w_r  / dirt_total_r.clip(1),  np.nan)

    overall = df['trainer_win_rate_ruikei'].fillna(0)
    df['trainer_shiba_rate'] = pd.Series(shiba_wr, index=df.index).fillna(overall)
    df['trainer_dirt_rate']  = pd.Series(dirt_wr,  index=df.index).fillna(overall)

    # ── 当該会場勝率（開催コードから動的に取得） ──────────────
    def venue_win_rate(row):
        venue = VENUE_MAP.get(str(row.get('keibajo_code', '00')).zfill(2), '')
        if not venue:
            return np.nan
        # 芝ダート別に取得
        for surface in ['shiba', 'dirt']:
            w_col = f"{venue}_{surface}_1chaku_honnen"
            o_col = f"{venue}_{surface}_chakugai_honnen"
            if w_col in row.index and o_col in row.index:
                w, o = _to_int(row[w_col]), _to_int(row[o_col])
                if w + o >= 3:
                    return w / (w + o)
        return np.nan

    df['trainer_venue_rate'] = df.apply(venue_win_rate, axis=1)

    # ── 距離帯別勝率 ──────────────────────────────────────
    # race_codeから距離カテゴリを推定することは難しいので
    # 全距離帯の中で最も勝率が高い距離帯スコアを「得意距離」として返す
    def best_dist_score(row, surface='shiba'):
        best = 0.0
        for dk in DIST_KEYS:
            w_col = f"{surface}_{dk}_1chaku_honnen"
            o_col = f"{surface}_{dk}_chakugai_honnen"
            if w_col in row.index:
                w, o = _to_int(row.get(w_col, 0)), _to_int(row.get(o_col, 0))
                if w + o >= 3:
                    best = max(best, w / (w + o))
        return best

    df['trainer_best_dist_shiba'] = df.apply(lambda r: best_dist_score(r, 'shiba'), axis=1)
    df['trainer_best_dist_dirt']  = df.apply(lambda r: best_dist_score(r, 'dirt'),  axis=1)

    # ── 通算会場勝率（サンプル数が少ない会場はruikeiを使用） ──
    def venue_win_rate_ruikei(row):
        venue = VENUE_MAP.get(str(row.get('keibajo_code', '00')).zfill(2), '')
        if not venue:
            return np.nan
        for surface in ['shiba', 'dirt']:
            w_col = f"{venue}_{surface}_1chaku_ruikei"
            o_col = f"{venue}_{surface}_chakugai_ruikei"
            if w_col in row.index and o_col in row.index:
                w, o = _to_int(row.get(w_col, 0)), _to_int(row.get(o_col, 0))
                if w + o >= 5:
                    return w / (w + o)
        return np.nan

    df['trainer_venue_rate_ruikei'] = df.apply(venue_win_rate_ruikei, axis=1)

    # 会場勝率: 本年が少ない場合は通算で補完
    df['trainer_venue_rate'] = df['trainer_venue_rate'].fillna(df['trainer_venue_rate_ruikei'])

    # ── 好調度スコア（0〜1に正規化） ─────────────────────────
    # form_ratio, 本年勝率, 会場勝率の加重平均
    form_norm = (df['trainer_form_ratio'].fillna(1.0).clip(0, 2) - 0.5) / 1.5  # 0〜1
    rate_norm = df['trainer_win_rate_honnen'].fillna(0).clip(0, 0.4) / 0.4
    venue_norm = df['trainer_venue_rate'].fillna(df['trainer_win_rate_ruikei'].fillna(0))

    df['trainer_hot_cold'] = (
        0.40 * form_norm +
        0.35 * rate_norm +
        0.25 * venue_norm.clip(0, 0.4) / 0.4
    ).clip(0, 1)

    # ── 得意条件スコア（会場 × 距離帯の一致度） ─────────────
    df['trainer_specialty_score'] = (
        0.50 * df['trainer_venue_rate'].fillna(df['trainer_win_rate_ruikei'].fillna(0)) +
        0.30 * df[['trainer_best_dist_shiba', 'trainer_best_dist_dirt']].max(axis=1) +
        0.20 * df['trainer_win_rate_ruikei'].fillna(0)
    ).clip(0, 1)

    return df


# ─────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────

TRAINER_FEATURE_COLS = [
    'race_code', 'ketto_toroku_bango', 'chokyoshi_code',
    'trainer_win_rate_honnen', 'trainer_win_rate_ruikei', 'trainer_form_ratio',
    'trainer_shiba_rate', 'trainer_dirt_rate',
    'trainer_venue_rate', 'trainer_venue_rate_ruikei',
    'trainer_best_dist_shiba', 'trainer_best_dist_dirt',
    'trainer_hot_cold', 'trainer_specialty_score',
]


def build_trainer_features(year_from: int = 2020) -> pd.DataFrame:
    engine = create_engine(DB_URL)

    print("    📥 shussobetsu_chokyoshi 読み込み中...")
    raw = _load_shussobetsu(engine, year_from)
    if raw.empty:
        return pd.DataFrame()

    print("    🔧 調教師特徴量計算中...")
    feat = compute_trainer_features(raw)

    # 東西所属を付与
    master = _load_trainer_master(engine)
    if not master.empty:
        feat = feat.merge(master[['chokyoshi_code', 'tozai', 'trainer_name']],
                          on='chokyoshi_code', how='left')
        feat['trainer_tozai'] = pd.to_numeric(feat['tozai'], errors='coerce').fillna(0)
    else:
        feat['trainer_tozai'] = 0

    keep = [c for c in TRAINER_FEATURE_COLS + ['trainer_tozai', 'trainer_name'] if c in feat.columns]
    return feat[keep]


def run_trainer_analysis(year_from: int = 2020, save: bool = True) -> pd.DataFrame:
    print("\n" + "="*55)
    print("🎓 調教師特性分析")
    print("="*55)

    feat_path = CSV_FEATURES
    if not os.path.exists(feat_path):
        print("  ⚠️ keiba_data_features.csv なし")
        return pd.DataFrame()

    trainer_feat = build_trainer_features(year_from)
    if trainer_feat.empty:
        return pd.DataFrame()

    # 統計サマリー
    print(f"\n  📊 取得完了: {len(trainer_feat):,}行 / {trainer_feat['chokyoshi_code'].nunique():,}調教師")

    if 'trainer_win_rate_honnen' in trainer_feat.columns:
        wr = trainer_feat.drop_duplicates('chokyoshi_code')['trainer_win_rate_honnen'].dropna()
        print(f"  📈 本年勝率: 平均={wr.mean():.1%} 最高={wr.max():.1%} 中央値={wr.median():.1%}")

    if 'trainer_hot_cold' in trainer_feat.columns:
        hot = trainer_feat.drop_duplicates('chokyoshi_code')
        hot_trainers = hot.nlargest(5, 'trainer_hot_cold')
        print("\n  🔥 好調調教師 TOP5:")
        for _, r in hot_trainers.iterrows():
            name = r.get('trainer_name', r['chokyoshi_code'])
            print(f"    {name:<12} "
                  f"本年={r['trainer_win_rate_honnen']:.1%} "
                  f"通算={r['trainer_win_rate_ruikei']:.1%} "
                  f"好調度={r['trainer_hot_cold']:.3f} "
                  f"会場={r.get('trainer_venue_rate', 0):.1%}")

    if save:
        print("\n  💾 keiba_data_features.csv に追記中...")
        df = pd.read_csv(feat_path, encoding='utf-8-sig',
                         low_memory=False, on_bad_lines='skip')

        # 旧調教師列を削除
        old = [c for c in df.columns if c.startswith('trainer_') and c != 'trainer_tozai']
        df = df.drop(columns=old, errors='ignore')

        # race_code × ketto_toroku_bango でマージ
        merge_cols = ['race_code', 'ketto_toroku_bango']
        new_cols = [c for c in trainer_feat.columns
                    if c not in merge_cols and c not in ('chokyoshi_code', 'trainer_name')]

        df['race_code']            = df['race_code'].astype(str)
        df['ketto_toroku_bango']   = df['ketto_toroku_bango'].astype(str)
        trainer_feat['race_code']  = trainer_feat['race_code'].astype(str)
        trainer_feat['ketto_toroku_bango'] = trainer_feat['ketto_toroku_bango'].astype(str)

        df = df.merge(trainer_feat[merge_cols + new_cols],
                      on=merge_cols, how='left')

        for c in new_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        df.to_csv(feat_path, index=False, encoding='utf-8-sig')
        print(f"  ✅ 保存完了: {len(df):,}件 × {len(df.columns)}列")

    return trainer_feat


if __name__ == "__main__":
    run_trainer_analysis()
