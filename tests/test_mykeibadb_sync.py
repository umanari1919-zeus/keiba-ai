import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools import mykeibadb_sync


SAMPLE_INI = """[DB]
SERVER=old-host
PORT=5433
DATABASE=mykeibadb

[KONSHU]
SE=1
O1=1
O2=1

[JIKEIRETSU]
O1=1
O2=1
"""


class MykeibadbSyncTest(unittest.TestCase):
    def test_update_ini_points_server_at_wsl_ip(self):
        updated = mykeibadb_sync.update_ini_text(SAMPLE_INI, server="172.28.79.71")

        self.assertIn("SERVER=172.28.79.71", updated)
        self.assertNotIn("SERVER=old-host", updated)

    def test_update_ini_disables_jikeiretsu_odds_only(self):
        updated = mykeibadb_sync.update_ini_text(SAMPLE_INI, server="172.28.79.71")

        self.assertIn("[KONSHU]\nSE=1\nO1=1\nO2=1", updated)
        self.assertIn("[JIKEIRETSU]\nO1=0\nO2=0", updated)

    def test_update_ini_adds_server_when_missing_in_db_section(self):
        text = "[DB]\nPORT=5433\n\n[JIKEIRETSU]\nO1=1\n"

        updated = mykeibadb_sync.update_ini_text(text, server="172.28.79.71")

        self.assertIn("[DB]\nSERVER=172.28.79.71\nPORT=5433", updated)

    def test_is_terminal_log_text_recognizes_update_end(self):
        self.assertTrue(mykeibadb_sync.is_terminal_log_text("0B30:更新終了\n"))
        self.assertTrue(mykeibadb_sync.is_terminal_log_text("0B30:譖ｴ譁ｰ邨ゆｺ�\n"))
        self.assertFalse(mykeibadb_sync.is_terminal_log_text("0B30:0B30202605090401.rtd\n"))

    def test_read_new_log_tail_ignores_previous_run(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.txt"
            old = "previous\n0B30:更新終了\n"
            log_path.write_text(old, encoding="cp932")
            start_size = log_path.stat().st_size
            log_path.write_text(old + "new run\n0B30:0B30202605090401.rtd\n", encoding="cp932")

            tail = mykeibadb_sync.read_new_log_tail(log_path, start_size)

        self.assertNotIn("previous", tail)
        self.assertNotIn("更新終了", tail)
        self.assertIn("0B30202605090401", tail)

    def test_parse_started_pid_uses_last_integer(self):
        self.assertEqual(26504, mykeibadb_sync.parse_started_pid("noise\r\nMYKEIBADB_PID=26504\r\n"))

    def test_parse_started_pid_requires_marker(self):
        with self.assertRaises(RuntimeError):
            mykeibadb_sync.parse_started_pid("PowerShell 5.1\r\n")

    def test_to_windows_path_converts_mnt_drive(self):
        self.assertEqual(
            r"C:\Program Files\mykeibadb_v4.1\mykeibadb.exe",
            mykeibadb_sync.to_windows_path(Path("/mnt/c/Program Files/mykeibadb_v4.1/mykeibadb.exe")),
        )


if __name__ == "__main__":
    unittest.main()
