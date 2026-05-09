import unittest

from tools.seed_core_tables_from_csv import (
    build_race_shosai_row,
    build_umagoto_row,
    normalize_code,
)


class SeedCoreTablesFromCsvTest(unittest.TestCase):
    def test_normalize_code_handles_numbers_and_padding(self):
        self.assertEqual("09", normalize_code(9, width=2))
        self.assertEqual("0412", normalize_code(412, width=4))
        self.assertEqual("", normalize_code(None, width=2))

    def test_builds_race_shosai_row_from_csv_record(self):
        row = {
            "race_code": "2026041209020611",
            "kaisai_nen": 2026,
            "kaisai_gappi": 412,
            "keibajo_code": 9,
            "kaisai_kai": 2,
            "kaisai_nichime": 6,
            "kyori": 1600,
            "track_code": "10",
            "tenko_code": 1,
            "shiba_babajotai_code": 2,
            "dirt_babajotai_code": 0,
            "shusso_tosu": 16,
            "race_grade": "A",
        }

        built = build_race_shosai_row(row)

        self.assertEqual("2026041209020611", built["race_code"])
        self.assertEqual("11", built["race_bango"])
        self.assertEqual("09", built["keibajo_code"])
        self.assertEqual("0412", built["kaisai_gappi"])
        self.assertEqual("A", built["grade_code"])

    def test_builds_umagoto_row_from_csv_record(self):
        row = {
            "race_code": "2026041209020611",
            "kaisai_nen": 2026,
            "kaisai_gappi": 412,
            "keibajo_code": 9,
            "kaisai_kai": 2,
            "kaisai_nichime": 6,
            "wakuban": 3,
            "umaban": 5,
            "ketto_toroku_bango": 2023104475,
            "bamei": "スウィートハピネス",
            "barei": 3,
            "seibetsu_code": 2,
            "kishu_code": 1213,
            "kishumei_ryakusho": "高杉吏麒",
            "chokyoshi_code": 11074,
            "chokyoshimei_ryakusho": "奥平雅士",
            "futan_juryo": 550,
            "bataiju": 480,
            "zogen_fugo": "+",
            "zogen_sa": 4,
            "tansho_odds": 290,
            "tansho_ninkijun": 13,
            "kakutei_chakujun": 1,
            "kyakushitsu_hantei": 2,
        }

        built = build_umagoto_row(row)

        self.assertEqual("05", built["umaban"])
        self.assertEqual("2023104475", built["ketto_toroku_bango"])
        self.assertEqual("0290", built["tansho_odds"])
        self.assertEqual("13", built["tansho_ninkijun"])
        self.assertEqual("01", built["kakutei_chakujun"])
        self.assertEqual("7", built["data_kubun"])


if __name__ == "__main__":
    unittest.main()
