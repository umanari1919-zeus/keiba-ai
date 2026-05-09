import unittest

from tools import postgres_advanced


class PostgresAdvancedTest(unittest.TestCase):
    def test_recommended_indexes_include_core_keiba_access_patterns(self):
        names = {item.name for item in postgres_advanced.RECOMMENDED_INDEXES}

        self.assertIn("idx_keiba_umagoto_race_horse", names)
        self.assertIn("idx_keiba_race_shosai_year_day_place", names)
        self.assertIn("idx_keiba_odds1_tansho_year_day", names)

    def test_create_index_sql_uses_concurrently_and_if_not_exists(self):
        index = postgres_advanced.RecommendedIndex(
            name="idx_demo",
            table="race_shosai",
            columns=("kaisai_nen", "kaisai_gappi"),
            where="kaisai_nen >= '2020'",
        )

        sql = index.create_sql()

        self.assertEqual(
            sql,
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_demo "
            "ON race_shosai (kaisai_nen, kaisai_gappi) "
            "WHERE kaisai_nen >= '2020'",
        )

    def test_create_unique_index_sql_uses_concurrently_and_if_not_exists(self):
        index = postgres_advanced.MykeibadbConflictIndex(
            name="uidx_demo",
            table="odds1_tansho",
            columns=("race_code", "umaban"),
        )

        sql = index.create_sql()

        self.assertEqual(
            sql,
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uidx_demo "
            "ON odds1_tansho (race_code, umaban)",
        )

    def test_mykeibadb_conflict_indexes_include_odds_targets(self):
        targets = {
            (item.table, item.columns)
            for item in postgres_advanced.MYKEIBADB_CONFLICT_INDEXES
        }

        self.assertIn(("odds1", ("race_code",)), targets)
        self.assertIn(("odds1_tansho", ("race_code", "umaban")), targets)
        self.assertIn(("odds6_sanrentan", ("race_code", "kumiban")), targets)

    def test_duplicate_key_probe_sql_limits_work(self):
        index = postgres_advanced.MykeibadbConflictIndex(
            name="uidx_demo",
            table="odds1_tansho",
            columns=("race_code", "umaban"),
        )

        query = postgres_advanced.duplicate_key_probe_sql(index)

        self.assertIn("GROUP BY", query)
        self.assertIn("HAVING COUNT(*) > 1", query)
        self.assertIn("LIMIT 1", query)

    def test_drop_index_sql_uses_concurrently_and_if_exists(self):
        index = postgres_advanced.MykeibadbConflictIndex(
            name="uidx_demo",
            table="odds1_tansho",
            columns=("race_code", "umaban"),
        )

        sql = postgres_advanced.drop_index_sql(index)

        self.assertEqual(sql, "DROP INDEX CONCURRENTLY IF EXISTS uidx_demo")

    def test_filter_available_indexes_skips_missing_columns(self):
        index = postgres_advanced.RecommendedIndex(
            name="idx_demo",
            table="race_shosai",
            columns=("kaisai_nen", "missing_column"),
        )
        existing_columns = {"race_shosai": {"race_code", "kaisai_nen"}}

        available, skipped = postgres_advanced.filter_available_indexes(
            [index],
            existing_columns,
        )

        self.assertEqual(available, [])
        self.assertEqual(skipped[0][0].name, "idx_demo")
        self.assertEqual(skipped[0][1], "missing columns: missing_column")


if __name__ == "__main__":
    unittest.main()
