# mykeibadb データベース仕様

## 接続情報

```
Host     : localhost
Port     : 5433
Database : mykeibadb
User     : postgres
Password : trust（pg_hba.conf で trust 認証）
URL      : postgresql://postgres:trust@localhost:5433/mykeibadb
```

Python での接続例:
```python
import psycopg2
conn = psycopg2.connect(
    host="localhost", port=5433,
    dbname="mykeibadb", user="postgres"
)
```

## 主要テーブル

### race_results（レース結果）

| 列名 | 型 | 説明 |
|------|----|------|
| race_code | VARCHAR(16) | レースコード（例: 202605020201） |
| kaisai_nen | INT | 開催年（YYYY） |
| kaisai_tsukihi | VARCHAR(4) | 開催月日（MMDD） |
| keibajo_code | VARCHAR(2) | 競馬場コード（01=札幌 … 10=小倉） |
| race_bango | INT | レース番号 |
| umaban | INT | 馬番 |
| bamei | VARCHAR(36) | 馬名 |
| kakutei_chakujun | INT | 確定着順（1着=1） |
| tansho_odds | FLOAT | 単勝オッズ × 10（例: 175 = 17.5倍） |
| kishumei_ryakusho | VARCHAR(8) | 騎手略称 |
| chokyoshi_ryakusho | VARCHAR(8) | 調教師略称 |
| barei | INT | 馬齢 |
| bataiju | INT | 馬体重（kg） |
| zogen_sa | INT | 馬体重増減（kg） |
| zogen_fugo | VARCHAR(1) | 増減符号（+/-/=） |
| kyori | INT | 距離（m） |
| track_code | VARCHAR(2) | トラックコード |
| race_grade | VARCHAR(4) | レースグレード（G1/G2/G3/OP/3勝…） |

### horse_info（馬情報）

| 列名 | 型 | 説明 |
|------|----|------|
| ketto_toroku_bango | VARCHAR(10) | 血統登録番号（馬ID） |
| bamei | VARCHAR(36) | 馬名 |
| chichi | VARCHAR(36) | 父馬名 |
| haha | VARCHAR(36) | 母馬名 |
| hahaChichi | VARCHAR(36) | 母父馬名 |
| seibetsu_code | VARCHAR(1) | 性別（1=牡/2=牝/3=騸） |
| keiro_code | VARCHAR(2) | 毛色コード |

### jockey_stats（騎手統計）

| 列名 | 型 | 説明 |
|------|----|------|
| kishumei_ryakusho | VARCHAR(8) | 騎手略称 |
| win_rate | FLOAT | 勝率 |
| place_rate | FLOAT | 連対率 |
| show_rate | FLOAT | 複勝率 |
| wins_current_year | INT | 今年の勝利数 |

## インデックス（パフォーマンス重要）

```sql
-- よく使うクエリ向け
CREATE INDEX IF NOT EXISTS idx_race_results_kaisai_nen ON race_results(kaisai_nen);
CREATE INDEX IF NOT EXISTS idx_race_results_race_code ON race_results(race_code);
CREATE INDEX IF NOT EXISTS idx_race_results_bamei ON race_results(bamei);
CREATE INDEX IF NOT EXISTS idx_horse_info_bamei ON horse_info(bamei);
```

## 注意事項

- `tansho_odds` は10倍した整数で格納 → Python側で `/10` して使う
- `kakutei_chakujun = 0` は除外対象（競走除外・取消）
- keiba_data_features.csv の **339766行目が破損** → `pd.read_csv(..., on_bad_lines='skip')` 必須
- JV-Link同期ツール: `C:\Users\uchih\Downloads\mykeibadb_v3.63\mykeibadb.exe`
  - `mykeibadb.ini` が同フォルダに必要（consoleモードで実行すること）

## CSV ファイルとの対応

| ファイル | 元テーブル | 行数目安 |
|---------|-----------|---------|
| keiba_data.csv | race_results JOIN horse_info | ~34万行 |
| keiba_data_features.csv | 上記 + 97特徴量付き | ~34万行 |

## 年別データ件数（参考）

| 年 | レース数 | 出走頭数 |
|----|---------|---------|
| 2020 | ~3,000 | ~45,000 |
| 2021 | ~3,000 | ~45,000 |
| 2022 | ~3,000 | ~45,000 |
| 2023 | ~3,000 | ~45,000 |
| 2024 | ~3,000 | ~45,000 |
| 2025 | ~3,000 | ~45,000 |
