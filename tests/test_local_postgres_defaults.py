import os
import pathlib
import tempfile
import unittest

from tools import local_postgres


class LocalPostgresDefaultsTest(unittest.TestCase):
    def test_prefers_postgres18_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / ".keiba_ai" / "postgres").mkdir(parents=True)
            (home / ".keiba_ai" / "postgres18").mkdir(parents=True)

            paths = local_postgres.resolve_paths(home=home, env={})

            self.assertEqual(home / ".keiba_ai" / "postgres18", paths.prefix)
            self.assertEqual(home / ".keiba_ai" / "pgdata18", paths.data_dir)

    def test_env_overrides_prefix_and_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            env = {
                "KEIBA_PG_PREFIX": str(home / "custom-pg"),
                "KEIBA_PGDATA": str(home / "custom-data"),
                "KEIBA_PGLOG": str(home / "custom.log"),
            }

            paths = local_postgres.resolve_paths(home=home, env=env)

            self.assertEqual(home / "custom-pg", paths.prefix)
            self.assertEqual(home / "custom-data", paths.data_dir)
            self.assertEqual(home / "custom.log", paths.log_file)


if __name__ == "__main__":
    unittest.main()
