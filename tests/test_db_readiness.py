import unittest

from tools.db_readiness import CORE_TABLES, summarize_core_table_health


class DatabaseReadinessTest(unittest.TestCase):
    def test_warns_when_core_tables_are_missing(self):
        status, detail = summarize_core_table_health({"umagoto_race_joho": True})

        self.assertEqual("WARN", status)
        self.assertIn("missing", detail)
        self.assertIn("race_shosai", detail)

    def test_warns_when_core_tables_are_empty(self):
        status, detail = summarize_core_table_health({
            table: (table != "odds1_tansho") for table in CORE_TABLES
        })

        self.assertEqual("WARN", status)
        self.assertIn("empty", detail)
        self.assertIn("odds1_tansho", detail)

    def test_passes_when_all_core_tables_have_rows(self):
        status, detail = summarize_core_table_health({table: True for table in CORE_TABLES})

        self.assertEqual("PASS", status)
        self.assertIn("ready", detail)


if __name__ == "__main__":
    unittest.main()
