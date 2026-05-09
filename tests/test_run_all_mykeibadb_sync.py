import unittest
from unittest.mock import patch

import run_all


class RunAllMykeibadbSyncTest(unittest.TestCase):
    def test_run_mykeibadb_daily_sync_invokes_sync_tool(self):
        calls = []

        def fake_run(cmd, cwd=None):
            calls.append((cmd, cwd))
            return 0

        with patch.object(run_all, "_run_subprocess", side_effect=fake_run):
            rc = run_all.run_mykeibadb_daily_sync(timeout_seconds=123)

        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][0][:4], [
            run_all.sys.executable,
            "-X",
            "utf8",
            str(run_all.BASE_DIR / "tools" / "mykeibadb_sync.py"),
        ])
        self.assertIn("--timeout", calls[0][0])
        self.assertIn("123", calls[0][0])


if __name__ == "__main__":
    unittest.main()
